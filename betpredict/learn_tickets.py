"""Auto-învățare pentru acumulatoare (săptămânal, în modul ``learn``).

1. Feedback live: biletele decontate ale Robotului pe nivel / variantă / piață / ligă; ce tipuri de
   selecții (piață × bandă de cotă) pică cel mai des față de probabilitatea promisă.
2. Propunere (challenger) de strategie:
   * ``shrink_w`` pe piață: cât credem modelul vs piața (grid pe logloss, rezultate reale + istoric);
   * ``leg_bias`` pe tip de selecție: corecție logit (Newton pe logloss) micșorată bayesian (n/(n+300));
   * ``blocked_leg_types``: P(rata reală < promisă − 5pp) > 90% (posterior Beta), n ≥ 40;
   * ``min_leg_p`` pe nivel: crește dacă selecțiile nivelului dezamăgesc, scade încet altfel;
   * ``variant_weights``: bandit Thompson pe „surpriza” selecțiilor din fiecare variantă (câștigate −
     promise, pe bilet) — semnal care apare mult mai repede decât biletele câștigate.
3. Campion vs challenger: ambele strategii construiesc bilete pe zilele trecute cu cote curate
   (probabilități out-of-sample, ``model.sim_rows``) și se decontează pe rezultatele reale.
   Challenger-ul e promovat doar dacă logloss-ul selecțiilor folosite scade și ROI-ul simulat nu e mai
   slab cu mai mult de o eroare standard. Fiecare schimbare intră în ``learning_log`` cu motivul ei.
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from betpredict.builder import optimizer as opt
from betpredict.robot.markets import settle_selection

TIERS = (50, 100, 500)
VARIANTS = ("echilibrat", "valoare", "goluri", "ancora_surpriza")
SEL_OF = {"H": ("1x2", 0.0, "HOME"), "D": ("1x2", 0.0, "DRAW"), "A": ("1x2", 0.0, "AWAY"),
          "O15": ("over_under", 1.5, "OVER"), "U15": ("over_under", 1.5, "UNDER"),
          "O25": ("over_under", 2.5, "OVER"), "U25": ("over_under", 2.5, "UNDER"),
          "O35": ("over_under", 3.5, "OVER"), "U35": ("over_under", 3.5, "UNDER"),
          "BY": ("btts", 0.0, "YES"), "BN": ("btts", 0.0, "NO")}


def _ll(p: float, y: float) -> float:
    p = min(1 - 1e-6, max(1e-6, p))
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def _full(p: Dict[str, float]) -> Dict[str, float]:
    out = dict(p)
    for k in ("15", "25", "35"):
        if "O" + k in p:
            out["U" + k] = 1 - p["O" + k]
    if "BY" in p:
        out["BN"] = 1 - p["BY"]
    return out


# ------------------------------------------------------------------ simulare
SIM_WINDOW_DAYS = 7  # ca biletele multi-zi live: pool pe ferestre de 7 zile (cotele curate istorice sunt rare)


def sim_pools(rows: Sequence[Dict[str, Any]], window_days: int = SIM_WINDOW_DAYS) -> Dict[str, List[Any]]:
    """Fereastră (RO, ``window_days`` zile) → pool de Cand din probabilitățile OOS + cotele reale."""
    from betpredict.builder.pool import Cand
    from betpredict.robot.engine import grade_and_confidence
    from betpredict.robot.markets import market_key
    from betpredict.robot.params import threshold_ok
    from betpredict.timeutil import ro_date_of

    pools: Dict[str, List[Any]] = defaultdict(list)
    pid = 0
    for r in rows:
        p, pm, mk, odds = _full(r["p"]), _full(r["p_model"]), _full(r.get("mk") or {}), r["odds"]
        d0 = ro_date_of(r["ko"]) or date(2000, 1, 1)
        day = (d0 - timedelta(days=d0.toordinal() % max(1, window_days))).isoformat()
        ko = r["ko"] if r["ko"].endswith("Z") else r["ko"] + "Z"
        for k, sel in SEL_OF.items():
            o = odds.get(k)
            if not o or k not in p or o < 1.15:
                continue
            pv = p[k]
            ev = pv * o - 1
            srcs = [v for v in (pm.get(k), mk.get(k)) if v is not None]
            agreement = max(0.0, 1 - 2 * max(abs(v - pv) for v in srcs)) if srcs else 0.5
            healthy = threshold_ok({}, market_key(sel[0], sel[1]), r["league"], ev)
            g, conf = grade_and_confidence(pv, agreement, True, ev, healthy, 1.0, 1.0)
            pid += 1
            c = Cand(pid, r["id"], r["league"], None, ko, None, None, sel[0], sel[1], sel[2], float(o), pv, ev, g, conf,
                     healthy, p_market=mk.get(k), odds_source="bsd_consensus")
            c.extra = {"won": settle_selection(sel[0], sel[1], sel[2], r["gh"], r["ga"])}
            pools[day].append(c)
    return pools


def simulate(pools: Dict[str, List[Any]], strat: Dict[str, Any], tiers=TIERS, variants=VARIANTS,
             n_sims: int = 1500) -> Dict[str, Any]:
    """Construiește biletele fiecărei zile cu ``strat`` și le decontează. ROI la 1u/bilet."""
    from betpredict.builder.tickets import build_variant

    opt.use_strategy(strat)
    tickets: List[Dict[str, Any]] = []
    for day in sorted(pools):
        pool = pools[day]
        if len({c.match_id for c in pool}) < 8:
            continue
        sel_used: Dict[int, int] = {}
        for tier in tiers:
            used: Dict[int, int] = {}
            for v in opt.variant_order(tier, variants, strat):
                cand = [c for c in opt.available(pool, sel_used, strat) if opt.leg_ok(c, tier, strat)]
                try:
                    res = build_variant(cand, tier, v, used, sel_used)
                except Exception:  # noqa: BLE001
                    res = None
                if not res:
                    continue
                legs = res[0]
                e = opt.ticket_eval(legs, n_sims=n_sims, s=strat)
                if e["ev"] <= 0:
                    continue
                for c in legs:
                    sel_used[c.prediction_id] = sel_used.get(c.prediction_id, 0) + 1
                    used[c.match_id] = used.get(c.match_id, 0) + 1
                res_legs = [c.extra["won"] for c in legs]
                if any(x is None for x in res_legs):
                    continue
                lost = sum(1 for x in res_legs if x == "lost")
                eff = math.prod(c.odds for c, x in zip(legs, res_legs) if x == "won")
                won = lost == 0
                tickets.append({"day": day, "tier": tier, "variant": v, "odds": e["odds"], "p": e["p"], "won": won,
                                "lost_legs": lost, "profit": (eff - 1) if won else -1.0,
                                "legs": [(opt.leg_type(c.market, c.line, c.odds), c.p_adj, 1.0 if x == "won" else 0.0, c.league_id)
                                         for c, x in zip(legs, res_legs) if x in ("won", "lost")]})
    return summarize(tickets)


def ticket_calibration(pools: Dict[str, List[Any]], strat: Dict[str, Any], n_tickets: int = 3000, seed: int = 7,
                       min_p: float = 0.55, n_legs=(3, 7)) -> Dict[str, Any]:
    """Cât de exactă e probabilitatea BILETULUI (fără filtrul de EV, deci eșantion mare): bilete aleatoare
    de 3–7 selecții (o selecție/meci, p ≥ ``min_p``) din fiecare fereastră; comparăm câștigurile reale cu
    suma probabilităților promise — naiv (produs) vs Monte Carlo cu corelații + corecțiile învățate."""
    rng = np.random.default_rng(seed)
    opt.use_strategy(strat)
    keys = [d for d in sorted(pools) if len({c.match_id for c in pools[d]}) >= n_legs[1]]
    if not keys:
        return {"n": 0}
    rows = []
    for i in range(n_tickets):
        pool = [c for c in pools[keys[i % len(keys)]] if c.p >= min_p and c.extra.get("won") in ("won", "lost")]
        by_m: Dict[int, List[Any]] = defaultdict(list)
        for c in pool:
            by_m[c.match_id].append(c)
        if len(by_m) < n_legs[0]:
            continue
        k = int(rng.integers(n_legs[0], min(n_legs[1], len(by_m)) + 1))
        ms = rng.choice(list(by_m), size=k, replace=False)
        legs = [by_m[m][int(rng.integers(len(by_m[m])))] for m in ms]
        e = opt.ticket_eval(legs, n_sims=600, seed=i, s=strat)
        y = 1.0 if all(c.extra["won"] == "won" for c in legs) else 0.0
        p_raw = float(np.prod([c.p for c in legs]))
        rows.append((p_raw, e["p_naive"], e["p"], y))
    if not rows:
        return {"n": 0}
    a = np.array(rows)
    out = {"n": len(a), "won": int(a[:, 3].sum())}
    for j, name in ((0, "raw"), (1, "naive"), (2, "mc")):
        out[f"exp_{name}"] = round(float(a[:, j].sum()), 1)
        out[f"ll_{name}"] = round(float(np.mean([_ll(p, y) for p, y in zip(a[:, j], a[:, 3])])), 4)
        out[f"brier_{name}"] = round(float(np.mean((a[:, j] - a[:, 3]) ** 2)), 4)
    return out


def summarize(tickets: List[Dict[str, Any]]) -> Dict[str, Any]:
    def agg(ts):
        if not ts:
            return {"n": 0}
        prof = np.array([t["profit"] for t in ts])
        legs = [l for t in ts for l in t["legs"]]
        return {"n": len(ts), "won": int(sum(t["won"] for t in ts)), "exp_won": round(sum(t["p"] for t in ts), 2),
                "roi": round(float(prof.mean()), 4), "se": round(float(prof.std(ddof=1) / math.sqrt(len(ts))), 4) if len(ts) > 1 else None,
                "avg_odds": round(float(np.mean([t["odds"] for t in ts])), 1),
                "near_miss": int(sum(1 for t in ts if t["lost_legs"] == 1)),
                "legs": len(legs), "leg_hit": round(float(np.mean([l[2] for l in legs])), 4) if legs else None,
                "leg_p": round(float(np.mean([l[1] for l in legs])), 4) if legs else None,
                "leg_logloss": round(float(np.mean([_ll(l[1], l[2]) for l in legs])), 4) if legs else None}
    out = {"all": agg(tickets), "by_tier": {str(t): agg([x for x in tickets if x["tier"] == t]) for t in TIERS},
           "by_variant": {v: agg([x for x in tickets if x["variant"] == v]) for v in VARIANTS},
           "days": len({t["day"] for t in tickets})}
    out["_tickets"] = tickets
    return out


# ------------------------------------------------------------------ învățare
def _settled_legs(conn: sqlite3.Connection, since: str) -> List[Tuple[str, str, float, Optional[float], float, float, Optional[int]]]:
    """Predicțiile decontate ale Robotului cu cote: (piață, tip, p_model, p_piață, cotă, y, ligă)."""
    from betpredict.robot import MODEL_VERSION
    from betpredict.robot.markets import market_key

    out = []
    for r in conn.execute(
        """SELECT p.market, p.line, p.p_calibrated, p.p_market_novig, p.odds_shown, p.result, m.league_id
           FROM prediction p JOIN match m ON m.id=p.match_id
           WHERE p.model_version=? AND p.result IN ('won','lost') AND p.odds_shown IS NOT NULL AND p.day >= ?""",
        (MODEL_VERSION, since)):
        out.append((market_key(r[0], r[1] or 0.0), opt.leg_type(r[0], r[1] or 0.0, r[4]), float(r[2]),
                    r[3], float(r[4]), 1.0 if r[5] == "won" else 0.0, r[6]))
    return out


def _sim_legs(pools: Dict[str, List[Any]]):
    from betpredict.robot.markets import market_key

    out = []
    for pool in pools.values():
        for c in pool:
            if c.extra.get("won") in ("won", "lost"):
                out.append((market_key(c.market, c.line), opt.leg_type(c.market, c.line, c.odds), c.p, c.p_market,
                            c.odds, 1.0 if c.extra["won"] == "won" else 0.0, c.league_id))
    return out


BIAS_PRIOR_N = 300  # micșorare bayesiană a corecțiilor pe tip de selecție: n/(n+300)


def _intercept(ps: Sequence[float], ys: Sequence[float], iters: int = 25) -> float:
    z = np.log(np.clip(ps, 1e-4, 1 - 1e-4) / (1 - np.clip(ps, 1e-4, 1 - 1e-4)))
    y = np.asarray(ys, float)
    b = 0.0
    for _ in range(iters):
        q = 1 / (1 + np.exp(-(z + b)))
        g, h = float(np.sum(q - y)), float(np.sum(q * (1 - q))) + 1e-9
        b -= g / h
        if abs(g / h) < 1e-6:
            break
    return float(b)


def propose(base: Dict[str, Any], legs, live_tickets: Dict[str, Any], sim_res: Optional[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Challenger = campion + actualizările învățate. Întoarce și lista schimbărilor (cu motiv)."""
    from scipy.stats import beta as beta_dist

    s = json.loads(json.dumps(base))
    changes: List[Dict[str, Any]] = []
    # 1) shrink pe piață
    by_mk: Dict[str, List] = defaultdict(list)
    for x in legs:
        by_mk[x[0]].append(x)
    for mk, xs in by_mk.items():
        if len(xs) < 150:
            continue
        best, bl = None, float("inf")
        for w in np.linspace(0, 1, 11):
            tmp = {**s, "shrink_w": {**s["shrink_w"], mk: float(w)}, "leg_bias": {}}
            ll = sum(_ll(opt.leg_p(pm, pk, o, mk.split("_")[0] if mk.startswith("over_under") else mk,
                                   float(mk.rsplit("_", 1)[1]) if mk.startswith("over_under") else 0.0, tmp), y)
                     for _, _, pm, pk, o, y, _ in xs) / len(xs)
            if ll < bl - 1e-9:
                best, bl = float(round(w, 2)), ll
        old = float(s["shrink_w"].get(mk, s["shrink_w"].get("default", 0.5)))
        if best is not None and abs(best - old) >= 0.1:
            new = round(old + 0.5 * (best - old), 2)  # pas pe jumătate (stabilitate)
            s["shrink_w"][mk] = new
            changes.append({"type": "ticket_shrink", "market": mk, "before": old, "after": new, "n": len(xs),
                            "why": f"Pe {len(xs)} selecții decontate, ponderea optimă a modelului față de piață e {best:.1f} (logloss {bl:.4f})"})
    # 2) corecții și blocări pe tip de selecție
    by_t: Dict[str, List] = defaultdict(list)
    for x in legs:
        by_t[x[1]].append(x)
    bias = dict(s.get("leg_bias") or {})
    blocked = set(s.get("blocked_leg_types") or [])
    for lt, xs in by_t.items():
        n = len(xs)
        if n < 40:
            continue
        mk, line = lt.split("|")[0], 0.0
        market = mk
        if mk.startswith("over_under_"):
            market, line = "over_under", float(mk.rsplit("_", 1)[1])
        ps = [opt.leg_p(pm, pk, o, market, line, {**s, "leg_bias": {}}) for _, _, pm, pk, o, _, _ in xs]
        hits = sum(x[5] for x in xs)
        exp = sum(ps) / n
        rate = hits / n
        raw = _intercept(ps, [x[5] for x in xs])  # corecția logit care minimizează logloss-ul (Newton)
        new_b = round(max(-0.6, min(0.4, raw * n / (n + BIAS_PRIOR_N))), 3)
        old_b = float(bias.get(lt, 0.0))
        if abs(new_b - old_b) >= 0.03:
            bias[lt] = new_b
            changes.append({"type": "leg_bias", "market": lt, "before": old_b, "after": new_b, "n": n,
                            "why": f"{lt}: câștigate {rate:.0%} vs promis {exp:.0%} pe {n} selecții → corecție {new_b:+.2f} (logit)"})
        p_worse = float(beta_dist.cdf(exp - 0.05, hits + 1, n - hits + 1))
        if p_worse > 0.9 and lt not in blocked:
            blocked.add(lt)
            changes.append({"type": "leg_block", "market": lt, "before": False, "after": True, "n": n,
                            "why": f"{lt} pică sistematic: {rate:.0%} câștigate vs {exp:.0%} promis (P={p_worse:.0%}) → exclus din bilete"})
        elif lt in blocked and p_worse < 0.5:
            blocked.discard(lt)
            changes.append({"type": "leg_unblock", "market": lt, "before": True, "after": False, "n": n,
                            "why": f"{lt} s-a recuperat: {rate:.0%} câștigate vs {exp:.0%} promis → readmis"})
    s["leg_bias"], s["blocked_leg_types"] = bias, sorted(blocked)
    # 3) ponderi variante (Thompson) + p minim pe nivel — din biletele reale + simulate
    rng = np.random.default_rng(5)
    sources = list((live_tickets or {}).get("_tickets", [])) + list((sim_res or {}).get("_tickets", []))
    vw = dict(s.get("variant_weights") or {})
    mlp = dict(s.get("min_leg_p") or {})
    for tier in TIERS:
        gaps: Dict[str, List[float]] = defaultdict(list)
        tier_legs = []
        for t in sources:
            if t["tier"] != tier or not t["legs"]:
                continue
            gaps[t["variant"]].append(float(np.mean([l[2] - l[1] for l in t["legs"]])))
            tier_legs += t["legs"]
        if sum(len(v) for v in gaps.values()) >= 20:
            draws = {}
            for v in VARIANTS:
                g = np.array(gaps.get(v, []))
                n0, m0, s0 = 5.0, 0.0, 0.15
                n = len(g)
                mean = (n0 * m0 + g.sum()) / (n0 + n)
                sd = math.sqrt((s0 ** 2 * n0 + (g.var() * n if n > 1 else 0)) / (n0 + n)) / math.sqrt(n0 + n)
                draws[v] = rng.normal(mean, sd, 4000)
            M = np.stack([draws[v] for v in VARIANTS])
            best = np.bincount(M.argmax(0), minlength=len(VARIANTS)) / M.shape[1]
            new_w = {v: round(float(0.1 + 0.9 * b), 3) for v, b in zip(VARIANTS, best)}
            old_w = vw.get(str(tier)) or {}
            if any(abs(new_w[v] - float(old_w.get(v, 0.325))) >= 0.05 for v in VARIANTS):
                vw[str(tier)] = new_w
                top = max(new_w, key=new_w.get)
                changes.append({"type": "variant_weights", "market": f"acca_{tier}", "before": old_w, "after": new_w,
                                "n": sum(len(v) for v in gaps.values()),
                                "why": f"Bilete ~{tier}: varianta „{top}” are selecțiile care depășesc cel mai des șansa promisă (bandit Thompson)"})
        if len(tier_legs) >= 60:
            gap = float(np.mean([l[2] - l[1] for l in tier_legs]))
            old = float(mlp.get(str(tier), opt.DEFAULT_STRATEGY["min_leg_p"][str(tier)]))
            base_p = opt.DEFAULT_STRATEGY["min_leg_p"][str(tier)]
            new = old
            if gap < -0.04:
                new = min(base_p + 0.10, old + 0.02)
            elif gap > 0.02:
                new = max(base_p - 0.04, old - 0.01)
            if abs(new - old) > 1e-9:
                mlp[str(tier)] = round(new, 3)
                changes.append({"type": "tier_min_p", "market": f"acca_{tier}", "before": old, "after": round(new, 3),
                                "n": len(tier_legs),
                                "why": f"Selecțiile biletelor ~{tier} au câștigat cu {gap * 100:+.1f}pp față de promis → p minim {old:.2f} → {new:.2f}"})
    s["variant_weights"], s["min_leg_p"] = vw, mlp
    return s, changes


