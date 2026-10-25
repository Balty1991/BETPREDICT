"""Biletele lui Ștefan: selecțiile lui reale, decontate din datele noastre și comparate cu robotul.

Surse: ``data/stefan_tickets.json`` (capturi) + linkurile de share Superbet (``data/stefan_links.txt``,
``stefan_links.py``); cum se adaugă bilete: ``docs/stefan_tickets.md``.
Pentru fiecare selecție vizibilă căutăm meciul (nume + zi), o decontăm din rezultatul nostru (goluri, cornere R1,
cornere pe echipă) și punem alături șansa robotului. „Următoarele 10 minute” e piață live: fără cornere pe minut
în date, rămâne „nesettlabil”. Nu e strategie: doar măsurăm dacă piețele lui intră mai des decât spune cota.
"""
from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from betpredict.timeutil import canon_utc

JSON_PATH = Path(__file__).resolve().parents[2] / "data" / "stefan_tickets.json"
MARGIN = 1.05  # ca în supersocial: șansa corectă ≈ (1/cotă) / 1.05
MIN_SIM = 0.65
LABELS = {"H1C_3_6": "Cornere R1 3–6 (BB)", "G14": "Interval goluri 1-4", "G15": "Interval goluri 1-5",
          "G25": "Interval goluri 2-5", "EACH_C3": "Fiecare echipă 3+ cornere", "NEXT10_C05": "Corner în 10 min (live)",
          "BB_H1O05_O15": "Gol R1 + Peste 1.5 (BB)", "H1O05": "Gol în R1 (Peste 0.5)", "O15": "Peste 1.5 goluri", "O25": "Peste 2.5 goluri"}
OVER = {"O15": 2, "O25": 3}
H1_SHARE = 0.45  # cât din golurile așteptate cad în prima repriză (aprox. standard)
GOALS = {"G14": (1, 4), "G15": (1, 5), "G25": (2, 5)}
SS_KEY = {"H1C_3_6": "BB_H1C25_U65", "G25": "G25"}  # aceeași piață în urmărirea Stil


def load(path: Path = JSON_PATH) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"tickets": []}


