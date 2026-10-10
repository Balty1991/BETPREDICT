"""Generează predicțiile Robotului pentru meciurile care n-au început și le salvează în
jurnal (tabela ``prediction``) ÎNAINTE de publicare. După kickoff o predicție e înghețată."""

from __future__ import annotations

import json
import logging
import math
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from betpredict.segments import segment_action

from betpredict.config import MIN_ODDS
from betpredict.ingest.history import finished_matches
from betpredict.robot import MODEL_VERSION, REC_MAX_ODDS, REC_MIN_ODDS, is_recommended
from betpredict.robot.markets import Selection, all_selections, label_ro, market_key
from betpredict.robot.model import GoalModel, fit_elo, fit_goal_model, match_probabilities
from betpredict.robot.params import blend_weights, bsd_weight, calibrate, load_params, threshold_ok
from betpredict.store import repo
from betpredict.timeutil import canon_utc, ro_date_of, ro_day_bounds_utc

PAGE = "predictii"
log = logging.getLogger("betpredict.robot")

# cheie compactă v2 ↔ selecție
V2_KEYS: Dict[Selection, str] = {
    ("1x2", 0.0, "HOME"): "H", ("1x2", 0.0, "DRAW"): "D", ("1x2", 0.0, "AWAY"): "A",
    ("double_chance", 0.0, "1X"): "1X", ("double_chance", 0.0, "12"): "12", ("double_chance", 0.0, "X2"): "X2",
    ("draw_no_bet", 0.0, "HOME"): "DH", ("draw_no_bet", 0.0, "AWAY"): "DA",
    ("over_under", 1.5, "OVER"): "O15", ("over_under", 1.5, "UNDER"): "U15",
    ("over_under", 2.5, "OVER"): "O25", ("over_under", 2.5, "UNDER"): "U25",
    ("over_under", 3.5, "OVER"): "O35", ("over_under", 3.5, "UNDER"): "U35",
    ("btts", 0.0, "YES"): "BY", ("btts", 0.0, "NO"): "BN",
}


def _logit(p: float) -> float:
    p = min(1 - 1e-6, max(1e-6, p))
    return math.log(p / (1 - p))


def _sig(z: float) -> float:
    return 1 / (1 + math.exp(-z))


def expand_core(c: Dict[str, float], o05: Optional[float] = None, o45: Optional[float] = None) -> Dict[Selection, float]:
    """H/D/A + Peste 1.5/2.5/3.5 + GG → toate selecțiile (DC, DNB, Sub, NG; O/U 0.5/4.5 din matricea DC)."""
    out: Dict[Selection, float] = {}
    if all(k in c for k in ("H", "D", "A")):
        h, d, a = c["H"], c["D"], c["A"]
        out[("1x2", 0.0, "HOME")], out[("1x2", 0.0, "DRAW")], out[("1x2", 0.0, "AWAY")] = h, d, a
        out[("double_chance", 0.0, "1X")], out[("double_chance", 0.0, "12")], out[("double_chance", 0.0, "X2")] = h + d, h + a, d + a
        out[("draw_no_bet", 0.0, "HOME")] = h / max(1e-9, h + a)
        out[("draw_no_bet", 0.0, "AWAY")] = a / max(1e-9, h + a)
    for ln, k in ((1.5, "O15"), (2.5, "O25"), (3.5, "O35")):
        if k in c:
            out[("over_under", ln, "OVER")], out[("over_under", ln, "UNDER")] = c[k], 1 - c[k]
    if "BY" in c:
        out[("btts", 0.0, "YES")], out[("btts", 0.0, "NO")] = c["BY"], 1 - c["BY"]
    for ln, v in ((0.5, o05), (4.5, o45)):
        if v is not None:
            out[("over_under", ln, "OVER")], out[("over_under", ln, "UNDER")] = v, 1 - v
    return out

MARKET_OUTCOMES = {"1x2": ("HOME", "DRAW", "AWAY"), "double_chance": None, "draw_no_bet": ("HOME", "AWAY"),
                   "btts": ("YES", "NO")}


