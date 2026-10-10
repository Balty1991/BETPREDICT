"""Robot v2: antrenare (artefact), predicție live și ciclul campion/challenger.

Artefactul (JSON, salvat în tabela ``model_artifact``) conține:
  * config: parametrii ELO, timp de înjumătățire Dixon-Coles, parametrii LightGBM;
  * gbm: modelele LightGBM serializate (1X2 multiclasă + Peste 1.5/2.5/3.5 + GG);
  * stack: coeficienții stacker-ului/calibrării fără piață (GBM + Dixon-Coles, beta-calibrare);
  * market: coeficienții stacker-ului cu piața (cât ne micșorăm spre cota fără marjă);
  * league_rel: fiabilitatea modelului pe ligă (0–1) din predicțiile out-of-sample;
  * metrics: metrici OOS + holdout.
"""

from __future__ import annotations

import json
import math
import sqlite3
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from betpredict.model import ENGINE_VERSION
from betpredict.model import gbm as G
from betpredict.model.backtest import (BIN, ODDS_CLEAN_FROM, day_of, dc_probs, dc_walk_forward, month_starts,
                                       outcomes, plausible_prematch)
from betpredict.model.data import History, load_history, load_snapshot_odds, load_warehouse_odds, novig_market
from betpredict.model.dc import fit_dc, market_probs_from_matrix, score_matrix
from betpredict.model.features import FEATURE_NAMES, EloParams, build_features
from betpredict.model.metrics import logloss_bin, logloss_multi
from betpredict.model.stack import apply_binary, apply_multi, fit_binary, fit_multi

# reglaje alese pe perioada de tuning 2023-07 → 2024-06 (vezi docs/robot-v2-backtest.md)
DEFAULT_CONFIG: Dict[str, Any] = {
    "elo": {"k": 14.0, "home_adv": 60.0, "margin": 0.6, "new_team_offset": -60.0, "regress": 0.2},
    "half_life": 365.0, "dc_years": 3.0, "train_years": 5.0, "oos_months": 12,
    "gbm": {"num_rounds": 350, "num_leaves": 24, "learning_rate": 0.04, "min_data_in_leaf": 300},
}
CORE = ("H", "D", "A", "O15", "O25", "O35", "BY")
MARKET_PRIOR_BIN = [0.35, 0.35, 0.65, 0.65, 0.0]
WAREHOUSE = Path(__file__).resolve().parents[2] / "data" / "warehouse"


def _ts(t: float) -> str:
    return str(np.datetime64(int(t * 86400), "s")) + "Z"


def _market_prior_multi() -> np.ndarray:
    pm = np.zeros((7, 3))
    for j in range(3):
        pm[j, j], pm[3 + j, j] = 0.35, 0.65
    return pm


def _features(hist: History, cfg: Dict[str, Any], extra=None):
    return build_features(hist, EloParams(**cfg["elo"]), extra=extra)


def _with_dc(X0: np.ndarray, lh, la, D) -> np.ndarray:
    return np.concatenate([X0, np.stack([lh, la, D["H"], D["D"], D["A"], D["O25"], D["BY"]], 1).astype(np.float32)], 1)


def clean_market(conn: sqlite3.Connection, hist: History, warehouse_dir: Path = WAREHOUSE) -> Dict[str, np.ndarray]:
    """Probabilități fără marjă (cote pre-meci curate) aliniate pe ``hist``; NaN unde lipsesc."""
    n = len(hist)
    MK = {k: np.full(n, np.nan) for k in CORE}
    pos = {int(i): j for j, i in enumerate(hist.ids.tolist())}
    t_clean = day_of(ODDS_CLEAN_FROM)
    srcs: Dict[int, Dict[str, float]] = {}
    if Path(warehouse_dir).is_dir():
        for mid, o in load_warehouse_odds(warehouse_dir).items():
            j = pos.get(mid)
            if j is not None and hist.t[j] >= t_clean and plausible_prematch(o):
                srcs[mid] = o
    for mid, d in load_snapshot_odds(conn).items():
        if mid in pos and d["close"]:
            srcs[mid] = d["close"]
    for mid, o in srcs.items():
        nv = novig_market(o)
        if all(k in nv for k in CORE):
            j = pos[mid]
            for k in CORE:
                MK[k][j] = nv[k]
    return MK


