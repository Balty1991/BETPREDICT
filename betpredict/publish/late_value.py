"""„Valoare în ultimele 3 ore”: cota Superbet ≥ 8% peste prețul corect Pinnacle, cu cel mult 3 ore înainte de start.

Regula vine din testul pe istoric (25.10.2026, Superbet vs Pinnacle fără marjă): simple, prima apariție pe selecție,
cota Superbet ≤ 2.5, piețele 1X2 și Peste/Sub 1.5/2.5/3.5 (fără Pauză/Final, Șansă dublă, DNB, cote mari).
Pe istoric: 62 de pariuri, ROI +11% (interval larg, −15%…+38%), CLV mediu +6.3% față de închiderea Pinnacle.
De aceea rubrica e „pe hârtie” până când urmărirea reală o confirmă.

La alertă se păstrează: momentul, cota Superbet, cota Pinnacle și șansa corectă. După start se completează
închiderea Pinnacle (ultima cotă înainte de start), CLV-ul (cota luată × șansa la închidere − 1) și rezultatul.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

MIN_EDGE = 0.08        # Superbet × șansa corectă − 1
MAX_EDGE = 0.30        # peste: aproape sigur linie/meci greșit potrivite
MAX_ODDS = 2.5         # cotele mari (outsideri) au ieșit pe minus
WINDOW_H = 3.0         # cel mult 3 ore până la start
MIN_LEAD_MIN = 5       # nu mai alertăm în ultimele 5 minute (nu mai ai timp să pariezi)
PIN_MAX_AGE_H = 2.0    # cota Pinnacle folosită: cel mult 2 h vechime
SB_MAX_AGE_H = 3.0     # oferta Superbet citită în ultimele 3 h (cotele se scriu doar când se schimbă)
OU_LINES = (1.5, 2.5, 3.5)
STAKE = 1.0            # miza de urmărire: 1 leu pe alertă
BACKTEST = {"n": 62, "roi": 0.11, "roi_ci": [-0.15, 0.38], "clv": 0.063, "per_week": 31,
            "note": "test pe istoric (Superbet vs Pinnacle, 25.10.2026); urmărirea reală pornește acum"}

TRACK = """CREATE TABLE IF NOT EXISTS lv_track (
  match_id INTEGER NOT NULL, market TEXT NOT NULL, outcome TEXT NOT NULL,
  alerted_at TEXT NOT NULL, kickoff_utc TEXT, superbet REAL NOT NULL, sb_seen_at TEXT,
  pin_price REAL, pin_at TEXT, p_fair REAL NOT NULL, edge REAL NOT NULL,
  close_pin REAL, close_p_fair REAL, close_at TEXT, clv REAL, result TEXT, settled_at TEXT,
  PRIMARY KEY (match_id, market, outcome))"""


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _devig(book: Dict[str, float], need: int) -> Optional[Dict[str, float]]:
    """Marja scoasă proporțional (multiplicativ), ca în testul pe istoric."""
    inv = {k: 1 / v for k, v in book.items() if v and v > 1}
    if len(inv) < need:
        return None
    s = sum(inv.values())
    if not 1.0 <= s <= 1.15:
        return None
    return {k: p / s for k, p in inv.items()}


def _key(market: str, line: float) -> Optional[str]:
    if market == "1x2":
        return "1x2"
    if market == "over_under" and float(line) in OU_LINES:
        return f"over_under_{float(line):g}"
    return None


def _books(conn: sqlite3.Connection, ids: List[int], source: str, asof: str, lo: Optional[str] = None
           ) -> Dict[Tuple[int, str], Dict[str, Tuple[float, str]]]:
    """Ultima cotă (și momentul ei) pe (meci, piață, rezultat) până la ``asof`` inclusiv, doar 1X2 și Peste/Sub 1.5–3.5."""
    if not ids:
        return {}
    q = ",".join("?" for _ in ids)
    out: Dict[Tuple[int, str], Dict[str, Tuple[float, str]]] = {}
    for mid, mk, line, o, d, t in conn.execute(f"""
            SELECT o.match_id, o.market, o.line, o.outcome, o.decimal, o.observed_at FROM odds_snapshot o
            JOIN (SELECT match_id, market, line, period, outcome, MAX(observed_at) mx FROM odds_snapshot
                  WHERE match_id IN ({q}) AND source=? AND observed_at <= ? AND market IN ('1x2','over_under')
                    AND (period IS NULL OR period IN ('', 'FT')) GROUP BY 1,2,3,4,5) l
              ON o.match_id=l.match_id AND o.market=l.market AND o.line=l.line AND o.period=l.period
             AND o.outcome=l.outcome AND o.observed_at=l.mx
            WHERE o.source=?""", [*ids, source, asof, source]):
        k = _key(mk, line)
        if k:
            out.setdefault((mid, k), {})[o] = (d, t)
    return out


def find(conn: sqlite3.Connection, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Selecțiile care respectă regula ACUM (cu prețurile de până acum, fără privit în viitor)."""
    now = now or datetime.now(timezone.utc)
    lo, hi = _iso(now + timedelta(minutes=MIN_LEAD_MIN)), _iso(now + timedelta(hours=WINDOW_H))
    rows = conn.execute("""SELECT m.id, m.kickoff_utc, m.home_name, m.away_name, l.name FROM match m
                           LEFT JOIN league l ON l.id=m.league_id
                           WHERE m.kickoff_utc >= ? AND m.kickoff_utc <= ? AND COALESCE(m.status,'') NOT IN
                           ('interrupted','postponed','cancelled','canceled','abandoned','unresolved')""", (lo, hi)).fetchall()
    meta = {r[0]: r for r in rows}
    if not meta:
        return []
    ids = list(meta)
    asof = _iso(now)
    pin = _books(conn, ids, "bsd:pinnacle", asof)
    sb = _books(conn, ids, "superbet", asof)
    try:
        chk = {r[0]: r[1] for r in conn.execute(
            f"SELECT match_id, MAX(COALESCE(detail_at,''), COALESCE(checked_at,'')) FROM ext_event WHERE source='superbet' "
            f"AND match_id IN ({','.join('?' for _ in ids)})", ids)}
    except sqlite3.OperationalError:
        chk = {}
    pin_lo, sb_lo = _iso(now - timedelta(hours=PIN_MAX_AGE_H)), _iso(now - timedelta(hours=SB_MAX_AGE_H))
    out = []
    for (mid, key), outs in sb.items():
        pbook = pin.get((mid, key))
        if not pbook or min(t for _d, t in pbook.values()) < pin_lo:
            continue
        seen = max([chk.get(mid) or ""] + [t for _d, t in outs.values()])
        if seen < sb_lo:  # oferta Superbet necitită de mult: cota poate să nu mai fie valabilă
            continue
        fair = _devig({k: d for k, (d, _t) in pbook.items()}, 3 if key == "1x2" else 2)
        if not fair:
            continue
        for o, (price, _t) in outs.items():
            if o not in fair or not price or price > MAX_ODDS:
                continue
            edge = price * fair[o] - 1
            if MIN_EDGE <= edge <= MAX_EDGE:
                _id, ko, hn, an, ln = meta[mid]
                out.append({"match_id": mid, "kickoff_utc": ko, "home": hn, "away": an, "league": ln, "market": key,
                            "outcome": o, "superbet": round(price, 2), "pinnacle": round(pbook[o][0], 3),
                            "pin_at": max(t for _d, t in pbook.values()), "sb_seen_at": seen or None,
                            "p_fair": round(fair[o], 4), "fair": round(1 / fair[o], 2), "edge": round(edge, 4)})
    out.sort(key=lambda x: -x["edge"])
    return out


