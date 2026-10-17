"""„Tiparul 80%+”: bilete scurte din predicțiile clasice ale Robotului cu șansa ≥ 80%, doar pe piețele care au ieșit
pe plus la cota Superbet reală în ambele jumătăți ale istoricului (17.10.2026, 207 predicții: 90% intrate, ROI +5,8%):
Peste 1.5 goluri, șansă dublă 1X și 12, victorie gazde, egal = pariu returnat oaspeți, Peste 2.5.
Sub 4.5 / Sub 3.5 / X2 (constant pe minus) și Peste 0.5 (cotă prea mică) nu intră.

Două bilete pe zi, cu meciuri diferite: ~2.5 (4–6 selecții) și ~4 (6–9 selecții); cotele tiparului sunt în jur de 1.18. Selecțiile au predicția lor, deci se
decontează singure. Auditul (``pattern_doc``) urmărește zilnic tiparul: piețele bune, restul 80%+, Stil 80%+ și biletele."""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from betpredict.store import repo
from betpredict.timeutil import canon_utc

KIND, VARIANT = "acca_80", "tipar_80"
P_MIN = 0.80
ODDS_MIN = 1.15
GOOD = {("over_under", 1.5, "OVER"), ("over_under", 2.5, "OVER"), ("double_chance", 0.0, "1X"),
        ("double_chance", 0.0, "12"), ("1x2", 0.0, "HOME"), ("draw_no_bet", 0.0, "AWAY")}
TARGETS: Tuple[Tuple[float, int, int], ...] = ((2.5, 4, 6), (4.0, 6, 9))
HORIZON_H = 36
MAX_PER_LEAGUE = 2
STAKE_U = 0.1


def candidates(conn: sqlite3.Connection, now: datetime) -> List[Dict[str, Any]]:
    """Ultima versiune a fiecărei predicții clasice ≥ 80% pe piețele bune, cu cotă Superbet, din următoarele 36 h."""
    lo, hi = canon_utc((now + timedelta(minutes=10)).isoformat()), canon_utc((now + timedelta(hours=HORIZON_H)).isoformat())
    rows = conn.execute(
        """SELECT p.id, p.match_id, p.market, p.line, p.selection, p.p_calibrated, p.reasons_json, m.kickoff_utc, m.league_id,
                  m.home_name, m.away_name
           FROM prediction p JOIN match m ON m.id=p.match_id
           WHERE p.period='FT' AND p.result IS NULL AND m.kickoff_utc > ? AND m.kickoff_utc <= ? ORDER BY p.created_at""",
        (lo, hi)).fetchall()
    last: Dict[Tuple[int, str, float, str], Dict[str, Any]] = {}
    for r in rows:
        key = (r["match_id"], r["market"], float(r["line"] or 0), r["selection"])
        try:
            js = json.loads(r["reasons_json"] or "{}")
        except ValueError:
            js = {}
        sb = (js.get("odds_alt") or {}).get("superbet")
        p = r["p_calibrated"]
        if (r["market"], float(r["line"] or 0), r["selection"]) not in GOOD or p is None or p < P_MIN or not sb or sb < ODDS_MIN:
            last.pop(key, None)  # cea mai nouă versiune nu mai trece: nu folosim una veche
            continue
        last[key] = {"pid": r["id"], "match_id": r["match_id"], "market": r["market"], "line": float(r["line"] or 0),
                     "selection": r["selection"], "p": float(p), "odds": float(sb), "kickoff_utc": r["kickoff_utc"],
                     "league_id": r["league_id"], "home": r["home_name"], "away": r["away_name"]}
    return list(last.values())


def _pick(pool: List[Dict[str, Any]], target: float, n_min: int, n_max: int, banned: set) -> Optional[List[Dict[str, Any]]]:
    """Cele mai sigure selecții (un meci o dată, cel mult 2 pe ligă) până la cota țintă."""
    legs: List[Dict[str, Any]] = []
    leagues: Dict[Any, int] = {}
    for c in sorted(pool, key=lambda c: (-c["p"], -c["odds"])):
        if c["match_id"] in banned or any(l["match_id"] == c["match_id"] for l in legs):
            continue
        if leagues.get(c["league_id"], 0) >= MAX_PER_LEAGUE:
            continue
        total = math.prod(l["odds"] for l in legs) * c["odds"]
        if total > target * 1.35 and len(legs) >= n_min:
            continue
        legs.append(c)
        leagues[c["league_id"]] = leagues.get(c["league_id"], 0) + 1
        if math.prod(l["odds"] for l in legs) >= target and len(legs) >= n_min:
            return legs
        if len(legs) >= n_max:
            break
    return legs if len(legs) >= n_min and math.prod(l["odds"] for l in legs) >= target * 0.8 else None