def stack_sources(GB: Dict[str, np.ndarray], D: Dict[str, np.ndarray], art_stack: Dict[str, Any]) -> Dict[str, np.ndarray]:
    out: Dict[str, np.ndarray] = {}
    B = np.array(art_stack["1x2"])
    P = apply_multi(B, [np.stack([GB["H"], GB["D"], GB["A"]], 1), np.stack([D["H"], D["D"], D["A"]], 1)])
    out["H"], out["D"], out["A"] = P[:, 0], P[:, 1], P[:, 2]
    for k in BIN:
        out[k] = apply_binary(np.array(art_stack[k]), [GB[k], D[k]])
    out["O25"] = np.minimum(out["O25"], out["O15"])
    out["O35"] = np.minimum(out["O35"], out["O25"])
    return out


def market_combine(S: Dict[str, np.ndarray], MK: Dict[str, np.ndarray], art_market: Dict[str, Any],
                   shrink: Optional[np.ndarray] = None) -> Dict[str, np.ndarray]:
    """Stacker cu piața + micșorare suplimentară spre piață când modelul e nesigur (``shrink`` 0–1)."""
    B = np.array(art_market["1x2"])
    S3 = np.stack([S["H"], S["D"], S["A"]], 1)
    M3 = np.stack([MK["H"], MK["D"], MK["A"]], 1)
    P = apply_multi(B, [S3, M3])
    if shrink is not None:
        s = shrink[:, None]
        P = np.exp((1 - s) * np.log(np.clip(P, 1e-6, 1)) + s * np.log(np.clip(M3, 1e-6, 1)))
        P = P / P.sum(1, keepdims=True)
    out = {"H": P[:, 0], "D": P[:, 1], "A": P[:, 2]}
    for k in BIN:
        p = apply_binary(np.array(art_market[k]), [S[k], MK[k]])
        if shrink is not None:
            z = (1 - shrink) * np.log(p / (1 - p)) + shrink * np.log(np.clip(MK[k], 1e-6, 1 - 1e-6) / np.clip(1 - MK[k], 1e-6, 1))
            p = 1 / (1 + np.exp(-z))
        out[k] = p
    out["O25"] = np.minimum(out["O25"], out["O15"])
    out["O35"] = np.minimum(out["O35"], out["O25"])
    return out


def _metrics(P: Dict[str, np.ndarray], Y: Dict[str, np.ndarray], yres: np.ndarray, m: np.ndarray) -> Dict[str, float]:
    if not m.any():
        return {}
    out = {"n": int(m.sum()), "1x2": logloss_multi(np.stack([P["H"][m], P["D"][m], P["A"][m]], 1), yres[m])}
    for k in BIN:
        out[k] = logloss_bin(P[k][m], Y[k][m])
    return {k: (round(v, 5) if isinstance(v, float) else v) for k, v in out.items()}


