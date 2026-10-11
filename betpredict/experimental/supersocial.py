"""„Stil Supersocial”: test înainte (forward/paper) cu prețuri REALE Superbet pentru tiparele tipsterului.

Piețe (din oferta publică Superbet, sb_offer): interval goluri 2–4 / 2–5 / 1–3, gol în ambele reprize, R1 Peste 0.5 & final
Peste 1.5, interval 1–3 în fiecare repriză, total cornere 7.5/8.5/9.5. Prețurile se salvează zilnic (ss_price).
Probabilitate: λ robot (match_model) → Poisson pe reprize (cota R1 0.446 din football-data) + corecția de frecvență
măsurată pe 38k meciuri (Poisson subestimează aceste piețe cu 0.8–2.4 pp). Cornerele se salvează, dar nu intră pe bilete
(nu avem cornere pentru decontare în feedul nostru). Biletele sunt EXPERIMENTALE (paper), miză fixă mică."""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from betpredict.lab.patterns import _probs, _won
from betpredict.timeutil import canon_utc

KIND, VARIANT = "acca_stil", "stil_supersocial"
STAKE_U = 0.05
H1_SHARE = 0.446
MIN_LEGS, MAX_LEGS = 10, 15
BAND = (1.20, 2.20)
MIN_EDGE = -0.08
MAX_TICKETS_PER_MATCH = 2
MAX_PER_KEY = 5  # biletele mixte: cel mult 5 selecții din aceeași piață (diversificare)
# (nume piață Superbet, rezultat) → cheie
MARKETS: Dict[Tuple[str, str], str] = {
    ("Interval goluri", "2-4"): "G24", ("Interval goluri", "2-5"): "G25", ("Interval goluri", "1-3"): "G13",
    ("Gol marcat în ambele reprize", "Da"): "R1R2",
    ("Total goluri prima repriză & Total goluri", "Peste 0.5 & Peste 1.5"): "R1O15",
    ("Interval goluri în fiecare repriză", "1-3"): "H13x2",
    ("Total cornere", "Peste 7.5"): "C75", ("Total cornere", "Peste 8.5"): "C85", ("Total cornere", "Peste 9.5"): "C95",
}
LABELS = {"G24": "Interval goluri 2-4", "G25": "Interval goluri 2-5", "G13": "Interval goluri 1-3",
          "R1R2": "Gol în ambele reprize", "R1O15": "R1 Peste 0.5 & Peste 1.5", "H13x2": "1-3 goluri în fiecare repriză",
          "C75": "Cornere Peste 7.5", "C85": "Cornere Peste 8.5", "C95": "Cornere Peste 9.5"}
# corecția Poisson → frecvență reală (pp), măsurată în laborator (football-data 2021–2026)
BIAS = {"R1R2": 0.018, "H13x2": 0.024, "R1O15": 0.012, "G24": 0.008, "G25": 0.009, "G13": 0.0}
TICKETS = (
    ("Goluri 2–4 / 2–5", ("G24", "G25")),
    ("Goluri 1–3 & reprize", ("G13", "R1R2", "R1O15", "H13x2")),
    ("Mix Supersocial", ("G24", "G25", "G13", "R1R2", "R1O15", "H13x2")),
)

SCHEMA = """CREATE TABLE IF NOT EXISTS ss_price (
  match_id INTEGER NOT NULL, mkey TEXT NOT NULL, day TEXT NOT NULL, price_first REAL NOT NULL, price_last REAL NOT NULL,
  first_at TEXT NOT NULL, last_at TEXT NOT NULL, PRIMARY KEY (match_id, mkey, day))"""


def snapshot(conn: sqlite3.Connection, now: Optional[datetime] = None) -> int:
    """Instantaneu zilnic al prețurilor Superbet pentru piețele de mai sus (primul și ultimul preț al zilei)."""
    conn.execute(SCHEMA)
    day = (now or datetime.now(timezone.utc)).date().isoformat()
    n = 0
    with conn:
        for (mname, out), key in MARKETS.items():
            for r in conn.execute("SELECT match_id, price, observed_at FROM sb_offer WHERE market_name=? AND outcome=?", (mname, out)).fetchall():
                conn.execute(
                    "INSERT INTO ss_price VALUES (?,?,?,?,?,?,?) ON CONFLICT(match_id, mkey, day) DO UPDATE SET "
                    "price_last=excluded.price_last, last_at=excluded.last_at",
                    (r[0], key, day, r[1], r[1], r[2], r[2]))
                n += 1
    return n