def novig(odds_by_outcome: Dict[str, float], outcomes) -> Dict[str, float]:
    vals = {o: odds_by_outcome.get(o) for o in outcomes}
    if any(not v or v <= 1.0 for v in vals.values()):
        return {}
    if len(vals) == 3:  # v4: Shin pe piețele cu 3 rezultate (1X2)
        from betpredict.model.calib import shin
        sh = shin([vals[o] for o in outcomes])
        if sh:
            return dict(zip(outcomes, sh))
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


LONGSHOT_ODDS = 4.0
EV_CAP = 0.25  # v4: EV afișat plafonat (peste ~25% e aproape sigur zgomot de model, nu valoare reală)
SHRINK_GROUP = {"top": 0.30, "second": 0.45, "other": 0.60}


TOP_PER_DAY, TOP_PER_LEAGUE = 12, 3


def select_top(conn, now: datetime) -> Dict[str, int]:
    """v4: din selecțiile „recomandate” rămân doar cele mai bune ~12/zi după edge × siguranță
    (max. 1 pe meci, 3 pe ligă). Marcajul ``top`` stă în reasons_json; ``is_recommended`` îl respectă."""
    from betpredict.robot import is_recommended
    from betpredict.timeutil import canon_utc
    now_s = canon_utc(now.isoformat())
    rows = conn.execute(
        """SELECT p.id, p.day, p.p_calibrated, p.odds_shown, p.ev, p.grade, p.confidence, p.reasons_json, m.league_id, p.match_id
           FROM prediction p JOIN match m ON m.id = p.match_id
           WHERE p.model_version = ? AND p.result IS NULL AND m.kickoff_utc > ?""", (MODEL_VERSION, now_s)).fetchall()
    by_day: Dict[str, List[Any]] = {}
    for r in rows:
        try:
            ex = json.loads(r["reasons_json"] or "{}")
        except ValueError:
            ex = {}
        ok = is_recommended(r["p_calibrated"], r["odds_shown"], r["ev"], r["grade"], bool(ex.get("healthy", True)), top=True)
        by_day.setdefault(r["day"], []).append((r, ex, ok))
    out = {"top": 0}
    for day, items in by_day.items():
        cands = sorted([x for x in items if x[2]], key=lambda x: (x[0]["ev"] or 0) * x[0]["p_calibrated"] * (0.5 + (x[0]["confidence"] or 0) / 200), reverse=True)
        chosen, per_m, per_l = set(), set(), {}
        for r, ex, _ in cands:
            if len(chosen) >= TOP_PER_DAY or r["match_id"] in per_m or per_l.get(r["league_id"], 0) >= TOP_PER_LEAGUE:
                continue
            chosen.add(r["id"]); per_m.add(r["match_id"]); per_l[r["league_id"]] = per_l.get(r["league_id"], 0) + 1
        for r, ex, _ in items:
            t = r["id"] in chosen
            if ex.get("top") != t:
                ex["top"] = t
                conn.execute("UPDATE prediction SET reasons_json=? WHERE id=?", (json.dumps(ex, ensure_ascii=False), r["id"]))
        out["top"] += len(chosen)
    conn.commit()
    return out


def market_shrink(league_id: Any, odds: Optional[float]) -> float:
    """Ponderea pieței în p final: 30% ligi top, 45% ligi secunde, 60% restul; +15 pp peste cota 3, +25 pp peste 5."""
    from betpredict.model.calib import league_group
    w = SHRINK_GROUP.get(league_group(league_id), 0.6)
    if odds and odds > 5:
        w += 0.25
    elif odds and odds > 3:
        w += 0.15
    return min(0.9, w)

BOOKMAKER_LABEL = {"superbet": "Superbet", "bsd_consensus": "Consens piață (BSD)"}


