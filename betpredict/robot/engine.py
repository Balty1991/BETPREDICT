"""Generează predicțiile Robotului pentru meciurile care n-au început și le salvează în
jurnal (tabela ``prediction``) ÎNAINTE de publicare. După kickoff o predicție e înghețată."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from betpredict.config import MIN_ODDS
from betpredict.ingest.history import finished_matches
from betpredict.robot import MODEL_VERSION
from betpredict.robot.markets import Selection, all_selections, label_ro, market_key
from betpredict.robot.model import GoalModel, fit_elo, fit_goal_model, match_probabilities
from betpredict.robot.params import blend_weights, calibrate, load_params
from betpredict.store import repo
from betpredict.timeutil import canon_utc, ro_date_of, ro_day_bounds_utc

PAGE = "predictii"
MARKET_OUTCOMES = {"1x2": ("HOME", "DRAW", "AWAY"), "double_chance": None, "draw_no_bet": ("HOME", "AWAY"),
                   "btts": ("YES", "NO")}


def novig(odds_by_outcome: Dict[str, float], outcomes) -> Dict[str, float]:
    vals = {o: odds_by_outcome.get(o) for o in outcomes}
    if any(not v or v <= 1.0 for v in vals.values()):
        return {}
    inv = {o: 1 / v for o, v in vals.items()}
    s = sum(inv.values())
    return {o: x / s for o, x in inv.items()}


def market_probs(odds: Dict[str, Dict[str, float]]) -> Dict[Selection, float]:
    out: Dict[Selection, float] = {}
    for mk, by in odds.items():
        if mk.startswith("over_under_"):
            line = float(mk.rsplit("_", 1)[1])
            nv = novig(by, ("OVER", "UNDER"))
            for o, p in nv.items():
                out[("over_under", line, o)] = p
        elif mk in ("1x2", "draw_no_bet", "btts"):
            for o, p in novig(by, MARKET_OUTCOMES[mk]).items():
                out[(mk, 0.0, o)] = p
        elif mk == "double_chance":
            # pe DC marja nu se poate elimina simplu (rezultatele se suprapun): 1/cotă × 0.95
            for o, v in by.items():
                if v and v > 1:
                    out[("double_chance", 0.0, o)] = min(0.99, 0.95 / v * 1.0)
    # DC derivat din 1X2 no-vig (mai curat decât cota DC)
    h, d, a = (out.get(("1x2", 0.0, s)) for s in ("HOME", "DRAW", "AWAY"))
    if h is not None and d is not None and a is not None:
        out[("double_chance", 0.0, "1X")] = h + d
        out[("double_chance", 0.0, "12")] = h + a
        out[("double_chance", 0.0, "X2")] = d + a
    return out


def odds_lookup(odds: Dict[str, Dict[str, float]], sel: Selection) -> Optional[float]:
    m, line, s = sel
    return (odds.get(market_key(m, line)) or {}).get(s)


def bsd_lookup(bsd: Dict[str, Dict[str, float]], sel: Selection) -> Optional[float]:
    m, line, s = sel
    v = (bsd.get(market_key(m, line)) or {}).get(s)
    if v is not None:
        return v
    if m == "double_chance":
        x = bsd.get("1x2") or {}
        if all(k in x for k in ("HOME", "DRAW", "AWAY")):
            return {"1X": x["HOME"] + x["DRAW"], "12": x["HOME"] + x["AWAY"], "X2": x["DRAW"] + x["AWAY"]}[s]
    return None


def grade_and_confidence(p: float, agreement: float, has_odds: bool, ev: Optional[float], healthy: bool,
                         coverage: float, league_mult: float) -> Tuple[str, int]:
    conf = 100 * (0.55 * p + 0.25 * agreement + 0.10 * (1.0 if has_odds else 0.4) + 0.10 * coverage)
    conf *= league_mult
    if not healthy:
        conf -= 8
    conf = int(round(max(0, min(100, conf))))
    ev_ok = ev is None or ev >= -0.04
    if conf >= 75 and ev_ok and healthy:
        g = "A"
    elif conf >= 65 and ev_ok:
        g = "B"
    elif conf >= 55:
        g = "C"
    else:
        g = "D"
    return g, conf


def build_reasons(sel: Selection, ctx: Dict[str, Any], info: Dict[str, Any], p_bsd: Optional[float],
                  p_mkt: Optional[float], p: float, movement: Optional[Dict[str, Any]] = None) -> List[str]:
    m, line, s = sel
    r: List[str] = []
    lh, la = info.get("lambda_home"), info.get("lambda_away")
    if lh is not None and la is not None:
        if m in ("over_under", "btts"):
            r.append(f"Goluri așteptate (model): {lh:.2f} – {la:.2f} (total {lh + la:.2f})")
        else:
            r.append(f"Forța echipelor (model): {lh:.2f} vs {la:.2f} goluri așteptate")
    form = ctx.get("form") or {}
    fh, fa = form.get("home"), form.get("away")
    if fh and fa and fh.get("ppm") is not None and fa.get("ppm") is not None:
        r.append(f"Formă ultimele {fh.get('played')}: gazde {fh['ppm']:.2f} pct/meci ({fh.get('sequence', '')[:5]}), "
                 f"oaspeți {fa['ppm']:.2f} ({fa.get('sequence', '')[:5]})")
    h2h = ctx.get("h2h") or {}
    if h2h.get("total"):
        if m == "over_under" and h2h.get("over25_rate") is not None:
            r.append(f"H2H: {int(round(h2h['over25_rate'] * 100))}% peste 2.5 în ultimele directe, medie {h2h.get('avg_goals')} goluri")
        elif m == "btts" and h2h.get("btts_rate") is not None:
            r.append(f"H2H: GG în {int(round(h2h['btts_rate'] * 100))}% din ultimele directe")
        else:
            r.append(f"H2H ({h2h['total']} meciuri): {h2h.get('home_wins')}-{h2h.get('draws')}-{h2h.get('away_wins')}")
    st = ctx.get("standings") or {}
    if st.get("home") and st.get("away") and st["home"].get("position") and st["away"].get("position"):
        r.append(f"Clasament: locul {st['home']['position']} vs locul {st['away']['position']}")
    ab = ctx.get("absences") or {}
    nh, na = len(ab.get("home") or []), len(ab.get("away") or [])
    if nh or na:
        r.append(f"Absențe: gazde {nh}, oaspeți {na}")
    if p_bsd is not None:
        diff = p - p_bsd
        if abs(diff) < 0.05:
            r.append(f"BSD confirmă ({p_bsd:.0%})")
        elif diff > 0:
            r.append(f"Robotul e mai optimist decât BSD ({p_bsd:.0%})")
        else:
            r.append(f"BSD e mai optimist decât Robotul ({p_bsd:.0%})")
    if p_mkt is not None:
        r.append(f"Piața (fără marjă): {p_mkt:.0%} vs Robot {p:.0%}")
    if movement and movement.get("dir"):
        r.append(f"Cota s-a mișcat {movement.get('open')} → {movement.get('now')} ({'scade' if movement['dir'] == 'SHORTENING' else 'crește'})")
    return r[:5]


def odds_movement(conn: sqlite3.Connection, match_ids: List[int]) -> Dict[int, Dict[str, Dict[str, Dict[str, Any]]]]:
    out: Dict[int, Dict[str, Dict[str, Dict[str, Any]]]] = defaultdict(dict)
    if not match_ids:
        return out
    q = ",".join("?" for _ in match_ids)
    rows = conn.execute(
        f"""SELECT match_id, market, line, outcome, decimal, opening_decimal, movement, MAX(observed_at) mx
            FROM odds_snapshot WHERE match_id IN ({q}) AND opening_decimal IS NOT NULL
            GROUP BY match_id, market, line, outcome""",
        match_ids,
    ).fetchall()
    for r in rows:
        if r["opening_decimal"] and abs(r["opening_decimal"] - r["decimal"]) >= 0.02:
            d = "SHORTENING" if r["decimal"] < r["opening_decimal"] else "DRIFTING"
            out[r["match_id"]].setdefault(market_key(r["market"], r["line"]), {})[r["outcome"]] = {
                "open": r["opening_decimal"], "now": r["decimal"], "dir": d}
    return out


def provider_probs(conn: sqlite3.Connection, match_ids: List[int]) -> Dict[int, Dict[str, Dict[str, float]]]:
    out: Dict[int, Dict[str, Dict[str, float]]] = defaultdict(dict)
    if not match_ids:
        return out
    q = ",".join("?" for _ in match_ids)
    for r in conn.execute(f"SELECT match_id, market, line, selection, probability FROM provider_prediction "
                          f"WHERE source='bsd' AND match_id IN ({q})", match_ids):
        out[r["match_id"]].setdefault(market_key(r["market"], r["line"]), {})[r["selection"]] = r["probability"]
    return out


def should_publish(p: float, odds: Optional[float], ev: Optional[float]) -> bool:
    if odds is not None:
        if odds < MIN_ODDS:
            return False
        return p >= 0.50 or (ev is not None and ev > 0 and p >= 0.30)
    return p >= 0.60


class Robot:
    def __init__(self, conn: sqlite3.Connection, now: Optional[datetime] = None):
        self.conn = conn
        self.now = now or datetime.now(timezone.utc)
        self.params = load_params(conn)
        rows = [tuple(r) for r in finished_matches(conn)]
        self.model: GoalModel = fit_goal_model(rows, self.now)
        self.elo = fit_elo(rows, canon_utc(self.now.isoformat()))
        self.n_history = len(rows)

    def predict_match(self, m: sqlite3.Row, odds: Dict[str, Dict[str, float]], bsd: Dict[str, Dict[str, float]],
                      ctx: Dict[str, Any], moves: Dict[str, Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        probs, info = match_probabilities(self.model, self.elo, m["home_id"], m["away_id"], m["league_id"])
        mkt = market_probs(odds)
        coverage = min(self.model.coverage(m["home_id"]), self.model.coverage(m["away_id"]))
        league_mult = float(self.params.get("league_penalty", {}).get(str(m["league_id"]), 1.0))
        excluded = set(self.params.get("excluded_markets", []))
        out: List[Dict[str, Any]] = []
        for sel in all_selections():
            mk = market_key(sel[0], sel[1])
            p_model = probs.get(sel)
            p_bsd = bsd_lookup(bsd, sel)
            p_mkt = mkt.get(sel)
            w = blend_weights(self.params, mk)
            parts = []
            if p_model is not None:
                parts.append((w["model"] * (0.3 + 0.7 * coverage), p_model))
            if p_bsd is not None:
                parts.append((w["bsd"], p_bsd))
            if p_mkt is not None:
                parts.append((w["market"], p_mkt))
            den = sum(x for x, _ in parts)
            if den <= 0:
                continue
            p_raw = sum(x * y for x, y in parts) / den
            p = round(min(0.995, max(0.005, calibrate(self.params, mk, p_raw))), 4)
            o = odds_lookup(odds, sel)
            ev = round(p * o - 1, 4) if o else None
            if not should_publish(p, o, ev):
                continue
            srcs = [v for v in (p_model, p_bsd, p_mkt) if v is not None]
            agreement = max(0.0, 1 - 2 * max(abs(v - p) for v in srcs)) if srcs else 0.5
            healthy = mk not in excluded
            g, conf = grade_and_confidence(p, agreement, o is not None, ev, healthy, coverage, league_mult)
            mv = (moves.get(mk) or {}).get(sel[2])
            out.append({
                "match_id": m["id"], "market": sel[0], "line": sel[1], "period": "FT", "selection": sel[2],
                "p_model": round(p_model, 4) if p_model is not None else None,
                "p_calibrated": p, "p_market_novig": round(p_mkt, 4) if p_mkt is not None else None,
                "p_bsd": round(p_bsd, 4) if p_bsd is not None else None,
                "odds_shown": o, "odds_source": "bsd_consensus" if o else None,
                "edge": round(p - 1 / o, 4) if o else None, "ev": ev, "confidence": conf, "grade": g,
                "reasons": build_reasons(sel, ctx, info, p_bsd, p_mkt, p, mv),
                "healthy": healthy,
            })
        # predicția principală: încredere maximă, cotă jucabilă 1.15–3.0, EV rezonabil
        cands = [x for x in out if x["odds_shown"] and x["odds_shown"] <= 3.0 and (x["ev"] or 0) > -0.05 and x["healthy"]]
        # ROI pozitiv întâi: dacă există selecții cu EV > 0 și p ≥ 45%, principala se alege dintre ele
        positive = [x for x in cands if (x["ev"] or 0) > 0 and x["p_calibrated"] >= 0.45]
        if positive:
            cands = positive
        if cands:
            best = max(cands, key=lambda x: (x["confidence"], x["ev"] or 0))
            best["is_pick"] = 1
        for x in out:  # motive detaliate doar unde contează (păstrăm fișierele zilei mici)
            if not (x.get("is_pick") or x["grade"] in ("A", "B") or (x["ev"] or 0) > 0):
                x["reasons"] = x["reasons"][:1]
        info["coverage"] = round(coverage, 2)
        return out, info

    def run(self, day_from: date, day_to: date) -> Dict[str, int]:
        start, _ = ro_day_bounds_utc(day_from)
        _, end = ro_day_bounds_utc(day_to)
        now_s = canon_utc(self.now.isoformat())
        matches = self.conn.execute(
            "SELECT * FROM match WHERE kickoff_utc >= ? AND kickoff_utc < ? AND kickoff_utc > ? "
            "AND (status IS NULL OR status IN ('notstarted','upcoming','scheduled'))",
            (max(start, now_s), end, now_s),
        ).fetchall()
        ids = [m["id"] for m in matches]
        odds_all = repo.latest_odds(self.conn, ids)
        bsd_all = provider_probs(self.conn, ids)
        moves_all = odds_movement(self.conn, ids)
        ctx_all = {r["match_id"]: json.loads(r["context_json"]) for r in self.conn.execute(
            f"SELECT match_id, context_json FROM match_context WHERE match_id IN ({','.join('?' for _ in ids) or 'NULL'})", ids)}
        stats = {"matches": len(matches), "predictions": 0}
        created = repo.now_iso()
        with self.conn:
            for m in matches:
                preds, info = self.predict_match(m, odds_all.get(m["id"], {}), bsd_all.get(m["id"], {}),
                                                 ctx_all.get(m["id"], {}), moves_all.get(m["id"], {}))
                day = (ro_date_of(m["kickoff_utc"]) or day_from).isoformat()
                self.conn.execute(
                    "INSERT INTO match_model(match_id, model_version, lambda_home, lambda_away, elo_home, elo_away, extra_json, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(match_id) DO UPDATE SET model_version=excluded.model_version, "
                    "lambda_home=excluded.lambda_home, lambda_away=excluded.lambda_away, elo_home=excluded.elo_home, "
                    "elo_away=excluded.elo_away, extra_json=excluded.extra_json, updated_at=excluded.updated_at",
                    (m["id"], MODEL_VERSION, info.get("lambda_home"), info.get("lambda_away"), info.get("elo_home"),
                     info.get("elo_away"), json.dumps({k: info[k] for k in ("most_likely_score", "top_scores", "coverage") if k in info}),
                     created),
                )
                # predicțiile nepublicate anterior rămân în jurnal (nu se șterg); doar se actualizează pre-kickoff
                self.conn.execute("UPDATE prediction SET is_pick=0 WHERE match_id=? AND model_version=? AND result IS NULL",
                                  (m["id"], MODEL_VERSION))
                for p in preds:
                    self.conn.execute(
                        """INSERT INTO prediction (match_id, market, line, period, selection, p_model, p_calibrated,
                               p_market_novig, p_bsd, odds_shown, odds_source, edge, ev, confidence, grade, reasons_json,
                               model_version, created_at, shown_on_page, is_pick, day)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(match_id, market, line, period, selection, model_version, shown_on_page)
                           DO UPDATE SET p_model=excluded.p_model, p_calibrated=excluded.p_calibrated,
                               p_market_novig=excluded.p_market_novig, p_bsd=excluded.p_bsd,
                               odds_shown=excluded.odds_shown, odds_source=excluded.odds_source, edge=excluded.edge,
                               ev=excluded.ev, confidence=excluded.confidence, grade=excluded.grade,
                               reasons_json=excluded.reasons_json, is_pick=excluded.is_pick, day=excluded.day
                           WHERE prediction.result IS NULL""",
                        (p["match_id"], p["market"], p["line"], p["period"], p["selection"], p["p_model"],
                         p["p_calibrated"], p["p_market_novig"], p["p_bsd"], p["odds_shown"], p["odds_source"],
                         p["edge"], p["ev"], p["confidence"], p["grade"],
                         json.dumps({"reasons": p["reasons"], "healthy": p["healthy"]}, ensure_ascii=False),
                         MODEL_VERSION, created, PAGE, p.get("is_pick", 0), day),
                    )
                    stats["predictions"] += 1
        return stats