def fit_artifact(conn: sqlite3.Connection, config: Optional[Dict[str, Any]] = None, cutoff: Optional[str] = None,
                 log=print, warehouse_dir: Path = WAREHOUSE, holdout_days: float = 0.0,
                 hist: Optional[History] = None, keep_holdout: bool = False, debug: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Antrenează un artefact cu date STRICT înainte de ``cutoff`` (implicit: tot istoricul).
    Dacă ``holdout_days`` > 0, evaluează și pe [cutoff, cutoff + holdout_days)."""
    t0 = time.time()
    cfg = json.loads(json.dumps(config or DEFAULT_CONFIG))
    full = hist or load_history(conn)
    t_cut = day_of(cutoff) if cutoff else float(full.t[-1]) + 1e-3
    X0, _, _ = _features(full, cfg)
    tr_years, oos = float(cfg["train_years"]), float(cfg["oos_months"]) * 30.44
    t_oos = t_cut - oos
    t_first = t_oos - 365 * tr_years
    lh, la, cov, rho = dc_walk_forward(full, t_first, t_cut + max(holdout_days, 1), cfg["half_life"], years=cfg["dc_years"])
    D = dc_probs(lh, la, rho)
    X = _with_dc(X0, lh, la, D)
    Y = outcomes(full.gh, full.ga)
    yres = np.where(full.gh > full.ga, 0, np.where(full.gh == full.ga, 1, 2))
    ytask = G.targets(full.gh, full.ga)
    ok = np.isfinite(lh)
    # 1) GBM pe [t_first, t_oos) → predicții OOS pe [t_oos, t_cut) pentru stacker
    tr = ok & (full.t >= t_first) & (full.t < t_oos)
    oo = ok & (full.t >= t_oos) & (full.t < t_cut)
    mA = G.train(X[tr], {k: v[tr] for k, v in ytask.items()}, cfg["gbm"])
    GB = {k: np.full(len(full), np.nan) for k in CORE}
    PA = G.predict(mA, X[oo])
    for k in CORE:
        GB[k][oo] = PA[k]
    log(f"  [{ENGINE_VERSION}] GBM-OOS: train={int(tr.sum())} oos={int(oo.sum())} ({time.time() - t0:.0f}s)")
    stack: Dict[str, Any] = {"1x2": fit_multi([np.stack([GB["H"][oo], GB["D"][oo], GB["A"][oo]], 1),
                                              np.stack([D["H"][oo], D["D"][oo], D["A"][oo]], 1)], yres[oo]).tolist()}
    for k in BIN:
        stack[k] = fit_binary([GB[k][oo], D[k][oo]], Y[k][oo]).tolist()
    S = {k: np.full(len(full), np.nan) for k in CORE}
    So = stack_sources({k: GB[k][oo] for k in CORE}, {k: D[k][oo] for k in CORE}, stack)
    for k in CORE:
        S[k][oo] = So[k]
    # 1b) v4: calibrare rolling pe piață × grup de ligi (60 zile, ≥300 ex.), păstrată doar dacă nu strică holdout-ul
    from betpredict.model.calib import calibrate_dict, fit_group_calibration, fit_league_weights, league_group
    Yc = dict(Y)
    Yc["H"], Yc["D"], Yc["A"] = (yres == 0).astype(float), (yres == 1).astype(float), (yres == 2).astype(float)
    try:
        gcal = fit_group_calibration(S, Yc, full.t, full.league, oo, t_cut, CORE)
    except Exception as exc:  # noqa: BLE001
        gcal = {"cal": {}, "blocked": [], "report": [], "error": str(exc)}
    if gcal["cal"]:
        grp_all = np.array([league_group(x) for x in full.league[oo]])
        Sc = calibrate_dict({k: S[k][oo] for k in CORE}, gcal["cal"], grp_all)
        for k in CORE:
            S[k][oo] = Sc[k]
    log(f"  [{ENGINE_VERSION}] calibrare pe grup: {len(gcal['cal'])} calibratori păstrați, blocate={gcal['blocked']}")
    # 2) fiabilitate pe ligă (OOS): câștigul de logloss 1X2 față de rata de bază a ligii
    league_rel: Dict[str, float] = {}
    base = {}
    for lg in np.unique(full.league[oo]):
        mm = oo & (full.league == lg)
        if mm.sum() < 40:
            continue
        prev = (full.league == lg) & (full.t < t_oos)
        fr = np.bincount(yres[prev], minlength=3) + 10.0
        fr = fr / fr.sum()
        ll_base = -np.mean(np.log(fr[yres[mm]]))
        ll_mod = logloss_multi(np.stack([S["H"][mm], S["D"][mm], S["A"][mm]], 1), yres[mm])
        base[int(lg)] = (ll_base - ll_mod, int(mm.sum()))
    if base:
        gains = np.array([g for g, _ in base.values()])
        ref = max(0.02, float(np.median(gains)))
        for lg, (g, n) in base.items():
            league_rel[str(lg)] = round(float(np.clip(g / ref, 0.0, 1.0) * n / (n + 60) + 0.5 * 60 / (n + 60)), 3)
    # 3) stacker cu piața, pe cotele curate din fereastra OOS
    MK = clean_market(conn, full, warehouse_dir)
    hm = oo & np.isfinite(MK["H"]) & np.isfinite(S["H"])
    pm = _market_prior_multi()
    pb = np.array(MARKET_PRIOR_BIN)
    nmk = int(hm.sum())
    if nmk >= 300:
        market = {"1x2": fit_multi([np.stack([S["H"][hm], S["D"][hm], S["A"][hm]], 1),
                                    np.stack([MK["H"][hm], MK["D"][hm], MK["A"][hm]], 1)], yres[hm], l2=40.0, prior=pm).tolist()}
        for k in BIN:
            market[k] = fit_binary([S[k][hm], MK[k][hm]], Y[k][hm], prior=pb, l2=40.0).tolist()
    else:
        market = {"1x2": pm.tolist(), **{k: pb.tolist() for k in BIN}}
    market["n"] = nmk
    # 3b) v4: blend logit cu piața, w pe ligă (micșorat spre grup/global); ales per piață doar dacă bate stacker-ul pe
    #     ultimele 40% din meciurile cu cote (split temporal), altfel rămâne stacker-ul
    blend_art: Dict[str, Any] = {"weights": {}, "use": {}, "eval": {}}
    if nmk >= 400:
        try:
            idx = np.where(hm)[0]
            cut_t = np.sort(full.t[idx])[int(len(idx) * 0.6)]
            trm, tem = hm & (full.t < cut_t), hm & (full.t >= cut_t)
            Wtr = fit_league_weights(S, MK, Yc, full.league, trm, CORE)
            mk_tr = {"1x2": fit_multi([np.stack([S["H"][trm], S["D"][trm], S["A"][trm]], 1),
                                       np.stack([MK["H"][trm], MK["D"][trm], MK["A"][trm]], 1)], yres[trm], l2=40.0, prior=pm).tolist()}
            for k in BIN:
                mk_tr[k] = fit_binary([S[k][trm], MK[k][trm]], Y[k][trm], prior=pb, l2=40.0).tolist()
            St = {k: S[k][tem] for k in CORE}
            Mt = {k: MK[k][tem] for k in CORE}
            Pst = market_combine(St, Mt, mk_tr)
            from betpredict.model.calib import blend as _blend, league_w as _lw
            lgs = full.league[tem]
            Q = {k: _blend(St[k], Mt[k], np.array([_lw(Wtr, k, l) or 0.9 for l in lgs])) for k in CORE if k in Wtr}
            if all(k in Q for k in ("H", "D", "A")):
                q3 = np.stack([Q["H"], Q["D"], Q["A"]], 1)
                q3 = q3 / q3.sum(1, keepdims=True)
                ll_b = logloss_multi(q3, yres[tem])
                ll_s = logloss_multi(np.stack([Pst["H"], Pst["D"], Pst["A"]], 1), yres[tem])
                blend_art["eval"]["1x2"] = {"stacker": round(ll_s, 5), "league_blend": round(ll_b, 5), "n": int(tem.sum())}
                blend_art["use"]["1x2"] = bool(ll_b < ll_s)
            for k in BIN:
                if k in Q:
                    ll_b, ll_s = logloss_bin(Q[k], Y[k][tem]), logloss_bin(Pst[k], Y[k][tem])
                    blend_art["eval"][k] = {"stacker": round(ll_s, 5), "league_blend": round(ll_b, 5), "n": int(tem.sum())}
                    blend_art["use"][k] = bool(ll_b < ll_s)
            blend_art["weights"] = fit_league_weights(S, MK, Yc, full.league, hm, CORE)
        except Exception as exc:  # noqa: BLE001
            blend_art["error"] = str(exc)
    log(f"  [{ENGINE_VERSION}] blend pe ligă folosit pentru: {[k for k, v in blend_art['use'].items() if v]}")
    if debug is not None:
        debug.update({"S": S, "MK": MK, "oo": oo, "hm": hm, "Y": Y, "yres": yres, "hist": full, "D": D, "market": market})
        if debug.get("stop"):
            return {}
    log(f"  [{ENGINE_VERSION}] stacker: oos={int(oo.sum())}, cu piață={nmk}; ligi cu fiabilitate={len(league_rel)}")
    oos_metrics = {"model": _metrics(S, Y, yres, oo), "dc": _metrics(D, Y, yres, oo)}
    # folds lunare (graficul „walk-forward” de pe site): model v2 vs rata de bază
    wf: List[Dict[str, Any]] = []
    prior = (full.t < t_oos) & (full.t >= t_oos - 365)
    fr = np.bincount(yres[prior], minlength=3) / max(1, prior.sum())
    o25 = float(Y["O25"][prior].mean()) if prior.any() else 0.5
    ms = month_starts(t_oos, t_cut)
    for a_, b_ in zip(ms[:-1], ms[1:]):
        mm = oo & (full.t >= a_) & (full.t < b_)
        if mm.sum() < 100:
            continue
        wf.append({"fold": str(np.datetime64(int(a_ * 86400), "s"))[:7], "n": int(mm.sum()),
                   "logloss_1x2": round(logloss_multi(np.stack([S["H"][mm], S["D"][mm], S["A"][mm]], 1), yres[mm]), 4),
                   "baseline_1x2": round(float(-np.mean(np.log(fr[yres[mm]]))), 4),
                   "logloss_ou25": round(logloss_bin(S["O25"][mm], Y["O25"][mm]), 4),
                   "baseline_ou25": round(logloss_bin(np.full(int(mm.sum()), o25), Y["O25"][mm]), 4)})
    if nmk:
        Mo = market_combine({k: S[k][hm] for k in CORE}, {k: MK[k][hm] for k in CORE}, market)
        oos_metrics["market_in_sample"] = _metrics({k: v for k, v in Mo.items()}, {k: v[hm] for k, v in Y.items()}, yres[hm],
                                                   np.ones(nmk, bool))
        oos_metrics["market_only"] = _metrics(MK, Y, yres, hm)
    # 4) GBM final pe [t_cut − ani, t_cut)
    trF = ok & (full.t >= t_cut - 365 * tr_years) & (full.t < t_cut)
    mF = G.train(X[trF], {k: v[trF] for k, v in ytask.items()}, cfg["gbm"])
    art: Dict[str, Any] = {
        "engine": ENGINE_VERSION, "config": cfg, "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "train_to": _ts(t_cut), "n_train": int(trF.sum()), "features": FEATURE_NAMES + ["dc_lh", "dc_la", "dc_h", "dc_d", "dc_a", "dc_o25", "dc_by"],
        "gbm": G.dumps(mF) if mF else "", "stack": stack, "market": market, "league_rel": league_rel,
        "calib": {"cal": gcal["cal"], "blocked": gcal["blocked"], "report": gcal["report"]}, "blend": blend_art,
        "metrics": {"oos": oos_metrics, "walk_forward": wf},
    }
    if holdout_days > 0:
        ho = ok & (full.t >= t_cut) & (full.t < t_cut + holdout_days)
        if ho.any():
            PH = G.predict(mF, X[ho])
            Sh = stack_sources(PH, {k: D[k][ho] for k in CORE}, stack)
            if gcal["cal"]:
                Sh = calibrate_dict(Sh, gcal["cal"], np.array([league_group(x) for x in full.league[ho]]))
            art["metrics"]["holdout"] = _metrics(Sh, {k: v[ho] for k, v in Y.items()}, yres[ho], np.ones(int(ho.sum()), bool))
            if keep_holdout:  # pentru simularea biletelor pe zile trecute (nu se salvează în artefact)
                art["_holdout"] = {"idx": np.where(ho)[0], "S": Sh, "hist": full}
    art["fit_seconds"] = round(time.time() - t0, 1)
    log(f"  [{ENGINE_VERSION}] artefact gata: train={art['n_train']} ({art['fit_seconds']}s)")
    return art


# ---------------------------------------------------------------- stocare
def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS model_artifact (
        id INTEGER PRIMARY KEY AUTOINCREMENT, engine TEXT NOT NULL, role TEXT NOT NULL,
        created_at TEXT NOT NULL, train_to TEXT, metrics_json TEXT, config_json TEXT, blob TEXT NOT NULL)""")


