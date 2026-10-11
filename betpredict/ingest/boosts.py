"""Cote mărite Superbet (Cote Mărite / Super Cota / SuperPariuri cu preț mărit) din oferta publică.

Detecție: în /events/{id} fiecare cotă are ``tags``; ``price_boost`` = cotă mărită (``extra.originalPrice`` =
„<marketId>:<cota normală>”, ``extra.boostLevel``), ``superKvota`` = piața „Final - Super Cota” (1X2 mărit).
Probabilitate corectă:
  * super_cota (1X2)   → piața fără marjă (consens multi-casă amestecat cu Pinnacle) — „sigur”;
  * core (X câștigă & peste 2.5, GG & peste N.5, …) → Poisson cu λ din piață (1X2 + Peste/Sub 2.5) — „model”;
  * rest (șuturi, cornere, jucători, combinații) → cota normală Superbet fără ~10% marjă — „incert”.
Regulament Superbet: cotele mărite se pot pune pe acumulator; SuperAvantaj nu se aplică; nu contează la Super Bonus."""

from __future__ import annotations

import json
import math
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

SCHEMA = """CREATE TABLE IF NOT EXISTS sb_boost (
  match_id INTEGER NOT NULL, uid TEXT NOT NULL, kind TEXT NOT NULL, market_name TEXT, name TEXT, info TEXT,
  price REAL NOT NULL, orig_price REAL, level TEXT, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
  p_fair REAL, method TEXT, ev REAL, result TEXT, settled_at TEXT, PRIMARY KEY (match_id, uid))"""
NONCORE_MARGIN = 1.10


def ensure(conn: sqlite3.Connection) -> None:
    conn.execute(SCHEMA)


