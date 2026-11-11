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
  odds REAL, odds_observed_at TEXT,
  PRIMARY KEY (match_id, market, line, selection));
"""
LABELS = {"team_home": "Goluri gazde", "team_away": "Goluri oaspeți", "h1": "Goluri prima repriză",
          "h2": "Goluri repriza a doua", "corners": "Cornere meci", "cards": "Cartonașe galbene",
          "ht_corners": "Cornere prima repriză", "h1_result": "Rezultat prima repriză",
          "h2_result": "Rezultat repriza a doua", "half_most_goals": "Repriza cu cele mai multe goluri",
          "goals_range": "Interval goluri", "corners_range": "Interval cornere meci",
          "ht_corners_range": "Interval cornere prima repriză"}
OFFER_MARKETS = {"h1": "Prima repriză - Total goluri", "h2": "A doua repriză - Total goluri",
                 "corners": "Total cornere", "ht_corners": "Prima repriză - Total cornere",
                 "h1_result": "Prima repriză - 1X2", "h2_result": "A doua repriză - 1X2",
                 "half_most_goals": "Repriza cu cele mai multe goluri", "goals_range": "Interval goluri",
                 "corners_range": "Interval cornere", "ht_corners_range": "Prima repriză - Interval cornere"}
ODDS_MAX_AGE_H = 6.0
EWMA = {"corners": 0.12, "cards": 0.05}
CARD_TEAM_W = 0.4  # backtest: media echipelor trasă 60% spre media ligii (singura variantă care bate referința)
PROOF_N = 300
REFEREE_FILE = Path(__file__).resolve().parents[2] / "data" / "referee_stats.json"


def ensure(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(exp_prediction)")}
    for name, decl in (("odds", "REAL"), ("odds_observed_at", "TEXT")):
        if name not in cols:
            conn.execute(f"ALTER TABLE exp_prediction ADD COLUMN {name} {decl}")


def _superbet_price(conn: sqlite3.Connection, match_id: int, market: str, line: float,
                    selection: str, now_s: str, home: str = "", away: str = "") -> Tuple[Optional[float], Optional[str]]:
    """Cota exactă Superbet pentru piața/linia/seleția predicției; ignoră prețuri stale/post-kickoff."""
    name = OFFER_MARKETS.get(market)
    if market == "team_home":
        name = f"Total goluri {home}"
    elif market == "team_away":
        name = f"Total goluri {away}"
    if not name:
        return None, None
    outcome = ("Peste" if selection == "OVER" else "Sub") + f" {line:g}"
    if market in ("h1_result", "h2_result"):
        outcome = {"HOME": home, "DRAW": "Egal", "AWAY": away}.get(selection, "")
    elif market == "half_most_goals":
        outcome = {"FIRST": "Repriza 1", "EQUAL": "Egalitate", "SECOND": "Repriza 2"}.get(selection, "")
    elif market == "goals_range":
        outcome = f"{int(line)}-{selection.split(':', 1)[1]}" if selection.startswith("RANGE:") else ""
    elif market == "corners_range":
        outcome = {"LT:9": "<9", "RANGE:11": "9-11", "GE:12": "12+"}.get(selection, "")
    elif market == "ht_corners_range":
        outcome = {"LT:5": "<5", "RANGE:6": "5-6", "GE:7": "7+"}.get(selection, "")
    if not outcome:
        return None, None
    row = conn.execute(
        "SELECT price, observed_at FROM sb_offer WHERE match_id=? AND market_name=? AND outcome=? "
        "ORDER BY observed_at DESC LIMIT 1", (match_id, name, outcome)).fetchone()
    if not row or not row[0] or float(row[0]) <= 1 or not row[1] or row[1] > now_s:
        return None, None
    try:
        observed = datetime.fromisoformat(row[1].replace("Z", "+00:00"))
        now_dt = datetime.fromisoformat(now_s.replace("Z", "+00:00"))
        if (now_dt - observed).total_seconds() > ODDS_MAX_AGE_H * 3600:
            return None, None
    except ValueError:
        return None, None
    return float(row[0]), row[1]


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


def _pois_probs(lam: float, max_goals: int = 15) -> List[float]:
    lam = max(1e-9, lam)
    probs = [math.exp(-lam)]
    for i in range(1, max_goals + 1):
        probs.append(probs[-1] * lam / i)
    return probs


def _outcome_1x2(lh: float, la: float) -> Dict[str, float]:
    ph, pa = _pois_probs(lh), _pois_probs(la)
    return {
        "HOME": sum(ph[i] * pa[j] for i in range(len(ph)) for j in range(len(pa)) if i > j),
        "DRAW": sum(ph[i] * pa[i] for i in range(min(len(ph), len(pa)))),
        "AWAY": sum(ph[i] * pa[j] for i in range(len(ph)) for j in range(len(pa)) if i < j),
    }


def match_probs(lh: Optional[float], la: Optional[float], share: float, th: Dict[str, float], ta: Dict[str, float],
                ref: Optional[Dict[str, Any]], corner_avg: float, card_avg: float) -> Dict[Tuple[str, float, str], Tuple[float, Optional[float]]]:
    out: Dict[Tuple[str, float, str], Tuple[float, Optional[float]]] = {}
    if lh and la:
        for k, p in M.goal_markets(lh, la, share).items():
            out[k] = (p, None)
        # Liniele 2.5 și intervalele sunt calculate exact pe distribuția Poisson a scorului.
        for team, lam in (("team_home", lh), ("team_away", la)):
            p_over = M.p_over_pois(2.5, lam)
            out[(team, 2.5, "OVER")] = (p_over, None)
            out[(team, 2.5, "UNDER")] = (1 - p_over, None)
        for lo, hi in ((1, 2), (1, 3), (2, 3), (2, 4), (2, 5), (3, 4), (3, 5), (3, 6)):
            p = sum(_pois_probs(lh + la)[lo:hi + 1])
            out[("goals_range", float(lo), f"RANGE:{hi}")] = (p, None)
        for market, scale in (("h1_result", share), ("h2_result", 1 - share)):
            for sel, p in _outcome_1x2(lh * scale, la * scale).items():
                out[(market, 0.0, sel)] = (p, None)
        p1, p2 = _pois_probs((lh + la) * share), _pois_probs((lh + la) * (1 - share))
        out[("half_most_goals", 0.0, "FIRST")] = (sum(p1[i] * p2[j] for i in range(len(p1)) for j in range(len(p2)) if i > j), None)
        out[("half_most_goals", 0.0, "EQUAL")] = (sum(p1[i] * p2[i] for i in range(min(len(p1), len(p2)))), None)
        out[("half_most_goals", 0.0, "SECOND")] = (sum(p1[i] * p2[j] for i in range(len(p1)) for j in range(len(p2)) if i < j), None)
    if th.get("nc", 0) >= 5 and ta.get("nc", 0) >= 5:
        mean = M.corner_mean(th["cf"], th["ca"], ta["cf"], ta["ca"])
        for k, p in M.count_markets("corners", mean, M.CORNER_LINES).items():
            out[k] = (p, mean)
        ht_mean = mean * 0.46
        for k, p in M.count_markets("corners", ht_mean, (2.5, 3.5, 4.5, 5.5)).items():
            out[("ht_corners", k[1], k[2])] = (p, ht_mean)
        # Superbet intervale: <9 / 9–11 / 12+ la meci; <5 / 5–6 / 7+ la pauză.
        for market, mu, cuts in (("corners_range", mean, ((0, 8, "LT:9"), (9, 11, "RANGE:11"), (12, 30, "GE:12"))),
                                 ("ht_corners_range", ht_mean, ((0, 4, "LT:5"), (5, 6, "RANGE:6"), (7, 30, "GE:7")))):
            for lo, hi, sel in cuts:
                p = M.nb_cdf(hi, mu, M.CORNER_R) if lo == 0 else (
                    M.nb_cdf(hi, mu, M.CORNER_R) - M.nb_cdf(lo - 1, mu, M.CORNER_R) if hi < 30
                    else 1 - M.nb_cdf(lo - 1, mu, M.CORNER_R))
                out[(market, float(lo), sel)] = (p, mu)
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
                    "SELECT m.id, m.league_id, m.home_id, m.away_id, m.referee_id, mm.lambda_home, mm.lambda_away, m.home_name, m.away_name "
                    "FROM match m LEFT JOIN match_model mm ON mm.match_id = m.id WHERE m.kickoff_utc >= ? AND m.kickoff_utc < ? "
                    "AND m.kickoff_utc > ?", (a, b, now_s)).fetchall():
                P = match_probs(m[5], m[6], shares.get(m[1], M.H1_SHARE_DEFAULT), T.get(m[2], {}), T.get(m[3], {}),
                                refs.get(str(m[4])) if m[4] else None, c_avg, y_avg)
                if not P:
                    continue
                st["matches"] += 1
                for (mk, ln, sel), (p, mean) in P.items():
                    price, price_at = _superbet_price(conn, int(m[0]), mk, ln, sel, now_s, m[7] or "", m[8] or "")
                    conn.execute(
                        "INSERT INTO exp_prediction (match_id, market, line, selection, p, mean, day, created_at, odds, odds_observed_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?) "
                        "ON CONFLICT(match_id, market, line, selection) DO UPDATE SET p=excluded.p, mean=excluded.mean, "
                        "created_at=excluded.created_at, odds=excluded.odds, odds_observed_at=excluded.odds_observed_at "
                        "WHERE exp_prediction.result IS NULL",
                        (m[0], mk, ln, sel, round(p, 4), round(mean, 2) if mean else None, d.isoformat(), created, price, price_at))
                    st["rows"] += 1
    return st


def actual(market: str, r: sqlite3.Row) -> Optional[Any]:
    h, a = r["ft_home"], r["ft_away"]
    if market == "team_home":
        return h
    if market == "team_away":
        return a
    if market in ("h1", "h2"):
        if r["ht_home"] is None or r["ht_away"] is None:
            return None
        h1 = r["ht_home"] + r["ht_away"]
        return h1 if market == "h1" else h + a - h1
    if market in ("h1_result", "h2_result", "half_most_goals"):
        if r["ht_home"] is None or r["ht_away"] is None:
            return None
        h1 = r["ht_home"] + r["ht_away"]
        h2 = h + a - h1
        if market == "half_most_goals":
            return "FIRST" if h1 > h2 else "SECOND" if h2 > h1 else "EQUAL"
        if market == "h1_result":
            x, y = r["ht_home"], r["ht_away"]
        else:
            x, y = h - r["ht_home"], a - r["ht_away"]
        return "HOME" if x > y else "AWAY" if x < y else "DRAW"
    if market == "corners":
        return r["c"]
    if market in ("ht_corners", "ht_corners_range"):
        vals = (r["corners_ht_home"], r["corners_ht_away"])
        return sum(vals) if all(v is not None for v in vals) else None
    if market == "corners_range":
        return r["c"]
    if market == "goals_range":
        return h + a
    if market == "cards":
        return r["y"]
    return None


def settle(conn: sqlite3.Connection) -> Dict[str, int]:
    ensure(conn)
    has_fd = conn.execute("SELECT 1 FROM sqlite_master WHERE name='fd_match'").fetchone() is not None
    match_cols = {r[1] for r in conn.execute("PRAGMA table_info(match)")}
    ht_home = "m.corners_ht_home" if "corners_ht_home" in match_cols else "NULL"
    ht_away = "m.corners_ht_away" if "corners_ht_away" in match_cols else "NULL"
    fd = ("(SELECT f.hc + f.ac FROM fd_match f WHERE f.match_id = m.id LIMIT 1)",
          "(SELECT f.hy + f.ay FROM fd_match f WHERE f.match_id = m.id LIMIT 1)") if has_fd else ("NULL", "NULL")
    rows = conn.execute(
        f"""SELECT e.rowid AS rid, e.market, e.line, e.selection, m.ft_home, m.ft_away, m.ht_home, m.ht_away,
               {ht_home} AS corners_ht_home, {ht_away} AS corners_ht_away,
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
            if r["market"] in ("h1_result", "h2_result", "half_most_goals"):
                won = v == r["selection"]
            elif r["selection"].startswith("RANGE:"):
                won = r["line"] <= v <= float(r["selection"].split(":", 1)[1])
            elif r["selection"].startswith("LT:"):
                won = v < float(r["selection"].split(":", 1)[1])
            elif r["selection"].startswith("GE:"):
                won = v >= float(r["selection"].split(":", 1)[1])
            else:
                won = (v > r["line"]) == (r["selection"] == "OVER")
            conn.execute("UPDATE exp_prediction SET result=?, settled_at=? WHERE rowid=?", ("won" if won else "lost", now, r["rid"]))
            st["settled"] += 1
    return st