def save_artifact(conn: sqlite3.Connection, art: Dict[str, Any], role: str = "champion") -> int:
    ensure_table(conn)
    with conn:
        if role == "champion":
            conn.execute("UPDATE model_artifact SET role='retired' WHERE role='champion'")
        cur = conn.execute("INSERT INTO model_artifact(engine, role, created_at, train_to, metrics_json, config_json, blob) "
                           "VALUES (?,?,?,?,?,?,?)",
                           (art["engine"], role, art["trained_at"], art.get("train_to"), json.dumps(art.get("metrics", {})),
                            json.dumps(art["config"]), json.dumps(art)))
        # păstrăm doar ultimele 4 artefacte retrase (DB-ul stă în release, nu în git)
        conn.execute("DELETE FROM model_artifact WHERE role='retired' AND id NOT IN "
                     "(SELECT id FROM model_artifact WHERE role='retired' ORDER BY id DESC LIMIT 4)")
    return int(cur.lastrowid)


def load_champion(conn: sqlite3.Connection) -> Optional[Dict[str, Any]]:
    ensure_table(conn)
    r = conn.execute("SELECT blob FROM model_artifact WHERE role='champion' ORDER BY id DESC LIMIT 1").fetchone()
    return json.loads(r[0]) if r else None


# ---------------------------------------------------------------- predicție live
class LivePredictor:
    """Probabilități Robot v2 pentru meciuri viitoare (feature-uri din tot istoricul, DC re-estimat acum)."""

    def __init__(self, conn: sqlite3.Connection, art: Dict[str, Any], upcoming: Sequence[sqlite3.Row], now_t: Optional[float] = None):
        self.art = art
        cfg = art["config"]
        hist = load_history(conn)
        self.hist_n = len(hist)
        now_t = now_t or (time.time() / 86400.0)
        extra = []
        for m in upcoming:
            extra.append((int(m["home_id"]), int(m["away_id"]), int(m["league_id"] if m["league_id"] is not None else -1),
                          int(m["season_id"] if m["season_id"] is not None else -1), day_of(m["kickoff_utc"])))
        self.ids = [int(m["id"]) for m in upcoming]
        self.out: Dict[int, Dict[str, Any]] = {}
        if not extra:
            return
        _, _, Xe = _features(hist, cfg, extra=extra)
        dc = fit_dc(hist, now_t + 1e-6, half_life=cfg["half_life"], years=cfg["dc_years"])
        H = np.array([e[0] for e in extra]); A = np.array([e[1] for e in extra]); L = np.array([e[2] for e in extra])
        lh, la, cov = dc.lambdas(H, A, L)
        Mx = score_matrix(lh, la, dc.rho)
        Dm = market_probs_from_matrix(Mx)
        X = _with_dc(Xe, lh, la, Dm)
        models = G.loads(art.get("gbm", ""))
        if models:
            GB = G.predict(models, X)
            S = stack_sources(GB, Dm, art["stack"])
        else:  # fără lightgbm: doar Dixon-Coles (calibrat de stacker cu GBM=DC)
            S = stack_sources(Dm, Dm, art["stack"])
        cal = (art.get("calib") or {}).get("cal") or {}
        self.groups = {}
        if cal:
            from betpredict.model.calib import calibrate_dict, league_group
            S = calibrate_dict(S, cal, np.array([league_group(x) for x in L]))
        g = np.arange(Mx.shape[1])
        tot = g[:, None] + g[None, :]
        o05 = (Mx * (tot > 0.5)).sum(axis=(1, 2))
        o45 = (Mx * (tot > 4.5)).sum(axis=(1, 2))
        rel = art.get("league_rel", {})
        for i, mid in enumerate(self.ids):
            flat = Mx[i].ravel()
            top = np.argsort(-flat)[:6]
            n1 = Mx.shape[1]
            self.out[mid] = {
                "p": {k: float(S[k][i]) for k in CORE}, "dc": {k: float(Dm[k][i]) for k in CORE},
                "o05": float(o05[i]), "o45": float(o45[i]),
                "lambda_home": round(float(lh[i]), 3), "lambda_away": round(float(la[i]), 3),
                "coverage": float(cov[i]), "league_rel": float(rel.get(str(extra[i][2]), 0.5)), "league_id": int(extra[i][2]),
                "elo_home": round(float(Xe[i][0]), 1), "elo_away": round(float(Xe[i][1]), 1),
                "most_likely_score": f"{top[0] // n1}-{top[0] % n1}",
                "top_scores": [{"score": f"{j // n1}-{j % n1}", "p": round(float(flat[j]), 4)} for j in top],
                "features": {n: (None if not np.isfinite(v) else round(float(v), 4)) for n, v in zip(FEATURE_NAMES, Xe[i])},
            }

    def get(self, match_id: int) -> Optional[Dict[str, Any]]:
        return self.out.get(int(match_id))

    def with_market(self, match_id: int, mk: Dict[str, float]) -> Optional[Dict[str, float]]:
        """Combinația cu piața (1X2, O/U 1.5/2.5/3.5, GG) dacă există cote complete; altfel None."""
        o = self.out.get(int(match_id))
        if not o:
            return None
        res: Dict[str, float] = {}
        cov, rel = o["coverage"], o["league_rel"]
        shrink = np.array([0.5 * (1 - cov * rel)])
        S = {k: np.array([o["p"][k]]) for k in CORE}
        if all(k in mk for k in ("H", "D", "A")):
            M = {k: np.array([mk.get(k, o["p"][k])]) for k in CORE}
            P = market_combine(S, M, self.art["market"], shrink)
            res.update({k: float(P[k][0]) for k in ("H", "D", "A")})
        for k in BIN:
            if k in mk:
                p = apply_binary(np.array(self.art["market"][k]), [S[k], np.array([mk[k]])])
                z = (1 - shrink) * np.log(p / (1 - p)) + shrink * math.log(min(1 - 1e-6, max(1e-6, mk[k])) / max(1e-6, 1 - mk[k]))
                res[k] = float(1 / (1 + np.exp(-z[0])))
        # v4: unde backtest-ul a ales blend-ul logit pe ligă (w învățat), îl folosim în locul stacker-ului
        bl = self.art.get("blend") or {}
        use, W = bl.get("use") or {}, bl.get("weights") or {}
        if use and W:
            from betpredict.model.calib import blend as _blend, league_w as _lw
            lid = o.get("league_id")
            if use.get("1x2") and all(k in mk for k in ("H", "D", "A")) and all(k in W for k in ("H", "D", "A")):
                q = {k: float(_blend(np.array([o["p"][k]]), np.array([mk[k]]), np.array([_lw(W, k, lid)]))[0]) for k in ("H", "D", "A")}
                sq = sum(q.values())
                res.update({k: v / sq for k, v in q.items()})
            for k in BIN:
                if use.get(k) and k in mk and k in W:
                    res[k] = float(_blend(np.array([o["p"][k]]), np.array([mk[k]]), np.array([_lw(W, k, lid)]))[0])
        if "O25" in res and "O15" in res:
            res["O25"] = min(res["O25"], res["O15"])
        if "O35" in res and "O25" in res:
            res["O35"] = min(res["O35"], res["O25"])
        return res


