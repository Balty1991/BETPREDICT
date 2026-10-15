"""Proiectul Egaluri: egaluri la care Superbet plătește peste mediana pieței.

Regula de bază (aleasă pe istoric Bet365): egal 2,80–3,60, cu cel puțin 2% peste mediana pieței.
Verificată din nou pe football-data (48.000 de meciuri, 7 sezoane, cea mai bună cotă din piață, împărțit
antrenare până în 06.2024 / test după): egalul „simplu” în bandă iese pe zero (+0,5%). Pe plus în ambele
perioade ies doar meciurile în care, pe lângă prețul bun, piața așteaptă puține goluri (Peste 2,5 cotat de la 2,00)
și echipele sunt apropiate (cotele 1 și 2 la cel mult ~35% una de alta): +5% antrenare, +3% test.
Acestea sunt „egalurile A”. Restul celor din banda de bază sunt „de urmărit” (B).

Biletul are două egaluri A din aceeași zi. Biletele în joc nu se mai înlocuiesc; un bilet neînceput se
reface doar dacă unul din meciuri a ieșit din regulă. Toate egalurile A/B sunt urmărite (sd_track), ca
regula să fie judecată și pe prețurile reale Superbet, nu doar pe istoric.
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
# egalul A: preț bun + meci strâns și cu puține goluri așteptate (istoric: pe plus în ambele perioade)
A_GAP = 0.03
A_O25 = 2.00   # cota de consens Peste 2,5 (cu marjă), ca în football-data
A_BAL = 0.30   # |ln(cota 1 / cota 2)|
# ligi alese DOAR pe perioada de antrenare (egal A cu ROI > 3% pe ≥ 80 de meciuri până în 06.2024); pe perioada
# de test aceste ligi au dat +6,6% (826 meciuri), restul −1,6% (656). Ligile engleze 2–4 și Scoția 1 au ieșit
# pe minus în ambele perioade: acolo un egal A rămâne doar „de urmărit”.
GOOD_DIVS = {"I1", "I2", "SP1", "SP2", "F2", "P1", "T1", "G1", "SC1"}
BAD_DIVS = {"E0", "E1", "E2", "SC0"}
# egal la pauză (Superbet „Prima repriză - 1X2: Egal”), testat 15.10.2026: rata pe istoric după Peste 2,5 și echilibru
# vs. prețul Superbet pe 233 de meciuri: EV mediu −9,5%. Nu merită; nu intră în proiect.
TRACK = """CREATE TABLE IF NOT EXISTS sd_track (
  match_id INTEGER PRIMARY KEY, tier TEXT NOT NULL, odds_first REAL NOT NULL, odds REAL NOT NULL, median REAL,
  o25 REAL, bal REAL, gap REAL, first_at TEXT NOT NULL, last_at TEXT NOT NULL, kickoff_utc TEXT NOT NULL, result TEXT)"""
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
        """SELECT m.id, m.kickoff_utc, m.home_name, m.away_name, m.league_id, l.name AS league, x.ext_id AS sb_id
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
    ou = market_key("over_under", 2.5, "FT")
    divs = league_divs(conn)
    out = []
    for r in rows:
        odds = ((sb.get(r["id"]) or {}).get(key) or {}).get("DRAW")
        cons = (med.get(r["id"]) or {}).get(key) or {}
        mid = cons.get("DRAW")
        if not odds or not mid or mid <= 1 or not (ODDS_LO <= odds < ODDS_HI):
            continue
        gap = _gap(odds, mid)
        if gap < MIN_GAP:
            continue
        o25 = ((med.get(r["id"]) or {}).get(ou) or {}).get("OVER")
        h, a = cons.get("HOME"), cons.get("AWAY")
        bal = abs(math.log(h / a)) if h and a and h > 1 and a > 1 else None
        tier = "A" if gap >= A_GAP and o25 and o25 >= A_O25 and bal is not None and bal < A_BAL else "B"
        div = divs.get(r["league_id"])
        league_tag = "bună" if div in GOOD_DIVS else "slabă" if div in BAD_DIVS else None
        if tier == "A" and league_tag == "slabă":
            tier = "B"  # pe istoric ligile astea au pierdut și la egalurile A
        day = ro_date_of(r["kickoff_utc"])
        from betpredict.publish.day import superbet_url

        sb_url = superbet_url(r["home_name"], r["away_name"], r["sb_id"]) if r["sb_id"] else None
        out.append({
            "match_id": r["id"], "kickoff_utc": r["kickoff_utc"], "day": day.isoformat() if day else None,
            "home": r["home_name"], "away": r["away_name"], "league": r["league"],
            "odds": round(odds, 3), "median": round(mid, 3), "gap": round(gap, 4),
            "o25": round(o25, 2) if o25 else None, "bal": round(bal, 3) if bal is not None else None, "tier": tier, "league_tag": league_tag,
            "superbet_url": sb_url,
        })
    out.sort(key=lambda c: (c["day"] or "", c["tier"], c["league_tag"] != "bună", -c["gap"]))
    return out