def _d(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def find_match(conn: sqlite3.Connection, home: str, away: str, kickoff: Optional[str], posted: Optional[str]) -> Optional[sqlite3.Row]:
    from betpredict.ingest.superbet import name_sim

    k, p = _d(kickoff), _d(posted)
    if k:
        lo, hi, ref = k - timedelta(hours=3), k + timedelta(hours=3), k
    elif p:
        lo, hi, ref = p - timedelta(days=2), p + timedelta(days=3), p + timedelta(hours=12)
    else:
        return None
    best, key = None, (0.0, 0.0)
    cur = conn.cursor()
    cur.row_factory = sqlite3.Row  # nu schimbăm conexiunea comună a pipeline-ului
    for m in cur.execute("SELECT * FROM match WHERE kickoff_utc BETWEEN ? AND ?", (canon_utc(lo.isoformat()), canon_utc(hi.isoformat()))):
        a, b = name_sim(home, m["home_name"] or ""), name_sim(away, m["away_name"] or "")
        s = (a + b) / 2 if max(a, b) >= 0.9 and min(a, b) >= 0.3 else 0.0
        kk = _d(m["kickoff_utc"])
        near = -abs((kk - ref).total_seconds()) if kk else -1e12
        if s >= MIN_SIM and (s, near) > key:
            best, key = m, (s, near)
    return best


def settle(market: str, m: Optional[sqlite3.Row]) -> str:
    """won / lost / pending / nesettlabil / negasit (meciul nu e în baza noastră)."""
    if market == "NEXT10_C05":
        return "nesettlabil"
    if m is None:
        return "negasit"
    if market in GOALS:
        if m["ft_home"] is None or m["ft_away"] is None:
            return "pending"
        lo, hi = GOALS[market]
        return "won" if lo <= m["ft_home"] + m["ft_away"] <= hi else "lost"
    if market in OVER:
        if m["ft_home"] is None or m["ft_away"] is None:
            return "pending"
        return "won" if m["ft_home"] + m["ft_away"] >= OVER[market] else "lost"
    if market in ("BB_H1O05_O15", "H1O05"):  # gol în R1 (+ min. 2 goluri în meci, la Bet Builder)
        h, a = m["ht_home"], m["ht_away"]
        if h is None or a is None:
            return "pending" if m["ft_home"] is None else "nesettlabil"
        if h + a == 0:
            return "lost"
        if market == "H1O05":
            return "won"
        if m["ft_home"] is None or m["ft_away"] is None:
            return "pending"
        return "won" if m["ft_home"] + m["ft_away"] >= 2 else "lost"
    if market == "H1C_3_6":
        h, a = m["corners_ht_home"], m["corners_ht_away"]
        if h is None or a is None:
            return "pending" if m["ft_home"] is None else "nesettlabil"
        return "won" if 3 <= h + a <= 6 else "lost"
    if market == "EACH_C3":
        h, a = m["corners_home"], m["corners_away"]
        if h is None or a is None:
            return "pending" if m["ft_home"] is None else "nesettlabil"
        return "won" if h >= 3 and a >= 3 else "lost"
    return "nesettlabil"


def _poisson_range(lam: float, lo: int, hi: int) -> float:
    return sum(math.exp(-lam) * lam ** k / math.factorial(k) for k in range(lo, hi + 1))


def model_p(conn: sqlite3.Connection, market: str, m: Optional[sqlite3.Row]) -> Optional[float]:
    """Șansa robotului pentru aceeași selecție (urmărirea Stil, altfel Poisson din modelul de goluri)."""
    if m is None:
        return None
    sk = SS_KEY.get(market)
    if sk:
        try:
            r = conn.execute("SELECT p FROM ss_track WHERE match_id=? AND mkey=?", (m["id"], sk)).fetchone()
        except sqlite3.Error:
            r = None
        if r and r[0] is not None:
            return float(r[0])
    if market == "H1C_3_6":  # P(3..6) = P(R1 ≥ 3) + P(R1 ≤ 6) − 1, din liniile simple urmărite
        try:
            got = dict(conn.execute("SELECT mkey, p FROM ss_track WHERE match_id=? AND mkey IN ('H1C25','H1U65')", (m["id"],)).fetchall())
        except sqlite3.Error:
            got = {}
        if got.get("H1C25") is not None and got.get("H1U65") is not None:
            return max(0.0, got["H1C25"] + got["H1U65"] - 1)
    if market in GOALS or market in OVER or market in ("BB_H1O05_O15", "H1O05"):
        try:
            r = conn.execute("SELECT lambda_home, lambda_away FROM match_model WHERE match_id=? ORDER BY updated_at DESC LIMIT 1", (m["id"],)).fetchone()
        except sqlite3.Error:
            r = None
        if r and r[0] is not None and r[1] is not None:
            lam = float(r[0]) + float(r[1])
            if market in GOALS:
                return _poisson_range(lam, *GOALS[market])
            if market in OVER:
                return 1 - _poisson_range(lam, 0, OVER[market] - 1)
            a, b = lam * H1_SHARE, lam * (1 - H1_SHARE)
            p1 = 1 - math.exp(-a)
            # P(R1 ≥ 1 și total ≥ 2) = P(R1 ≥ 1) − P(R1 = 1, R2 = 0)
            return p1 if market == "H1O05" else p1 - a * math.exp(-a) * math.exp(-b)
    return None


def history(conn: sqlite3.Connection, market: str) -> Optional[Dict[str, Any]]:
    """Aceeași piață pe toate meciurile urmărite de noi (nu doar ale lui): intră mai des decât spune cota?"""
    sk = SS_KEY.get(market)
    if not sk:
        return None
    try:
        rows = conn.execute("SELECT result, odds FROM ss_track WHERE mkey=? AND result IN ('won','lost') AND odds > 1", (sk,)).fetchall()
    except sqlite3.Error:
        return None
    if not rows:
        return None
    n = len(rows)
    won = sum(r[0] == "won" for r in rows)
    return {"n": n, "hit": round(won / n, 3), "implied": round(sum(1 / r[1] / MARGIN for r in rows) / n, 3),
            "roi": round(sum((r[1] - 1) if r[0] == "won" else -1 for r in rows) / n, 3)}


def report(conn: sqlite3.Connection, data: Optional[Dict[str, Any]] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
    data = load() if data is None else data
    if conn is not None:  # biletele venite din linkurile de share Superbet (stefan_links)
        from betpredict.experimental.stefan_links import tickets as sb_tickets

        have = {t.get("id") for t in data.get("tickets", [])}
        data = {**data, "tickets": list(data.get("tickets", [])) + [t for t in sb_tickets(conn) if t["id"] not in have]}
    now = now or datetime.now(timezone.utc)
    by_m: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"n": 0, "won": 0, "imp": 0.0, "seen": 0, "mp": [], "pick": 0, "with_model": 0})
    tickets: List[Dict[str, Any]] = []
    legs_all, mismatch = 0, []
    for t in data.get("tickets", []):
        legs = []
        for l in t.get("legs", []):
            legs_all += 1
            mk = l.get("market") or ""
            m = find_match(conn, l.get("home") or "", l.get("away") or "", l.get("kickoff"), t.get("posted"))
            res = settle(mk, m)
            odds = l.get("odds")
            imp = 1 / odds / MARGIN if odds else None
            p = model_p(conn, mk, m)
            ev = p * odds - 1 if (p is not None and odds) else None
            shown = l.get("result_shown")
            if res in ("won", "lost") and shown in ("won", "lost") and res != shown:
                mismatch.append({"home": l.get("home"), "away": l.get("away"), "market": mk, "their": shown, "ours": res})
            k = by_m[mk]
            k["seen"] += 1
            if res in ("won", "lost") and imp:
                k["n"] += 1
                k["won"] += res == "won"
                k["imp"] += imp
            if ev is not None:
                k["with_model"] += 1
                k["pick"] += ev >= 0
                k["mp"].append(p)
            legs.append({"home": l.get("home"), "away": l.get("away"), "market": mk, "label": LABELS.get(mk, mk), "odds": odds,
                         "implied": round(imp, 3) if imp else None, "result": res, "result_shown": shown,
                         "match_id": m["id"] if m else None, "kickoff_utc": m["kickoff_utc"] if m else l.get("kickoff"),
                         "model_p": round(p, 3) if p is not None else None, "model_ev": round(ev, 3) if ev is not None else None,
                         "model_pick": (ev >= 0) if ev is not None else None})
        res = [x["result"] for x in legs]
        ours = "lost" if "lost" in res else ("won" if legs and all(r == "won" for r in res) else "open")
        status = "lost" if (t.get("status_shown") == "lost" or ours == "lost") else t.get("status_shown") or "pending"
        if status == "pending" and ours == "won" and len(legs) == (t.get("legs_total") or len(legs)):
            status = "won"
        tickets.append({"id": t.get("id"), "posted": t.get("posted"), "odds": t.get("total_odds"), "legs_total": t.get("legs_total"),
                        "legs_visible": len(legs), "status": status, "status_shown": t.get("status_shown"), "badge": t.get("badge"),
                        "note": t.get("note"), "source": t.get("source") or "captura", "ticket_id": t.get("ticket_id"),
                        "link": t.get("link"), "user": t.get("user"), "sb": t.get("sb"), "legs": legs})
    markets = []
    for mk, k in sorted(by_m.items(), key=lambda kv: (-kv[1]["seen"], kv[0])):
        n = k["n"]
        markets.append({"market": mk, "label": LABELS.get(mk, mk), "seen": k["seen"], "n": n, "won": k["won"],
                        "hit": round(k["won"] / n, 3) if n else None, "implied": round(k["imp"] / n, 3) if n else None,
                        "model_p": round(sum(k["mp"]) / len(k["mp"]), 3) if k["mp"] else None,
                        "model_pick": k["pick"], "with_model": k["with_model"], "history": history(conn, mk)})
    n = sum(x["n"] for x in markets)
    won = sum(x["won"] for x in markets)
    imp = sum(by_m[x["market"]]["imp"] for x in markets)
    allp = [l for t in tickets for l in t["legs"] if l["model_pick"] is not None]
    return {"generated_at": canon_utc(now.isoformat()), "tickets": tickets, "markets": markets,
            "summary": {"tickets": len(tickets), "won": sum(t["status"] == "won" for t in tickets),
                        "lost": sum(t["status"] == "lost" for t in tickets),
                        "pending": sum(t["status"] not in ("won", "lost") for t in tickets),
                        "legs": legs_all, "legs_settled": n, "legs_won": won,
                        "hit": round(won / n, 3) if n else None, "implied": round(imp / n, 3) if n else None,
                        "unsettlable": sum(l["result"] in ("nesettlabil", "negasit") for t in tickets for l in t["legs"]),
                        "model_compared": len(allp), "model_would_pick": sum(bool(l["model_pick"]) for l in allp)},
            "data_check": {"mismatches": mismatch},
            "caveat": "Capturi: doar selecțiile vizibile („+N mai mult” nu se văd). Linkuri Superbet: toate selecțiile + statusul Superbet. Eșantion mic: nu e dovadă de plus."}
