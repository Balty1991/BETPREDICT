"""Harness de backtest walk-forward pe depozitul istoric (≈215k meciuri).

Totul e strict out-of-sample: feature-urile sunt secvențiale (starea de dinaintea meciului),
Dixon-Coles se re-estimează lunar doar pe trecut, LightGBM se re-antrenează trimestrial doar pe
trecut, stacker-ul/calibrarea se re-estimează lunar doar pe predicțiile OOS anterioare, iar
pragurile adaptive de recomandare se aleg doar din lunile anterioare.

Raportează pe piață (1X2, O/U 1.5/2.5/3.5, GG, DNB, șansă dublă): logloss, Brier, ECE și ROI
simulat pe cotele disponibile (sezonul 2025/26 din depozit + snapshot-urile BSD din DB; unde
există cota de deschidere se calculează și CLV)."""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from betpredict.model import gbm as G
from betpredict.model.data import History, load_history, load_snapshot_odds, load_warehouse_odds, novig_market
from betpredict.model.dc import fit_dc, market_probs_from_matrix, score_matrix
from betpredict.model.features import FEATURE_NAMES, EloParams, build_features, elo_only
from betpredict.model.metrics import brier_bin, brier_multi, ece, logloss_bin, logloss_multi, roi
from betpredict.model.stack import apply_binary, apply_multi, fit_binary, fit_multi

BIN = ("O15", "O25", "O35", "BY")

# Cotele din depozit pentru dec. 2025 – apr. 2026 sunt în mare parte cote LIVE (capturate în timpul
# meciului: ex. Elveția–Germania 3-4 cu cota 1.09 la oaspeți). Logloss-ul pieței pe acele luni este
# 0.70–0.85 (imposibil pentru cote pre-meci, ~0.97–1.00), iar din iunie 2026 revine la 0.96–0.99.
# Folosim doar perioada curată + un filtru de plauzibilitate care NU se uită la rezultat.
ODDS_CLEAN_FROM = "2026-06-01"


def plausible_prematch(o: Dict[str, float]) -> bool:
    if all(k in o for k in ("H", "D", "A")):
        if min(o["H"], o["D"], o["A"]) < 1.04 or max(o["H"], o["D"], o["A"]) > 26 or o["D"] < 2.4:
            return False
    return True
SELS = ("H", "D", "A", "1X", "12", "X2", "DH", "DA", "O15", "U15", "O25", "U25", "O35", "U35", "BY", "BN")


def month_starts(t0: float, t1: float) -> List[float]:
    a = np.datetime64(int(t0 * 86400), "s").astype("datetime64[M]")
    b = np.datetime64(int(t1 * 86400), "s").astype("datetime64[M]") + np.timedelta64(1, "M")
    return [float(m.astype("datetime64[s]").astype(np.int64)) / 86400 for m in np.arange(a, b + np.timedelta64(1, "M"))]


def day_of(s: str) -> float:
    return float(np.datetime64(s[:19], "s").astype(np.int64)) / 86400