def live_ticket_feedback(conn: sqlite3.Connection, since: str) -> Dict[str, Any]:
    """Biletele reale decontate (acca), în același format ca simularea."""
    rows = conn.execute(
        """SELECT t.id, t.kind, t.variant, t.total_odds, t.p_ticket, t.status, t.day,
                  tl.market AS lm, tl.odds AS lo, p.result AS pr, p.p_calibrated, p.p_market_novig, m.league_id, p.market, p.line
           FROM ticket t JOIN ticket_leg tl ON tl.ticket_id=t.id LEFT JOIN prediction p ON p.id=tl.prediction_id
           LEFT JOIN match m ON m.id=tl.match_id
           WHERE t.created_by='robot' AND t.kind LIKE 'acca_%' AND t.status IN ('won','lost') AND t.day >= ?""", (since,)).fetchall()
    by: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        try:
            tier = int(str(r["kind"]).split("_")[1])
        except (ValueError, IndexError):
            continue
        t = by.setdefault(r["id"], {"day": r["day"], "tier": tier, "variant": r["variant"], "odds": r["total_odds"] or 0,
                                    "p": r["p_ticket"] or 0, "won": r["status"] == "won", "lost_legs": 0,
                                    "profit": ((r["total_odds"] or 1) - 1) if r["status"] == "won" else -1.0, "legs": []})
        if r["pr"] in ("won", "lost") and r["p_calibrated"] is not None:
            pa = opt.leg_p(r["p_calibrated"], r["p_market_novig"], r["lo"], r["market"], r["line"] or 0.0)
            t["legs"].append((opt.leg_type(r["market"], r["line"] or 0.0, r["lo"]), pa, 1.0 if r["pr"] == "won" else 0.0, r["league_id"]))
            t["lost_legs"] += 1 if r["pr"] == "lost" else 0
    res = summarize([t for t in by.values() if t["tier"] in TIERS])
    # ce tip de selecție pică cel mai des în bilete
    lt: Dict[str, List[Tuple[float, float]]] = defaultdict(list)
    for t in by.values():
        for l in t["legs"]:
            lt[l[0]].append((l[1], l[2]))
    res["leg_types"] = sorted(({"type": k, "n": len(v), "hit": round(float(np.mean([y for _, y in v])), 3),
                                "promised": round(float(np.mean([p for p, _ in v])), 3)} for k, v in lt.items()),
                              key=lambda x: x["hit"] - x["promised"])[:12]
    return res


