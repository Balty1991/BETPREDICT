"""Autoînvățare zilnică (rulează în modul ``daily``, o dată pe zi, idempotent) + secțiunea „Ce a învățat Robotul”.

1. **Recalibrare zilnică** pe predicțiile decontate (ultimele 90 de zile): corecție logit (bias) pe piață, apoi
   rezidualul pe grup de ligi × piață, ambele micșorate bayesian (n/(n+K)) și plafonate. Se aplică DUPĂ
   calibrarea Platt săptămânală (``robot.params.calibrate``) — p-ul dinainte (``p_cal0``) e salvat în reasons_json,
   deci recalibrarea nu se „autoalimentează”.
2. **Segmente ligă × piață** (CLV Pinnacle + ROI, cu prag de semnificație și histerezis, ``segments.learn_segments``)
   reevaluate zilnic, nu doar luni.
3. **Auto-tuning bilete** (Biletul zilei, Piramida, Super bilete) din selecțiile biletelor decontate: dacă
   selecțiile câștigă semnificativ sub șansa promisă (z ≤ −1.64, n ≥ 40), pragul minim de șansă pe selecție crește
   cu 2 pp; dacă sunt în linie sau peste (n ≥ 80), revine treptat (−1 pp) spre valoarea implicită. Limite stricte.

Orice schimbare intră în ``learning_log`` (cu motivul ei); fără schimbare nu se scrie nimic.
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from betpredict.robot.params import load_params, logit, save_params, sigmoid
from betpredict.store import repo

STATE_KEY = "selflearn.daily"
RECAL_DAYS = 90
K_MARKET = 200.0     # prior: 200 de selecții fără bias
K_GROUP = 300.0
B_CAP = 0.35         # |bias logit| maxim (~±8 pp în jurul lui 50%)
MIN_N_MARKET = 40
MIN_N_GROUP = 40
LOG_DELTA = 0.02     # logăm doar schimbări ≥ 0.02 în logit

# auto-tuning bilete: (implicit, minim, maxim)
TUNE_SPECS: Dict[str, Dict[str, Tuple[float, float, float]]] = {
    "biletul_zilei": {"leg_p": (0.70, 0.66, 0.82)},
    "pyramid": {"min_p": (0.45, 0.42, 0.60)},
    "super": {"min_leg_p": (0.0, 0.0, 0.85)},
}
TUNE_MIN_N, TUNE_OK_N, TUNE_Z = 40, 80, -1.645
TUNE_DAYS = 60


# ------------------------------------------------------------------ aplicare (folosit de Robot și buildere)
def recal_apply(params: Dict[str, Any], mkey: str, league_id: Any, p: float) -> float:
    rc = params.get("daily_recal") or {}
    b = float(((rc.get("market") or {}).get(mkey) or {}).get("b", 0.0))
    if league_id is not None and rc.get("group"):
        try:
            from betpredict.segments import group_key

            b += float((rc["group"].get(group_key(league_id, mkey)) or {}).get("b", 0.0))
        except Exception:  # noqa: BLE001
            pass
    if not b:
        return p
    return sigmoid(logit(p) + max(-B_CAP, min(B_CAP, b)))


def tuned(name: str, key: str, default: float, params: Optional[Dict[str, Any]] = None) -> float:
    """Valoarea auto-tunată (sau implicită). ``params`` lipsă → cea activată de ``activate``."""
    src = params if params is not None else _ACTIVE
    v = ((src or {}).get("ticket_tuning") or {}).get(name, {}).get(key)
    return default if v is None else float(v)


_ACTIVE: Dict[str, Any] = {}


def activate(conn: sqlite3.Connection) -> None:
    global _ACTIVE
    try:
        _ACTIVE = load_params(conn)
    except Exception:  # noqa: BLE001
        _ACTIVE = {}


# ------------------------------------------------------------------ fit
def _bias(pairs: List[Tuple[float, float]], offs: Optional[List[float]] = None, iters: int = 30) -> float:
    """Intercept logit (pantă 1) maxim-verosimil: Σ σ(logit p + off + b) = Σ y."""
    xs = [logit(p) + (offs[i] if offs else 0.0) for i, (p, _) in enumerate(pairs)]
    ys = [y for _, y in pairs]
    b = 0.0
    for _ in range(iters):
        q = [sigmoid(x + b) for x in xs]
        g = sum(qi - yi for qi, yi in zip(q, ys))
        h = sum(qi * (1 - qi) for qi in q) + 1e-6
        step = g / h
        b -= max(-1.0, min(1.0, step))
        if abs(step) < 1e-7:
            break
    return b


def _p0(r) -> Optional[float]:
    try:
        ex = json.loads(r["reasons_json"] or "{}")
    except (ValueError, TypeError):
        ex = {}
    p = ex.get("p_cal0", r["p_calibrated"])
    return float(p) if p is not None else None


def fit_recal(rows) -> Dict[str, Any]:
    from betpredict.robot.markets import market_key
    from betpredict.segments import group_key

    by_m: Dict[str, List] = defaultdict(list)
    for r in rows:
        p = _p0(r)
        if p is None or r["result"] not in ("won", "lost"):
            continue
        by_m[market_key(r["market"], r["line"] or 0.0)].append((r, min(0.995, max(0.005, p)), 1.0 if r["result"] == "won" else 0.0))
    out: Dict[str, Any] = {"market": {}, "group": {}}
    for mk, xs in by_m.items():
        if len(xs) < MIN_N_MARKET:
            continue
        n = len(xs)
        b = _bias([(p, y) for _, p, y in xs]) * n / (n + K_MARKET)
        b = max(-B_CAP, min(B_CAP, b))
        out["market"][mk] = {"b": round(b, 4), "n": n}
        by_g: Dict[str, List] = defaultdict(list)
        for r, p, y in xs:
            if r["league_id"] is not None:
                by_g[group_key(r["league_id"], mk)].append((p, y))
        for gk, ps in by_g.items():
            if len(ps) < MIN_N_GROUP:
                continue
            ng = len(ps)
            bg = _bias(ps, [b] * ng) * ng / (ng + K_GROUP)
            out["group"][gk] = {"b": round(max(-B_CAP, min(B_CAP, bg)), 4), "n": ng}
    return out


def tune_tickets(conn: sqlite3.Connection, params: Dict[str, Any], today: date) -> List[Dict[str, Any]]:
    """Ajustează pragurile builderelor din selecțiile biletelor decontate (șansă promisă vs. rată reală)."""
    since = (today - timedelta(days=TUNE_DAYS)).isoformat()
    sel = {"biletul_zilei": "t.variant LIKE 'biletul_zilei%'", "pyramid": "t.kind = 'pyramid'",
           "super": "t.variant LIKE 'super%'"}
    cur = dict(params.get("ticket_tuning") or {})
    changes = []
    for name, where in sel.items():
        try:
            legs = conn.execute(
                f"""SELECT p.p_calibrated p, p.result FROM ticket t JOIN ticket_leg l ON l.ticket_id = t.id
                    JOIN prediction p ON p.id = l.prediction_id
                    WHERE t.created_by = 'robot' AND t.status != 'replaced' AND {where} AND t.day >= ?
                      AND p.result IN ('won','lost') AND p.p_calibrated IS NOT NULL""", (since,)).fetchall()
        except sqlite3.Error:
            continue
        n = len(legs)
        (key, (dflt, lo, hi)), = TUNE_SPECS[name].items()
        before = (cur.get(name) or {}).get(key)
        base = dflt if before is None else before
        if n < TUNE_MIN_N:
            continue
        exp = sum(r["p"] for r in legs)
        won = sum(r["result"] == "won" for r in legs)
        var = sum(r["p"] * (1 - r["p"]) for r in legs) or 1e-9
        z = (won - exp) / math.sqrt(var)
        avg_p = exp / n
        if z <= TUNE_Z:
            new = min(hi, max(base, avg_p if name == "super" else base) + 0.02)
            why = f"selecțiile au câștigat {won}/{n} față de {exp:.0f} promise (z={z:.2f}) → prag mai strict"
        elif n >= TUNE_OK_N and z > -0.5 and base > dflt:
            new = max(dflt, base - 0.01)
            why = f"selecțiile sunt în linie: {won}/{n} vs {exp:.0f} promise (z={z:.2f}) → revine spre {dflt:.2f}"
        else:
            continue
        new = round(max(lo, min(hi, new)), 3)
        if before is not None and abs(new - before) < 1e-9 or (before is None and abs(new - dflt) < 1e-9):
            continue
        cur.setdefault(name, {})[key] = new
        cur[name]["evidence"] = {"n": n, "won": won, "expected": round(exp, 1), "z": round(z, 2)}
        _log(conn, "ticket_tuning", name, {key: base}, {key: new}, {"n": n, "won": won, "expected": round(exp, 1), "z": round(z, 2), "why": why})
        changes.append({"type": "ticket_tuning", "name": name, "key": key, "before": base, "after": new})
    params["ticket_tuning"] = cur
    return changes


def _log(conn, ct, market, before, after, evidence, league_id=None):
    conn.execute(
        "INSERT INTO learning_log(run_at, market, league_id, change_type, before, after, evidence_json) VALUES (?,?,?,?,?,?,?)",
        (repo.now_iso(), market, league_id, ct, json.dumps(before, ensure_ascii=False),
         json.dumps(after, ensure_ascii=False), json.dumps(evidence, ensure_ascii=False)))


def daily_learn(conn: sqlite3.Connection, today: date, force: bool = False) -> Dict[str, Any]:
    """O dată pe zi (cheie de stare pe dată): recalibrare, segmente, auto-tuning bilete. Rulări repetate = no-op."""
    from betpredict.robot import MODEL_VERSION

    done = repo.get_state(conn, STATE_KEY)
    if done == today.isoformat() and not force:
        return {"skipped": "already_ran_today"}
    params = load_params(conn)
    since = (today - timedelta(days=RECAL_DAYS)).isoformat()
    rows = conn.execute(
        """SELECT p.market, p.line, p.result, p.p_calibrated, p.reasons_json, m.league_id FROM prediction p
           JOIN match m ON m.id = p.match_id
           WHERE p.model_version = ? AND p.shown_on_page = 'predictii' AND p.result IN ('won','lost') AND p.day >= ?""",
        (MODEL_VERSION, since)).fetchall()
    changes: List[Dict[str, Any]] = []
    with conn:
        new = fit_recal(rows)
        old = params.get("daily_recal") or {}
        for lvl in ("market", "group"):
            o, nw = old.get(lvl) or {}, new[lvl]
            for k in sorted(set(o) | set(nw)):
                b0, b1 = (o.get(k) or {}).get("b", 0.0), (nw.get(k) or {}).get("b", 0.0)
                if abs(b1 - b0) >= LOG_DELTA:
                    n = (nw.get(k) or {}).get("n", 0)
                    _log(conn, "daily_recal", k, b0, b1, {"n": n, "level": lvl,
                         "why": f"{k}: corecție logit {b0:+.2f} → {b1:+.2f} pe {n} rezultate (micșorată spre 0)"})
                    changes.append({"type": "daily_recal", "key": k, "before": b0, "after": b1})
        params["daily_recal"] = {**new, "fitted_on": today.isoformat(), "n": len(rows)}
        try:
            from betpredict.robot import STATS_SINCE
            from betpredict.segments import learn_segments

            changes += learn_segments(conn, params, STATS_SINCE,
                                      lambda ct, mk, b, a, ev, lid=None: _log(conn, ct, mk, b, a, ev, league_id=lid))
        except Exception as exc:  # noqa: BLE001
            changes.append({"type": "segments_error", "error": str(exc)})
        changes += tune_tickets(conn, params, today)
    save_params(conn, params)
    with conn:
        repo.set_state(conn, STATE_KEY, today.isoformat())
    activate(conn)
    return {"samples": len(rows), "recal_markets": len(new["market"]), "recal_groups": len(new["group"]),
            "changes": changes}


# ------------------------------------------------------------------ raport „Ce a învățat Robotul”
def _week_metrics(conn: sqlite3.Connection, start: date, end: date) -> Dict[str, Any]:
    from betpredict.robot import MODEL_VERSION

    rs = conn.execute(
        """SELECT p_calibrated p, result, clv, profit_1u, is_pick FROM prediction WHERE model_version = ? AND shown_on_page = 'predictii'
           AND day >= ? AND day <= ? AND result IN ('won','lost')""", (MODEL_VERSION, start.isoformat(), end.isoformat())).fetchall()
    ps = [(r["p"], 1.0 if r["result"] == "won" else 0.0) for r in rs if r["p"] is not None]
    ll = sum(-(y * math.log(max(1e-6, p)) + (1 - y) * math.log(max(1e-6, 1 - p))) for p, y in ps) / len(ps) if ps else None
    br = sum((p - y) ** 2 for p, y in ps) / len(ps) if ps else None
    cl = [r["clv"] for r in rs if r["clv"] is not None]
    pk = [r["profit_1u"] for r in rs if r["is_pick"] and r["profit_1u"] is not None]
    return {"week_from": start.isoformat(), "n": len(ps), "logloss": round(ll, 4) if ll is not None else None,
            "brier": round(br, 4) if br is not None else None, "clv": round(sum(cl) / len(cl), 4) if cl else None, "clv_n": len(cl),
            "roi_picks": round(sum(pk) / len(pk), 4) if pk else None, "picks": len(pk)}


def learned_section(conn: sqlite3.Connection, start: date, end: date, weeks: int = 6) -> Dict[str, Any]:
    """Secțiunea „Ce a învățat Robotul” din raportul săptămânal (schimbări, segmente, tendința metricilor)."""
    rows = conn.execute(
        """SELECT run_at, change_type, market, league_id, before, after, evidence_json FROM learning_log
           WHERE change_type != 'legacy_performance_snapshot' AND run_at >= ? AND run_at < ? ORDER BY id""",
        (start.isoformat(), (end + timedelta(days=2)).isoformat())).fetchall()
    counts: Dict[str, int] = defaultdict(int)
    blocked, promoted, tuning, champion, items = [], [], [], None, []
    for r in rows:
        ev = json.loads(r["evidence_json"] or "{}") or {}
        counts[r["change_type"]] += 1
        after = json.loads(r["after"]) if r["after"] else None
        if r["change_type"] == "segment":
            (blocked if after == "oprit" else promoted if after == "întărit" else items).append(ev.get("why") or r["market"])
        elif r["change_type"] == "ticket_tuning":
            tuning.append(ev.get("why") and f"{r['market']}: {ev['why']}")
        elif r["change_type"] == "champion_cycle":
            champion = {"promoted": bool(ev.get("promoted")), "champion_holdout": ev.get("champion_holdout"),
                        "challenger_holdout": ev.get("challenger_holdout")}
        elif ev.get("why"):
            items.append(ev["why"])
    trend = [_week_metrics(conn, end - timedelta(days=7 * k + 6), end - timedelta(days=7 * k)) for k in range(weeks - 1, -1, -1)]
    lls = [t["logloss"] for t in trend if t["logloss"] is not None]
    direction = None
    if len(lls) >= 2:
        direction = "mai bun" if lls[-1] < lls[0] - 0.005 else "mai slab" if lls[-1] > lls[0] + 0.005 else "stabil"
    total = sum(counts.values())
    summary = (f"{total} ajustări automate: {counts.get('daily_recal', 0)} recalibrări, {len(blocked)} segmente oprite, "
               f"{len(promoted)} întărite, {len(tuning)} reglaje de bilete"
               + (f"; model nou promovat" if champion and champion["promoted"] else "; campionul a rămas" if champion else "")
               + (f"; precizia (logloss) e {direction} față de acum {len(trend) - 1} săptămâni" if direction else ""))
    return {"title": "Ce a învățat Robotul", "summary": summary, "change_counts": dict(counts),
            "segments_blocked": blocked[:15], "segments_promoted": promoted[:15], "ticket_tuning": [t for t in tuning if t][:10],
            "champion": champion, "changes": items[-15:], "metrics_trend": trend, "logloss_direction": direction}
