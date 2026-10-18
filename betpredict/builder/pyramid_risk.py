"""Piramide riscante ~5 și ~10: 2–4 selecții, EV realist ≥ 0, doar piețe sănătoase.

Fără oprire automată după pierderi. În locul ei, reorganizare adaptivă după fiecare pierdere:
- piețele și ligile sunt reclasate după calibrarea și ROI-ul recent (ultimele 30 de zile decontate);
- se schimbă amestecul de selecții (familia de piață a biletului pierdut e evitată la pasul următor);
- ținta de cotă se mută în interiorul benzii (spre capătul de jos după pierderi, spre cel de sus după câștiguri);
- seria se reia de la treapta 1 cu miza mică fixă din bugetul săptămânal (1–2 lei). Niciodată martingale:
  miza de start nu crește după pierderi.
"""

from __future__ import annotations

import itertools
import math
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from betpredict.builder import pyramid as P
from betpredict.builder.pool import Cand

BASE = {"start_bank": 2.0, "profit_withdraw_pct": 0.0, "withdraw_steps": [], "withdraw_pct": 0.0,
        "target_multiple": 10**9, "target_withdraw_pct": 0.0, "pause_after_losses": 0,
        "min_legs": 2, "max_legs": 4, "min_ev": 0.0, "leg_odds": [1.25, 4.5], "leg_min_p": 0.25}
RULES_R5: Dict[str, Any] = {**BASE, "target_odds": 5.0, "band": [4.0, 6.5], "max_steps": 3, "variant": "pr5", "alt_variant": "pr5_alt"}
RULES_R10: Dict[str, Any] = {**BASE, "target_odds": 10.0, "band": [8.0, 13.0], "max_steps": 2, "variant": "pr10", "alt_variant": "pr10_alt"}
KEY_R5, KEY_R10 = "pyramidr5.day.", "pyramidr10.day."
SCORE_DAYS, SCORE_MIN_N, SCORE_FLOOR = 30, 30, -0.08


def family(market: str) -> str:
    return (market or "").split("|")[0]


def recent_scores(conn: sqlite3.Connection, before: str, days: int = SCORE_DAYS) -> Dict[str, Dict[str, float]]:
    """Scor = ROI recent (micșorat spre −5%) + abaterea de calibrare (realizat − p). Pe familie de piață și pe ligă."""
    lo = (datetime.fromisoformat(before[:10]) - timedelta(days=days)).date().isoformat()
    rows = conn.execute(
        """SELECT p.market, m.league_id, p.p_calibrated, p.odds_shown, p.result FROM prediction p JOIN match m ON m.id=p.match_id
           WHERE p.result IN ('won','lost') AND p.odds_shown > 1 AND p.p_calibrated IS NOT NULL AND m.kickoff_utc >= ? AND m.kickoff_utc < ?""",
        (lo, before)).fetchall()
    out: Dict[str, Dict[str, float]] = {"market": {}, "league": {}}
    agg: Dict[Tuple[str, Any], List[float]] = {}
    for mk, lg, p, o, r in rows:
        w = 1.0 if r == "won" else 0.0
        for key in (("market", family(mk)), ("league", lg)):
            a = agg.setdefault(key, [0, 0.0, 0.0, 0.0])
            a[0] += 1; a[1] += w; a[2] += p; a[3] += (o - 1) if w else -1
    for (kind, k), (n, w, p, pl) in agg.items():
        if n >= SCORE_MIN_N:
            out[kind][str(k)] = round((pl + 30 * -0.05) / (n + 30) + (w - p) / n, 4)
    return out


def adapt(conn: sqlite3.Connection, rules: Dict[str, Any], day: date) -> Dict[str, Any]:
    """Starea adaptivă din ultimele bilete decontate ale pistei: țintă în bandă și familia de evitat."""
    last = conn.execute("SELECT id, status FROM ticket WHERE kind='pyramid' AND variant=? AND status IN ('won','lost') AND day < ? "
                        "ORDER BY day DESC, id DESC LIMIT 4", (rules["variant"], day.isoformat())).fetchall()
    losses = 0
    for r in last:
        if r[1] != "lost":
            break
        losses += 1
    lo, hi = rules["band"]
    t = rules["target_odds"]
    if losses:
        t = max(lo, t * (0.9 ** min(losses, 3)))        # după pierderi: ținta coboară în bandă
    elif last and last[0][1] == "won":
        t = min(hi, t * 1.1)
    avoid: List[str] = []
    if losses and last:
        avoid = sorted({family(x[0]) for x in conn.execute("SELECT market FROM ticket_leg WHERE ticket_id=?", (last[0][0],))})
    return {"losses": losses, "target": round(t, 2), "band": [round(max(lo, t * 0.85), 2), round(min(hi, t * 1.2), 2)], "avoid": avoid}


