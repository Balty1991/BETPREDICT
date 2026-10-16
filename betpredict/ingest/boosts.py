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
    try:
        conn.execute("ALTER TABLE sb_boost ADD COLUMN ref TEXT")  # outcomeId,sbv,uuid pentru biletul precompletat
    except sqlite3.OperationalError:
        pass


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
                    "price": price, "orig_price": orig, "level": x.get("boostLevel"),
                    "ref": f"{o.get('outcomeId')},{o.get('specialBetValue') or ''},{o.get('uuid')}" if o.get("outcomeId") is not None and o.get("uuid") else None})
    return out


def store(conn: sqlite3.Connection, mid: int, ev: Dict[str, Any], stamp: str) -> int:
    ensure(conn)
    n = 0
    for b in parse_boosts(ev):
        conn.execute(
            "INSERT INTO sb_boost (match_id, uid, kind, market_name, name, info, price, orig_price, level, first_seen, last_seen, ref) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(match_id, uid) DO UPDATE SET price=excluded.price, "
            "orig_price=COALESCE(excluded.orig_price, sb_boost.orig_price), last_seen=excluded.last_seen, "
            "ref=COALESCE(excluded.ref, sb_boost.ref)",
            (mid, b["uid"], b["kind"], b["market_name"], b["name"], b["info"], b["price"], b["orig_price"], b["level"], stamp, stamp,
             b.get("ref")))
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
    if "șuturi" in s or "cornere" in s or "cartonaș" in s or "jucător" in s or "repriz" in s or "pauz" in s or "minut" in s:
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


EV_SUSPECT = 0.25  # EV > 25% la o cotă mărită = aproape sigur probabilitate greșit modelată → suspect, nu intră în bilet
HT_SHARE = 0.45   # ~45% din goluri în prima repriză (football-data, ligi europene)


def htft_side(name: str, home: str, away: str) -> Optional[str]:
    """„X câștigă la pauză și la final” → 'H'/'A'; altfel None."""
    s = name.lower()
    if "pauz" in s and "final" in s and ("câștigă" in s or "castiga" in s):
        if home and home.lower() in s:
            return "H"
        if away and away.lower() in s:
            return "A"
    return None


def htft_prob(lh: float, la: float, side: str, n: int = 8) -> float:
    """P(conduce la pauză și câștigă la final): reprize Poisson independente, λ1 = 45% λ, λ2 = 55% λ."""
    g1, g2 = grid(lh * HT_SHARE, la * HT_SHARE, n), grid(lh * (1 - HT_SHARE), la * (1 - HT_SHARE), n)
    tot = 0.0
    for h1 in range(n):
        for a1 in range(n):
            if (h1 > a1) if side == "H" else (a1 > h1):
                p1 = g1[h1][a1]
                for h2 in range(n):
                    for a2 in range(n):
                        H, A = h1 + h2, a1 + a2
                        if (H > A) if side == "H" else (A > H):
                            tot += p1 * g2[h2][a2]
    return tot


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
    side = htft_side(b["name"] or "", home, away)
    if side:
        lam = market_lambdas(conn, b["match_id"])
        if lam:
            return htft_prob(*lam, side), "model pauză/final (λ din piață)"
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
        # și cele pauză/final marcate odinioară „nedecontabile”: acum se decontează din scorul la pauză
        for b in conn.execute("""SELECT b.*, m.status, m.ft_home, m.ft_away, m.ht_home, m.ht_away, m.home_name, m.away_name
                                 FROM sb_boost b JOIN match m ON m.id = b.match_id
                                 WHERE b.result IS NULL OR (b.result = 'unsettleable' AND b.name LIKE '%pauz%final%')""").fetchall():
            res = None
            if b["status"] in VOID_STATUSES:
                res = "void"
            elif b["status"] == "finished" and b["ft_home"] is not None:
                if b["kind"] == "super_cota":
                    h, a = b["ft_home"], b["ft_away"]
                    res = "won" if {"SC-1": h > a, "SC-X": h == a, "SC-2": a > h}.get(b["name"]) else "lost"
                elif b["kind"] == "core" and (rule := core_rule(b["name"] or "", b["home_name"] or "", b["away_name"] or "")):
                    res = "won" if rule(b["ft_home"], b["ft_away"]) else "lost"
                elif (side := htft_side(b["name"] or "", b["home_name"] or "", b["away_name"] or "")):
                    if b["ht_home"] is None or b["ht_away"] is None:
                        continue  # scorul la pauză vine mai târziu
                    h1, a1, h, a = b["ht_home"], b["ht_away"], b["ft_home"], b["ft_away"]
                    ok = (h1 > a1 and h > a) if side == "H" else (a1 > h1 and a > h)
                    res = "won" if ok else "lost"
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
              "p_fair": r["p_fair"], "ev": r["ev"], "method": r["method"], "reliable": (r["method"] or "").startswith(("piață", "model")) and (r["ev"] or 0) <= EV_SUSPECT,
              "suspect": (r["ev"] or 0) > EV_SUSPECT,
              "sb_event_id": r["sb_event_id"]} for r in rows]
    return {"generated_at": now.isoformat()[:19] + "Z", "count": len(items), "positive_ev": sum(1 for i in items if (i["ev"] or -1) > 0),
            "boosts": items, "stats": stats(conn),
            "rules": "Superbet: cotele mărite se pot pune pe acumulator; SuperAvantaj nu se aplică; nu contează la Super Bonus."}