def best_price(o_superbet: Optional[float], o_consensus: Optional[float]) -> Tuple[Optional[float], Optional[str]]:
    """Cota folosită pentru EV: prețul JUCABIL. Superbet (casă reală, verificată în ultimele ore) are
    prioritate; consensul BSD (media pieței) e folosit doar când Superbet nu oferă selecția."""
    if o_superbet and o_superbet > 1.0:
        return o_superbet, "superbet"
    if o_consensus and o_consensus > 1.0:
        return o_consensus, "bsd_consensus"
    return None, None


def price_reason(o_sb: Optional[float], o_cons: Optional[float]) -> List[str]:
    if o_sb and o_cons:
        d = o_sb / o_cons - 1
        tag = "peste" if d > 0.005 else "sub" if d < -0.005 else "la nivelul"
        return [f"Cotă Superbet {o_sb:.2f} — {tag} consensului pieței ({o_cons:.2f}, {d * 100:+.1f}%)"]
    if o_cons and not o_sb:
        return [f"Cotă de referință: consensul pieței {o_cons:.2f} (Superbet nu listează selecția)"]
    return []


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
            FROM odds_snapshot WHERE match_id IN ({q}) AND opening_decimal IS NOT NULL AND source='bsd_consensus'
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


def load_v2_artifact(conn: sqlite3.Connection, train_if_missing: bool = True) -> Optional[Dict[str, Any]]:
    """Campionul Robot v2 din DB; dacă lipsește (prima rulare), îl antrenează o dată (~3–6 min)."""
    try:
        from betpredict.model import gbm as _g
        from betpredict.model.v2 import fit_artifact, load_champion, save_artifact

        art = load_champion(conn)
        if art is not None and "calib" not in art and train_if_missing and _g.available():
            log.info("Robot v2: campion fără calibrare v4 — reantrenare o singură dată")
            art = None  # upgrade v4: calibrare pe piață×grup + blend pe ligă + Shin
        if art is None and train_if_missing and _g.available():
            art = fit_artifact(conn, log=log.info)
            save_artifact(conn, art, "champion")
        return art
    except Exception as exc:  # noqa: BLE001
        log.warning("Robot v2: artefact indisponibil (%s)", exc)
        return None