def league_divs(conn: sqlite3.Connection) -> Dict[Any, str]:
    """Liga noastră → diviziunea football-data, din meciurile legate."""
    try:
        return {r[0]: r[1] for r in conn.execute("""SELECT m.league_id, f.div FROM fd_match f JOIN match m ON m.id=f.match_id
                                                     WHERE m.league_id IS NOT NULL GROUP BY m.league_id""")}
    except sqlite3.OperationalError:
        return {}


def track(conn: sqlite3.Connection, cands: List[Dict[str, Any]], now: datetime) -> int:
    """Ține minte fiecare egal A/B (prima cotă văzută și ultima înainte de start), ca să fie judecat la final."""
    conn.execute(TRACK)
    stamp = canon_utc(now.isoformat())
    with conn:
        for c in cands:
            conn.execute(
                """INSERT INTO sd_track (match_id, tier, odds_first, odds, median, o25, bal, gap, first_at, last_at, kickoff_utc)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(match_id) DO UPDATE SET tier=excluded.tier, odds=excluded.odds, median=excluded.median,
                     o25=excluded.o25, bal=excluded.bal, gap=excluded.gap, last_at=excluded.last_at
                   WHERE sd_track.result IS NULL AND sd_track.kickoff_utc > excluded.last_at""",
                (c["match_id"], c["tier"], c["odds"], c["odds"], c["median"], c["o25"], c["bal"], c["gap"], stamp, stamp, c["kickoff_utc"]))
    return len(cands)


def settle_track(conn: sqlite3.Connection) -> int:
    from betpredict.ingest.normalize import VOID_STATUSES

    conn.execute(TRACK)
    n = 0
    with conn:
        for r in conn.execute("""SELECT s.match_id, m.status, m.ft_home, m.ft_away FROM sd_track s JOIN match m ON m.id=s.match_id
                                 WHERE s.result IS NULL""").fetchall():
            if r["status"] in VOID_STATUSES:
                res = "void"
            elif r["status"] == "finished" and r["ft_home"] is not None and r["ft_away"] is not None:
                res = "won" if r["ft_home"] == r["ft_away"] else "lost"
            else:
                continue
            conn.execute("UPDATE sd_track SET result=? WHERE match_id=?", (res, r["match_id"]))
            n += 1
    return n


