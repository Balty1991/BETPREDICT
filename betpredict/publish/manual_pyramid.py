"""Piramida manuală (25.10): oferta zilei din care Alin își alege singur selecțiile pe fiecare treaptă.

``api/pyramid/manual_pool.json``  – selecțiile de azi, întâi cele cu EV ≥ 0 față de Pinnacle fără marjă (ambele cote văzute
                                     în ultimele 2 ore), apoi cele mai sigure după probabilitatea calibrată. Aceleași filtre ca
                                     Calea 100+: fără piețele/ligile slabe (BAD_KEYS/BAD_LEAGUES), poarta cartonașelor, piețe în
                                     pauză, meciuri de noapte, start în < 10 min.
``api/pyramid/manual_results.json`` – rezultatul fiecărei selecții oferite (id → w/l/v), ca aplicația să deconteze piramidele
                                     salvate local (localStorage), fără cont.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

TRACK = """CREATE TABLE IF NOT EXISTS manual_pick_track (id TEXT PRIMARY KEY, match_id INTEGER, market TEXT, selection TEXT,
           odds REAL, first_seen TEXT, result TEXT)"""
LEG_ODDS = (1.10, 5.0)
MAX_ITEMS = 160
MIN_EV_REST = -0.05   # în afara Pinnacle: EV-ul modelului ≥ −5% (altfel nu apare deloc)
MIN_P_REST = 0.45


def leg_id(match_id: Any, market: str, selection: str) -> str:
    return f"{match_id}|{market}|{selection}"


def _label(market: str, sel: str) -> str:
    from betpredict.experimental.supersocial import LABELS

    if market == "ss|0":
        return LABELS.get(sel, sel)
    if market.startswith("over_under|"):
        return f"{'Peste' if sel == 'OVER' else 'Sub'} {market.split('|')[1]} goluri"
    if market == "btts|0":
        return f"Ambele marchează: {'Da' if sel == 'YES' else 'Nu'}"
    return sel


def _records(conn: sqlite3.Connection, now: datetime) -> Dict[str, Dict[Any, Dict[str, Any]]]:
    from betpredict.publish.value_alerts import _won

    since = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    agg: Dict[str, Dict[Any, List[float]]] = {"key": {}, "league": {}, "pin": {}}

    def add(kind: str, k: Any, w: bool, o: float) -> None:
        a = agg[kind].setdefault(k, [0, 0, 0.0])
        a[0] += 1; a[1] += w; a[2] += (o - 1) if w else -1

    try:
        for k, lg, o, r in conn.execute("""SELECT s.mkey, m.league_id, s.odds, s.result FROM ss_track s JOIN match m ON m.id=s.match_id
                                           WHERE s.result IN ('won','lost') AND s.odds > 1 AND s.kickoff_utc >= ?""", (since,)):
            add("key", k, r == "won", o); add("league", lg, r == "won", o)
    except sqlite3.Error:
        pass
    try:
        for mk, oc, o, h, a in conn.execute("""SELECT v.market, v.outcome, v.superbet, m.ft_home, m.ft_away FROM va_track v JOIN match m
                                               ON m.id=v.match_id WHERE m.status='finished' AND v.first_seen >= ?""", (since,)):
            w = _won(mk, oc, int(h), int(a)) if h is not None and a is not None else None
            if w is not None:
                add("pin", "all", w, o)
    except sqlite3.Error:
        pass
    return {kind: {k: {"n": v[0], "hit": round(v[1] / v[0], 3), "roi": round(v[2] / v[0], 3)} for k, v in d.items()}
            for kind, d in agg.items()}


def pool_doc(conn: sqlite3.Connection, today: date, now: Optional[datetime] = None, rows: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    from betpredict.builder import calea100 as C

    now = now or datetime.now(timezone.utc)
    if rows is None:
        from betpredict.experimental.supersocial import today_doc

        rows = today_doc(conn, now)["rows"]
    old = C.LEG_ODDS
    C.LEG_ODDS = LEG_ODDS
    try:
        pool = C.candidates(conn, rows, today, now)
    finally:
        C.LEG_ODDS = old
    meta = {r["match_id"]: r for r in rows}
    names = {r[0]: r[1] for r in conn.execute("SELECT id, name FROM league")}
    teams: Dict[int, Any] = {}
    rec = _records(conn, now)
    items: List[Dict[str, Any]] = []
    seen = set()
    for c in pool:
        ev = c["p"] * c["odds"] - 1
        pin = c["src"] == "pinnacle" and ev >= 0
        if not pin and (ev < MIN_EV_REST or c["p"] < MIN_P_REST):
            continue
        i = leg_id(c["match_id"], c["market"], c["selection"])
        if i in seen:
            continue
        seen.add(i)
        m = meta.get(c["match_id"])
        if m is None and c["match_id"] not in teams:
            teams[c["match_id"]] = conn.execute("SELECT home_name, away_name FROM match WHERE id=?", (c["match_id"],)).fetchone()
        home, away = (m["home"], m["away"]) if m else tuple(teams.get(c["match_id"]) or (None, None))
        r_mk = rec["pin"].get("all") if c["src"] == "pinnacle" else rec["key"].get(c["selection"]) if c["market"] == "ss|0" else None
        r_lg = rec["league"].get(c["league_id"])
        items.append({"id": i, "match_id": c["match_id"], "home": home, "away": away, "league": names.get(c["league_id"]),
                      "kickoff_utc": c["kickoff_utc"], "market": c["market"], "selection": c["selection"],
                      "label": _label(c["market"], c["selection"]), "odds": round(float(c["odds"]), 2), "p": round(float(c["p"]), 4),
                      "ev": round(ev, 4), "src": c["src"], "group": 0 if pin else 1 if ev >= 0 and r_mk and r_mk["n"] >= 40 and r_mk["roi"] >= 0 else 2,
                      "rec": r_mk if r_mk and r_mk["n"] >= 20 else None, "lrec": r_lg if r_lg and r_lg["n"] >= 30 else None})
    items.sort(key=lambda x: (x["group"], -x["ev"] if x["group"] == 0 else -x["p"]))
    items = items[:MAX_ITEMS]
    track(conn, items, now)
    return {"generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "date": today.isoformat(), "items": items,
            "rules": "Întâi EV ≥ 0 vs Pinnacle fără marjă (cote ≤ 2h), apoi piețele cu istoric pe plus (EV model ≥ 0), apoi restul, după probabilitatea calibrată. Fără piețele și ligile slabe, "
                     "poarta cartonașelor, fără meciuri de noapte.",
            "pin_record": rec["pin"].get("all")}


def track(conn: sqlite3.Connection, items: List[Dict[str, Any]], now: datetime) -> None:
    conn.execute(TRACK)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    with conn:
        for x in items:
            conn.execute("INSERT OR IGNORE INTO manual_pick_track VALUES (?,?,?,?,?,?,NULL)",
                         (x["id"], x["match_id"], x["market"], x["selection"], x["odds"], stamp))


def settle(conn: sqlite3.Connection) -> int:
    from betpredict.ingest.normalize import VOID_STATUSES
    from betpredict.publish.value_alerts import _won

    conn.execute(TRACK)
    n = 0
    with conn:
        for i, mid, mk, sel in conn.execute("SELECT id, match_id, market, selection FROM manual_pick_track WHERE result IS NULL").fetchall():
            res = None
            if mk == "ss|0":
                r = conn.execute("SELECT result FROM ss_track WHERE match_id=? AND mkey=? AND result IS NOT NULL", (mid, sel)).fetchone()
                res = r[0] if r else None
            elif mk == "boost|0":
                r = conn.execute("SELECT result FROM sb_boost WHERE match_id=? AND name=? AND result IN ('won','lost','void','unsettleable')",
                                 (mid, sel)).fetchone()
                res = ("void" if r[0] == "unsettleable" else r[0]) if r else None
            else:
                m = conn.execute("SELECT ft_home, ft_away, status FROM match WHERE id=?", (mid,)).fetchone()
                if m and m[2] in VOID_STATUSES:
                    res = "void"
                elif m and m[2] == "finished" and m[0] is not None and m[1] is not None:
                    va = "btts" if mk == "btts|0" else "over_under_" + mk.split("|")[1]
                    w = _won(va, sel, int(m[0]), int(m[1]))
                    res = "void" if w is None else "won" if w else "lost"
            if res:
                conn.execute("UPDATE manual_pick_track SET result=? WHERE id=?", (res, i))
                n += 1
    return n


def results_doc(conn: sqlite3.Connection, now: Optional[datetime] = None, days: int = 30) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    conn.execute(TRACK)
    since = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = {i: {"won": "w", "lost": "l"}.get(r, "v") for i, r in conn.execute(
        "SELECT id, result FROM manual_pick_track WHERE result IS NOT NULL AND first_seen >= ?", (since,))}
    return {"generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "results": out}
