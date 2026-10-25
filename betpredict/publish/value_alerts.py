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
MAX_ODDS = 4.0      # cotele mari: bias favorit–outsider, alertele de acolo au ieșit −40% în probă
HORIZON_H = 36
MARKETS_OFF = {"1x2"}  # 1X2: în probă 7 câștigate din 12.9 așteptate (−49%); peste/sub: 14/14.2, +4%
MAX_AGE_H = 2      # vârsta maximă a ambelor prețuri (Superbet și Pinnacle), pe piață
MIN_OUTCOMES = {"1x2": 3}


def _fair(book: Dict[str, float], market: str) -> Optional[Dict[str, float]]:
    pr = {k: 1 / v for k, v in book.items() if v and v > 1}
    if len(pr) < MIN_OUTCOMES.get(market.split("_")[0], 2):
        return None
    s = sum(pr.values())
    if not 1.0 <= s <= 1.15:  # set incomplet sau cote stricate
        return None
    # marja scoasă „power” (p_i^k, Σ = 1): cotele mari poartă mai multă marjă decât cele mici, nu proporțional
    lo, hi = 1.0, 3.0
    for _ in range(50):
        k = (lo + hi) / 2
        lo, hi = (lo, k) if sum(p ** k for p in pr.values()) < 1 else (k, hi)
    k = (lo + hi) / 2
    return {o: p ** k for o, p in pr.items()}


SWAP = {"HOME": "AWAY", "AWAY": "HOME", "OVER": "UNDER", "UNDER": "OVER", "YES": "NO", "NO": "YES"}
MAX_GAP = 0.12  # o diferență de șansă mai mare pe un rezultat = meci/linie potrivite greșit, nu valoare


def _mismatch(fair: Dict[str, float], sb: Dict[str, float]) -> bool:
    """Gazdă/oaspete inversate între surse sau linie greșită: rezultatele inversate se potrivesc mai bine, ori un
    rezultat diferă cu peste MAX_GAP în șansă."""
    imp = {k: 1 / v for k, v in sb.items() if v and v > 1}
    common = [k for k in imp if k in fair]
    if not common:
        return True
    same = sum(abs(imp[k] - fair[k]) for k in common)
    sw = [k for k in common if SWAP.get(k) in fair]
    if sw and sum(abs(imp[k] - fair[SWAP[k]]) for k in sw) < same:
        return True
    return any(abs(imp[k] - fair[k]) > MAX_GAP for k in common)


def _latest(conn: sqlite3.Connection, ids: List[int], source: str, asof: str) -> Dict[int, Dict[str, Dict[str, tuple]]]:
    """Ultima cotă (și momentul ei) pe (meci, piață, rezultat), până la ``asof`` inclusiv: fără privit în viitor."""
    q = ",".join("?" for _ in ids)
    out: Dict[int, Dict[str, Dict[str, tuple]]] = {}
    for mid, mk, line, per, o, d, t in conn.execute(f"""
            SELECT o.match_id, o.market, o.line, o.period, o.outcome, o.decimal, o.observed_at FROM odds_snapshot o
            JOIN (SELECT match_id, market, line, period, outcome, MAX(observed_at) mx FROM odds_snapshot
                  WHERE match_id IN ({q}) AND source=? AND observed_at <= ? GROUP BY 1,2,3,4,5) l
              ON o.match_id=l.match_id AND o.market=l.market AND o.line=l.line AND o.period=l.period AND o.outcome=l.outcome
             AND o.observed_at=l.mx WHERE o.source=?""", [*ids, source, asof, source]):
        out.setdefault(mid, {}).setdefault(repo.market_key(mk, line, per), {})[o] = (d, t)
    return out


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
    asof = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    pin = _latest(conn, ids, "bsd:pinnacle", asof)
    sb = _latest(conn, ids, "superbet", asof)
    age_lo = (now - timedelta(hours=MAX_AGE_H)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = []
    for mid, mk in sb.items():
        for key, outs in mk.items():
            if key in MARKETS_OFF:
                continue
            pbook = pin.get(mid, {}).get(key, {})
            # ambele prețuri văzute de curând (nu o cotă Superbet veche de 2 zile față de un Pinnacle care s-a mișcat)
            if not pbook or not outs or min(t for _d, t in pbook.values()) < age_lo or min(t for _d, t in outs.values()) < age_lo:
                continue
            fair = _fair({k: d for k, (d, _t) in pbook.items()}, key)
            if not fair or _mismatch(fair, {k: d for k, (d, _t) in outs.items()}):
                continue
            for o, (price, _t) in outs.items():
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
        # 25.10: doar meciuri TERMINATE (înainte se deconta pe scorul live → 23 din 56 greșit); tabela e mică, așa că
        # recalculăm la fiecare rulare tot ce s-a jucat în ultimele 30 de zile (repară și deconturile vechi)
        since = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        for mid, mk, o in conn.execute("SELECT match_id, market, outcome FROM va_track WHERE result IS NULL OR first_seen >= ?", (since,)).fetchall():
            r = conn.execute("SELECT ft_home, ft_away, status FROM match WHERE id=?", (mid,)).fetchone()
            if not r or r[0] is None or r[1] is None or r[2] != "finished":
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