def pick(pool: List[Cand], rules: Dict[str, Any], scores: Dict[str, Dict[str, float]], st: Dict[str, Any]) -> Dict[str, Any]:
    lo, hi = st["band"]
    llo, lhi = rules["leg_odds"]
    paused = set(st.get("paused") or [])

    def score(c: Cand) -> float:
        return scores["market"].get(family(c.market), 0.0) + scores["league"].get(str(c.league_id), 0.0)

    per: Dict[int, Cand] = {}
    for c in pool:
        if not (c.playable and llo <= c.odds <= lhi and c.p_honest >= rules["leg_min_p"]):
            continue
        if family(c.market) in st["avoid"] or f"{c.market}|{c.line:g}" in paused or c.market in paused:
            continue
        if score(c) < SCORE_FLOOR:  # piață/ligă cu calibrare + ROI recent slab
            continue
        b = per.get(c.match_id)
        if b is None or (c.ev_honest + score(c)) > (b.ev_honest + score(b)):
            per[c.match_id] = c
    cands = sorted(per.values(), key=lambda c: c.ev_honest + score(c), reverse=True)[:16]
    combos = []
    for k in range(rules["min_legs"], rules["max_legs"] + 1):
        for cb in itertools.combinations(cands, k):
            if not P.one_league_each(cb):
                continue
            o = math.prod(c.odds for c in cb)
            if not (lo <= o <= hi):
                continue
            p = math.prod(c.p_honest for c in cb)
            ev = p * o - 1
            if ev < rules["min_ev"]:
                continue
            # cele mai bune selecții: EV realist + scorul recent, penalizare mică pe selecție în plus, aproape de țintă
            combos.append((list(cb), p, ev + sum(score(c) for c in cb) / k - 0.02 * (k - 2) - 0.05 * abs(math.log(o / st["target"]))))
    combos.sort(key=lambda x: x[2], reverse=True)
    name = f"~{rules['target_odds']:g}"
    if not combos:
        return {"status": "no_bet", "main": None, "alternatives": [],
                "reason": f"Azi fără Piramida {name}: nicio combinație de 2–4 selecții cu EV realist ≥ 0 pe piețe sănătoase în cota {lo:g}–{hi:g}."}
    main, p_main, _ = combos[0]
    o = math.prod(c.odds for c in main)
    why = f"{len(main)} selecții, cotă {o:.2f}, șansă realistă {p_main:.0%}, EV {p_main * o - 1:+.1%}"
    if st["losses"]:
        why += f" · reorganizată după {st['losses']} {'pierdere' if st['losses'] == 1 else 'pierderi'}: țintă {st['target']:g}" + (f", fără {', '.join(st['avoid'])}" if st["avoid"] else "")
    return {"status": "pick", "main": (main, p_main), "alternatives": [], "reason": why}


def _paused(conn: sqlite3.Connection) -> List[str]:
    try:
        return [r[0] for r in conn.execute("SELECT mkey FROM market_state WHERE status='paused'")]
    except sqlite3.Error:
        return []


def build_day(conn: sqlite3.Connection, day: date, now: Optional[datetime], rules: Dict[str, Any], prefix: str, key: str) -> Dict[str, Any]:
    st = {**adapt(conn, rules, day), "paused": _paused(conn)}
    scores = recent_scores(conn, (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"))

    def picker(pool, r):
        return pick(pool, r, scores, st)
    out = P._build_track_day(conn, day, now, False, prefix, key, rules, picker, rules["variant"])
    out["adapt"] = {k: st[k] for k in ("losses", "target", "band", "avoid")}
    return out


def build_r5_day(conn, day, now=None):
    return build_day(conn, day, now, RULES_R5, "pyramidr5", KEY_R5)


def build_r10_day(conn, day, now=None):
    return build_day(conn, day, now, RULES_R10, "pyramidr10", KEY_R10)