def build(conn: sqlite3.Connection, today: date, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    have = conn.execute("SELECT COUNT(*) FROM ticket WHERE kind=? AND day=? AND status!='replaced'", (KIND, today.isoformat())).fetchone()[0]
    if have:
        return {"skipped_existing": have}
    pool = candidates(conn, now)
    made, banned = [], set()
    with conn:
        for target, n_min, n_max in TARGETS:
            legs = _pick(pool, target, n_min, n_max, banned)
            if not legs:
                continue
            total = math.prod(l["odds"] for l in legs)
            p = math.prod(l["p"] for l in legs)
            notes = {"label": f"Tiparul 80%+ · cotă ~{target:g}", "pattern": "80", "paper": True, "risk_acknowledged": True,
                     "reasons": [f"{len(legs)} predicții clasice ale Robotului cu șansă ≥ 80%, doar pe piețele care au ieșit pe plus "
                                 "la cota Superbet (Peste 1.5, 1X, 12, victorie gazde): pe istoric 90% intrate, ROI +5,8% pe selecție.",
                                 f"Șansa Robotului pentru tot biletul: {p:.0%} · cotă {total:.2f}. Miză {STAKE_U:g}u."]}
            cur = conn.execute(
                """INSERT INTO ticket (kind, variant, created_by, target_odds, total_odds, p_ticket, ev, stake, status, created_at, notes, day)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (KIND, VARIANT, "robot", target, round(total, 2), round(p, 6), round(p * total - 1, 4), STAKE_U, "pending",
                 repo.now_iso(), json.dumps(notes, ensure_ascii=False), today.isoformat()))
            for l in sorted(legs, key=lambda l: l["kickoff_utc"]):
                conn.execute("INSERT INTO ticket_leg (ticket_id, prediction_id, match_id, market, selection, odds, odds_source) VALUES (?,?,?,?,?,?,?)",
                             (cur.lastrowid, l["pid"], l["match_id"], f"{l['market']}|{l['line']:g}", l["selection"], l["odds"], "superbet"))
                banned.add(l["match_id"])
            made.append({"target": target, "legs": len(legs), "odds": round(total, 2), "p": round(p, 3)})
    return {"pool": len(pool), "tickets": made}


def _group(rows: List[Tuple[float, bool]]) -> Dict[str, Any]:
    n = len(rows)
    if not n:
        return {"n": 0, "win_rate": None, "roi": None, "avg_odds": None}
    return {"n": n, "win_rate": round(sum(1 for _, w in rows if w) / n, 4),
            "roi": round(sum((o - 1) if w else -1 for o, w in rows) / n, 4), "avg_odds": round(sum(o for o, _ in rows) / n, 3)}


def pattern_doc(conn: sqlite3.Connection, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Monitorizarea tiparului 80%+: total și ultimele 7 zile, pe zile, plus biletele „Tiparul 80%+”."""
    now = now or datetime.now(timezone.utc)
    since7 = (now - timedelta(days=7)).date().isoformat()
    good, rest, stil = [], [], []
    by_day: Dict[str, List[Tuple[float, bool]]] = {}
    try:
        for m, line, sel, p, res, rj, d in conn.execute(
                """SELECT p.market, p.line, p.selection, p.p_calibrated, p.result, p.reasons_json, substr(m.kickoff_utc,1,10)
                   FROM prediction p JOIN match m ON m.id=p.match_id
                   WHERE p.period='FT' AND p.result IN ('won','lost') AND p.p_calibrated >= ?""", (P_MIN,)):
            try:
                sb = (json.loads(rj or "{}").get("odds_alt") or {}).get("superbet")
            except ValueError:
                sb = None
            if not sb or sb <= 1:
                continue
            x = (float(sb), res == "won", d)
            if (m, float(line or 0), sel) in GOOD and sb >= ODDS_MIN:
                good.append(x)
                by_day.setdefault(d, []).append(x[:2])
            else:
                rest.append(x)
    except sqlite3.OperationalError:
        pass
    try:
        for o, res, d in conn.execute("SELECT odds, result, substr(kickoff_utc,1,10) FROM ss_track WHERE result IN ('won','lost') AND odds>1 AND p>=?", (P_MIN,)):
            stil.append((float(o), res == "won", d))
    except sqlite3.OperationalError:
        pass
    tk = conn.execute("SELECT status, total_odds FROM ticket WHERE kind=? AND status IN ('won','lost')", (KIND,)).fetchall()
    g = lambda rs: _group([r[:2] for r in rs])
    g7 = lambda rs: _group([r[:2] for r in rs if r[2] >= since7])
    groups = [
        {"name": "Clasice 80%+ pe piețele tiparului", "all": g(good), "last7": g7(good)},
        {"name": "Clasice 80%+ restul (Sub 4.5, X2, Peste 0.5…)", "all": g(rest), "last7": g7(rest)},
        {"name": "Stil Supersocial 80%+", "all": g(stil), "last7": g7(stil)},
    ]
    days = [{"day": d, **_group(v)} for d, v in sorted(by_day.items())[-10:]]
    return {"generated_at": canon_utc(now.isoformat()), "groups": groups, "days": days,
            "tickets": {"n": len(tk), "won": sum(1 for t in tk if t[0] == "won"),
                        "roi": round(sum((t[1] - 1) if t[0] == "won" else -1 for t in tk) / len(tk), 4) if tk else None},
            "note": "ROI la 1 unitate pe selecție, la cota Superbet reală. Tiparul: predicții clasice ≥ 80% pe Peste 1.5, 1X, 12, "
                    "victorie gazde, Peste 2.5, egal = returnat oaspeți, cota de la 1.15."}
