"""Jurnalul piețelor experimentale: generare (înainte de start), decontare (doar meciuri terminate), publicare.

Nu intră în ``prediction``, deci nu ajunge niciodată în recomandări, bilete, piramidă sau statisticile principale."""

from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from betpredict.experimental import models as M
from betpredict.store import repo
from betpredict.timeutil import canon_utc, ro_day_bounds_utc

SCHEMA = """
CREATE TABLE IF NOT EXISTS exp_prediction (
  match_id INTEGER NOT NULL, market TEXT NOT NULL, line REAL NOT NULL, selection TEXT NOT NULL,
  p REAL NOT NULL, mean REAL, day TEXT, created_at TEXT NOT NULL, result TEXT, settled_at TEXT,
  PRIMARY KEY (match_id, market, line, selection));
"""
LABELS = {"team_home": "Gazde", "team_away": "Oaspeți", "h1": "Prima repriză", "h2": "A doua repriză",
          "corners": "Cornere", "cards": "Cartonașe galbene"}
EWMA = {"corners": 0.12, "cards": 0.05}
CARD_TEAM_W = 0.4  # backtest: media echipelor trasă 60% spre media ligii (singura variantă care bate referința)
PROOF_N = 300
REFEREE_FILE = Path(__file__).resolve().parents[2] / "data" / "referee_stats.json"


