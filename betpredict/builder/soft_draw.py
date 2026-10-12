"""Egaluri la care Superbet e mai scump decât mediana pieței.

Regula a fost aleasă pe istoric Bet365 (cotă 2,80–3,60, cu cel puțin 2% peste media pieței)
și verificată pe sezoanele 2022/23–2024/25. Aici se aplică aceleași praguri pe cota
jucabilă Superbet față de mediana BSD. Nu e o garanție: proba nu a fost pe Superbet.

Biletul are exact două meciuri din aceeași zi. Mai lung nu a acoperit seria.
"""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from betpredict.store import repo
from betpredict.timeutil import canon_utc, ro_date_of

KIND, VARIANT = "acca_soft", "egal_superbet"
STAKE_U = 0.05
ODDS_LO, ODDS_HI = 2.80, 3.60
MIN_GAP = 0.02
HORIZON_H = 24 * 7
MAX_DAYS = 7


def _gap(odds: float, median: float) -> float:
    return odds / median - 1.0


def candidates(conn: sqlite3.Connection, now: Optional[datetime] = None, horizon_h: int = HORIZON_H) -> List[Dict[str, Any]]:
    """Meciuri viitoare la care egalul Superbet e în bandă și cu cel puțin 2% peste mediană."""
    from betpredict.store.repo import latest_odds, market_key

    now = now or datetime.now(timezone.utc)
    lo, hi = canon_utc(now.isoformat()), canon_utc((now + timedelta(hours=horizon_h)).isoformat())
    rows = conn.execute(
        """SELECT m.id, m.kickoff_utc, m.home_name, m.away_name, l.name AS league, x.ext_id AS sb_id
           FROM match m LEFT JOIN league l ON l.id = m.league_id
           LEFT JOIN ext_event x ON x.match_id = m.id AND x.source = 'superbet'
           WHERE m.kickoff_utc > ? AND m.kickoff_utc <= ?
             AND (m.status IS NULL OR m.status IN ('notstarted', 'upcoming', 'scheduled'))
           ORDER BY m.kickoff_utc""",
        (lo, hi)).fetchall()
    if not rows:
        return []
    ids = [r["id"] for r in rows]
    key = market_key("1x2", 0.0, "FT")
    sb = latest_odds(conn, ids, "superbet")
    med = latest_odds(conn, ids, "bsd_consensus")
    out = []
    for r in rows:
        odds = ((sb.get(r["id"]) or {}).get(key) or {}).get("DRAW")
        mid = ((med.get(r["id"]) or {}).get(key) or {}).get("DRAW")
        if not odds or not mid or mid <= 1 or not (ODDS_LO <= odds < ODDS_HI):
            continue
        gap = _gap(odds, mid)
        if gap < MIN_GAP:
            continue
        day = ro_date_of(r["kickoff_utc"])
        from betpredict.publish.day import superbet_url

        sb_url = superbet_url(r["home_name"], r["away_name"], r["sb_id"]) if r["sb_id"] else None
        out.append({
            "match_id": r["id"], "kickoff_utc": r["kickoff_utc"], "day": day.isoformat() if day else None,
            "home": r["home_name"], "away": r["away_name"], "league": r["league"],
            "odds": round(odds, 3), "median": round(mid, 3), "gap": round(gap, 4),
            "superbet_url": sb_url,
        })
    out.sort(key=lambda c: (c["day"] or "", -c["gap"]))
    return out


def events_doc(conn: sqlite3.Connection, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    rows = candidates(conn, now)
    return {
        "schema": "betpredict.soft_draw.v1",
        "generated_at": canon_utc(now.isoformat()),
        "rule": "Egal, cotă Superbet 2,80–3,60, cu cel puțin 2% peste mediana pieței. Biletul are două meciuri din aceeași zi.",
        "count": len(rows),
        "events": rows,
    }


def settle_legs(conn: sqlite3.Connection) -> int:
    """Decontează egalul din scorul final. Meci anulat sau amânat → void."""
    from betpredict.ingest.normalize import VOID_STATUSES

    n = 0
    for l in conn.execute(
            """SELECT tl.rowid rid, m.status, m.ft_home, m.ft_away
               FROM ticket_leg tl JOIN ticket t ON t.id = tl.ticket_id JOIN match m ON m.id = tl.match_id
               WHERE t.kind=? AND tl.result IS NULL""", (KIND,)).fetchall():
        if l["status"] in VOID_STATUSES:
            res = "void"
        elif l["status"] == "finished" and l["ft_home"] is not None and l["ft_away"] is not None:
            res = "won" if l["ft_home"] == l["ft_away"] else "lost"
        else:
            continue
        conn.execute("UPDATE ticket_leg SET result=? WHERE rowid=?", (res, l["rid"]))
        n += 1
    return n


def build(conn: sqlite3.Connection, today: date, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Reface biletele în așteptare. Câte un bilet de două egaluri pentru fiecare pereche din zi, cele mai moi primele."""
    now = now or datetime.now(timezone.utc)
    found = candidates(conn, now)
    by: Dict[str, List[Dict[str, Any]]] = {}
    last = today + timedelta(days=MAX_DAYS - 1)
    for c in found:
        if not c["day"]:
            continue
        day = date.fromisoformat(c["day"])
        if day < today or day > last:
            continue
        by.setdefault(c["day"], []).append(c)
    made = []
    with conn:
        conn.execute("UPDATE ticket SET status='replaced' WHERE kind=? AND status='pending'", (KIND,))
        for day, group in sorted(by.items()):
            ordered = sorted(group, key=lambda c: -c["gap"])
            pairs = [ordered[i:i + 2] for i in range(0, len(ordered) - 1, 2)]
            for legs in pairs:
                total = math.prod(c["odds"] for c in legs)
                notes = {
                    "experimental": True, "paper": True, "risk_acknowledged": True, "soft_draw": True,
                    "label": "Egaluri Superbet",
                    "events": legs,
                    "reasons": [
                        "Două egaluri la care Superbet e cu cel puțin 2% peste mediana pieței.",
                        "Cota fiecărui egal e între 2,80 și 3,60. Proba pe 10 ani a fost la Bet365, nu la Superbet.",
                        "Miză mică. Un al treilea meci nu a mai acoperit seria.",
                    ],
                }
                cur = conn.execute(
                    """INSERT INTO ticket (kind, variant, created_by, target_odds, total_odds, p_ticket, ev, stake, status, created_at, notes, day)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (KIND, VARIANT, "robot", round(total, 2), round(total, 2), None, None, STAKE_U, "pending",
                     repo.now_iso(), json.dumps(notes, ensure_ascii=False), day))
                tid = cur.lastrowid
                for c in sorted(legs, key=lambda c: c["kickoff_utc"]):
                    conn.execute(
                        "INSERT INTO ticket_leg (ticket_id, prediction_id, match_id, market, selection, odds, odds_source) VALUES (?,?,?,?,?,?,?)",
                        (tid, None, c["match_id"], "1x2|0", "DRAW", c["odds"], "superbet"))
                made.append({"day": day, "odds": round(total, 2), "legs": [
                    {"match_id": c["match_id"], "gap": c["gap"], "odds": c["odds"]} for c in legs]})
    return {"events": len(found), "tickets": made}