def parse_boosts(ev: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for o in ev.get("odds") or []:
        tags = str(o.get("tags") or "")
        if (o.get("status") or "active") != "active" or not ("price_boost" in tags or "superKvota" in tags):
            continue
        try:
            price = float(o.get("price"))
        except (TypeError, ValueError):
            continue
        x = o.get("extra") or {}
        orig = None
        m = re.match(r"^\d+:([\d.]+)$", str(x.get("originalPrice") or ""))
        if m:
            orig = float(m.group(1))
        if "superKvota" in tags:
            kind = "super_cota"
        elif "boost_core_market" in tags and "price_boost_combo" not in tags:
            kind = "core"
        else:
            kind = "combo" if "price_boost_combo" in tags else "non_core"
        out.append({"uid": str(o.get("uuid") or o.get("outcomeId") or f"{o.get('marketId')}:{o.get('name')}"), "kind": kind,
                    "market_name": o.get("marketName"), "name": str(o.get("name") or ""), "info": o.get("info"),
                    "price": price, "orig_price": orig, "level": x.get("boostLevel")})
    return out


def store(conn: sqlite3.Connection, mid: int, ev: Dict[str, Any], stamp: str) -> int:
    ensure(conn)
    n = 0
    for b in parse_boosts(ev):
        conn.execute(
            "INSERT INTO sb_boost (match_id, uid, kind, market_name, name, info, price, orig_price, level, first_seen, last_seen) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(match_id, uid) DO UPDATE SET price=excluded.price, "
            "orig_price=COALESCE(excluded.orig_price, sb_boost.orig_price), last_seen=excluded.last_seen",
            (mid, b["uid"], b["kind"], b["market_name"], b["name"], b["info"], b["price"], b["orig_price"], b["level"], stamp, stamp))
        n += 1
    return n


# ---------------------------------------------------------------- probabilitate corectă
def _pois(lam: float, k: int) -> float:
    return math.exp(-lam) * lam ** k / math.factorial(k)


def grid(lh: float, la: float, n: int = 11):
    ph = [_pois(lh, k) for k in range(n)]
    pa = [_pois(la, k) for k in range(n)]
    return [[ph[i] * pa[j] for j in range(n)] for i in range(n)]


def core_rule(name: str, home: str, away: str):
    """Textul unei Cote Mărite „core” → funcție (h, a) → bool; None dacă nu o recunoaștem."""
    s = name.lower()
    m_tot = re.search(r"peste (\d+)\.5 goluri", s)
    m_sub = re.search(r"sub (\d+)\.5 goluri", s)
    side = None
    if "câștigă" in s or "castiga" in s:
        if home and home.lower() in s:
            side = "H"
        elif away and away.lower() in s:
            side = "A"
        else:
            return None
    gg = s.startswith("gg") or "ambele echipe marchează" in s
    if "șuturi" in s or "cornere" in s or "cartonaș" in s or "jucător" in s or "repriz" in s:
        return None
    if not (m_tot or m_sub or side or gg):
        return None

    def f(h: int, a: int) -> bool:
        ok = True
        if side == "H":
            ok &= h > a
        if side == "A":
            ok &= a > h
        if gg:
            ok &= h > 0 and a > 0
        if m_tot:
            ok &= h + a > int(m_tot.group(1))
        if m_sub:
            ok &= h + a <= int(m_sub.group(1))
        return ok
    return f


def market_lambdas(conn: sqlite3.Connection, mid: int) -> Optional[Tuple[float, float]]:
    from betpredict.store import repo
    import numpy as np
    from betpredict.lab.engine import lambdas_from_market
    from betpredict.robot.engine import blend_pinnacle, market_probs

    mk = blend_pinnacle(market_probs(repo.latest_odds(conn, [mid]).get(mid, {})),
                        market_probs(repo.latest_odds(conn, [mid], source="bsd:pinnacle").get(mid, {})))
    h, a, o = mk.get(("1x2", 0.0, "HOME")), mk.get(("1x2", 0.0, "AWAY")), mk.get(("over_under", 2.5, "OVER"))
    if not (h and a and o):
        return None
    lh, la = lambdas_from_market(np.array([h]), np.array([a]), np.array([o]))
    return float(lh[0]), float(la[0])


def fair(conn: sqlite3.Connection, b: sqlite3.Row, home: str, away: str) -> Tuple[Optional[float], str]:
    from betpredict.store import repo
    from betpredict.robot.engine import blend_pinnacle, market_probs

    if b["kind"] == "super_cota":
        sel = {"SC-1": "HOME", "SC-X": "DRAW", "SC-2": "AWAY"}.get(b["name"])
        mk = blend_pinnacle(market_probs(repo.latest_odds(conn, [b["match_id"]]).get(b["match_id"], {})),
                            market_probs(repo.latest_odds(conn, [b["match_id"]], source="bsd:pinnacle").get(b["match_id"], {})))
        p = mk.get(("1x2", 0.0, sel)) if sel else None
        if p:
            return p, "piață (Pinnacle + consens)"
    if b["kind"] == "core":
        rule = core_rule(b["name"] or "", home, away)
        lam = market_lambdas(conn, b["match_id"]) if rule else None
        if rule and lam:
            g = grid(*lam)
            return sum(g[i][j] for i in range(len(g)) for j in range(len(g)) if rule(i, j)), "model (λ din piață)"
    if b["orig_price"]:
        return 1 / (b["orig_price"] * NONCORE_MARGIN), "incert (cota normală − ~10% marjă)"
    return None, "necunoscut"


def evaluate(conn: sqlite3.Connection) -> int:
    ensure(conn)
    n = 0
    with conn:
        for b in conn.execute("""SELECT b.*, m.home_name, m.away_name FROM sb_boost b JOIN match m ON m.id = b.match_id
                                 WHERE b.result IS NULL""").fetchall():
            p, method = fair(conn, b, b["home_name"] or "", b["away_name"] or "")
            conn.execute("UPDATE sb_boost SET p_fair=?, method=?, ev=? WHERE match_id=? AND uid=?",
                         (round(p, 4) if p else None, method, round(p * b["price"] - 1, 4) if p else None, b["match_id"], b["uid"]))
            n += 1
    return n


def settle(conn: sqlite3.Connection) -> int:
    from betpredict.ingest.normalize import VOID_STATUSES

    ensure(conn)
    n = 0
    stamp = datetime.now(timezone.utc).isoformat()[:19] + "Z"
    with conn:
        for b in conn.execute("""SELECT b.*, m.status, m.ft_home, m.ft_away, m.home_name, m.away_name FROM sb_boost b
                                 JOIN match m ON m.id = b.match_id WHERE b.result IS NULL""").fetchall():
            res = None
            if b["status"] in VOID_STATUSES:
                res = "void"
            elif b["status"] == "finished" and b["ft_home"] is not None:
                if b["kind"] == "super_cota":
                    h, a = b["ft_home"], b["ft_away"]
                    res = "won" if {"SC-1": h > a, "SC-X": h == a, "SC-2": a > h}.get(b["name"]) else "lost"
                elif b["kind"] == "core" and (rule := core_rule(b["name"] or "", b["home_name"] or "", b["away_name"] or "")):
                    res = "won" if rule(b["ft_home"], b["ft_away"]) else "lost"
                else:
                    res = "unsettleable"  # șuturi/cornere/jucători: fără date de decontare în feed
            if res:
                conn.execute("UPDATE sb_boost SET result=?, settled_at=? WHERE match_id=? AND uid=?", (res, stamp, b["match_id"], b["uid"]))
                n += 1
    return n


def stats(conn: sqlite3.Connection) -> Dict[str, Any]:
    ensure(conn)
    out: Dict[str, Any] = {}
    for key, cond in (("toate", "1=1"), ("ev_pozitiv", "ev > 0"), ("super_cota", "kind='super_cota'"), ("core", "kind='core'")):
        r = conn.execute(f"""SELECT COUNT(*) n, SUM(result='won') w, SUM(CASE WHEN result='won' THEN price ELSE 0 END) ret
                             FROM sb_boost WHERE result IN ('won','lost') AND {cond}""").fetchone()
        n = r["n"] or 0
        out[key] = {"n": n, "won": r["w"] or 0, "hit_rate": round((r["w"] or 0) / n, 3) if n else None,
                    "roi": round((r["ret"] or 0) / n - 1, 3) if n else None}
    out["unsettleable"] = conn.execute("SELECT COUNT(*) FROM sb_boost WHERE result='unsettleable'").fetchone()[0]
    return out


def today_doc(conn: sqlite3.Connection, now: Optional[datetime] = None) -> Dict[str, Any]:
    ensure(conn)
    now = now or datetime.now(timezone.utc)
    lo = now.isoformat()[:19] + "Z"
    hi = (now + timedelta(hours=36)).isoformat()[:19] + "Z"
    rows = conn.execute(
        """SELECT b.*, m.kickoff_utc, m.home_name, m.away_name, l.name league,
                  (SELECT ext_id FROM ext_event x WHERE x.match_id=b.match_id AND x.source='superbet') sb_event_id
           FROM sb_boost b JOIN match m ON m.id=b.match_id LEFT JOIN league l ON l.id=m.league_id
           WHERE m.kickoff_utc > ? AND m.kickoff_utc <= ? AND b.last_seen >= ? ORDER BY COALESCE(b.ev, -9) DESC""",
        (lo, hi, (now - timedelta(hours=30)).isoformat()[:19] + "Z")).fetchall()
    items = [{"match_id": r["match_id"], "home": r["home_name"], "away": r["away_name"], "league": r["league"], "kickoff_utc": r["kickoff_utc"],
              "kind": r["kind"], "label": r["name"] if r["kind"] != "super_cota" else f"Super Cota {r['name'].replace('SC-', '')}",
              "info": r["info"], "price": r["price"], "orig_price": r["orig_price"], "boost_pct": round(r["price"] / r["orig_price"] - 1, 3) if r["orig_price"] else None,
              "p_fair": r["p_fair"], "ev": r["ev"], "method": r["method"], "reliable": (r["method"] or "").startswith(("piață", "model")),
              "sb_event_id": r["sb_event_id"]} for r in rows]
    return {"generated_at": now.isoformat()[:19] + "Z", "count": len(items), "positive_ev": sum(1 for i in items if (i["ev"] or -1) > 0),
            "boosts": items, "stats": stats(conn),
            "rules": "Superbet: cotele mărite se pot pune pe acumulator; SuperAvantaj nu se aplică; nu contează la Super Bonus."}


TICKET_KIND, TICKET_VARIANT, TICKET_STAKE = "acca_boost", "cote_marite", 0.10


def build_ticket(conn: sqlite3.Connection, today: date, now: Optional[datetime] = None, max_legs: int = 3) -> Dict[str, Any]:
    """Bilet „Cote mărite +EV”: până la 3 cote mărite cu EV>0 și probabilitate sigură/model, meciuri diferite
    (cotele mărite se pot combina pe acumulator; fără SuperAvantaj)."""
    from betpredict.store import repo

    ensure(conn)
    if conn.execute("SELECT COUNT(*) FROM ticket WHERE day=? AND variant=? AND status!='replaced'", (today.isoformat(), TICKET_VARIANT)).fetchone()[0]:
        return {"skipped_existing": True}
    doc = today_doc(conn, now)
    legs, seen = [], set()
    for b in doc["boosts"]:
        if (b["ev"] or -1) > 0 and b["reliable"] and b["match_id"] not in seen:
            legs.append(b)
            seen.add(b["match_id"])
        if len(legs) >= max_legs:
            break
    if not legs:
        return {"tickets": 0, "reason": "nicio cotă mărită cu EV>0 sigur/model"}
    total = math.prod(b["price"] for b in legs)
    p = math.prod(b["p_fair"] for b in legs)
    notes = {"risk_acknowledged": True, "boost": True, "label": "Cote mărite +EV",
             "reasons": [f"Cote mărite Superbet cu EV pozitiv: {len(legs)} selecții, șansă {p:.1%}, EV {p * total - 1:+.1%}",
                         "Probabilitate din piață (Pinnacle + consens) sau model Poisson cu λ din piață; fără SuperAvantaj."]}
    with conn:
        cur = conn.execute(
            """INSERT INTO ticket (kind, variant, created_by, target_odds, total_odds, p_ticket, ev, stake, status, created_at, notes, day)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (TICKET_KIND, TICKET_VARIANT, "robot", round(total, 2), round(total, 2), round(p, 6), round(p * total - 1, 4), TICKET_STAKE,
             "pending", repo.now_iso(), json.dumps(notes, ensure_ascii=False), today.isoformat()))
        for b in legs:
            conn.execute("INSERT INTO ticket_leg (ticket_id, prediction_id, match_id, market, selection, odds, odds_source) VALUES (?,?,?,?,?,?,?)",
                         (cur.lastrowid, None, b["match_id"], "boost|0", b["label"], b["price"], "superbet"))
    return {"tickets": 1, "legs": len(legs), "odds": round(total, 2), "ev": round(p * total - 1, 4)}


def settle_legs(conn: sqlite3.Connection) -> int:
    n = 0
    for l in conn.execute("SELECT rowid rid, match_id, selection FROM ticket_leg WHERE market='boost|0' AND result IS NULL").fetchall():
        name = l["selection"].replace("Super Cota ", "SC-") if l["selection"].startswith("Super Cota ") else l["selection"]
        r = conn.execute("SELECT result FROM sb_boost WHERE match_id=? AND name=? AND result IN ('won','lost','void')",
                         (l["match_id"], name)).fetchone()
        if r:
            conn.execute("UPDATE ticket_leg SET result=? WHERE rowid=?", (r[0], l["rid"]))
            n += 1
    return n