def _won(market: str, outcome: str, h: int, a: int) -> Optional[bool]:
    from betpredict.publish.value_alerts import _won as va_won

    return va_won(market, outcome, h, a)


def _closing(conn: sqlite3.Connection, mid: int, market: str, ko: str) -> Optional[Dict[str, Tuple[float, str]]]:
    """Închiderea Pinnacle: ultima cotă înainte de start pe fiecare rezultat → {rezultat: (cota, momentul)}."""
    if market == "1x2":
        mk, line, need = "1x2", 0.0, 3
    else:
        mk, line, need = "over_under", float(market.rsplit("_", 1)[1]), 2
    rows = conn.execute("""SELECT o.outcome, o.decimal, o.observed_at FROM odds_snapshot o
                           JOIN (SELECT outcome, MAX(observed_at) mx FROM odds_snapshot WHERE match_id=? AND source='bsd:pinnacle'
                                 AND market=? AND line=? AND observed_at <= ? AND (period IS NULL OR period IN ('','FT')) GROUP BY 1) l
                             ON o.outcome=l.outcome AND o.observed_at=l.mx
                           WHERE o.match_id=? AND o.source='bsd:pinnacle' AND o.market=? AND o.line=?""",
                        (mid, mk, line, ko, mid, mk, line)).fetchall()
    return {r[0]: (r[1], r[2]) for r in rows} or None