# ---------------------------------------------------------------- campion / challenger (săptămânal)
SCORE_KEYS = ("1x2", "O15", "O25", "O35", "BY")


def holdout_score(m: Dict[str, Any]) -> Optional[float]:
    if not m or not m.get("n"):
        return None
    return float(sum(m[k] for k in SCORE_KEYS))


def challenger_config(champ: Dict[str, Any], week: int) -> Dict[str, Any]:
    """Variantă locală a configurației campionului (o singură dimensiune pe săptămână, rotativ)."""
    c = json.loads(json.dumps(champ))
    knob = week % 5
    if knob == 0:
        c["half_life"] = {90.0: 150.0, 150.0: 240.0, 240.0: 365.0, 365.0: 150.0}.get(float(c["half_life"]), 240.0)
    elif knob == 1:
        c["elo"]["k"] = {14.0: 20.0, 20.0: 26.0, 26.0: 32.0, 32.0: 14.0}.get(float(c["elo"]["k"]), 20.0)
    elif knob == 2:
        c["elo"]["home_adv"] = {45.0: 60.0, 60.0: 75.0, 75.0: 90.0, 90.0: 45.0}.get(float(c["elo"]["home_adv"]), 60.0)
    elif knob == 3:
        c["gbm"]["num_leaves"] = {16: 24, 24: 32, 32: 16}.get(int(c["gbm"].get("num_leaves", 24)), 24)
    else:
        c["gbm"]["num_rounds"] = {250: 350, 350: 500, 500: 250}.get(int(c["gbm"].get("num_rounds", 350)), 350)
    return c