TICKET_KIND, TICKET_VARIANT, TICKET_STAKE = "acca_boost", "cote_marite", 0.10


# Cotele mărite cu EV>0 (piață sau model) au ieșit pe plus pe rezultatele reale (11–15.10.2026: 62 de pariuri, ROI +24%;
# „Cote mărite” pe piețe obișnuite +47% pe 42). Duble (cotă ~5–11) și un triplu din cele mai bune 3; fără simple:
# cota de ~2.5 pe un singur meci nu se joacă la o bancă mică (doar în piramide).
MAX_SINGLES, MAX_DOUBLES, MAX_TRIPLES = 0, 0, 2
MIN_ACCA_ODDS = 20.0  # în listă intră doar biletele de la cota 20


def build_ticket(conn: sqlite3.Connection, today: date, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Cote mărite +EV: bilete simple (cele mai bune 5) și duble (perechi din meciuri diferite, cel mult 3), adăugate pe
    parcursul zilei pe măsură ce apar cote noi; o cotă nu intră de două ori în același fel de bilet."""
    from betpredict.store import repo

    ensure(conn)
    doc = today_doc(conn, now)
    pool = [b for b in doc["boosts"] if (b["ev"] or -1) > 0 and b["reliable"]]
    if not pool:
        return {"tickets": 0, "reason": "nicio cotă mărită cu EV>0 sigur/model"}
    have_single, have_double, in_double, n_double, n_triple = set(), set(), set(), 0, 0
    start = now.isoformat()[:19] + "Z" if now else datetime.now(timezone.utc).isoformat()[:19] + "Z"
    with conn:
        for t in conn.execute("SELECT id, notes FROM ticket WHERE day=? AND variant=? AND status='pending'", (today.isoformat(), TICKET_VARIANT)).fetchall():
            legs = conn.execute("SELECT l.match_id, m.kickoff_utc FROM ticket_leg l JOIN match m ON m.id=l.match_id WHERE l.ticket_id=?", (t[0],)).fetchall()
            if MAX_SINGLES == 0 and len(legs) == 1 and legs[0][1] > start:  # simplele de dinainte, încă neîncepute
                conn.execute("UPDATE ticket SET status='replaced' WHERE id=?", (t[0],))
    for t in conn.execute("SELECT id, notes FROM ticket WHERE day=? AND variant=? AND status!='replaced'", (today.isoformat(), TICKET_VARIANT)):
        legs = tuple(sorted((r[0], r[1]) for r in conn.execute("SELECT match_id, selection FROM ticket_leg WHERE ticket_id=?", (t[0],))))
        if len(legs) == 1:
            have_single.add(legs[0])
        elif len(legs) == 2:
            have_double.add(legs); in_double.update(legs); n_double += 1
        elif len(legs) >= 3:
            n_triple += 1
    made = []

    def _add(legs: List[Dict[str, Any]], kind: str) -> None:
        total = math.prod(b["price"] for b in legs)
        p = math.prod(b["p_fair"] for b in legs)
        notes = {"risk_acknowledged": True, "boost": True, "boost_type": kind, "label": f"Cote mărite +EV · {kind}",
                 "reasons": [f"Cote mărite Superbet cu EV pozitiv, bilet {kind}: șansă {p:.1%}, EV {p * total - 1:+.1%}.",
                             "Probabilitate din piață (Pinnacle + consens) sau model Poisson cu λ din piață; fără SuperAvantaj.",
                             "Pe rezultatele reale cotele mărite +EV au ieșit pe plus; simple și duble ca să iasă verde mai des."]}
        cur = conn.execute(
            """INSERT INTO ticket (kind, variant, created_by, target_odds, total_odds, p_ticket, ev, stake, status, created_at, notes, day)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (TICKET_KIND, TICKET_VARIANT, "robot", round(total, 2), round(total, 2), round(p, 6), round(p * total - 1, 4), TICKET_STAKE,
             "pending", repo.now_iso(), json.dumps(notes, ensure_ascii=False), today.isoformat()))
        for b in legs:
            conn.execute("INSERT INTO ticket_leg (ticket_id, prediction_id, match_id, market, selection, odds, odds_source) VALUES (?,?,?,?,?,?,?)",
                         (cur.lastrowid, None, b["match_id"], "boost|0", b["label"], b["price"], "superbet"))
        made.append({"type": kind, "odds": round(total, 2), "ev": round(p * total - 1, 4)})

    with conn:
        for b in pool[:MAX_SINGLES]:
            if (b["match_id"], b["label"]) not in have_single:
                _add([b], "simplu")
        free = [b for b in pool if (b["match_id"], b["label"]) not in in_double]
        while n_double < MAX_DOUBLES and len(free) >= 2:
            a = free.pop(0)
            j = next((i for i, x in enumerate(free) if x["match_id"] != a["match_id"]), None)
            if j is None:
                break
            b = free.pop(j)
            key = tuple(sorted(((a["match_id"], a["label"]), (b["match_id"], b["label"]))))
            if key in have_double:
                continue
            _add([a, b], "dublu")
            n_double += 1
        # bilete de la cota 20: cele mai bune cote mărite, 3 (sau 4, dacă 3 nu ajung la 20), fiecare bilet cu alte meciuri
        used_m = {r[0] for r in conn.execute(
            """SELECT l.match_id FROM ticket_leg l JOIN ticket t ON t.id=l.ticket_id
               WHERE t.day=? AND t.variant=? AND t.status!='replaced'""", (today.isoformat(), TICKET_VARIANT))}
        rest = [b for b in pool if b["match_id"] not in used_m]
        while n_triple < MAX_TRIPLES:
            top, seen = [], set()
            for b in rest:
                if b["match_id"] in seen:
                    continue
                top.append(b); seen.add(b["match_id"])
                if len(top) >= 3 and math.prod(x["price"] for x in top) >= MIN_ACCA_ODDS or len(top) == 4:
                    break
            if len(top) < 3 or math.prod(x["price"] for x in top) < MIN_ACCA_ODDS:
                break
            _add(top, "triplu" if len(top) == 3 else "4 cote")
            n_triple += 1
            rest = [b for b in rest if b["match_id"] not in seen]
    return {"tickets": len(made), "made": made}


