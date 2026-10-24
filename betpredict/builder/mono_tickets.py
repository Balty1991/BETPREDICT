"""Biletele Robotului „O singură piață”: ca biletele de cotă ~100 de pe Supersocial, fiecare bilet are o singură piață
(R1 cornere 3-6, A doua repriză 1-3 goluri, Gol în ambele reprize) pe 8–16 meciuri.

Meciurile se aleg acolo unde piața iese cel mai des: șansa Robotului pe meci, combinată cu cât de des a ieșit piața în
liga respectivă (rezultate reale, trase spre media generală când liga are puține meciuri). Urmărite pe hârtie (miză 0.1u),
ca să vedem pe rezultate reale dacă stilul ăsta prinde bilete."""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from betpredict.store import repo
from betpredict.timeutil import canon_utc

KIND = "acca_mono"
MARKETS = (("BB_H1C25_U65", "R1 cornere 3-6", "mono_r1c36"), ("H2G13", "A doua repriză 1-3 goluri", "mono_h2g13"),
           ("R1R2", "Gol în ambele reprize", "mono_r1r2"))
TARGET, MIN_TOTAL = 100.0, 70.0  # cota țintă; sub 70 biletul nu se face
LEGS = (8, 16)
LEG_ODDS = (1.15, 2.20)
MAX_PER_LEAGUE = 3
LEAGUE_K = 30.0      # câte meciuri „valorează” media generală la o ligă (micșorare spre medie)
LEAGUE_DAYS = 120
STAKE_U = 0.1


def league_rates(conn: sqlite3.Connection, key: str, now: datetime) -> Tuple[Dict[Any, float], float]:
    """Cât de des a ieșit piața pe ligă (micșorat spre media generală), din meciurile terminate recente."""
    from betpredict.experimental.supersocial import _settle_result

    since = canon_utc((now - timedelta(days=LEAGUE_DAYS)).isoformat())
    too_old = canon_utc(now.isoformat())
    by: Dict[Any, List[int]] = {}
    for m in conn.execute("""SELECT * FROM match WHERE status='finished' AND kickoff_utc >= ? AND ft_home IS NOT NULL
                             AND ht_home IS NOT NULL""", (since,)):
        try:
            res = _settle_result(key, m, too_old)
        except (KeyError, TypeError, IndexError):
            res = None
        if res in ("won", "lost"):
            by.setdefault(m["league_id"], []).append(res == "won")
    allv = [x for v in by.values() for x in v]
    base = sum(allv) / len(allv) if allv else 0.6
    return {lg: (sum(v) + LEAGUE_K * base) / (len(v) + LEAGUE_K) for lg, v in by.items()}, base


def _pick(pool: List[Dict[str, Any]], banned: set) -> Optional[List[Dict[str, Any]]]:
    legs: List[Dict[str, Any]] = []
    leagues: Dict[Any, int] = {}
    for c in sorted(pool, key=lambda c: -c["score"]):
        if c["match_id"] in banned or any(l["match_id"] == c["match_id"] for l in legs):
            continue
        if leagues.get(c["league_id"], 0) >= MAX_PER_LEAGUE:
            continue
        legs.append(c)
        leagues[c["league_id"]] = leagues.get(c["league_id"], 0) + 1
        total = math.prod(l["odds"] for l in legs)
        if total >= TARGET and len(legs) >= LEGS[0] or len(legs) >= LEGS[1]:
            break
    total = math.prod(l["odds"] for l in legs) if legs else 0
    return legs if len(legs) >= LEGS[0] and total >= MIN_TOTAL else None


def build(conn: sqlite3.Connection, today: date, now: Optional[datetime] = None, rows: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    have = {r[0] for r in conn.execute("SELECT variant FROM ticket WHERE kind=? AND day=? AND status!='replaced'", (KIND, today.isoformat()))}
    if len(have) >= len(MARKETS):
        return {"skipped_existing": len(have)}
    if rows is None:
        from betpredict.experimental.supersocial import today_doc

        rows = today_doc(conn, now)["rows"]
    soon = canon_utc((now + timedelta(minutes=10)).isoformat())
    until = (today + timedelta(days=1)).isoformat() + "T23:59:59Z"
    made, skipped = [], []
    with conn:
        for key, name, variant in MARKETS:
            if variant in have:
                continue
            rates, base = league_rates(conn, key, now)
            pool = []
            for r in rows:
                if r["key"] != key or r.get("suspect") or not r.get("odds") or not LEG_ODDS[0] <= r["odds"] <= LEG_ODDS[1]:
                    continue
                if not soon < (r.get("kickoff_utc") or "") <= until:
                    continue
                lg = rates.get(r.get("league_id"), base)
                pool.append({**r, "league_rate": lg, "score": 0.5 * r["p"] + 0.5 * lg})
            legs = _pick(pool, set())
            if not legs:
                skipped.append({"key": key, "pool": len(pool)})
                continue
            total = math.prod(l["odds"] for l in legs)
            p = math.prod(min(0.99, 0.5 * l["p"] + 0.5 * l["league_rate"]) for l in legs)
            notes = {"label": f"O singură piață · {name}", "mono": True, "paper": True, "risk_acknowledged": True,
                     "reasons": [f"{len(legs)} meciuri, aceeași piață: {name}, ca biletele de cotă ~100 de pe Supersocial.",
                                 "Meciurile unde piața iese cel mai des: șansa Robotului pe meci și cât de des a ieșit în ligă.",
                                 f"Șansa estimată pentru tot biletul: {p:.1%} · cotă {total:.2f}. Miză {STAKE_U:g}u (urmărit pe hârtie)."]}
            cur = conn.execute(
                """INSERT INTO ticket (kind, variant, created_by, target_odds, total_odds, p_ticket, ev, stake, status, created_at, notes, day)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (KIND, variant, "robot", TARGET, round(total, 2), round(p, 6), round(p * total - 1, 4), STAKE_U, "pending",
                 repo.now_iso(), json.dumps(notes, ensure_ascii=False), today.isoformat()))
            for l in sorted(legs, key=lambda l: l["kickoff_utc"]):
                conn.execute("INSERT INTO ticket_leg (ticket_id, prediction_id, match_id, market, selection, odds, odds_source) VALUES (?,?,?,?,?,?,?)",
                             (cur.lastrowid, None, l["match_id"], "ss|0", key, l["odds"], "superbet"))
            made.append({"key": key, "legs": len(legs), "odds": round(total, 2), "p": round(p, 4)})
    return {"tickets": made, "skipped": skipped}
