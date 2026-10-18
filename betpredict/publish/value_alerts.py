"""Alerte de valoare: cota Superbet bate prețul corect Pinnacle (fără marjă) cu ≥ 5%, pe meciuri neîncepute.

Pinnacle e casa „ascuțită”: cotele ei, scoase de marjă proporțional pe toate rezultatele pieței, sunt cea mai bună
estimare publică a șansei reale. Dacă Superbet plătește mai mult decât atât, pariul are EV pozitiv după piață,
independent de modelul nostru.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from betpredict.store import repo

MIN_VALUE = 0.05     # Superbet × șansa corectă − 1
MAX_VALUE = 0.30     # peste: aproape sigur linie/piață greșit potrivită, nu valoare
MAX_ODDS = 8.0
HORIZON_H = 36
FRESH_H = 6
MIN_OUTCOMES = {"1x2": 3}


def _fair(book: Dict[str, float], market: str) -> Optional[Dict[str, float]]:
    pr = {k: 1 / v for k, v in book.items() if v and v > 1}
    if len(pr) < MIN_OUTCOMES.get(market.split("_")[0], 2):
        return None
    s = sum(pr.values())
    if not 1.0 <= s <= 1.15:  # set incomplet sau cote stricate
        return None
    return {k: v / s for k, v in pr.items()}


def find(conn: sqlite3.Connection, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    lo, hi = now.strftime("%Y-%m-%dT%H:%M:%SZ"), (now + timedelta(hours=HORIZON_H)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = conn.execute("""SELECT m.id, m.kickoff_utc, m.home_name, m.away_name, l.name FROM match m
                           LEFT JOIN league l ON l.id=m.league_id
                           WHERE m.kickoff_utc > ? AND m.kickoff_utc <= ?""", (lo, hi)).fetchall()
    meta = {r[0]: r for r in rows}
    ids = list(meta)
    if not ids:
        return []
    # doar meciuri cu ambele surse proaspete (≤ 6 ore), altfel compari o cotă de azi cu una de ieri
    fresh_lo = (now - timedelta(hours=FRESH_H)).strftime("%Y-%m-%dT%H:%M:%SZ")
    q = ",".join("?" for _ in ids)
    fresh = {}
    for mid, src in conn.execute(f"""SELECT match_id, source FROM odds_snapshot WHERE match_id IN ({q})
                                     AND source IN ('bsd:pinnacle','superbet') AND observed_at >= ? GROUP BY match_id, source""",
                                 [*ids, fresh_lo]):
        fresh.setdefault(mid, set()).add(src)
    ids = [i for i in ids if len(fresh.get(i, ())) == 2]
    pin = repo.latest_odds(conn, ids, source="bsd:pinnacle")
    sb = repo.latest_odds(conn, ids, source="superbet")
    out = []
    for mid, mk in sb.items():
        for key, outs in mk.items():
            fair = _fair(pin.get(mid, {}).get(key, {}), key)
            if not fair:
                continue
            for o, price in outs.items():
                if o not in fair or not price or price > MAX_ODDS:
                    continue
                v = price * fair[o] - 1
                if MIN_VALUE <= v <= MAX_VALUE:
                    _id, ko, hn, an, ln = meta[mid]
                    out.append({"match_id": mid, "kickoff_utc": ko, "home": hn, "away": an, "league": ln, "market": key,
                                "outcome": o, "superbet": round(price, 2), "fair": round(1 / fair[o], 2),
                                "p_fair": round(fair[o], 4), "value": round(v, 4)})
    out.sort(key=lambda x: -x["value"])
    return out


# ---- urmărire: fiecare alertă se ține minte la prima apariție și se decontează din scorul final ----
TRACK = """CREATE TABLE IF NOT EXISTS va_track (match_id INTEGER, market TEXT, outcome TEXT, first_seen TEXT, superbet REAL,
           p_fair REAL, value REAL, result TEXT, PRIMARY KEY (match_id, market, outcome))"""
PUSH_MIN_N = 50       # notificările pornesc doar după destule alerte decontate…
PUSH_MIN_ROI = 0.0    # …și doar dacă au ieșit cel puțin pe zero
LABEL = {"HOME": "1", "DRAW": "X", "AWAY": "2", "OVER": "Peste", "UNDER": "Sub", "YES": "Da", "NO": "Nu"}


def _won(market: str, outcome: str, h: int, a: int) -> Optional[bool]:
    if market == "1x2":
        return {"HOME": h > a, "DRAW": h == a, "AWAY": h < a}.get(outcome)
    if market.startswith("over_under_") and market.count("_") == 2:
        line = float(market.rsplit("_", 1)[1])
        if h + a == line:
            return None
        return (h + a > line) if outcome == "OVER" else (h + a < line) if outcome == "UNDER" else None
    if market == "btts":
        return ((h > 0 and a > 0) == (outcome == "YES")) if outcome in ("YES", "NO") else None
    return None


def label(market: str, outcome: str) -> str:
    if market.startswith("over_under_"):
        return f"{LABEL.get(outcome, outcome)} {market.rsplit('_', 1)[1]} goluri"
    if market == "btts":
        return f"Ambele marchează: {LABEL.get(outcome, outcome)}"
    if market == "1x2":
        return f"Final {LABEL.get(outcome, outcome)}"
    return f"{market} {outcome}"


def track_and_settle(conn: sqlite3.Connection, alerts: List[Dict[str, Any]], now: datetime) -> Dict[str, Any]:
    conn.execute(TRACK)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    with conn:
        for a in alerts:
            conn.execute("INSERT OR IGNORE INTO va_track VALUES (?,?,?,?,?,?,?,NULL)",
                         (a["match_id"], a["market"], a["outcome"], stamp, a["superbet"], a["p_fair"], a["value"]))
        for mid, mk, o in conn.execute("SELECT match_id, market, outcome FROM va_track WHERE result IS NULL").fetchall():
            r = conn.execute("SELECT ft_home, ft_away FROM match WHERE id=?", (mid,)).fetchone()
            if not r or r[0] is None or r[1] is None:
                continue
            w = _won(mk, o, int(r[0]), int(r[1]))
            conn.execute("UPDATE va_track SET result=? WHERE match_id=? AND market=? AND outcome=?",
                         ("void" if w is None else "won" if w else "lost", mid, mk, o))
    n, won, exp, pl = conn.execute("""SELECT COUNT(*), SUM(result='won'), SUM(p_fair),
                                      SUM(CASE WHEN result='won' THEN superbet-1 ELSE -1 END)
                                      FROM va_track WHERE result IN ('won','lost')""").fetchone()
    n = n or 0
    roi = round(pl / n, 4) if n else None
    return {"settled": n, "won": won or 0, "expected": round(exp or 0, 1), "roi": roi,
            "push_enabled": bool(n >= PUSH_MIN_N and roi is not None and roi >= PUSH_MIN_ROI)}


def publish(conn: sqlite3.Connection, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    alerts = find(conn, now)
    rec = track_and_settle(conn, alerts, now)
    for a in alerts:
        a["label"] = label(a["market"], a["outcome"])
    return {"generated_at": now.isoformat(timespec="seconds"), "min_value": MIN_VALUE, "alerts": alerts[:40],
            "record": {k: rec[k] for k in ("settled", "won", "expected", "roi")}, "push_enabled": rec["push_enabled"],
            "push_rule": f"notificări după {PUSH_MIN_N} alerte decontate cu ROI ≥ 0"}