def settle_legs(conn: sqlite3.Connection) -> int:
    n = 0
    for l in conn.execute("SELECT rowid rid, match_id, selection FROM ticket_leg WHERE market='boost|0' AND result IS NULL").fetchall():
        name = l["selection"].replace("Super Cota ", "SC-") if l["selection"].startswith("Super Cota ") else l["selection"]
        r = conn.execute("SELECT result FROM sb_boost WHERE match_id=? AND name=? AND result IN ('won','lost','void','unsettleable')",
                         (l["match_id"], name)).fetchone()
        if r:
            # o selecție fără date de decontare nu ține biletul blocat la nesfârșit: contează ca anulată
            conn.execute("UPDATE ticket_leg SET result=? WHERE rowid=?", ("void" if r[0] == "unsettleable" else r[0], l["rid"]))
            n += 1
    return n


def _grp(conn: sqlite3.Connection, cond: str) -> Dict[str, Any]:
    r = conn.execute(f"""SELECT COUNT(*) n, SUM(result='won') w, SUM(result='lost') l, SUM(result IS NULL) p,
                                SUM(result='unsettleable') u, SUM(CASE WHEN result='won' THEN price ELSE 0 END) ret
                         FROM sb_boost WHERE {cond}""").fetchone()
    s = (r["w"] or 0) + (r["l"] or 0)
    return {"total": r["n"] or 0, "won": r["w"] or 0, "lost": r["l"] or 0, "pending": r["p"] or 0, "unsettleable": r["u"] or 0,
            "hit_rate": round((r["w"] or 0) / s, 3) if s else None, "roi": round((r["ret"] or 0) / s - 1, 3) if s else None}