def live_record(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Rezultatele reale pe prețurile Superbet: pe egaluri A/B (miză 1 pe fiecare) și pe biletele de două egaluri."""
    conn.execute(TRACK)
    tiers = {}
    for tier in ("A", "B"):
        rows = conn.execute("SELECT odds, result FROM sd_track WHERE tier=? AND result IN ('won','lost')", (tier,)).fetchall()
        n, w = len(rows), sum(1 for r in rows if r["result"] == "won")
        ret = sum(r["odds"] for r in rows if r["result"] == "won")
        tiers[tier] = {"n": n, "won": w, "hit": round(w / n, 3) if n else None, "roi": round(ret / n - 1, 3) if n else None,
                       "avg_odds": round(sum(r["odds"] for r in rows) / n, 2) if n else None}
    tk = conn.execute("SELECT status, total_odds FROM ticket WHERE kind=? AND status IN ('won','lost')", (KIND,)).fetchall()
    tw = [t for t in tk if t["status"] == "won"]
    return {"singles": tiers, "tickets": {"n": len(tk), "won": len(tw),
                                         "roi": round(sum(t["total_odds"] for t in tw) / len(tk) - 1, 3) if tk else None}}


def backtest(conn: sqlite3.Connection) -> Optional[Dict[str, Any]]:
    """Regula pe football-data (cea mai bună cotă din piață la închidere): bază vs. egal A, antrenare / test, pe ligi."""
    try:
        rows = conn.execute("""SELECT f.div, f.day, f.avgc_h, f.avgc_d, f.avgc_a, f.maxc_d, f.avgc_o25, f.fthg, f.ftag, l.name AS league
                               FROM fd_match f LEFT JOIN match m ON m.id=f.match_id LEFT JOIN league l ON l.id=m.league_id
                               WHERE f.fthg IS NOT NULL AND f.avgc_d IS NOT NULL AND f.maxc_d IS NOT NULL AND f.avgc_o25 IS NOT NULL""").fetchall()
    except sqlite3.OperationalError:
        return None
    if not rows:
        return None

    def stat(sel: List[Any]) -> Optional[Dict[str, Any]]:
        if not sel:
            return None
        w = [r for r in sel if r["fthg"] == r["ftag"]]
        return {"n": len(sel), "hit": round(len(w) / len(sel), 3), "roi": round(sum(r["maxc_d"] for r in w) / len(sel) - 1, 3),
                "avg_odds": round(sum(r["maxc_d"] for r in sel) / len(sel), 2)}

    base = [r for r in rows if ODDS_LO <= r["avgc_d"] < ODDS_HI]
    a = [r for r in base if r["maxc_d"] >= r["avgc_d"] * (1 + A_GAP) and r["avgc_o25"] >= A_O25
         and abs(math.log(r["avgc_h"] / r["avgc_a"])) < A_BAL]
    split = "2024-07-01"
    by_div: Dict[str, List[Any]] = {}
    names: Dict[str, str] = {}
    for r in a:
        by_div.setdefault(r["div"], []).append(r)
        if r["league"]:
            names.setdefault(r["div"], r["league"])
    leagues = []
    for d, v in by_div.items():
        st = stat(v)
        if st and st["n"] >= 80:
            leagues.append({"div": d, "league": names.get(d, d), **st})
    for x in leagues:
        x["tag"] = "bună" if x["div"] in GOOD_DIVS else "slabă" if x["div"] in BAD_DIVS else None
    leagues.sort(key=lambda x: -x["roi"])
    good_test = stat([r for r in a if r["day"] >= split and r["div"] in GOOD_DIVS])
    rest_test = stat([r for r in a if r["day"] >= split and r["div"] not in GOOD_DIVS])
    return {"source": "football-data, 7 sezoane, cea mai bună cotă la închidere", "split": split,
            "base": {"train": stat([r for r in base if r["day"] < split]), "test": stat([r for r in base if r["day"] >= split])},
            "a": {"train": stat([r for r in a if r["day"] < split]), "test": stat([r for r in a if r["day"] >= split])},
            "leagues": leagues[:16], "good_test": good_test, "rest_test": rest_test,
            "ht_draw": "Egal la pauză testat pe 233 de meciuri cu preț Superbet: EV mediu −9,5%. Nu merită."}


def events_doc(conn: sqlite3.Connection, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    rows = candidates(conn, now)
    return {
        "schema": "betpredict.soft_draw.v2",
        "generated_at": canon_utc(now.isoformat()),
        "rule": "Egal, cotă Superbet 2,80–3,60, cu cel puțin 2% peste mediana pieței. Biletul are două meciuri din aceeași zi.",
        "rule_a": (f"Egal A: Superbet cu cel puțin {A_GAP:.0%} peste mediană, Peste 2,5 cotat de la {A_O25:.2f} (puține goluri "
                   f"așteptate) și echipe apropiate (cotele 1 și 2 la cel mult ~35% una de alta). În ligile engleze 2–4 și Scoția 1 "
                   f"rămâne B (pe istoric au pierdut); ligile „bune” intră primele pe bilete."),
        "count": len(rows),
        "count_a": sum(1 for r in rows if r["tier"] == "A"),
        "events": rows,
        "live": live_record(conn),
        "backtest": backtest(conn),
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
    """Bilete de două egaluri A din aceeași zi, cele mai bune prețuri primele. Biletele existente rămân dacă sunt încă bune:
    unul în joc nu se atinge, unul neînceput se reface doar dacă un meci a ieșit din regula A."""
    now = now or datetime.now(timezone.utc)
    found = candidates(conn, now)
    track(conn, found, now)
    a_ids = {c["match_id"] for c in found if c["tier"] == "A"}
    start = canon_utc(now.isoformat())
    kept_matches: set = set()
    dropped = 0
    with conn:
        for t in conn.execute("SELECT id FROM ticket WHERE kind=? AND status='pending'", (KIND,)).fetchall():
            legs = conn.execute("""SELECT tl.match_id, m.kickoff_utc FROM ticket_leg tl JOIN match m ON m.id=tl.match_id
                                   WHERE tl.ticket_id=?""", (t["id"],)).fetchall()
            started = any(l["kickoff_utc"] <= start for l in legs)
            if started or all(l["match_id"] in a_ids for l in legs):
                kept_matches |= {l["match_id"] for l in legs}
                continue
            conn.execute("UPDATE ticket SET status='replaced' WHERE id=?", (t["id"],))
            dropped += 1
    by: Dict[str, List[Dict[str, Any]]] = {}
    last = today + timedelta(days=MAX_DAYS - 1)
    for c in found:
        if c["tier"] != "A" or not c["day"] or c["match_id"] in kept_matches:
            continue
        day = date.fromisoformat(c["day"])
        if day < today or day > last:
            continue
        by.setdefault(c["day"], []).append(c)
    made = []
    with conn:
        for day, group in sorted(by.items()):
            ordered = sorted(group, key=lambda c: (c["league_tag"] != "bună", -c["gap"]))
            pairs = [ordered[i:i + 2] for i in range(0, len(ordered) - 1, 2)]
            for legs in pairs:
                total = math.prod(c["odds"] for c in legs)
                notes = {
                    "experimental": True, "paper": True, "risk_acknowledged": True, "soft_draw": True,
                    "label": "Proiectul Egaluri",
                    "events": legs,
                    "reasons": [
                        "Două egaluri A: Superbet peste mediana pieței, meci strâns, puține goluri așteptate.",
                        "Pe istoric (football-data, 7 sezoane) egalurile A au ieșit pe plus și la antrenare, și la test; "
                        "egalul doar „scump” ieșea pe zero.",
                        "Miză mică. Rezultatele reale pe prețurile Superbet se văd în pagina Proiectul Egaluri.",
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
    return {"events": len(found), "events_a": len(a_ids), "replaced": dropped, "tickets": made}