def ensure(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def h1_shares(conn: sqlite3.Connection) -> Dict[int, float]:
    out = {}
    for lg, g, g1 in conn.execute(
            "SELECT league_id, SUM(ft_home+ft_away), SUM(ht_home+ht_away) FROM match WHERE status='finished' "
            "AND ht_home IS NOT NULL AND ft_home IS NOT NULL GROUP BY league_id"):
        if g and g >= 150:
            out[lg] = (g1 + M.H1_SHARE_DEFAULT * 100) / (g + 100)
    return out


def team_counts(conn: sqlite3.Connection) -> Tuple[Dict[int, Dict[str, float]], float, float]:
    """EWMA pe echipă (cornere câștigate/cedate, galbene) din football-data legat de meciurile noastre."""
    try:
        rows = conn.execute(
            "SELECT m.home_id, m.away_id, f.hc, f.ac, f.hy, f.ay FROM fd_match f JOIN match m ON m.id=f.match_id "
            "ORDER BY f.day").fetchall()
    except sqlite3.OperationalError:
        return {}, 10.0, 4.0
    T: Dict[int, Dict[str, float]] = defaultdict(dict)
    sc = nc = sy = ny = 0.0

    def ew(d, k, x, a):
        d[k] = x if k not in d else (1 - a) * d[k] + a * x

    for h, a, hc, ac, hy, ay in rows:
        if hc is not None and ac is not None:
            ew(T[h], "cf", hc, EWMA["corners"]); ew(T[h], "ca", ac, EWMA["corners"])
            ew(T[a], "cf", ac, EWMA["corners"]); ew(T[a], "ca", hc, EWMA["corners"])
            T[h]["nc"] = T[h].get("nc", 0) + 1; T[a]["nc"] = T[a].get("nc", 0) + 1
            sc += hc + ac; nc += 1
        if hy is not None and ay is not None:
            ew(T[h], "y", hy, EWMA["cards"]); ew(T[a], "y", ay, EWMA["cards"])
            T[h]["ny"] = T[h].get("ny", 0) + 1; T[a]["ny"] = T[a].get("ny", 0) + 1
            sy += hy + ay; ny += 1
    return T, (sc / nc if nc else 10.0), (sy / ny if ny else 4.0)


def referees() -> Dict[str, Dict[str, Any]]:
    try:
        return json.loads(REFEREE_FILE.read_text()).get("referees", {})
    except (OSError, ValueError):
        return {}


def match_probs(lh: Optional[float], la: Optional[float], share: float, th: Dict[str, float], ta: Dict[str, float],
                ref: Optional[Dict[str, Any]], corner_avg: float, card_avg: float) -> Dict[Tuple[str, float, str], Tuple[float, Optional[float]]]:
    out: Dict[Tuple[str, float, str], Tuple[float, Optional[float]]] = {}
    if lh and la:
        for k, p in M.goal_markets(lh, la, share).items():
            out[k] = (p, None)
    if th.get("nc", 0) >= 5 and ta.get("nc", 0) >= 5:
        mean = M.corner_mean(th["cf"], th["ca"], ta["cf"], ta["ca"])
        for k, p in M.count_markets("corners", mean, M.CORNER_LINES).items():
            out[k] = (p, mean)
    if th.get("ny", 0) >= 5 and ta.get("ny", 0) >= 5:
        half = card_avg / 2
        hy = CARD_TEAM_W * (th["y"] + ta["y"]) / 2 + (1 - CARD_TEAM_W) * half
        r_avg, r_n = (ref.get("avg_yellow"), int(ref.get("matches") or 0)) if ref else (None, 0)
        mean = M.card_mean(hy, hy, r_avg, r_n, card_avg)
        for k, p in M.count_markets("cards", mean, M.CARD_LINES).items():
            out[k] = (p, mean)
    return out


def generate(conn: sqlite3.Connection, days: List[date], now: Optional[datetime] = None) -> Dict[str, int]:
    ensure(conn)
    now_s = canon_utc((now or datetime.now(timezone.utc)).isoformat())
    shares, (T, c_avg, y_avg), refs = h1_shares(conn), team_counts(conn), referees()
    st = {"matches": 0, "rows": 0}
    created = repo.now_iso()
    with conn:
        for d in days:
            a, b = ro_day_bounds_utc(d)
            for m in conn.execute(
                    "SELECT m.id, m.league_id, m.home_id, m.away_id, m.referee_id, mm.lambda_home, mm.lambda_away "
                    "FROM match m LEFT JOIN match_model mm ON mm.match_id = m.id WHERE m.kickoff_utc >= ? AND m.kickoff_utc < ? "
                    "AND m.kickoff_utc > ?", (a, b, now_s)).fetchall():
                P = match_probs(m[5], m[6], shares.get(m[1], M.H1_SHARE_DEFAULT), T.get(m[2], {}), T.get(m[3], {}),
                                refs.get(str(m[4])) if m[4] else None, c_avg, y_avg)
                if not P:
                    continue
                st["matches"] += 1
                for (mk, ln, sel), (p, mean) in P.items():
                    conn.execute(
                        "INSERT INTO exp_prediction (match_id, market, line, selection, p, mean, day, created_at) VALUES (?,?,?,?,?,?,?,?) "
                        "ON CONFLICT(match_id, market, line, selection) DO UPDATE SET p=excluded.p, mean=excluded.mean, "
                        "created_at=excluded.created_at WHERE exp_prediction.result IS NULL",
                        (m[0], mk, ln, sel, round(p, 4), round(mean, 2) if mean else None, d.isoformat(), created))
                    st["rows"] += 1
    return st


def actual(market: str, r: sqlite3.Row) -> Optional[float]:
    h, a = r["ft_home"], r["ft_away"]
    if market == "team_home":
        return h
    if market == "team_away":
        return a
    if market in ("h1", "h2"):
        if r["ht_home"] is None:
            return None
        h1 = r["ht_home"] + r["ht_away"]
        return h1 if market == "h1" else h + a - h1
    if market == "corners":
        return r["c"]
    if market == "cards":
        return r["y"]
    return None


def settle(conn: sqlite3.Connection) -> Dict[str, int]:
    ensure(conn)
    has_fd = conn.execute("SELECT 1 FROM sqlite_master WHERE name='fd_match'").fetchone() is not None
    fd = ("(SELECT f.hc + f.ac FROM fd_match f WHERE f.match_id = m.id LIMIT 1)",
          "(SELECT f.hy + f.ay FROM fd_match f WHERE f.match_id = m.id LIMIT 1)") if has_fd else ("NULL", "NULL")
    rows = conn.execute(
        f"""SELECT e.rowid AS rid, e.market, e.line, e.selection, m.ft_home, m.ft_away, m.ht_home, m.ht_away,
               COALESCE(m.corners_home + m.corners_away, {fd[0]}) AS c, COALESCE(m.cards_home + m.cards_away, {fd[1]}) AS y
            FROM exp_prediction e JOIN match m ON m.id = e.match_id
            WHERE e.result IS NULL AND m.status = 'finished' AND m.ft_home IS NOT NULL""").fetchall()
    st = {"settled": 0}
    now = repo.now_iso()
    with conn:
        for r in rows:
            v = actual(r["market"], r)
            if v is None:
                continue
            won = (v > r["line"]) == (r["selection"] == "OVER")
            conn.execute("UPDATE exp_prediction SET result=?, settled_at=? WHERE rowid=?", ("won" if won else "lost", now, r["rid"]))
            st["settled"] += 1
    return st


def stats(conn: sqlite3.Connection) -> Dict[str, Any]:
    ensure(conn)
    out = {}
    for mk, ln, n, w, sp, ll in conn.execute(
            """SELECT market, line, COUNT(*), SUM(result='won'), SUM(p),
                      SUM(-LN(MAX(1e-6, CASE WHEN result='won' THEN p ELSE 1-p END)))
               FROM exp_prediction WHERE result IS NOT NULL AND selection='OVER' GROUP BY market, line"""):
        out[f"{mk}_{ln:g}"] = {"n": n, "hit_over": round(w / n, 3), "p_over": round(sp / n, 3), "logloss": round(ll / n, 4),
                               "proven": False}
    return out


def publish(conn: sqlite3.Connection, out_root: Path, days: List[date]) -> None:
    from betpredict.publish.day import write_json

    ensure(conn)
    for d in days:
        rows = conn.execute(
            """SELECT e.*, m.home_name, m.away_name, m.kickoff_utc FROM exp_prediction e JOIN match m ON m.id = e.match_id
               WHERE e.day = ? ORDER BY m.kickoff_utc, e.match_id, e.market, e.line, e.selection""", (d.isoformat(),)).fetchall()
        by: Dict[int, Dict[str, Any]] = {}
        for r in rows:
            x = by.setdefault(r["match_id"], {"match_id": r["match_id"], "home": r["home_name"], "away": r["away_name"],
                                              "kickoff_utc": r["kickoff_utc"], "markets": []})
            x["markets"].append({"market": r["market"], "label": f"{LABELS.get(r['market'], r['market'])} "
                                 f"{'peste' if r['selection'] == 'OVER' else 'sub'} {r['line']:g}",
                                 "line": r["line"], "selection": r["selection"], "p": r["p"],
                                 "fair_odds": round(1 / r["p"], 2) if r["p"] > 0.01 else None, "mean": r["mean"],
                                 "result": r["result"]})
        write_json(out_root / "api" / "experimental" / f"{d.isoformat()}.json",
                   {"schema": "betpredict.experimental.v1", "date": d.isoformat(), "experimental": True, "recommended": False,
                    "note": "Piețe experimentale: doar urmărite, nu sunt recomandări și nu intră în bilete până nu sunt dovedite.",
                    "matches": list(by.values())})
    write_json(out_root / "api" / "experimental" / "stats.json",
               {"schema": "betpredict.experimental_stats.v1", "experimental": True, "proof_rule":
                f"n ≥ {PROOF_N} decontate și logloss sub referința ligii + ROI ≥ 0 la cote Superbet", "markets": stats(conn)})