def track(conn: sqlite3.Connection, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Caută alertele noi (doar prima apariție pe selecție), completează închiderea/CLV și decontează."""
    from betpredict.ingest.normalize import VOID_STATUSES

    now = now or datetime.now(timezone.utc)
    conn.execute(TRACK)
    stamp = _iso(now)
    new: List[Dict[str, Any]] = []
    with conn:
        for a in find(conn, now):
            cur = conn.execute("""INSERT OR IGNORE INTO lv_track (match_id, market, outcome, alerted_at, kickoff_utc, superbet, sb_seen_at,
                                  pin_price, pin_at, p_fair, edge) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                               (a["match_id"], a["market"], a["outcome"], stamp, a["kickoff_utc"], a["superbet"], a["sb_seen_at"],
                                a["pinnacle"], a["pin_at"], a["p_fair"], a["edge"]))
            if cur.rowcount:
                new.append(a)
        since = _iso(now - timedelta(days=30))
        for mid, mk, o, ko, price, res, pin_at in conn.execute(
                "SELECT match_id, market, outcome, kickoff_utc, superbet, result, pin_at FROM lv_track WHERE kickoff_utc <= ? AND alerted_at >= ?",
                (stamp, since)).fetchall():
            cl = _closing(conn, mid, mk, ko)
            fair = _devig({k: d for k, (d, _t) in cl.items()}, 3 if mk == "1x2" else 2) if cl else None
            if fair and o in fair:
                c_at = max(t for _d, t in cl.values())
                # CLV doar dacă închiderea e o cotă Pinnacle de DUPĂ alertă; altfel ar fi chiar marja de la alertă
                clv = round(price * fair[o] - 1, 4) if c_at > (pin_at or "") else None
                conn.execute("UPDATE lv_track SET close_pin=?, close_p_fair=?, close_at=?, clv=? WHERE match_id=? AND market=? AND outcome=?",
                             (cl[o][0], round(fair[o], 4), c_at, clv, mid, mk, o))
            r = conn.execute("SELECT ft_home, ft_away, status FROM match WHERE id=?", (mid,)).fetchone()
            if r and r[2] in VOID_STATUSES and res is None:
                conn.execute("UPDATE lv_track SET result='void', settled_at=? WHERE match_id=? AND market=? AND outcome=?", (stamp, mid, mk, o))
            elif r and r[0] is not None and r[1] is not None and r[2] == "finished":
                w = _won(mk, o, int(r[0]), int(r[1]))
                nr = "void" if w is None else "won" if w else "lost"
                if nr != res:
                    conn.execute("UPDATE lv_track SET result=?, settled_at=? WHERE match_id=? AND market=? AND outcome=?",
                                 (nr, stamp, mid, mk, o))
    return {"new": len(new), "new_alerts": [f"{a['home']} – {a['away']} {a['market']} {a['outcome']} @{a['superbet']}" for a in new]}