def model_p(lh: float, la: float) -> Dict[str, float]:
    p = _probs(lh, la, H1_SHARE, None)
    return {k: min(0.995, p[k] + BIAS.get(k, 0.0)) for k in BIAS}


def candidates(conn: sqlite3.Connection, now: datetime, horizon_h: int = 60) -> List[Dict[str, Any]]:
    lo, hi = canon_utc(now.isoformat()), canon_utc((now + timedelta(hours=horizon_h)).isoformat())
    rows = conn.execute(
        """SELECT m.id, m.kickoff_utc, m.home_name, m.away_name, mm.lambda_home lh, mm.lambda_away la
           FROM match m JOIN match_model mm ON mm.match_id = m.id
           WHERE m.kickoff_utc > ? AND m.kickoff_utc <= ? AND mm.lambda_home IS NOT NULL""", (lo, hi)).fetchall()
    out = []
    for r in rows:
        ps = model_p(r["lh"], r["la"])
        offers = {MARKETS[(o["market_name"], o["outcome"])]: o["price"] for o in conn.execute(
            "SELECT market_name, outcome, price FROM sb_offer WHERE match_id=?", (r["id"],)) if (o["market_name"], o["outcome"]) in MARKETS}
        for k, p in ps.items():
            price = offers.get(k)
            if price and BAND[0] <= price <= BAND[1]:
                out.append({"match_id": r["id"], "key": k, "p": p, "odds": price, "edge": p * price - 1, "kickoff_utc": r["kickoff_utc"]})
    return out


