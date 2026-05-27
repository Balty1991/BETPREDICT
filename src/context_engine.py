#!/usr/bin/env python3
"""BetPredict Context Engine v1.0.

Mathematical context layer for predictions.json.
Pure stdlib: json, math, pathlib, typing.
No API calls, no ML, no external dependencies.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

EPS = 1e-9
CTX_VERSION = "v1.0"

FACTOR_WEIGHTS = {
    "form": 0.28,
    "h2h": 0.18,
    "xgd": 0.20,
    "manager": 0.14,
    "odds_movement": 0.12,
    "referee": 0.05,
    "weather": 0.03,
}

TACTICAL_MAP = {
    "attacking": 0.14,
    "high_press": 0.11,
    "direct": 0.07,
    "possession": -0.04,
    "balanced": 0.00,
    "counter": -0.06,
    "defensive": -0.13,
    "low_block": -0.16,
}

WEATHER_GOAL_ADJ = {
    "senin": 0.00,
    "înnorat": -0.02,
    "innorat": -0.02,
    "necunoscut / acoperit": 0.00,
    "acoperit": 0.00,
    "ploaie": -0.10,
    "ninsoare": -0.13,
    "extrem": -0.17,
}

VERDICT_THRESHOLDS = {
    "homeWin": {"bet_prob": 0.58, "bet_edge": 7.0, "risk_prob": 0.50, "risk_edge": 3.0},
    "draw": {"bet_prob": 0.35, "bet_edge": 8.0, "risk_prob": 0.28, "risk_edge": 4.0},
    "awayWin": {"bet_prob": 0.55, "bet_edge": 7.0, "risk_prob": 0.47, "risk_edge": 3.0},
    "over15": {"bet_prob": 0.74, "bet_edge": 6.0, "risk_prob": 0.65, "risk_edge": 2.0},
    "over25": {"bet_prob": 0.60, "bet_edge": 6.0, "risk_prob": 0.50, "risk_edge": 2.5},
    "under25": {"bet_prob": 0.58, "bet_edge": 6.0, "risk_prob": 0.50, "risk_edge": 2.5},
    "under35": {"bet_prob": 0.72, "bet_edge": 5.0, "risk_prob": 0.63, "risk_edge": 2.0},
    "btts": {"bet_prob": 0.58, "bet_edge": 6.0, "risk_prob": 0.50, "risk_edge": 2.5},
}


def _adaptive_verdict_thresholds(base: Dict[str, Dict]) -> Dict[str, Dict]:
    """Ajustează VERDICT_THRESHOLDS pe baza adaptive_thresholds.json.
    Aceeași logică ca în fetch_daily: încearcă reabilitare, elimină ca ultimă opțiune.
    """
    try:
        at_path = Path(__file__).parent.parent / "data" / "adaptive_thresholds.json"
        if not at_path.exists():
            return base
        at = json.loads(at_path.read_text(encoding="utf-8"))
        by_market = at.get("by_market") or {}
        if not by_market:
            return base

        updated = {}
        for market, t in base.items():
            mdata = by_market.get(market) or {}
            rec = mdata.get("recommended") or {}
            edge_bkts = mdata.get("edge_buckets") or []

            if not rec or rec.get("use_defaults"):
                updated[market] = t
                continue

            prof_edge = [b for b in edge_bkts if (b.get("roi_pct") or 0) > 0 and (b.get("n") or 0) >= 3]
            market_roi = (mdata.get("stats") or {}).get("roi_pct") or 0
            market_n = (mdata.get("stats") or {}).get("n") or 0
            needs_rehab = (not prof_edge) and (market_roi < 0) and (market_n >= 10)

            if (rec.get("blacklisted") or needs_rehab) and not prof_edge:
                # Piată eliminată → praguri imposibil de atins = mereu "EVITA"
                updated[market] = {**t, "bet_prob": 0.99, "bet_edge": 99.0,
                                   "risk_prob": 0.95, "risk_edge": 50.0}
            elif market_roi < 0:
                # Pierderi moderate → ridică barele pentru "PARIAZA"
                new_bet_prob = round(max(t["bet_prob"], rec.get("min_prob_pct", 0) / 100), 2)
                new_bet_edge = round(max(t["bet_edge"], rec.get("min_edge_pp", t["bet_edge"])), 1)
                updated[market] = {**t, "bet_prob": new_bet_prob, "bet_edge": new_bet_edge}
            else:
                updated[market] = t

        return updated
    except Exception:
        return base


VERDICT_THRESHOLDS = _adaptive_verdict_thresholds(VERDICT_THRESHOLDS)

MARKET_ORDER = ("homeWin", "draw", "awayWin", "over25", "over15", "btts", "under25", "under35")


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def fnum(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def normalize3(h: float, d: float, a: float) -> Tuple[float, float, float]:
    total = h + d + a
    if total <= EPS:
        return h, d, a
    return h / total, d / total, a / total


def first_number(obj: Dict[str, Any], keys: Iterable[str], default: Optional[float] = None) -> Optional[float]:
    if not isinstance(obj, dict):
        return default
    for key in keys:
        value = fnum(obj.get(key), None)
        if value is not None:
            return value
    return default


def empty_goal_adj() -> Dict[str, float]:
    return {
        "over25": 1.0,
        "over15": 1.0,
        "over35": 1.0,
        "btts": 1.0,
        "under25": 1.0,
        "under35": 1.0,
    }


def pct_to_prob(value: Any, default: float = 0.5) -> float:
    x = fnum(value, None)
    if x is None:
        return default
    return clamp(x / 100.0 if x > 1 else x, 0.0, 1.0)


class ContextIndex:
    team_form: Dict[str, Dict[str, Any]]
    h2h: Dict[str, Dict[str, Any]]
    context_intel: Dict[str, Dict[str, Any]]
    market_intel: Dict[str, Dict[str, Any]]
    standings: Dict[str, Dict[str, Any]]
    weather: Dict[str, Dict[str, Any]]

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.team_form = {}
        self.h2h = {}
        self.context_intel = {}
        self.market_intel = {}
        self.standings = {}
        self.weather = {}
        self._load_all()

    def _load_all(self) -> None:
        team_form = read_json(self.data_dir / "team_form.json", {})
        for row in team_form.get("results", []) if isinstance(team_form, dict) else []:
            if isinstance(row, dict) and row.get("team_id") is not None:
                self.team_form[str(row["team_id"])] = row

        h2h = read_json(self.data_dir / "h2h_context.json", {})
        for row in h2h.get("results", []) if isinstance(h2h, dict) else []:
            if isinstance(row, dict) and row.get("event_id") is not None:
                self.h2h[str(row["event_id"])] = row

        ctx = read_json(self.data_dir / "context_intelligence.json", {})
        for row in ctx.get("results", []) if isinstance(ctx, dict) else []:
            if isinstance(row, dict) and row.get("event_id") is not None:
                self.context_intel[str(row["event_id"])] = row

        market = read_json(self.data_dir / "market_intelligence.json", {})
        rows = []
        if isinstance(market, dict):
            rows = market.get("results") or market.get("events") or []
        for row in rows if isinstance(rows, list) else []:
            if isinstance(row, dict) and row.get("event_id") is not None:
                self.market_intel[str(row["event_id"])] = row

        standings = read_json(self.data_dir / "standings.json", {})
        leagues = standings.get("leagues", {}) if isinstance(standings, dict) else {}
        for _league_id, league in leagues.items() if isinstance(leagues, dict) else []:
            rows = league.get("standings", []) if isinstance(league, dict) else []
            for row in rows if isinstance(rows, list) else []:
                if isinstance(row, dict) and row.get("team_id") is not None:
                    self.standings[str(row["team_id"])] = row

        match_ctx = read_json(self.data_dir / "match_context.json", {})
        for row in match_ctx.get("results", []) if isinstance(match_ctx, dict) else []:
            if not isinstance(row, dict) or row.get("event_id") is None:
                continue
            weather = row.get("weather_context")
            if isinstance(weather, dict):
                self.weather[str(row["event_id"])] = weather


def momentum_from_form(form: Any) -> Optional[float]:
    text = str(form or "").upper().strip()
    values: List[float] = []
    for ch in text[-5:]:
        if ch == "W":
            values.append(1.0)
        elif ch == "D":
            values.append(0.5)
        elif ch == "L":
            values.append(0.0)
    if not values:
        return None
    # recency: last match x3, previous x2.5, then 2, 1.5, 1
    weights = [1.0, 1.5, 2.0, 2.5, 3.0][-len(values):]
    return sum(v * w for v, w in zip(values, weights)) / sum(weights)


def factor_form(home_form: Optional[Dict[str, Any]], away_form: Optional[Dict[str, Any]]) -> Tuple[Tuple[float, float, float], float, Dict[str, float]]:
    if not isinstance(home_form, dict) or not isinstance(away_form, dict):
        return (1.0, 1.0, 1.0), 0.0, empty_goal_adj()
    hm = momentum_from_form(home_form.get("form"))
    am = momentum_from_form(away_form.get("form"))
    if hm is None or am is None:
        return (1.0, 1.0, 1.0), 0.0, empty_goal_adj()

    diff = clamp(hm - am, -1.0, 1.0)
    m_h = clamp(1.0 + 0.18 * diff, 0.70, 1.40)
    m_a = clamp(1.0 - 0.18 * diff, 0.70, 1.40)
    m_d = clamp(1.0 - 0.08 * abs(diff), 0.70, 1.40)

    combined_over25 = (pct_to_prob(home_form.get("over25_pct")) + pct_to_prob(away_form.get("over25_pct"))) / 2
    combined_btts = (pct_to_prob(home_form.get("btts_pct")) + pct_to_prob(away_form.get("btts_pct"))) / 2
    over25_adj = clamp(0.70 + combined_over25 * 0.60, 0.75, 1.25)
    btts_adj = clamp(0.70 + combined_btts * 0.60, 0.75, 1.25)
    under25_adj = clamp(2.0 - over25_adj, 0.75, 1.25)
    over15_base = (pct_to_prob(home_form.get("over15_pct"), 0.70) + pct_to_prob(away_form.get("over15_pct"), 0.70)) / 2
    over15_adj = clamp(0.82 + over15_base * 0.30, 0.82, 1.18)
    goal_ratio = clamp(((fnum(home_form.get("avg_gf"), 1.2) or 1.2) + (fnum(away_form.get("avg_gf"), 1.2) or 1.2)) / 2.4, 0.6, 1.6)
    under35_adj = clamp(1.15 - (goal_ratio - 1.0) * 0.30, 0.80, 1.20)

    sample = min(fnum(home_form.get("sample"), 0) or 0, fnum(away_form.get("sample"), 0) or 0)
    conf = clamp(sample / 5.0, 0.0, 1.0)
    return (m_h, m_d, m_a), conf, {
        **empty_goal_adj(),
        "over25": over25_adj,
        "btts": btts_adj,
        "under25": under25_adj,
        "over15": over15_adj,
        "under35": under35_adj,
    }


def factor_h2h(h2h: Optional[Dict[str, Any]], current_home_id: str) -> Tuple[Tuple[float, float, float], float, Dict[str, float]]:
    if not isinstance(h2h, dict):
        return (1.0, 1.0, 1.0), 0.0, empty_goal_adj()
    sample = int(fnum(h2h.get("sample"), 0) or 0)
    if sample < 3:
        return (1.0, 1.0, 1.0), 0.0, empty_goal_adj()
    home_wins = fnum(h2h.get("home_wins"), 0) or 0
    away_wins = fnum(h2h.get("away_wins"), 0) or 0
    draws = fnum(h2h.get("draws"), 0) or 0
    if str(h2h.get("home_team_id")) != str(current_home_id):
        home_wins, away_wins = away_wins, home_wins
    p_h, p_d, p_a = home_wins / sample, draws / sample, away_wins / sample
    w = 0.30 if sample >= 8 else 0.20
    m_h = clamp(1.0 + w * (p_h - 0.38) / 0.38, 0.72, 1.38)
    m_d = clamp(1.0 + w * (p_d - 0.26) / 0.26, 0.72, 1.38)
    m_a = clamp(1.0 + w * (p_a - 0.33) / 0.33, 0.72, 1.38)
    over25_adj = clamp(0.60 + pct_to_prob(h2h.get("over25_pct")) * 0.80, 0.75, 1.30)
    btts_adj = clamp(0.60 + pct_to_prob(h2h.get("btts_pct")) * 0.80, 0.75, 1.30)
    under25_adj = clamp(2.0 - over25_adj, 0.75, 1.25)
    avg_goals = fnum(h2h.get("avg_goals"), 2.4) or 2.4
    under35_adj = clamp(1.35 - (avg_goals / 2.4 - 1.0) * 0.50, 0.78, 1.25)
    conf = clamp(sample / 8.0, 0.0, 1.0)
    return (m_h, m_d, m_a), conf, {
        **empty_goal_adj(),
        "over25": over25_adj,
        "btts": btts_adj,
        "under25": under25_adj,
        "under35": under35_adj,
    }


def factor_xgd(home_stand: Optional[Dict[str, Any]], away_stand: Optional[Dict[str, Any]]) -> Tuple[Tuple[float, float, float], float, Dict[str, float]]:
    if not isinstance(home_stand, dict) or not isinstance(away_stand, dict):
        return (1.0, 1.0, 1.0), 0.0, empty_goal_adj()
    h_xgd = first_number(home_stand, ("xgd", "xg_diff"), 0.0) or 0.0
    a_xgd = first_number(away_stand, ("xgd", "xg_diff"), 0.0) or 0.0
    h_pos = first_number(home_stand, ("position", "rank"), None)
    a_pos = first_number(away_stand, ("position", "rank"), None)
    if h_pos is None or a_pos is None:
        h_pos, a_pos = 10.0, 10.0
    xgd_factor = clamp((h_xgd - a_xgd) / 3.0, -1.0, 1.0)
    pos_factor = clamp((a_pos - h_pos) / 18.0, -1.0, 1.0)
    combined = 0.70 * xgd_factor + 0.30 * pos_factor
    strength = 0.14
    m_h = clamp(1.0 + strength * combined, 0.78, 1.28)
    m_a = clamp(1.0 - strength * combined, 0.78, 1.28)
    m_d = clamp(1.0 - 0.06 * abs(combined), 0.78, 1.28)
    conf = clamp((abs(h_xgd) + abs(a_xgd)) / 2.0, 0.0, 1.0)
    return (m_h, m_d, m_a), conf, empty_goal_adj()


def factor_referee(referee_risk: Optional[Dict[str, Any]]) -> Tuple[float, Dict[str, float]]:
    if not isinstance(referee_risk, dict):
        return 0.0, empty_goal_adj()
    cards = fnum(referee_risk.get("cards_risk_score"), None)
    fouls = fnum(referee_risk.get("avg_fouls_per_match"), None)
    if cards is None:
        return 0.0, empty_goal_adj()
    if cards > 70:
        goal_factor = 1.0 - (cards - 70) / 100.0 * 0.10
    elif cards < 30:
        goal_factor = 1.0 + (30 - cards) / 100.0 * 0.06
    else:
        goal_factor = 1.0
    goal_factor = clamp(goal_factor, 0.88, 1.10)
    if fouls is not None:
        if fouls > 28:
            goal_factor *= 0.96
        elif fouls < 18:
            goal_factor *= 1.03
    goal_factor = clamp(goal_factor, 0.88, 1.10)
    conf = 0.7 if cards > 65 or cards < 35 else 0.3
    return conf, {
        **empty_goal_adj(),
        "over25": goal_factor,
        "over15": clamp(goal_factor * 1.05, 0.88, 1.12),
        "over35": clamp(goal_factor * 0.95, 0.85, 1.10),
        "btts": clamp(goal_factor * 0.98, 0.88, 1.10),
        "under25": clamp(2.0 - goal_factor, 0.90, 1.12),
        "under35": clamp(1.10 - (goal_factor - 1.0) * 0.5, 0.92, 1.10),
    }


def tactical_profile(manager: Dict[str, Any]) -> str:
    return str(manager.get("tactical_profile") or "").strip().lower().replace(" ", "_")


def factor_manager(home_mgr: Optional[Dict[str, Any]], away_mgr: Optional[Dict[str, Any]]) -> Tuple[Tuple[float, float, float], float, Dict[str, float]]:
    has_home = isinstance(home_mgr, dict) and bool(home_mgr)
    has_away = isinstance(away_mgr, dict) and bool(away_mgr)
    if not has_home and not has_away:
        return (1.0, 1.0, 1.0), 0.0, empty_goal_adj()
    home_mgr = home_mgr if isinstance(home_mgr, dict) else {}
    away_mgr = away_mgr if isinstance(away_mgr, dict) else {}
    h_prof = tactical_profile(home_mgr)
    a_prof = tactical_profile(away_mgr)
    h_goal = TACTICAL_MAP.get(h_prof, 0.0)
    a_goal = TACTICAL_MAP.get(a_prof, 0.0)
    h_win = pct_to_prob(home_mgr.get("win_pct"), 0.50)
    a_win = pct_to_prob(away_mgr.get("win_pct"), 0.50)
    win_diff = h_win - a_win
    m_h = clamp(1.0 + 0.10 * win_diff + 0.05 * h_goal, 0.78, 1.28)
    m_a = clamp(1.0 - 0.10 * win_diff + 0.05 * a_goal, 0.78, 1.28)
    m_d = clamp(1.0 - 0.05 * abs(win_diff), 0.78, 1.28)
    combined_tactical = (h_goal + a_goal) / 2.0
    over_adj_tactic = clamp(1.0 + combined_tactical * 0.70, 0.78, 1.25)
    h_over = fnum(home_mgr.get("over_25_pct"), None)
    a_over = fnum(away_mgr.get("over_25_pct"), None)
    if h_over is not None and a_over is not None:
        over_tendency = (pct_to_prob(h_over) + pct_to_prob(a_over)) / 2.0
        over_adj = 0.60 * over_adj_tactic + 0.40 * clamp(0.5 + over_tendency, 0.78, 1.25)
    else:
        over_adj = over_adj_tactic
    btts_adj = clamp(0.65 + combined_tactical * 0.50, 0.78, 1.22)
    under25_adj = clamp(2.0 - over_adj, 0.78, 1.22)
    conf = 0.75 if has_home and has_away else 0.35
    if h_prof in TACTICAL_MAP and a_prof in TACTICAL_MAP:
        conf += 0.15
    return (m_h, m_d, m_a), clamp(conf, 0.0, 1.0), {
        **empty_goal_adj(),
        "over25": clamp(over_adj, 0.78, 1.25),
        "over15": clamp(0.96 + (over_adj - 1.0) * 0.50, 0.85, 1.15),
        "over35": clamp(0.94 + (over_adj - 1.0) * 0.70, 0.80, 1.18),
        "btts": btts_adj,
        "under25": under25_adj,
        "under35": clamp(1.0 - (over_adj - 1.0) * 0.35, 0.84, 1.16),
    }


def factor_weather(weather: Optional[Dict[str, Any]]) -> Tuple[float, Dict[str, float]]:
    if not isinstance(weather, dict) or not weather:
        return 0.0, empty_goal_adj()
    label = str(weather.get("label") or "").lower()
    weather_adj = 0.0
    for key, val in WEATHER_GOAL_ADJ.items():
        if key in label:
            weather_adj = val
            break
    goal_factor = 1.0 + weather_adj
    temp = fnum(weather.get("temperature_c"), None)
    if temp is not None:
        if temp < 3:
            goal_factor *= 0.93
        elif temp < 8:
            goal_factor *= 0.97
    goal_factor = clamp(goal_factor, 0.82, 1.05)
    conf = 0.8 if goal_factor < 0.95 else 0.2
    return conf, {
        **empty_goal_adj(),
        "over25": goal_factor,
        "over15": clamp(goal_factor * 1.03, 0.82, 1.07),
        "over35": clamp(goal_factor * 0.96, 0.80, 1.05),
        "btts": clamp(goal_factor * 0.98, 0.82, 1.06),
        "under25": clamp(2.0 - goal_factor, 0.88, 1.18),
        "under35": clamp(1.10 - (goal_factor - 1.0) * 0.5, 0.92, 1.16),
    }


def first_movement(outcome: Any) -> str:
    if not isinstance(outcome, dict):
        return ""
    books = outcome.get("bookmakers")
    if isinstance(books, list) and books:
        first = books[0]
        if isinstance(first, dict):
            return str(first.get("movement") or "").upper()
    # fallback from counts when bookmaker rows are absent
    s = fnum(outcome.get("shortening_count"), 0) or 0
    d = fnum(outcome.get("drifting_count"), 0) or 0
    if s > d and s > 0:
        return "SHORTENING"
    if d > s and d > 0:
        return "DRIFTING"
    return ""


def mov_factor(movement: str) -> float:
    m = str(movement or "").upper()
    if m == "SHORTENING":
        return 1.07
    if m == "DRIFTING":
        return 0.96
    return 1.0


def outcome_block(market_intel: Dict[str, Any], market: str, names: Iterable[str]) -> Dict[str, Any]:
    markets = market_intel.get("markets") if isinstance(market_intel, dict) else {}
    block = markets.get(market) if isinstance(markets, dict) else {}
    outcomes = block.get("outcomes") if isinstance(block, dict) else {}
    if not isinstance(outcomes, dict):
        return {}
    lower = {str(k).lower(): v for k, v in outcomes.items()}
    for name in names:
        if name in outcomes and isinstance(outcomes[name], dict):
            return outcomes[name]
        val = lower.get(str(name).lower())
        if isinstance(val, dict):
            return val
    return {}


def factor_odds_movement(market_intel: Optional[Dict[str, Any]]) -> Tuple[Tuple[float, float, float], float, Dict[str, float]]:
    if not isinstance(market_intel, dict):
        return (1.0, 1.0, 1.0), 0.0, empty_goal_adj()
    home = first_movement(outcome_block(market_intel, "1x2", ("HOME", "home", "1")))
    draw = first_movement(outcome_block(market_intel, "1x2", ("DRAW", "draw", "X")))
    away = first_movement(outcome_block(market_intel, "1x2", ("AWAY", "away", "2")))
    over25 = first_movement(outcome_block(market_intel, "over_under_25", ("OVER 2.50", "over", "OVER")))
    btts = first_movement(outcome_block(market_intel, "btts", ("YES", "yes")))
    m_h = clamp(mov_factor(home), 0.88, 1.14)
    m_d = clamp(mov_factor(draw), 0.88, 1.14)
    m_a = clamp(mov_factor(away), 0.88, 1.14)
    over25_factor = clamp(mov_factor(over25), 0.88, 1.14)
    btts_factor = clamp(mov_factor(btts), 0.88, 1.14)
    book_conf = clamp((fnum(market_intel.get("bookmakers_count"), 0) or 0) / 14.0, 0.0, 1.0)
    n_moving = sum(1 for x in (home, draw, away, over25, btts) if x in {"SHORTENING", "DRIFTING"})
    conf = book_conf * min(1.0, n_moving * 0.35)
    return (m_h, m_d, m_a), conf, {
        **empty_goal_adj(),
        "over25": over25_factor,
        "btts": btts_factor,
        "under25": clamp(2.0 - over25_factor, 0.88, 1.12),
    }


def combine_goal_adj(*adjs: Dict[str, float]) -> Dict[str, float]:
    out = empty_goal_adj()
    for adj in adjs:
        if not isinstance(adj, dict):
            continue
        for key in out:
            out[key] *= fnum(adj.get(key), 1.0) or 1.0
    return out


def verdict_for_market(prob: float, edge_pp: float, market: str) -> str:
    t = VERDICT_THRESHOLDS[market]
    if prob >= t["bet_prob"] and edge_pp >= t["bet_edge"]:
        return "PARIAZA"
    if prob >= t["risk_prob"] and edge_pp >= t["risk_edge"]:
        return "RISC"
    return "EVITA"


def quality_grade_from_score(score: float) -> str:
    if score >= 82:
        return "A+"
    if score >= 74:
        return "A"
    if score >= 66:
        return "B+"
    if score >= 58:
        return "B"
    if score >= 50:
        return "C"
    if score >= 42:
        return "D"
    return "E"


class ContextEngine:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.idx = ContextIndex(self.data_dir)

    def enrich(self, pred: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(pred, dict):
            return pred
        ev = pred.get("event") if isinstance(pred.get("event"), dict) else {}
        event_id = str(ev.get("id") or pred.get("event_id") or "")
        home_id = str(ev.get("home_team_id") or pred.get("home_team_id") or pred.get("_home_team_id") or "")
        away_id = str(ev.get("away_team_id") or pred.get("away_team_id") or pred.get("_away_team_id") or "")

        p_h = fnum(pred.get("blended_home"), None)
        if p_h is None:
            p_h = fnum(pred.get("home_win_probability"), 0.0) or 0.0
        p_d = fnum(pred.get("blended_draw"), None)
        if p_d is None:
            p_d = fnum(pred.get("draw_probability"), 0.0) or 0.0
        p_a = fnum(pred.get("blended_away"), None)
        if p_a is None:
            p_a = fnum(pred.get("away_win_probability"), 0.0) or 0.0
        if p_h + p_d + p_a < EPS:
            return pred
        p_h, p_d, p_a = normalize3(p_h, p_d, p_a)

        p_over25 = fnum(pred.get("poisson_over25"), None)
        if p_over25 is None:
            p_over25 = fnum(pred.get("over_25_probability"), 0.5) or 0.5
        p_over15 = fnum(pred.get("poisson_over15"), None)
        if p_over15 is None:
            p_over15 = fnum(pred.get("over_15_probability"), 0.70) or 0.70
        p_btts = fnum(pred.get("poisson_btts"), None)
        if p_btts is None:
            p_btts = fnum(pred.get("btts_probability"), 0.50) or 0.50
        p_u25 = fnum(pred.get("under_25_probability"), None)
        if p_u25 is None:
            p_u25 = 1.0 - p_over25
        p_u35 = fnum(pred.get("poisson_under35"), None)
        if p_u35 is None:
            p_u35 = fnum(pred.get("under_35_probability"), 0.70) or 0.70

        home_form = self.idx.team_form.get(home_id)
        away_form = self.idx.team_form.get(away_id)
        h2h = self.idx.h2h.get(event_id)
        ctx_intel = self.idx.context_intel.get(event_id) or {}
        market_intel = self.idx.market_intel.get(event_id)
        home_stand = self.idx.standings.get(home_id)
        away_stand = self.idx.standings.get(away_id)
        weather = self.idx.weather.get(event_id)
        ref_risk = ctx_intel.get("referee_risk") if isinstance(ctx_intel, dict) else {}
        home_mgr = ctx_intel.get("home_manager") if isinstance(ctx_intel, dict) else {}
        away_mgr = ctx_intel.get("away_manager") if isinstance(ctx_intel, dict) else {}

        (m_h_f, m_d_f, m_a_f), conf_form, gadj_form = factor_form(home_form, away_form)
        (m_h_h, m_d_h, m_a_h), conf_h2h, gadj_h2h = factor_h2h(h2h, home_id)
        (m_h_x, m_d_x, m_a_x), conf_xgd, gadj_xgd = factor_xgd(home_stand, away_stand)
        conf_ref, gadj_ref = factor_referee(ref_risk)
        (m_h_m, m_d_m, m_a_m), conf_mgr, gadj_mgr = factor_manager(home_mgr, away_mgr)
        conf_wthr, gadj_wthr = factor_weather(weather)
        (m_h_o, m_d_o, m_a_o), conf_mov, gadj_mov = factor_odds_movement(market_intel)

        p_h_adj = p_h * m_h_f * m_h_h * m_h_x * m_h_m * m_h_o
        p_d_adj = p_d * m_d_f * m_d_h * m_d_x * m_d_m * m_d_o
        p_a_adj = p_a * m_a_f * m_a_h * m_a_x * m_a_m * m_a_o
        p_h_adj, p_d_adj, p_a_adj = normalize3(p_h_adj, p_d_adj, p_a_adj)

        g = combine_goal_adj(gadj_form, gadj_h2h, gadj_ref, gadj_mgr, gadj_wthr, gadj_mov, gadj_xgd)
        p_over25_adj = clamp(p_over25 * g["over25"], 0.01, 0.99)
        p_u25_adj = clamp(p_u25 * g["under25"], 0.01, 0.99)
        total_u25 = p_over25_adj + p_u25_adj
        if total_u25 > EPS:
            p_over25_adj, p_u25_adj = p_over25_adj / total_u25, p_u25_adj / total_u25
        p_over15_adj = clamp(p_over15 * g["over15"], 0.01, 0.99)
        p_btts_adj = clamp(p_btts * g["btts"], 0.01, 0.99)
        p_u35_adj = clamp(p_u35 * g["under35"], 0.01, 0.99)

        confs = {
            "form": conf_form,
            "h2h": conf_h2h,
            "xgd": conf_xgd,
            "manager": conf_mgr,
            "odds_movement": conf_mov,
            "referee": conf_ref,
            "weather": conf_wthr,
        }
        context_confidence = clamp(sum(FACTOR_WEIGHTS[k] * clamp(confs[k], 0.0, 1.0) for k in FACTOR_WEIGHTS), 0.0, 1.0)

        best_p_adj = max(p_h_adj, p_d_adj, p_a_adj)
        prob_score = clamp((best_p_adj - 0.50) / 0.30 * 100.0, 0.0, 100.0)
        edge_pp = fnum(pred.get("edge_pp"), 0.0) or 0.0
        edge_score = clamp(edge_pp / 15.0 * 100.0, 0.0, 100.0)
        base_smartbet = prob_score * 0.60 + edge_score * 0.40
        full_smartbet = prob_score * 0.42 + edge_score * 0.33 + context_confidence * 100.0 * 0.25
        blended_smartbet = (1.0 - context_confidence) * base_smartbet + context_confidence * full_smartbet
        smartbet_original = fnum(pred.get("smartbet_score"), base_smartbet) or base_smartbet
        smartbet_enhanced = clamp(max(smartbet_original, base_smartbet, blended_smartbet), 0.0, 100.0)

        probs_by_market = {
            "homeWin": p_h_adj,
            "draw": p_d_adj,
            "awayWin": p_a_adj,
            "over25": p_over25_adj,
            "over15": p_over15_adj,
            "btts": p_btts_adj,
            "under25": p_u25_adj,
            "under35": p_u35_adj,
        }
        verdicts = {m: verdict_for_market(probs_by_market[m], edge_pp, m) for m in MARKET_ORDER}
        bet_markets = [m for m in MARKET_ORDER if verdicts[m] == "PARIAZA"]
        ctx_best = max(bet_markets, key=lambda m: probs_by_market[m]) if bet_markets else None

        pred["ctx_home_win"] = round(p_h_adj, 4)
        pred["ctx_draw"] = round(p_d_adj, 4)
        pred["ctx_away_win"] = round(p_a_adj, 4)
        pred["ctx_over25"] = round(p_over25_adj, 4)
        pred["ctx_over15"] = round(p_over15_adj, 4)
        pred["ctx_btts"] = round(p_btts_adj, 4)
        pred["ctx_under25"] = round(p_u25_adj, 4)
        pred["ctx_under35"] = round(p_u35_adj, 4)
        pred["context_confidence"] = round(context_confidence, 3)
        pred["smartbet_score_base"] = round(smartbet_original, 2)
        pred["smartbet_score"] = round(smartbet_enhanced, 1)
        pred["smartbet_context_boost"] = round(smartbet_enhanced - smartbet_original, 2)
        pred["quality_grade_base"] = pred.get("quality_grade")
        pred["quality_grade"] = quality_grade_from_score(smartbet_enhanced)
        pred["ctx_verdicts"] = verdicts
        pred["ctx_best_verdict"] = ctx_best
        pred["ctx_factors"] = {
            "form": {"conf": round(conf_form, 3), "m_H": round(m_h_f, 4), "m_A": round(m_a_f, 4)},
            "h2h": {"conf": round(conf_h2h, 3), "m_H": round(m_h_h, 4), "m_A": round(m_a_h, 4)},
            "xgd": {"conf": round(conf_xgd, 3), "m_H": round(m_h_x, 4), "m_A": round(m_a_x, 4)},
            "referee": {"conf": round(conf_ref, 3)},
            "manager": {"conf": round(conf_mgr, 3), "m_H": round(m_h_m, 4), "m_A": round(m_a_m, 4)},
            "weather": {"conf": round(conf_wthr, 3)},
            "odds_movement": {"conf": round(conf_mov, 3), "m_H": round(m_h_o, 4), "m_A": round(m_a_o, 4)},
        }
        pred["_context_engine"] = CTX_VERSION
        return pred


_engine_instance: Optional[ContextEngine] = None


def get_engine(data_dir: Path) -> ContextEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = ContextEngine(data_dir)
    return _engine_instance


def enrich_with_context(pred: Dict[str, Any], data_dir: Path) -> Dict[str, Any]:
    return get_engine(data_dir).enrich(pred)


def reset_engine() -> None:
    global _engine_instance
    _engine_instance = None


__all__ = ["ContextIndex", "ContextEngine", "get_engine", "enrich_with_context", "reset_engine"]