def full_probs(P: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
    """Completează DC/DNB și Sub din H/D/A și Peste."""
    out = dict(P)
    out["1X"], out["12"], out["X2"] = P["H"] + P["D"], P["H"] + P["A"], P["D"] + P["A"]
    nd = np.maximum(1e-9, P["H"] + P["A"])
    out["DH"], out["DA"] = P["H"] / nd, P["A"] / nd
    for k in ("15", "25", "35"):
        out["U" + k] = 1 - P["O" + k]
    out["BN"] = 1 - P["BY"]
    return out


def outcomes(gh: np.ndarray, ga: np.ndarray) -> Dict[str, np.ndarray]:
    tot = gh + ga
    y = {"H": gh > ga, "D": gh == ga, "A": gh < ga}
    y["1X"], y["12"], y["X2"] = y["H"] | y["D"], y["H"] | y["A"], y["D"] | y["A"]
    y["DH"], y["DA"] = y["H"], y["A"]
    for ln, k in ((1.5, "15"), (2.5, "25"), (3.5, "35")):
        y["O" + k], y["U" + k] = tot > ln, tot < ln
    y["BY"] = (gh > 0) & (ga > 0)
    y["BN"] = ~y["BY"]
    return {k: v.astype(float) for k, v in y.items()}


# ------------------------------------------------------------------ componente walk-forward
def dc_walk_forward(hist: History, t_from: float, t_to: float, half_life: float, years: float = 3.0,
                    rho: Optional[float] = None, league_home: bool = True) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    n = len(hist)
    lh, la, cov, rr = (np.full(n, np.nan) for _ in range(4))
    ms = month_starts(t_from, t_to)
    for a, b in zip(ms[:-1], ms[1:]):
        sel = (hist.t >= a) & (hist.t < b)
        if not sel.any():
            continue
        m = fit_dc(hist, a, half_life=half_life, years=years, rho=rho, league_home_shrink=200.0 if league_home else 1e12)
        x, y, c = m.lambdas(hist.home[sel], hist.away[sel], hist.league[sel])
        lh[sel], la[sel], cov[sel], rr[sel] = x, y, c, m.rho
    return lh, la, cov, rr


def dc_probs(lh, la, rho) -> Dict[str, np.ndarray]:
    out = {k: np.full(len(lh), np.nan) for k in ("H", "D", "A", "O15", "O25", "O35", "BY")}
    ok = np.isfinite(lh)
    if not ok.any():
        return out
    for r in np.unique(rho[ok]):
        m = ok & (rho == r)
        P = market_probs_from_matrix(score_matrix(lh[m], la[m], float(r)))
        for k in out:
            out[k][m] = P[k]
    return out


def v1_baseline(hist: History, t_from: float, t_to: float) -> Dict[str, np.ndarray]:
    """Robot-v1 exact: GoalModel (hl 180, rho −0.08) lunar + ELO analytics_core (k 20, HA 60) blend 0.35."""
    from analytics_core import EloConfig, EloRatings

    lh, la, cov, _ = dc_walk_forward(hist, t_from, t_to, 180.0, rho=-0.08, league_home=False)
    P = dc_probs(lh, la, np.full(len(lh), -0.08))
    elo = EloRatings(EloConfig(k_factor=20.0, home_advantage=60.0))
    e = np.full(len(hist), np.nan)
    H, A, GH, GA, T = hist.home.tolist(), hist.away.tolist(), hist.gh.tolist(), hist.ga.tolist(), hist.t.tolist()
    for i in range(len(H)):
        if t_from <= T[i] < t_to:
            e[i] = elo.expected_home(H[i], A[i])
        elo.update(H[i], A[i], GH[i], GA[i])
    pd = P["D"]
    ph_e = np.clip(e - 0.5 * pd, 0.01, 0.97)
    pa_e = np.maximum(0.01, 1 - pd - ph_e)
    ph = 0.65 * P["H"] + 0.35 * ph_e
    pa = 0.65 * P["A"] + 0.35 * pa_e
    s = ph + pd + pa
    P["H"], P["D"], P["A"] = ph / s, pd / s, pa / s
    P["cov"] = cov
    return P


def gbm_walk_forward(X: np.ndarray, hist: History, t_from: float, t_to: float, train_years: float = 6.0,
                     step_months: int = 3, params: Optional[Dict] = None, log=print) -> Dict[str, np.ndarray]:
    n = len(hist)
    out = {k: np.full(n, np.nan) for k in ("H", "D", "A", "O15", "O25", "O35", "BY")}
    y = G.targets(hist.gh, hist.ga)
    ms = month_starts(t_from, t_to)[::step_months] + [t_to + 1]
    for a, b in zip(ms[:-1], ms[1:]):
        te = (hist.t >= a) & (hist.t < b)
        if not te.any():
            continue
        tr = (hist.t < a) & (hist.t >= a - 365 * train_years) & np.isfinite(X[:, -1])
        t0 = time.time()
        models = G.train(X[tr], {k: v[tr] for k, v in y.items()}, params)
        P = G.predict(models, X[te])
        for k in out:
            out[k][te] = P[k]
        log(f"  gbm fold {np.datetime64(int(a * 86400), 's')} train={tr.sum()} test={te.sum()} {time.time() - t0:.0f}s")
    return out


def stack_walk_forward(t: np.ndarray, srcs: List[Dict[str, np.ndarray]], y_res: np.ndarray, Y: Dict[str, np.ndarray],
                       t_from: float, t_to: float, window_days: float = 540, mask: Optional[np.ndarray] = None,
                       prior_bin: Optional[np.ndarray] = None, prior_multi: Optional[np.ndarray] = None,
                       l2: float = 2.0, min_train: int = 300) -> Dict[str, np.ndarray]:
    """Re-estimare lunară a stacker-ului pe OOS-ul anterior. ``mask``: rânduri eligibile (ex. cu cote)."""
    n = len(t)
    ok = np.ones(n, bool) if mask is None else mask.copy()
    for s in srcs:
        for k in ("H", "O25"):
            ok &= np.isfinite(s[k])
    out = {k: np.full(n, np.nan) for k in ("H", "D", "A", "O15", "O25", "O35", "BY")}
    ms = month_starts(t_from, t_to)
    for a, b in zip(ms[:-1], ms[1:]):
        te = ok & (t >= a) & (t < b)
        if not te.any():
            continue
        tr = ok & (t < a) & (t >= a - window_days)
        S3 = [np.stack([s["H"], s["D"], s["A"]], 1) for s in srcs]
        if tr.sum() >= min_train:
            B = fit_multi([x[tr] for x in S3], y_res[tr].astype(int), l2=l2, prior=prior_multi)
        else:
            B = fit_multi([x[tr][:0] for x in S3], np.zeros(0, int), l2=1e6, prior=prior_multi) if prior_multi is not None \
                else None
        if B is None:
            B = fit_multi([x[:1] for x in S3], np.zeros(1, int), l2=1e9)
        P = apply_multi(B, [x[te] for x in S3])
        out["H"][te], out["D"][te], out["A"][te] = P[:, 0], P[:, 1], P[:, 2]
        for k in BIN:
            src = [s[k] for s in srcs]
            if tr.sum() >= min_train:
                c = fit_binary([x[tr] for x in src], Y[k][tr], prior=prior_bin, l2=l2)
            else:
                c = fit_binary([x[:1] for x in src], Y[k][:1], prior=prior_bin, l2=1e9)
            out[k][te] = apply_binary(c, [x[te] for x in src])
    out["O25"] = np.minimum(out["O25"], out["O15"])
    out["O35"] = np.minimum(out["O35"], out["O25"])
    return out


# ------------------------------------------------------------------ evaluare
MARKETS = {
    "1x2": ("H", "D", "A"), "ou_1.5": ("O15",), "ou_2.5": ("O25",), "ou_3.5": ("O35",), "btts": ("BY",),
    "dnb": ("DH",), "double_chance": ("1X", "12", "X2"),
}


def evaluate(P: Dict[str, np.ndarray], Y: Dict[str, np.ndarray], sel: np.ndarray, y_res: np.ndarray) -> Dict[str, Dict[str, float]]:
    P = full_probs(P)
    out: Dict[str, Dict[str, float]] = {}
    m = sel & np.isfinite(P["H"]) & np.isfinite(P["O25"])
    if not m.any():
        return out
    M3 = np.stack([P["H"][m], P["D"][m], P["A"][m]], 1)
    out["1x2"] = {"n": int(m.sum()), "logloss": logloss_multi(M3, y_res[m]), "brier": brier_multi(M3, y_res[m]),
                  "ece": float(np.mean([ece(P[k][m], Y[k][m]) for k in ("H", "D", "A")]))}
    for mk, ks in MARKETS.items():
        if mk == "1x2":
            continue
        mm = m & (Y["D"] == 0) if mk == "dnb" else m
        ll = np.mean([logloss_bin(P[k][mm], Y[k][mm]) for k in ks])
        br = np.mean([brier_bin(P[k][mm], Y[k][mm]) for k in ks])
        ec = np.mean([ece(P[k][mm], Y[k][mm]) for k in ks])
        out[mk] = {"n": int(mm.sum()), "logloss": float(ll), "brier": float(br), "ece": float(ec)}
    return {k: {kk: (round(vv, 4) if isinstance(vv, float) else vv) for kk, vv in v.items()} for k, v in out.items()}


ROI_GROUPS = {"1x2": ("H", "D", "A"), "ou_1.5": ("O15", "U15"), "ou_2.5": ("O25", "U25"), "ou_3.5": ("O35", "U35"),
              "btts": ("BY", "BN"), "dnb": ("DH", "DA"), "double_chance": ("1X", "12", "X2")}


def roi_table(P: Dict[str, np.ndarray], Y: Dict[str, np.ndarray], O: Dict[str, np.ndarray], sel: np.ndarray,
              policies: Dict[str, Dict[str, float]]) -> Dict[str, Dict[str, Any]]:
    P = full_probs(P)
    out: Dict[str, Dict[str, Any]] = {}
    for mk, ks in ROI_GROUPS.items():
        row = {}
        for pol, kw in policies.items():
            ps, os_, ws, vs = [], [], [], []
            for k in ks:
                m = sel & np.isfinite(O[k]) & np.isfinite(P[k])
                ps.append(P[k][m]); os_.append(O[k][m]); ws.append(Y[k][m])
                vs.append(((Y["D"][m] > 0) if k in ("DH", "DA") else np.zeros(m.sum(), bool)))
            row[pol] = roi(np.concatenate(ps), np.concatenate(os_), np.concatenate(ws), void=np.concatenate(vs), **kw)
        out[mk] = row
    return out


POLICIES = {"ev>0": {"ev_min": 0.0}, "ev>3%": {"ev_min": 0.03}, "ev>5%": {"ev_min": 0.05},
            "rec": {"ev_min": 0.0, "p_min": 0.60, "odds_max": 2.20}}


def adaptive_roi(P: Dict[str, np.ndarray], Y: Dict[str, np.ndarray], O: Dict[str, np.ndarray], t: np.ndarray,
                 mask: np.ndarray, league: np.ndarray, t_from: float, t_to: float,
                 grid=(0.0, 0.02, 0.04, 0.06, 0.08, 0.12), min_n: int = 60, prior_n: float = 80.0) -> Dict[str, Any]:
    """Prag EV pe piață × ligă ales DOAR din lunile anterioare (ROI micșorat bayesian spre −marjă),
    aplicat lunii următoare. Returnează ROI-ul OOS al politicii adaptive."""
    P = full_probs(P)
    res: Dict[str, Any] = {}
    ms = month_starts(t_from, t_to)
    for mk, ks in ROI_GROUPS.items():
        rows = []
        for k in ks:
            m = mask & np.isfinite(O[k]) & np.isfinite(P[k]) & (O[k] >= 1.15)
            idx = np.where(m)[0]
            void = (Y["D"][idx] > 0) if k in ("DH", "DA") else np.zeros(len(idx), bool)
            prof = np.where(void, 0.0, np.where(Y[k][idx] > 0, O[k][idx] - 1, -1.0))
            ev = P[k][idx] * O[k][idx] - 1
            rows.append(np.stack([t[idx], ev, prof, league[idx].astype(float), P[k][idx]], 1))
        R = np.concatenate(rows) if rows else np.zeros((0, 5))
        taken = []
        for a, b in zip(ms[:-1], ms[1:]):
            past = R[R[:, 0] < a]
            cur = R[(R[:, 0] >= a) & (R[:, 0] < b)]
            if len(cur) == 0:
                continue
            thr = None
            best = 0.0
            for g in grid:
                q = past[past[:, 1] > g]
                if len(q) < min_n:
                    continue
                shr = (q[:, 2].sum() + prior_n * -0.05) / (len(q) + prior_n)
                if shr > best:
                    best, thr = shr, g
            if thr is None:
                continue
            # ligi cu ROI istoric negativ (micșorat) pe piața asta → excluse
            bad = set()
            for lg in np.unique(past[:, 3]):
                q = past[(past[:, 3] == lg) & (past[:, 1] > thr)]
                if len(q) >= 25 and (q[:, 2].sum() + 30 * 0.0) / (len(q) + 30) < -0.08:
                    bad.add(lg)
            pick = cur[(cur[:, 1] > thr) & ~np.isin(cur[:, 3], list(bad))]
            taken.append(pick)
        T = np.concatenate(taken) if taken else np.zeros((0, 5))
        res[mk] = {"n": int(len(T)), "roi": round(float(T[:, 2].mean()), 4) if len(T) else None,
                   "se": round(float(T[:, 2].std(ddof=1) / math.sqrt(len(T))), 4) if len(T) > 1 else None}
    return res


# ------------------------------------------------------------------ reglaje (pe perioada de tuning, înainte de evaluare)
def tune_elo(hist: History, t_from: float, t_to: float, log=print) -> EloParams:
    sel = (hist.t >= t_from) & (hist.t < t_to)
    y = np.where(hist.gh > hist.ga, 1.0, np.where(hist.gh == hist.ga, 0.5, 0.0))[sel]
    best, bs = EloParams(), float("inf")
    for k in (14.0, 20.0, 26.0, 32.0):
        for ha in (45.0, 60.0, 75.0, 90.0):
            for mg in (0.0, 0.6, 1.0):
                for off in (0.0, -60.0):
                    ep = EloParams(k=k, home_adv=ha, margin=mg, new_team_offset=off, regress=0.2)
                    e = elo_only(hist, ep)[sel]
                    s = float(np.mean((e - y) ** 2))
                    if s < bs:
                        best, bs = ep, s
    log(f"  elo tuned: {asdict(best)} brier_exp={bs:.5f}")
    return best


def tune_half_life(hist: History, t_from: float, t_to: float, log=print) -> Tuple[float, float]:
    sel = (hist.t >= t_from) & (hist.t < t_to)
    y = np.where(hist.gh > hist.ga, 0, np.where(hist.gh == hist.ga, 1, 2))
    tot = hist.gh + hist.ga
    best, bl = (180.0, 3.0), float("inf")
    for hl in (90.0, 150.0, 240.0, 365.0):
        for yrs in (2.0, 3.0):
            lh, la, _, rho = dc_walk_forward(hist, t_from, t_to, hl, years=yrs)
            P = dc_probs(lh, la, rho)
            m = sel & np.isfinite(P["H"])
            M3 = np.stack([P["H"][m], P["D"][m], P["A"][m]], 1)
            l = logloss_multi(M3, y[m]) + logloss_bin(P["O25"][m], (tot[m] > 2.5).astype(float))
            log(f"  dc hl={hl:.0f} years={yrs:.0f}: ll(1x2)+ll(o25)={l:.5f}")
            if l < bl:
                best, bl = (hl, yrs), l
    return best


# ------------------------------------------------------------------ rularea completă
def run_backtest(conn, warehouse_dir: Optional[Path] = None, eval_from: str = "2024-07-01", tune_from: str = "2023-07-01",
                 gbm_from: str = "2022-07-01", out: Optional[Path] = None, log=print, quick: bool = False,
                 odds_clean_from: str = ODDS_CLEAN_FROM) -> Dict[str, Any]:
    t_start = time.time()
    hist = load_history(conn)
    t_end = float(hist.t[-1]) + 1
    te_from, tu_from, tg_from = day_of(eval_from), day_of(tune_from), day_of(gbm_from)
    dc_from = tg_from - 365 * (2 if quick else 6)
    log(f"istoric: {len(hist)} meciuri; tuning {tune_from}→{eval_from}; evaluare {eval_from}→sfârșit")
    ep = tune_elo(hist, tu_from, te_from, log) if not quick else EloParams(k=20, home_adv=60, margin=0.6, regress=0.2)
    hl, yrs = tune_half_life(hist, tu_from, te_from, log) if not quick else (240.0, 3.0)
    log(f"  dc half-life={hl} years={yrs}")
    log("feature-uri secvențiale…")
    X0, _, _ = build_features(hist, ep)
    lh, la, cov, rho = dc_walk_forward(hist, dc_from, t_end, hl, years=yrs)
    D = dc_probs(lh, la, rho)
    X = np.concatenate([X0, np.stack([lh, la, D["H"], D["D"], D["A"], D["O25"], D["BY"]], 1).astype(np.float32)], 1)
    log("v1 (baseline)…")
    V1 = v1_baseline(hist, tu_from, t_end)
    log("LightGBM walk-forward…")
    GB = gbm_walk_forward(X, hist, tg_from, t_end, train_years=4 if quick else 6, log=log)
    Y = outcomes(hist.gh, hist.ga)
    y_res = np.where(hist.gh > hist.ga, 0, np.where(hist.gh == hist.ga, 1, 2))
    log("stacking + calibrare walk-forward…")
    ST = stack_walk_forward(hist.t, [GB, D], y_res, Y, tg_from + 180, t_end)
    # cote: depozit (2025/26) + snapshot-uri DB (consens BSD; ultima cotă pre-start ≈ closing)
    O = {k: np.full(len(hist), np.nan) for k in SELS}
    Oopen = {k: np.full(len(hist), np.nan) for k in SELS}
    wo = load_warehouse_odds(warehouse_dir) if warehouse_dir and Path(warehouse_dir).is_dir() else {}
    so = load_snapshot_odds(conn)
    pos = {int(i): j for j, i in enumerate(hist.ids.tolist())}
    t_clean = day_of(odds_clean_from)
    for mid, o in wo.items():
        j = pos.get(mid)
        if j is not None and hist.t[j] >= t_clean and plausible_prematch(o):
            for k, v in o.items():
                O[k][j] = v
    n_snap = 0
    for mid, d in so.items():
        j = pos.get(mid)
        if j is None:
            continue
        n_snap += 1
        for k, v in d["close"].items():
            O[k][j] = v
        for k, v in d["open"].items():
            Oopen[k][j] = v
    MK = {k: np.full(len(hist), np.nan) for k in SELS}
    has = np.zeros(len(hist), bool)
    for j in np.where(np.isfinite(O["H"]) | np.isfinite(O["O25"]))[0]:
        nv = novig_market({k: float(O[k][j]) for k in SELS if np.isfinite(O[k][j])})
        if all(k in nv for k in ("H", "D", "A", "O15", "O25", "O35", "BY")):
            has[j] = True
            for k, v in nv.items():
                MK[k][j] = v
    log(f"cote: depozit={len(wo)} snapshot={n_snap} meciuri complete (1X2+O/U+GG)={int(has.sum())}")
    # v1 + piață (blend-ul actual: model 0.4·(0.3+0.7·acoperire), piață 0.4; BSD lipsă în istoric)
    V1M = {}
    wm = 0.4 * (0.3 + 0.7 * np.nan_to_num(V1["cov"]))
    for k in ("H", "D", "A", "O15", "O25", "O35", "BY"):
        V1M[k] = np.where(has, (wm * V1[k] + 0.4 * MK[k]) / (wm + 0.4), np.nan)
    # v2 + piață: stacker cu piața (prior: 35% model, 65% piață în spațiul log), lunar, expanding
    odds_t0 = float(hist.t[has].min()) if has.any() else t_end
    pb = np.array([0.35, 0.35, 0.65, 0.65, 0.0])
    pm = np.zeros((7, 3))
    for j in range(3):
        pm[j, j], pm[3 + j, j] = 0.35, 0.65
    STM = stack_walk_forward(hist.t, [ST, MK], y_res, Y, odds_t0, t_end, window_days=3650, mask=has,
                             prior_bin=pb, prior_multi=pm, l2=40.0, min_train=400)
    # fallback pe lunile fără destule date: prior-ul fix (deja în stack_walk_forward)
    sel_eval = (hist.t >= te_from)
    sel_odds = has & (hist.t >= odds_t0)
    res: Dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "history_matches": len(hist), "eval_from": eval_from, "tune_from": tune_from,
        "elo_params": asdict(ep), "dc_half_life": hl, "dc_years": yrs, "features": FEATURE_NAMES,
        "odds_matches": int(has.sum()), "odds_clean_from": odds_clean_from, "odds_from": str(np.datetime64(int(odds_t0 * 86400), "s")) if has.any() else None,
        "model_only": {}, "with_market": {}, "roi": {}, "adaptive_roi": {},
    }
    for name, P in (("v1", V1), ("dc_v2", D), ("gbm_raw", GB), ("v2", ST)):
        res["model_only"][name] = evaluate(P, Y, sel_eval, y_res)
    for name, P in (("market", MK), ("v1_market", V1M), ("v2", ST), ("v2_market", STM)):
        res["with_market"][name] = evaluate(P, Y, sel_odds, y_res)
    # ROI: doar luni după prima lună de cote (stacker-ul cu piață are nevoie de istoric)
    for name, P in (("v1_market", V1M), ("v2", ST), ("v2_market", STM)):
        res["roi"][name] = roi_table(P, Y, O, sel_odds, POLICIES)
        res["adaptive_roi"][name] = adaptive_roi(P, Y, O, hist.t, sel_odds, hist.league, odds_t0, t_end)
    # CLV (doar unde avem cota de deschidere): dacă am fi pariat la deschidere, cota s-a mișcat în favoarea noastră?
    clv = {}
    for name, P in (("v1_market", V1M), ("v2_market", STM)):
        FP = full_probs(P)
        vals = []
        for k in SELS:
            m = sel_odds & np.isfinite(Oopen[k]) & np.isfinite(O[k]) & np.isfinite(FP[k]) & (FP[k] * Oopen[k] - 1 > 0)
            vals += list(Oopen[k][m] / O[k][m] - 1)
        clv[name] = {"n": len(vals), "avg_clv": round(float(np.mean(vals)), 4) if vals else None}
    res["clv"] = clv
    res["runtime_s"] = round(time.time() - t_start, 1)
    if out:
        Path(out).write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    return res