def build(conn: sqlite3.Connection, today: date, now: Optional[datetime] = None, replace: bool = False) -> Dict[str, Any]:
    from betpredict.store import repo

    now = now or datetime.now(timezone.utc)
    conn.execute(SCHEMA)
    rep: Dict[str, Any] = {"snapshot_rows": snapshot(conn, now)}
    have = conn.execute("SELECT COUNT(*) FROM ticket WHERE day=? AND variant=? AND status!='replaced'", (today.isoformat(), VARIANT)).fetchone()[0]
    if have and not replace:
        rep["skipped_existing"] = True
        return rep
    cands = candidates(conn, now)
    rep["candidates"] = len(cands)
    used_match: Dict[int, int] = {}
    used_sel: set = set()
    made = []
    with conn:
        if have:
            conn.execute("UPDATE ticket SET status='replaced' WHERE day=? AND variant=? AND status='pending'", (today.isoformat(), VARIANT))
        for name, keys in TICKETS:
            legs, per_key, in_t = [], {}, set()
            for c in sorted(cands, key=lambda c: -c["edge"]):
                if c["key"] not in keys or c["edge"] < MIN_EDGE or (c["match_id"], c["key"]) in used_sel or c["match_id"] in in_t:
                    continue
                if used_match.get(c["match_id"], 0) >= MAX_TICKETS_PER_MATCH:
                    continue
                if len(keys) > 2 and per_key.get(c["key"], 0) >= MAX_PER_KEY:
                    continue
                legs.append(c)
                in_t.add(c["match_id"])
                per_key[c["key"]] = per_key.get(c["key"], 0) + 1
                if len(legs) >= MAX_LEGS:
                    break
            if len(legs) < MIN_LEGS:
                continue
            total = math.prod(c["odds"] for c in legs)
            p = math.prod(c["p"] for c in legs)
            notes = {"experimental": True, "paper": True, "risk_acknowledged": True, "stil": name,
                     "label": f"Stil Supersocial · {name}",
                     "reasons": [f"Stil Supersocial · {name} · {len(legs)} selecții, prețuri reale Superbet",
                                 f"Șansă model {p:.2%} · EV model {p * total - 1:+.0%} (corecție Poisson inclusă)",
                                 "EXPERIMENTAL / paper: test înainte, fără istoric de prețuri; miză fixă mică."]}
            cur = conn.execute(
                """INSERT INTO ticket (kind, variant, created_by, target_odds, total_odds, p_ticket, ev, stake, status, created_at, notes, day)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (KIND, VARIANT, "robot", round(total, 2), round(total, 2), round(p, 6), round(p * total - 1, 4), STAKE_U, "pending",
                 repo.now_iso(), json.dumps(notes, ensure_ascii=False), today.isoformat()))
            for c in sorted(legs, key=lambda c: c["kickoff_utc"]):
                conn.execute("INSERT INTO ticket_leg (ticket_id, prediction_id, match_id, market, selection, odds, odds_source) VALUES (?,?,?,?,?,?,?)",
                             (cur.lastrowid, None, c["match_id"], "ss|0", c["key"], c["odds"], "superbet"))
                used_sel.add((c["match_id"], c["key"]))
                used_match[c["match_id"]] = used_match.get(c["match_id"], 0) + 1
            made.append({"name": name, "legs": len(legs), "odds": round(total, 2), "ev_model": round(p * total - 1, 3)})
    rep["tickets"] = made
    return rep


def settle_legs(conn: sqlite3.Connection) -> int:
    """Decontare reală a selecțiilor Stil Supersocial din scorul final + pauză (void la meci anulat/amânat)."""
    from betpredict.ingest.normalize import VOID_STATUSES

    n = 0
    for l in conn.execute(
            """SELECT tl.rowid rid, tl.selection, m.status, m.ft_home, m.ft_away, m.ht_home, m.ht_away, m.corners_home, m.corners_away
               FROM ticket_leg tl JOIN match m ON m.id = tl.match_id WHERE tl.market='ss|0' AND tl.result IS NULL""").fetchall():
        if l["status"] in VOID_STATUSES:
            res = "void"
        elif l["status"] == "finished" and l["ft_home"] is not None and l["ht_home"] is not None:
            if l["selection"].startswith("C") and l["corners_home"] is None:
                continue
            r = {"fthg": l["ft_home"], "ftag": l["ft_away"], "hthg": l["ht_home"], "htag": l["ht_away"],
                 "hc": l["corners_home"], "ac": l["corners_away"]}
            res = "won" if _won(l["selection"], r) else "lost"
        else:
            continue
        conn.execute("UPDATE ticket_leg SET result=? WHERE rowid=?", (res, l["rid"]))
        n += 1
    return n


def live_stats(conn: sqlite3.Connection) -> Dict[str, Any]:
    out: Dict[str, Dict[str, Any]] = {}
    for t in conn.execute("SELECT status, stake, payout, notes FROM ticket WHERE variant=? AND status!='replaced'", (VARIANT,)):
        name = json.loads(t["notes"] or "{}").get("stil", "?")
        r = out.setdefault(name, {"n": 0, "won": 0, "lost": 0, "pending": 0, "staked_u": 0.0, "profit_u": 0.0})
        r["n"] += 1
        st = t["status"] if t["status"] in ("won", "lost") else "pending"
        r[st] += 1
        if st != "pending":
            r["staked_u"] = round(r["staked_u"] + (t["stake"] or 0), 2)
            r["profit_u"] = round(r["profit_u"] + (t["payout"] or 0) - (t["stake"] or 0), 2)
    legs = conn.execute("""SELECT selection, COUNT(*) n, SUM(result='won') w, AVG(odds) o FROM ticket_leg
                           WHERE market='ss|0' AND result IN ('won','lost') GROUP BY selection""").fetchall()
    return {"tickets": out, "legs": {r["selection"]: {"n": r["n"], "won": r["w"], "hit": round(r["w"] / r["n"], 3), "avg_odds": round(r["o"], 2),
                                                       "roi_single": round(r["w"] / r["n"] * r["o"] - 1, 3)} for r in legs}}