def record(conn: sqlite3.Connection) -> Dict[str, Any]:
    conn.execute(TRACK)
    n, won, pl, pend, tot = conn.execute(
        """SELECT SUM(result IN ('won','lost')), SUM(result='won'),
                  SUM(CASE WHEN result='won' THEN superbet-1 WHEN result='lost' THEN -1 ELSE 0 END),
                  SUM(result IS NULL), COUNT(*) FROM lv_track""").fetchone()
    n = n or 0
    cn, clv = conn.execute("SELECT COUNT(clv), AVG(clv) FROM lv_track WHERE clv IS NOT NULL").fetchone()
    beat = conn.execute("SELECT AVG(clv > 0) FROM lv_track WHERE clv IS NOT NULL").fetchone()[0]
    return {"alerts": tot or 0, "settled": n, "won": won or 0, "pending": pend or 0,
            "hit_rate": round((won or 0) / n, 3) if n else None,
            "staked": round(n * STAKE, 2), "profit": round((pl or 0) * STAKE, 2),
            "roi": round((pl or 0) / n, 4) if n else None,
            "clv_n": cn or 0, "avg_clv": round(clv, 4) if clv is not None else None,
            "beat_close": round(beat, 3) if beat is not None else None}


def _label(market: str, outcome: str) -> str:
    from betpredict.publish.value_alerts import label

    return label(market, outcome)


def _enrich(conn: sqlite3.Connection, x: Dict[str, Any]) -> Dict[str, Any]:
    from betpredict.publish.day import superbet_url
    from betpredict.publish.outputs import _robot_pick

    x["label"] = _label(x["market"], x["outcome"])
    r = conn.execute("SELECT ext_id FROM ext_event WHERE match_id=? AND source='superbet'", (x["match_id"],)).fetchone()
    x["sb_event_id"] = r[0] if r else None
    x["superbet_url"] = superbet_url(x["home"] or "", x["away"] or "", r[0]) if r else None
    mk, line = ("1x2", None) if x["market"] == "1x2" else ("over_under", float(x["market"].rsplit("_", 1)[1]))
    try:
        x["sb_pick"] = _robot_pick(conn, x["match_id"], mk, line, x["outcome"])
    except Exception:  # noqa: BLE001  (fără oferta salvată: rămâne linkul spre meci)
        x["sb_pick"] = None
    return x


def doc(conn: sqlite3.Connection, now: Optional[datetime] = None, limit: int = 40) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    conn.execute(TRACK)
    stamp = _iso(now)
    cols = ("match_id", "market", "outcome", "alerted_at", "kickoff_utc", "superbet", "pin_price", "p_fair", "edge",
            "close_pin", "close_p_fair", "clv", "result")
    q = f"""SELECT {', '.join('t.' + c for c in cols)}, m.home_name, m.away_name, l.name, m.ft_home, m.ft_away FROM lv_track t
            JOIN match m ON m.id=t.match_id LEFT JOIN league l ON l.id=m.league_id"""
    def row(r: tuple) -> Dict[str, Any]:
        x = dict(zip(cols, r[:len(cols)]))
        x.update(home=r[-5], away=r[-4], league=r[-3], fair=round(1 / x["p_fair"], 2) if x["p_fair"] else None,
                 score=f"{r[-2]}-{r[-1]}" if r[-2] is not None else None, stake=STAKE)
        return x
    active = [_enrich(conn, row(r)) for r in conn.execute(q + " WHERE t.kickoff_utc > ? ORDER BY t.kickoff_utc, t.edge DESC", (stamp,))]
    recent = [row(r) for r in conn.execute(q + " WHERE t.kickoff_utc <= ? ORDER BY t.kickoff_utc DESC LIMIT ?", (stamp, limit))]
    for x in recent:
        x["label"] = _label(x["market"], x["outcome"])
    return {"generated_at": now.isoformat(timespec="seconds"), "paper": True,
            "rule": {"min_edge": MIN_EDGE, "max_edge": MAX_EDGE, "max_odds": MAX_ODDS, "window_h": WINDOW_H,
                     "markets": ["1x2", "over_under_1.5", "over_under_2.5", "over_under_3.5"], "stake": STAKE,
                     "text": "Simplu, cota Superbet ≥ 8% peste prețul corect Pinnacle, cu cel mult 3 ore înainte de start, cota ≤ 2.5; "
                             "o singură alertă pe selecție (prima apariție). Fără Șansă dublă, Pauză/Final sau cote mari."},
            "alerts": active, "record": record(conn), "recent": recent, "backtest": BACKTEST}