def stats(conn: sqlite3.Connection) -> Dict[str, Any]:
    ensure(conn)
    out = {}
    for mk, ln, sel, n, w, sp, ll, n_price, roi in conn.execute(
            """SELECT market, line, selection, COUNT(*), SUM(result='won'), SUM(p),
                      SUM(-LN(MAX(1e-6, CASE WHEN result='won' THEN p ELSE 1-p END))),
                      SUM(odds IS NOT NULL), SUM(CASE WHEN odds IS NULL THEN 0 WHEN result='won' THEN odds-1 ELSE -1 END)
               FROM exp_prediction WHERE result IS NOT NULL GROUP BY market, line, selection"""):
        out[f"{mk}_{ln:g}_{sel.lower()}"] = {"market": mk, "line": ln, "selection": sel, "n": n,
            "won": int(w or 0), "lost": n - int(w or 0), "hit_rate": round(w / n, 4),
            "p_mean": round(sp / n, 4), "logloss": round(ll / n, 4), "n_with_superbet_odds": int(n_price or 0),
            "paper_roi": round(roi / n_price, 4) if n_price else None,
            "proven": False, "ticket_eligible": False}
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
            if r["market"] in ("h1_result", "h2_result"):
                label = f"{LABELS[r['market']]}: " + {"HOME": r["home_name"], "DRAW": "Egal", "AWAY": r["away_name"]}[r["selection"]]
            elif r["market"] == "half_most_goals":
                label = "Repriza cu cele mai multe goluri: " + {"FIRST": "Repriza 1", "EQUAL": "Egalitate", "SECOND": "Repriza 2"}[r["selection"]]
            elif r["selection"].startswith("RANGE:"):
                label = f"{LABELS.get(r['market'], r['market'])} {r['line']:g}–{r['selection'].split(':', 1)[1]}"
            elif r["selection"].startswith("LT:"):
                label = f"{LABELS.get(r['market'], r['market'])} sub {r['selection'].split(':', 1)[1]}"
            elif r["selection"].startswith("GE:"):
                label = f"{LABELS.get(r['market'], r['market'])} {r['selection'].split(':', 1)[1]}+"
            else:
                label = f"{LABELS.get(r['market'], r['market'])} {'peste' if r['selection'] == 'OVER' else 'sub'} {r['line']:g}"
            x["markets"].append({"market": r["market"], "label": label,
                                 "line": r["line"], "selection": r["selection"], "p": r["p"],
                                 "fair_odds": round(1 / r["p"], 2) if r["p"] > 0.01 else None, "odds": r["odds"],
                                 "odds_observed_at": r["odds_observed_at"], "odds_source": "superbet" if r["odds"] else None,
                                 "mean": r["mean"],
                                 "result": r["result"]})
        write_json(out_root / "api" / "experimental" / f"{d.isoformat()}.json",
                   {"schema": "betpredict.experimental.v1", "date": d.isoformat(), "experimental": True, "recommended": False,
                    "note": "Piețe experimentale: doar urmărite, nu sunt recomandări și nu intră în bilete până nu sunt dovedite.",
                    "matches": list(by.values())})
    write_json(out_root / "api" / "experimental" / "stats.json",
                    {"schema": "betpredict.experimental_stats.v2", "experimental": True, "proof_rule":
                f"n ≥ {PROOF_N} decontate și logloss sub referința ligii + ROI ≥ 0 la cote Superbet efectiv observate; nu intră în bilete până la validare",
                "markets": stats(conn)})