def _log(conn, change: Dict[str, Any]) -> None:
    from betpredict.store import repo

    conn.execute(
        "INSERT INTO learning_log(run_at, market, league_id, change_type, before, after, evidence_json) VALUES (?,?,?,?,?,?,?)",
        (repo.now_iso(), change.get("market"), None, change["type"], json.dumps(change.get("before"), ensure_ascii=False),
         json.dumps(change.get("after"), ensure_ascii=False),
         json.dumps({"n": change.get("n"), "why": change.get("why")}, ensure_ascii=False)))


def _strip(res: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return {k: v for k, v in res.items() if not k.startswith("_")} if res else None


def learn_tickets(conn: sqlite3.Connection, since: Optional[str] = None, rebuild_sim: bool = False, log=print) -> Dict[str, Any]:
    from betpredict.model.sim_rows import build_sim_rows, load_sim_rows, save_sim_rows
    from betpredict.robot import STATS_SINCE
    from betpredict.store import repo

    since = since or STATS_SINCE
    champ = opt.load_strategy(conn)
    rows = load_sim_rows(conn)
    if rebuild_sim or not rows:
        try:
            rows = build_sim_rows(conn, log=log)
            save_sim_rows(conn, rows)
        except Exception as exc:  # noqa: BLE001
            log(f"sim_rows indisponibil: {exc}")
            rows = rows or []
    pools = sim_pools(rows)
    live = live_ticket_feedback(conn, since)
    live_legs = _settled_legs(conn, since)
    legs = live_legs + _sim_legs(pools)
    res_champ = simulate(pools, champ) if pools else None
    chal, changes = propose(champ, legs, live, res_champ)
    res_chal = simulate(pools, chal) if pools else None
    # Campion vs challenger, fără scurgere: challenger-ul e reînvățat DOAR pe ferestrele vechi și comparat
    # pe ultimele ferestre (selecții + probabilitatea biletelor), apoi — dacă trece — promovat pe tot.
    holdout = holdout_check(champ, pools, live, res_champ) if changes else None
    a, b = (res_champ or {}).get("all", {}), (res_chal or {}).get("all", {})
    promote = bool(changes)
    why = "fără schimbări propuse"
    if changes and holdout:
        promote = holdout["ok"]
        why = holdout["why"]
        if promote and (a.get("n") or 0) >= 20 and (b.get("n") or 0) >= 20:
            roi_ok = (b.get("roi") or -1) >= (a.get("roi") or -1) - (a.get("se") or 0)
            promote = roi_ok
            why += f"; bilete simulate: ROI {a.get('roi')} → {b.get('roi')} (±{a.get('se')}, n={b.get('n')})"
    elif changes:
        promote = len(live_legs) >= 300
        why = (f"fără istoric simulabil — schimbări bazate pe {len(live_legs)} selecții reale decontate"
               if promote else f"prea puține date ({len(live_legs)} selecții reale) — campionul rămâne")
    with conn:
        if promote:
            chal["version"] = int(champ.get("version", 1)) + 1
            for ch in changes:
                _log(conn, ch)
        _log(conn, {"type": "ticket_strategy", "market": None, "before": champ.get("version"),
                    "after": chal.get("version") if promote else champ.get("version"), "n": len(changes),
                    "why": ("Strategie nouă promovată: " if promote else "Strategia campion păstrată: ") + why})
        repo.set_state(conn, "tickets.learning", json.dumps({
            "run_at": repo.now_iso(), "promoted": promote, "why": why, "changes": changes,
            "live": _strip(live), "sim_champion": _strip(res_champ), "sim_challenger": _strip(res_chal),
            "holdout": holdout,
            "sim_matches": len(rows)}, ensure_ascii=False, default=float))
    if promote:
        opt.save_strategy(conn, chal)
    else:
        opt.use_strategy(champ)
    return {"promoted": promote, "why": why, "changes": len(changes), "sim_champion": _strip(res_champ and {**res_champ, "by_variant": None}),
            "sim_challenger": _strip(res_chal and {**res_chal, "by_variant": None})}


def _leg_ll(st: Dict[str, Any], legs) -> float:
    if not legs:
        return float("nan")
    tot = 0.0
    for mk, _, pm, pk, o, y, _ in legs:
        market, line = mk, 0.0
        if mk.startswith("over_under_"):
            market, line = "over_under", float(mk.rsplit("_", 1)[1])
        tot += _ll(opt.leg_p(pm, pk, o, market, line, st), y)
    return tot / len(legs)


def holdout_check(champ: Dict[str, Any], pools: Dict[str, List[Any]], live: Dict[str, Any], res_champ,
                  n_hold: int = 3) -> Optional[Dict[str, Any]]:
    """Challenger învățat pe ferestrele vechi vs campion, pe ultimele ``n_hold`` ferestre."""
    ks = sorted(pools)
    if len(ks) < n_hold + 2:
        return None
    tr = {k: pools[k] for k in ks[:-n_hold]}
    te = {k: pools[k] for k in ks[-n_hold:]}
    opt.use_strategy(champ)
    chal_tr, _ = propose(champ, _sim_legs(tr), live, res_champ)
    te_legs = _sim_legs(te)
    la, lb = _leg_ll(champ, te_legs), _leg_ll(chal_tr, te_legs)
    ca, cb = ticket_calibration(te, champ, n_tickets=1500), ticket_calibration(te, chal_tr, n_tickets=1500)
    opt.use_strategy(champ)
    ta, tb = ca.get("ll_mc"), cb.get("ll_mc")
    ok = lb <= la + 5e-4 and (ta is None or tb is None or tb <= ta + 5e-4)
    why = (f"test pe ultimele {n_hold} săptămâni ({len(te_legs)} selecții): logloss selecții {la:.4f} → {lb:.4f}; "
           f"bilete aleatoare: câștigate {cb.get('won')} vs promise {ca.get('exp_mc')} → {cb.get('exp_mc')}, "
           f"logloss {ta} → {tb}")
    return {"ok": bool(ok), "why": why, "leg_ll": [round(la, 5), round(lb, 5)], "calib_champion": ca, "calib_challenger": cb}


def tickets_learning_doc(conn: sqlite3.Connection) -> Optional[Dict[str, Any]]:
    r = conn.execute("SELECT value FROM ingest_state WHERE key='tickets.learning'").fetchone()
    doc = json.loads(r[0]) if r else None
    if doc is not None:
        doc["strategy"] = {k: v for k, v in opt.load_strategy(conn).items() if k != "sigma"}
    return doc