def weekly_cycle(conn: sqlite3.Connection, holdout_days: int = 42, log=print, min_gain: float = 0.002) -> Dict[str, Any]:
    """Antrenează campionul și un challenger cu același cutoff (azi − holdout), compară pe holdout
    (suma logloss 1X2 + O/U 1.5/2.5/3.5 + GG). Challenger-ul e promovat DOAR dacă e mai bun cu ≥ min_gain
    și nicio piață nu se strică cu > 0.002. Apoi configurația câștigătoare se re-antrenează pe tot istoricul."""
    hist = load_history(conn)
    if len(hist) < 5000:
        return {"skipped": "istoric insuficient"}
    champ = load_champion(conn)
    champ_cfg = champ["config"] if champ else DEFAULT_CONFIG
    week = int(time.time() // (7 * 86400))
    chal_cfg = challenger_config(champ_cfg, week)
    cutoff = _ts(float(hist.t[-1]) - holdout_days)[:10]
    log(f"campion/challenger: cutoff={cutoff}, holdout={holdout_days} zile")
    a = fit_artifact(conn, champ_cfg, cutoff=cutoff, holdout_days=holdout_days, log=log, hist=hist)
    b = fit_artifact(conn, chal_cfg, cutoff=cutoff, holdout_days=holdout_days, log=log, hist=hist)
    ha, hb = a["metrics"].get("holdout", {}), b["metrics"].get("holdout", {})
    sa, sb = holdout_score(ha), holdout_score(hb)
    worse = [k for k in SCORE_KEYS if ha.get(k) is not None and hb.get(k) is not None and hb[k] - ha[k] > 0.002]
    promote = sa is not None and sb is not None and (sa - sb) / len(SCORE_KEYS) >= min_gain / len(SCORE_KEYS) and not worse
    win_cfg = chal_cfg if promote else champ_cfg
    final = fit_artifact(conn, win_cfg, log=log, hist=hist)
    final["metrics"]["holdout_champion"] = ha
    final["metrics"]["holdout_challenger"] = hb
    final["metrics"]["promoted"] = bool(promote)
    save_artifact(conn, final, "champion")
    return {"cutoff": cutoff, "champion_holdout": ha, "challenger_holdout": hb, "challenger_config_diff": _diff(champ_cfg, chal_cfg),
            "promoted": bool(promote), "worse_markets": worse, "final_train_to": final["train_to"], "fit_seconds": final["fit_seconds"]}


def _diff(a: Dict[str, Any], b: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    out = {}
    for k in set(a) | set(b):
        if isinstance(a.get(k), dict) and isinstance(b.get(k), dict):
            out.update(_diff(a[k], b[k], prefix + k + "."))
        elif a.get(k) != b.get(k):
            out[prefix + k] = [a.get(k), b.get(k)]
    return out