class Robot:
    def __init__(self, conn: sqlite3.Connection, now: Optional[datetime] = None, train_if_missing: bool = True):
        self.conn = conn
        self.now = now or datetime.now(timezone.utc)
        self.params = load_params(conn)
        rows = [tuple(r) for r in finished_matches(conn)]
        self.model: GoalModel = fit_goal_model(rows, self.now)
        self.elo = fit_elo(rows, canon_utc(self.now.isoformat()))
        self.n_history = len(rows)
        self.v2 = None            # LivePredictor (setat în run)
        self.features: Dict[int, Dict[str, Any]] = {}
        self.art = load_v2_artifact(conn, train_if_missing=train_if_missing and len(rows) >= 5000)
        self.engine = self.art["engine"] if self.art else MODEL_VERSION

    def _superavantaj(self, m, info: Dict[str, Any]) -> Dict[str, float]:
        from betpredict.model.calib import league_group
        if league_group(m["league_id"]) == "other":  # aplicăm doar pe competițiile principale (eligibilitate probabilă)
            return {}
        cache = self.__dict__.setdefault("_sa_cache", {})
        if m["id"] not in cache:
            try:
                from betpredict.model import sim as SIM
                S = SIM.simulate(float(info["lambda_home"]), float(info["lambda_away"]), n=6000, seed=int(m["id"]) % 100000)
                cache[m["id"]] = SIM.superavantaj(S)
            except Exception:  # noqa: BLE001
                cache[m["id"]] = {}
        return cache[m["id"]]

    def _blocked(self, key: str, league_id: Any) -> bool:
        from betpredict.model.calib import league_group
        bl = set(((self.art or {}).get("calib") or {}).get("blocked") or [])
        base = {"DH": "H", "DA": "A", "1X": "A", "X2": "H", "12": "D", "U15": "O15", "U25": "O25", "U35": "O35", "BN": "BY"}.get(key, key)
        return f"{base}|{league_group(league_id)}" in bl

    def predict_match(self, m: sqlite3.Row, odds: Dict[str, Dict[str, float]], bsd: Dict[str, Dict[str, float]],
                      ctx: Dict[str, Any], moves: Dict[str, Dict[str, Any]],
                      playable: Optional[Dict[str, Dict[str, float]]] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        mkt = market_probs(odds)
        league_mult = float(self.params.get("league_penalty", {}).get(str(m["league_id"]), 1.0))
        excluded = set(self.params.get("excluded_markets", []))
        v2 = self.v2.get(m["id"]) if self.v2 is not None else None
        core: Dict[Selection, float] = {}
        if v2 is not None:
            # Robot v2: GBM + Dixon-Coles (stacking calibrat) → combinat cu piața (shrink învățat) → BSD (pondere învățată)
            probs = expand_core(v2["p"], v2["o05"], v2["o45"])
            mk_c = {V2_KEYS[k]: v for k, v in mkt.items() if k in V2_KEYS and V2_KEYS[k] in ("H", "D", "A", "O15", "O25", "O35", "BY")}
            comb = self.v2.with_market(m["id"], mk_c) or {}
            core = expand_core({**{k: v2["p"][k] for k in v2["p"]}, **comb})
            for ln in (0.5, 4.5):  # liniile fără stacker: 35% model, 65% piață (spațiul logit)
                for side in ("OVER", "UNDER"):
                    sel_ = ("over_under", ln, side)
                    pm_, pk_ = probs.get(sel_), mkt.get(sel_)
                    if pm_ is not None:
                        core[sel_] = _sig(0.35 * _logit(pm_) + 0.65 * _logit(pk_)) if pk_ is not None else pm_
            info = {k: v2[k] for k in ("lambda_home", "lambda_away", "elo_home", "elo_away", "most_likely_score", "top_scores")}
            coverage = v2["coverage"]
            league_mult *= 0.85 + 0.15 * v2["league_rel"]
            self.features[m["id"]] = v2["features"]
        else:
            probs, info = match_probabilities(self.model, self.elo, m["home_id"], m["away_id"], m["league_id"])
            coverage = min(self.model.coverage(m["home_id"]), self.model.coverage(m["away_id"]))
        out: List[Dict[str, Any]] = []
        for sel in all_selections():
            mk = market_key(sel[0], sel[1])
            p_model = probs.get(sel)
            p_bsd = bsd_lookup(bsd, sel)
            p_mkt = mkt.get(sel)
            if v2 is not None:
                if sel not in core:
                    continue
                p_pre = p_core = core[sel]
                wb = bsd_weight(self.params, mk) if p_bsd is not None else 0.0
                if wb > 0:
                    p_pre = _sig((1 - wb) * _logit(p_pre) + wb * _logit(p_bsd))
            else:
                p_core = None
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
                p_pre = sum(x * y for x, y in parts) / den
            p = round(min(0.995, max(0.005, calibrate(self.params, mk, p_pre))), 4)
            # cota JUCABILĂ: Superbet (proaspătă) are prioritate; consensul BSD rămâne referința de piață
            o_cons = odds_lookup(odds, sel)
            o_sb = odds_lookup(playable or {}, sel)
            o, o_src = best_price(o_sb, o_cons)
            if p_mkt is not None and 0 < p_mkt < 1:  # v4: shrink spre piață, mai puternic în ligi mici și la cote mari
                wm = market_shrink(m["league_id"], o)
                p = round(_sig(wm * _logit(p_mkt) + (1 - wm) * _logit(p)), 4)
            ev_raw = round(p * o - 1, 4) if o else None
            ev = min(EV_CAP, ev_raw) if ev_raw is not None else None
            sa_bonus = 0.0
            if ev is not None and o_src == "superbet" and sel in (("1x2", 0.0, "HOME"), ("1x2", 0.0, "AWAY")) and v2 is not None:
                sa_bonus = self._superavantaj(m, info).get("home" if sel[2] == "HOME" else "away", 0.0)
                if sa_bonus > 0:  # v4: SuperAvantaj — câștig și când echipa conduce cu 2 goluri oricând (cote normale, nu mărite)
                    ev = min(EV_CAP, round((p + sa_bonus) * o - 1, 4))
            if not should_publish(p, o, ev):
                continue
            srcs = [v for v in (p_model, p_bsd, p_mkt) if v is not None]
            agreement = max(0.0, 1 - 2 * max(abs(v - p) for v in srcs)) if srcs else 0.5
            # piață sănătoasă = calibrare OK + pragul adaptiv (EV minim pe piață, ligi blocate) învățat din rezultate
            healthy = mk not in excluded and threshold_ok(self.params, mk, m["league_id"], ev)
            if healthy and v2 is not None and sel in V2_KEYS and self._blocked(V2_KEYS[sel], m["league_id"]):
                healthy = False  # v4: piață × grup de ligi cu ECE > 3% pe ultimele 30 zile (backtest artefact)
            if healthy and o and o > LONGSHOT_ODDS and segment_action(self.params, m["league_id"], mk) != "boost":
                healthy = False  # v4: bias favorit–outsider — cote > 4.0 doar pe segmente cu CLV istoric pozitiv
            seg_mult = 1.05 if segment_action(self.params, m["league_id"], mk) == "boost" else 1.0  # segment întărit (CLV+)
            g, conf = grade_and_confidence(p, agreement, o is not None, ev, healthy, coverage, league_mult * seg_mult)
            mv = (moves.get(mk) or {}).get(sel[2])
            out.append({
                "match_id": m["id"], "market": sel[0], "line": sel[1], "period": "FT", "selection": sel[2],
                "p_model": round(p_model, 4) if p_model is not None else None,
                "p_calibrated": p, "p_market_novig": round(p_mkt, 4) if p_mkt is not None else None,
                "p_bsd": round(p_bsd, 4) if p_bsd is not None else None,
                "odds_shown": o, "odds_source": o_src,
                "odds_alt": {k: v for k, v in (("superbet", o_sb), ("bsd_consensus", o_cons)) if v},
                "edge": round(p - 1 / o, 4) if o else None, "ev": ev, "confidence": conf, "grade": g,
                "reasons": build_reasons(sel, ctx, info, p_bsd, p_mkt, p, mv) + price_reason(o_sb, o_cons)
                + ([f"SuperAvantaj Superbet: +{sa_bonus * 100:.1f} pp șansă de plată (conduce cu 2 goluri oricând) — inclus în EV"] if sa_bonus > 0 else []),
                "healthy": healthy, "p_pre": round(p_pre, 4),
                "p_core": round(p_core, 4) if p_core is not None else None,
            })
        # predicția principală (conservator): întâi selecțiile „recomandate” (p ≥ 60%, EV > 0, cotă 1.15–2.20, A/B);
        # altfel cea mai probabilă selecție cu cotă 1.15–2.20 și EV ≥ −3% (afișată, dar NEmarcată recomandată).
        for x in out:
            x["recommended"] = is_recommended(x["p_calibrated"], x["odds_shown"], x["ev"], x["grade"], x["healthy"])
        rec = [x for x in out if x["recommended"]]
        if rec:
            best = max(rec, key=lambda x: (x["p_calibrated"] + 0.5 * (x["ev"] or 0), x["confidence"]))
            best["is_pick"] = 1
        else:
            safe = [x for x in out if x["odds_shown"] and REC_MIN_ODDS <= x["odds_shown"] <= REC_MAX_ODDS
                    and (x["ev"] or 0) >= -0.03 and x["healthy"] and x["grade"] in ("A", "B")]
            if safe:
                max(safe, key=lambda x: (x["p_calibrated"], x["confidence"]))["is_pick"] = 1
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
        try:
            from betpredict.ingest.superbet import playable_odds

            sb_all = playable_odds(self.conn, ids, self.now)
        except Exception as exc:  # noqa: BLE001
            log.warning("Superbet indisponibil (%s)", exc)
            sb_all = {}
        bsd_all = provider_probs(self.conn, ids)
        moves_all = odds_movement(self.conn, ids)
        ctx_all = {r["match_id"]: json.loads(r["context_json"]) for r in self.conn.execute(
            f"SELECT match_id, context_json FROM match_context WHERE match_id IN ({','.join('?' for _ in ids) or 'NULL'})", ids)}
        self.features: Dict[int, Dict[str, Any]] = {}
        if self.art is not None and matches:
            try:
                from betpredict.model.v2 import LivePredictor

                ok_m = [m for m in matches if m["home_id"] is not None and m["away_id"] is not None]
                self.v2 = LivePredictor(self.conn, self.art, ok_m, now_t=self.now.timestamp() / 86400.0)
            except Exception as exc:  # noqa: BLE001 — robotul nu cade: revine la v1
                log.warning("Robot v2 indisponibil (%s); folosesc v1", exc)
                self.v2 = None
        stats = {"matches": len(matches), "predictions": 0, "engine": self.engine if self.v2 is not None else MODEL_VERSION}
        created = repo.now_iso()
        with self.conn:
            for m in matches:
                preds, info = self.predict_match(m, odds_all.get(m["id"], {}), bsd_all.get(m["id"], {}),
                                                 ctx_all.get(m["id"], {}), moves_all.get(m["id"], {}), sb_all.get(m["id"]))
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
                               model_version, created_at, shown_on_page, is_pick, day,
                               odds_taken, odds_taken_source, odds_taken_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(match_id, market, line, period, selection, model_version, shown_on_page)
                           DO UPDATE SET p_model=excluded.p_model, p_calibrated=excluded.p_calibrated,
                               p_market_novig=excluded.p_market_novig, p_bsd=excluded.p_bsd,
                               odds_shown=excluded.odds_shown, odds_source=excluded.odds_source, edge=excluded.edge,
                               ev=excluded.ev, confidence=excluded.confidence, grade=excluded.grade,
                               reasons_json=excluded.reasons_json, is_pick=excluded.is_pick, day=excluded.day,
                               odds_taken=COALESCE(prediction.odds_taken, excluded.odds_taken),
                               odds_taken_source=COALESCE(prediction.odds_taken_source, excluded.odds_taken_source),
                               odds_taken_at=COALESCE(prediction.odds_taken_at, excluded.odds_taken_at)
                           WHERE prediction.result IS NULL""",
                        (p["match_id"], p["market"], p["line"], p["period"], p["selection"], p["p_model"],
                         p["p_calibrated"], p["p_market_novig"], p["p_bsd"], p["odds_shown"], p["odds_source"],
                         p["edge"], p["ev"], p["confidence"], p["grade"],
                         json.dumps({"reasons": p["reasons"], "healthy": p["healthy"], "p_pre": p.get("p_pre"), "p_core": p.get("p_core"),
                                     "odds_alt": p.get("odds_alt") or None,
                                     "engine": self.engine if m["id"] in self.features else MODEL_VERSION}, ensure_ascii=False),
                         MODEL_VERSION, created, PAGE, p.get("is_pick", 0), day,
                         p["odds_shown"], p["odds_source"] if p["odds_shown"] else None, created if p["odds_shown"] else None),
                    )
                    stats["predictions"] += 1
                if m["id"] in self.features:  # snapshotul exact de feature-uri folosit (pentru auto-învățare)
                    self.conn.execute(
                        "INSERT INTO feature_row(match_id, model_version, features, created_at) VALUES (?,?,?,?) "
                        "ON CONFLICT(match_id, model_version) DO UPDATE SET features=excluded.features, created_at=excluded.created_at",
                        (m["id"], self.engine, json.dumps(self.features[m["id"]]), created))
        stats["top"] = select_top(self.conn, self.now)
        return stats