def history_doc(conn: sqlite3.Connection, limit: int = 60) -> Dict[str, Any]:
    """Statistici „Cote mărite”: pe tip, subset EV>0, listă recentă, rezultatele biletului „Cote mărite +EV” (ROI la cota mărită, miză 1)."""
    ensure(conn)
    groups = {"toate": "1=1", "ev_pozitiv": "ev > 0", "super_cota": "kind='super_cota'",
              "model": "kind!='super_cota' AND method LIKE 'model%'", "estimat": "method LIKE 'incert%'"}
    recent = [{"match_id": r["match_id"], "home": r["home_name"], "away": r["away_name"], "kickoff_utc": r["kickoff_utc"], "kind": r["kind"],
               "label": r["name"] if r["kind"] != "super_cota" else f"Super Cota {r['name'].replace('SC-', '')}",
               "price": r["price"], "orig_price": r["orig_price"], "ev": r["ev"], "method": r["method"], "result": r["result"],
               "score": f"{r['ft_home']}-{r['ft_away']}" if r["ft_home"] is not None else None}
              for r in conn.execute("""SELECT b.*, m.home_name, m.away_name, m.kickoff_utc, m.ft_home, m.ft_away FROM sb_boost b
                                       JOIN match m ON m.id=b.match_id ORDER BY m.kickoff_utc DESC LIMIT ?""", (limit,))]
    tk = conn.execute("""SELECT day, total_odds, stake, status, ev, (SELECT COUNT(*) FROM ticket_leg l WHERE l.ticket_id=t.id) legs
                         FROM ticket t WHERE variant=? AND status!='replaced' ORDER BY day DESC""", (TICKET_VARIANT,)).fetchall()
    st = [t for t in tk if t["status"] in ("won", "lost")]
    stake = sum(t["stake"] or 0 for t in st)
    ret = sum((t["stake"] or 0) * t["total_odds"] for t in st if t["status"] == "won")
    return {"generated_at": datetime.now(timezone.utc).isoformat()[:19] + "Z",
            "groups": {k: _grp(conn, v) for k, v in groups.items()}, "recent": recent,
            "ticket": {"n": len(st), "won": sum(t["status"] == "won" for t in st), "pending": sum(t["status"] == "pending" for t in tk),
                       "roi": round(ret / stake - 1, 3) if stake else None,
                       "list": [dict(t) for t in tk[:30]]}}
