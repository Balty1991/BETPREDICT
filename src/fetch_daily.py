#!/usr/bin/env python3
"""
BetPredict Pro — Daily Data Fetcher (v13 Settlement Logic)
==================================================
Pasul 13: Settlement Logic — evaluare explicabilă WIN/LOSS pe piețe 1X2, O/U și BTTS.

Ce rezolvă această versiune:
  - folosește endpointul BSD v2 corect pentru best odds: /api/v2/odds/best/
  - înlocuiește parametrul vechi days=N cu date_from/date_to
  - normalizează odds v2 în forma compatibilă cu UI-ul existent și analytics_core
  - adaugă debug JSON structurat în data/debug/
  - nu suprascrie fișiere utile cu rezultate goale când un endpoint pică
  - păstrează logica utilă existentă: Poisson, no-vig, Kelly, quality grade
  - filtrează Value Bets locale speculative și elimină odds estimate din semnale
  - construiește data/match_context.json pentru meciuri prioritare
  - construiește data/performance_summary.json pentru monitorizarea performanței
  - construiește data/selection_journal.json și data/recent_results.json pentru backtesting real în timp
  - adaugă settlement_reason, actual_score și market_canonical pentru fiecare selecție finalizată
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

_ROOT = Path(__file__).parent.parent.resolve()
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from analytics_core import (
        blend_probabilities,
        expected_value_decimal,
        kelly_fraction as ac_kelly,
        normalize_no_vig,
        poisson_market_probabilities,
        quality_grade,
        safe_float,
    )

    no_vig_prob = normalize_no_vig
    HAS_AC = True
    print("analytics_core: OK")
except Exception as exc:  # păstrăm pipeline-ul funcțional chiar dacă analytics_core are o problemă
    HAS_AC = False
    print(f"analytics_core: SKIP ({exc})")

# ── Config ──────────────────────────────────────────────────────────────────
API_KEY = os.environ.get("BSD_API_KEY", "").strip()
BASE_V2 = "https://sports.bzzoiro.com/api/v2"
BASE_V1 = "https://sports.bzzoiro.com/api"
IMG_BASE = "https://sports.bzzoiro.com/img"  # FREE, no auth
HEADERS = {"Authorization": f"Token {API_KEY}"} if API_KEY else {}
DATA_DIR = Path(__file__).parent.parent / "data"
DEBUG_DIR = DATA_DIR / "debug"

# Toate cele 52 ligi BSD
LEAGUES = {
    1: "Premier League",
    2: "Liga Portugal",
    3: "La Liga",
    4: "Serie A",
    5: "Bundesliga",
    6: "Ligue 1",
    7: "Champions League",
    8: "Europa League",
    9: "Brasileirao Serie A",
    10: "Eredivisie",
    11: "Veikkausliiga",
    12: "Championship",
    13: "Scottish Prem",
    14: "Pro League BE",
    15: "Super League CH",
    16: "Trendyol Super Lig",
    17: "Saudi Pro League",
    18: "Coppa Italia",
    19: "Liga MX Clausura",
    20: "Liga MX Apertura",
    21: "Copa del Rey",
    22: "Parva Liga",
    23: "Superliga România",
    24: "Super League GR",
    25: "Ekstraklasa",
    26: "Allsvenskan",
    27: "World Cup 2026",
    28: "Copa Libertadores",
    29: "Copa Sudamericana",
    30: "MLS",
    31: "DFB Pokal",
    32: "FA Cup",
    33: "Carabao Cup",
    34: "J1 League",
    35: "K League 1",
    36: "Chinese Super League",
    37: "Brasileirao Serie B",
    38: "Eliteserien",
    39: "Africa Cup",
    40: "CAF Champions",
    41: "Copa do Brasil",
    42: "Botola Pro",
    43: "Nigeria Premier",
    44: "Puchar Polski",
    45: "Emperor Cup",
    46: "Segunda Division",
    47: "Coupe de France",
    48: "International Friendly",
    49: "Suomen Cup",
    50: "Coupe de Tunisie",
    51: "Tunisian Ligue",
    52: "Liga F",
}

STRATEGIES = {
    "engine_overall": {
        "label": "Engine Overall",
        "icon": "🎯",
        "markets": ["homeWin", "draw", "awayWin", "over15", "under25", "under35"],
        "min_adj": 66.0,
        "min_edge": 8.0,
        "odd_min": 1.15,
        "odd_max": 1.65,
        "color": "#00e87a",
    },
    "best_single": {
        "label": "Evenimentul zilei",
        "icon": "⭐",
        "markets": ["homeWin", "over15", "over25", "under35"],
        "min_adj": 72.0,
        "min_edge": 8.0,
        "odd_min": 1.20,
        "odd_max": 1.95,
        "color": "#ffb830",
    },
    "conservative": {
        "label": "Bilet conservator",
        "icon": "🛡️",
        "markets": ["over15", "under35"],
        "min_adj": 74.0,
        "min_edge": 5.0,
        "odd_min": 1.12,
        "odd_max": 1.65,
        "color": "#4a9eff",
    },
    "smart_ev": {
        "label": "Smart EV",
        "icon": "💡",
        "markets": ["homeWin", "awayWin", "over15", "over25", "under35"],
        "min_adj": 66.0,
        "min_edge": 2.0,
        "odd_min": 1.20,
        "odd_max": 2.20,
        "color": "#a78bfa",
    },
    "over15_specialist": {
        "label": "Over 1.5G",
        "icon": "⚽",
        "markets": ["over15"],
        "min_adj": 76.0,
        "min_edge": 8.0,
        "odd_min": 1.43,
        "odd_max": 1.60,
        "color": "#22d3ee",
    },
}

MARKET_LABELS = {
    "homeWin": "1 Victorie acasă",
    "draw": "X Egal",
    "awayWin": "2 Victorie deplasare",
    "over15": "Over 1.5G",
    "over25": "Over 2.5G",
    "under25": "Under 2.5G",
    "under35": "Under 3.5G",
    "btts": "BTTS",
    "home_win": "Victorie acasă",
    "away_win": "Victorie deplasare",
    "draw_result": "Egal",
    "under_25": "Under 2.5",
    "under_35": "Under 3.5",
    "over_25": "Over 2.5",
    "over_15": "Over 1.5",
    "1": "Victorie acasă",
    "X": "Egal",
    "2": "Victorie deplasare",
    "1x2": "1X2",
    "over_under_15": "Over/Under 1.5",
    "over_under_25": "Over/Under 2.5",
    "over_under_35": "Over/Under 3.5",
}

DEBUG: Dict[str, Any] = {
    "started_at": None,
    "finished_at": None,
    "has_api_key": bool(API_KEY),
    "requests": [],
    "jobs": {},
    "warnings": [],
}

# ── Helpers ─────────────────────────────────────────────────────────────────
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_iso() -> str:
    # GitHub Actions rulează pe UTC. +4h evită rularea prea devreme pentru România.
    return (datetime.now(timezone.utc) + timedelta(hours=4)).strftime("%Y-%m-%d")


def date_window(days: int = 7) -> Tuple[str, str]:
    start = datetime.now(timezone.utc)
    end = start + timedelta(days=days)
    return start.replace(microsecond=0).isoformat().replace("+00:00", "Z"), end.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def logo_url(typ: str, id_: Any) -> Optional[str]:
    return f"{IMG_BASE}/{typ}/{id_}/" if id_ else None


def as_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def as_pct(value: Any) -> Optional[float]:
    """Normalizează probabilități 0-1 sau 0-100 către procent 0-100."""
    v = as_float(value)
    if v is None:
        return None
    return round(v * 100, 2) if 0 <= v <= 1 else round(v, 2)


def count_payload(data: Any) -> int:
    if isinstance(data, list):
        return len(data)
    if not isinstance(data, dict):
        return 0
    if isinstance(data.get("count"), int):
        return int(data["count"])
    for key in ("results", "signals", "events", "standings"):
        value = data.get(key)
        if isinstance(value, (list, dict)):
            return len(value)
    if isinstance(data.get("leagues"), dict):
        return len(data["leagues"])
    return 0


def record_job(name: str, **payload: Any) -> None:
    DEBUG["jobs"][name] = {**payload, "recorded_at": now_iso()}


def warn(message: str, **context: Any) -> None:
    entry = {"message": message, "context": context, "time": now_iso()}
    DEBUG["warnings"].append(entry)
    print(f"  ⚠ {message}")


def save_debug(filename: str, data: Any) -> None:
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    path = DEBUG_DIR / filename
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_all_debug() -> None:
    DEBUG["finished_at"] = now_iso()
    save_debug("daily_debug.json", DEBUG)


def save(filename: str, data: Any, protect_empty: bool = True, job_name: Optional[str] = None) -> bool:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / filename
    new_cnt = count_payload(data)

    if isinstance(data, dict):
        data.setdefault("updated_at", now_iso())
        data.setdefault("count", new_cnt)
        data.setdefault("_pipeline_version", "v13-settlement-logic")

    if protect_empty and new_cnt == 0 and path.exists():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
            old_cnt = count_payload(old)
            if old_cnt > 0:
                warn(
                    f"SKIP {filename}: rezultat nou gol, păstrez fișierul existent",
                    old_count=old_cnt,
                    new_count=new_cnt,
                )
                if job_name:
                    record_job(job_name, file=filename, saved=False, reason="protected_empty", old_count=old_cnt, new_count=0)
                return False
        except Exception as exc:
            warn(f"Nu pot citi fișierul vechi {filename}; voi scrie noul payload", error=str(exc))

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    print(f"  OK {filename} ({new_cnt})")
    if job_name:
        record_job(job_name, file=filename, saved=True, count=new_cnt)
    return True


# ── HTTP ─────────────────────────────────────────────────────────────────────
def get(url: str, params: Optional[Dict[str, Any]] = None, label: str = "") -> Optional[Any]:
    params = {k: v for k, v in (params or {}).items() if v is not None}
    for attempt in range(1, 4):
        started = datetime.now(timezone.utc)
        try:
            r = requests.get(url, headers=HEADERS, params=params or None, timeout=35)
            elapsed_ms = round((datetime.now(timezone.utc) - started).total_seconds() * 1000)
            DEBUG["requests"].append(
                {
                    "label": label,
                    "url": url,
                    "params": params,
                    "status": r.status_code,
                    "attempt": attempt,
                    "elapsed_ms": elapsed_ms,
                }
            )
            if r.status_code in (401, 403):
                warn("Auth BSD eșuat — verifică secretul BSD_API_KEY", url=url, status=r.status_code)
                return None
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError as exc:
            if attempt == 3:
                status = getattr(exc.response, "status_code", None)
                warn("HTTP error după 3 încercări", url=url, params=params, status=status, error=str(exc))
                return None
        except Exception as exc:
            if attempt == 3:
                warn("Request eșuat după 3 încercări", url=url, params=params, error=str(exc))
                return None
    return None


def extract_results(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("results", "events", "value_bets", "picks", "data"):
        value = data.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []


def get_all_pages(url: str, params: Optional[Dict[str, Any]] = None, max_pages: int = 30, label: str = "") -> List[Dict[str, Any]]:
    params = dict(params or {})
    params.setdefault("limit", 100)
    results: List[Dict[str, Any]] = []
    page_url: Optional[str] = url
    seen: set[str] = set()
    page = 0

    while page_url and page_url not in seen and page < max_pages:
        seen.add(page_url)
        data = get(page_url, params if page_url == url else None, label=label)
        if not data:
            break
        batch = extract_results(data)
        results.extend(batch)
        page += 1
        if batch:
            print(f"    p{page}: +{len(batch)} (Σ{len(results)})")
        page_url = data.get("next") if isinstance(data, dict) else None
        params = {}
    return results


# ── Normalize BSD v2 prediction ─────────────────────────────────────────────
def normalize_pred(p: Dict[str, Any], fallback_lid: Optional[int] = None, fallback_lname: str = "") -> Dict[str, Any]:
    ev = p.get("event") or {}
    markets = p.get("markets") or {}
    mr = markets.get("match_result") or {}
    xg = markets.get("expected_goals") or {}
    ou = markets.get("over_under") or {}
    bt = markets.get("btts") or {}
    sc = markets.get("score") or {}
    mdl = p.get("model") or {}

    lid = ev.get("league_id") or fallback_lid
    lname = ev.get("league_name") or LEAGUES.get(int(lid) if lid else 0, f"Liga {lid}") or fallback_lname

    p["_league_id"] = lid
    p["_league_name"] = lname
    p["_home_team_id"] = ev.get("home_team_id")
    p["_away_team_id"] = ev.get("away_team_id")
    p["_team_logo_home"] = logo_url("team", ev.get("home_team_id"))
    p["_team_logo_away"] = logo_url("team", ev.get("away_team_id"))
    p["_league_logo"] = logo_url("league", lid)

    ph, pd_, pa = mr.get("prob_home"), mr.get("prob_draw"), mr.get("prob_away")
    if ph is not None:
        p["home_win_probability"] = round(float(ph) / 100, 4)
    if pd_ is not None:
        p["draw_probability"] = round(float(pd_) / 100, 4)
    if pa is not None:
        p["away_win_probability"] = round(float(pa) / 100, 4)

    p["recommended_bet"] = {"H": "1", "D": "X", "A": "2"}.get(mr.get("predicted", ""), "")

    if xg.get("home") is not None:
        p["predicted_home_goals"] = xg["home"]
        p["predicted_away_goals"] = xg.get("away")

    o15 = ou.get("prob_over_15")
    o25 = ou.get("prob_over_25")
    o35 = ou.get("prob_over_35")
    if o15 is not None:
        p["over_15_probability"] = round(float(o15) / 100, 4)
    if o25 is not None:
        p["over_25_probability"] = round(float(o25) / 100, 4)
        p["under_25_probability"] = round(1 - float(o25) / 100, 4)
    if o35 is not None:
        p["over_35_probability"] = round(float(o35) / 100, 4)
        p["under_35_probability"] = round(1 - float(o35) / 100, 4)

    pbtts = bt.get("prob_yes")
    if pbtts is not None:
        p["btts_probability"] = round(float(pbtts) / 100, 4)

    p["confidence"] = mdl.get("confidence")
    p["most_likely_score"] = sc.get("most_likely")
    return p


def enrich_analytics(p: Dict[str, Any]) -> Dict[str, Any]:
    if not HAS_AC:
        p["quality_grade"] = "—"
        p["smartbet_score"] = 0
        return p

    pH = p.get("home_win_probability", 0)
    pD = p.get("draw_probability", 0)
    pA = p.get("away_win_probability", 0)
    xgH = p.get("predicted_home_goals")
    xgA = p.get("predicted_away_goals")

    if xgH and xgA and float(xgH) > 0 and float(xgA) > 0:
        try:
            poi = poisson_market_probabilities(float(xgH), float(xgA))
            p.update(
                {
                    "poisson_home": round(poi["home_win"], 4),
                    "poisson_draw": round(poi["draw"], 4),
                    "poisson_away": round(poi["away_win"], 4),
                    "poisson_btts": round(poi["btts"], 4),
                    "poisson_over15": round(poi.get("over15", 0), 4),
                    "poisson_over25": round(poi.get("over25", 0), 4),
                    "poisson_under35": round(poi.get("under35", 0), 4),
                    "top_scores": poi.get("top_correct_scores", [])[:4],
                }
            )
            if not p.get("most_likely_score"):
                p["most_likely_score"] = poi["most_likely_score"]
            if pH > 0:
                p["blended_home"] = round(blend_probabilities({"b": pH, "p": poi["home_win"]}, {"b": 0.65, "p": 0.35}) or pH, 4)
                p["blended_draw"] = round(blend_probabilities({"b": pD, "p": poi["draw"]}, {"b": 0.65, "p": 0.35}) or pD, 4)
                p["blended_away"] = round(blend_probabilities({"b": pA, "p": poi["away_win"]}, {"b": 0.65, "p": 0.35}) or pA, 4)
            delta = round((poi["home_win"] - pH) * 100, 1) if pH > 0 else 0
            p["poisson_delta"] = delta
            p["poisson_direction"] = "value" if delta > 5 else ("risk" if delta < -5 else "flat")
        except Exception as exc:
            p["poisson_error"] = str(exc)

    best_p = max(p.get("blended_home") or pH, p.get("blended_draw") or pD, p.get("blended_away") or pA)
    edge_pp = (best_p - 0.5) * 100
    p["smartbet_score"] = round(
        min(100, min(100, max(0, (best_p - 0.5) / 0.3 * 100)) * 0.6 + min(100, max(0, edge_pp / 15 * 100)) * 0.4),
        1,
    )
    p["edge_pp"] = round(edge_pp, 2)
    gs = (p.get("confidence") or best_p or 0) * 100 * 0.6 + p["smartbet_score"] * 0.4
    p["quality_grade"] = quality_grade(gs)
    return p


def get_all_markets(pred: Dict[str, Any]) -> Dict[str, float]:
    pH = pred.get("blended_home") or pred.get("home_win_probability") or 0
    pD = pred.get("blended_draw") or pred.get("draw_probability") or 0
    pA = pred.get("blended_away") or pred.get("away_win_probability") or 0
    return {
        "homeWin": pH,
        "draw": pD,
        "awayWin": pA,
        "over15": pred.get("poisson_over15") or pred.get("over_15_probability") or 0,
        "over25": pred.get("poisson_over25") or pred.get("over_25_probability") or 0,
        "under25": pred.get("under_25_probability") or 0,
        "under35": pred.get("poisson_under35") or pred.get("under_35_probability") or 0,
        "btts": pred.get("poisson_btts") or pred.get("btts_probability") or 0,
    }


def market_price(
    odds_idx: Dict[str, Dict[str, Dict[str, Any]]],
    event_id: str,
    market_key: str,
    prob: float,
    allow_estimated: bool = False,
) -> Tuple[float, bool, str]:
    """Returnează cota reală BSD pentru o piață internă.

    În v8 multe semnale erau generate cu odds estimate. Pentru produs profesional
    preferăm semnale bazate pe piață reală; estimarea rămâne opțională, doar ca fallback.
    """
    cfg = {
        "homeWin": ("1x2", ["home_odds", "odds_1"], "HOME"),
        "draw": ("1x2", ["draw_odds", "odds_x"], "DRAW"),
        "awayWin": ("1x2", ["away_odds", "odds_2"], "AWAY"),
        "over15": ("over_under_15", ["over_odds", "odds_over"], "OVER"),
        "over25": ("over_under_25", ["over_odds", "odds_over"], "OVER"),
        "under25": ("over_under_25", ["under_odds", "odds_under"], "UNDER"),
        "under35": ("over_under_35", ["under_odds", "odds_under"], "UNDER"),
        "btts": ("btts", ["yes_odds", "odds_yes"], "YES"),
    }.get(market_key)

    if cfg:
        odds_market, fields, outcome = cfg
        row = (odds_idx.get(event_id) or {}).get(odds_market) or {}
        for field in fields:
            value = as_float(row.get(field))
            if value and value > 1:
                return value, True, odds_market
        for odd in row.get("best_odds") or []:
            if str(odd.get("outcome") or "").upper() == outcome:
                value = as_float(odd.get("decimal_odds"))
                if value and value > 1:
                    return value, True, odds_market

    if allow_estimated and prob > 0.05:
        return round(1 / (prob * 1.05), 2), False, "estimated"
    return 0, False, "missing"


def compute_signals_from_preds(preds: List[Dict[str, Any]], odds_idx: Dict[str, Dict[str, Dict[str, Any]]]) -> Tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    seen: Dict[str, float] = {}
    all_sigs: List[Dict[str, Any]] = []
    rejected = {"missing_real_odds": 0, "low_probability": 0, "odds_range": 0, "low_edge": 0, "non_positive_ev": 0}

    for pred in preds:
        ev = pred.get("event") or {}
        eid = str(ev.get("id", ""))
        if not eid:
            continue
        conf = (pred.get("confidence") or 0) * 100
        sb = pred.get("smartbet_score", 0)
        grade = pred.get("quality_grade", "—")
        mkts = get_all_markets(pred)

        for sk, strat in STRATEGIES.items():
            for mk in strat["markets"]:
                prob01 = mkts.get(mk, 0)
                if prob01 <= 0:
                    continue
                adj = prob01 * 100
                if adj < strat["min_adj"]:
                    rejected["low_probability"] += 1
                    continue

                # Pasul 2: semnalele publice se bazează pe cote reale BSD, nu pe cote estimate.
                odd, is_real, odds_market = market_price(odds_idx, eid, mk, prob01, allow_estimated=False)
                if not is_real:
                    rejected["missing_real_odds"] += 1
                    continue
                if odd < strat["odd_min"] or odd > strat["odd_max"]:
                    rejected["odds_range"] += 1
                    continue

                ev_val = prob01 * odd - 1
                if ev_val <= 0:
                    rejected["non_positive_ev"] += 1
                    continue
                edge_pp = (prob01 - 1 / odd) * 100 if odd > 1 else 0
                if edge_pp < strat["min_edge"]:
                    rejected["low_edge"] += 1
                    continue

                kelly = min(0.06, max(0, (prob01 * odd - 1) / (odd - 1))) * 100 if odd > 1 else 0
                sig_key = f"{eid}_{mk}"
                if sig_key in seen and sb <= seen[sig_key]:
                    continue
                seen[sig_key] = sb
                all_sigs.append(
                    {
                        "event_id": int(eid) if eid.isdigit() else 0,
                        "home_team": ev.get("home_team", "—"),
                        "away_team": ev.get("away_team", "—"),
                        "home_team_id": ev.get("home_team_id"),
                        "away_team_id": ev.get("away_team_id"),
                        "league": pred.get("_league_name", "—"),
                        "league_id": pred.get("_league_id"),
                        "event_date": ev.get("event_date"),
                        "market": mk,
                        "market_label": MARKET_LABELS.get(mk, mk),
                        "adj_prob": round(adj, 1),
                        "confidence": round(conf, 1),
                        "smartbet_score": sb,
                        "quality_grade": grade,
                        "odds": round(odd, 2),
                        "odds_real": True,
                        "odds_market": odds_market,
                        "ev": round(ev_val, 4),
                        "ev_pct": f"{ev_val * 100:.1f}%",
                        "edge_pp": round(edge_pp, 2),
                        "kelly_pct": f"{kelly:.1f}%",
                        "strategy": sk,
                        "strategy_label": strat["label"],
                        "strategy_icon": strat["icon"],
                        "strategy_color": strat["color"],
                        "most_likely_score": pred.get("most_likely_score"),
                        "xg_home": pred.get("predicted_home_goals"),
                        "xg_away": pred.get("predicted_away_goals"),
                    }
                )

    all_sigs.sort(key=lambda x: (x["smartbet_score"], x["edge_pp"], x["adj_prob"]), reverse=True)
    by_strat: Dict[str, List[Dict[str, Any]]] = {}
    for signal in all_sigs:
        by_strat.setdefault(signal["strategy"], []).append(signal)
    save_debug("signals_debug.json", {"updated_at": now_iso(), "count": len(all_sigs), "rejected": rejected, "real_odds_only": True})
    return all_sigs, by_strat

# ── Normalizare odds BSD v2 ─────────────────────────────────────────────────
def _best_odds_to_fields(item: Dict[str, Any]) -> Dict[str, Any]:
    """Transformă /api/v2/odds/best/ în schema veche folosită de UI/signals."""
    market = item.get("market") or "1x2"
    normalized = dict(item)
    normalized["_market"] = market
    normalized["event"] = {
        "id": item.get("event_id"),
        "event_date": item.get("event_date"),
        "league_id": item.get("league_id"),
        "league_name": item.get("league_name"),
        "home_team": item.get("home_team"),
        "away_team": item.get("away_team"),
        "home_team_id": item.get("home_team_id"),
        "away_team_id": item.get("away_team_id"),
    }

    for odd in item.get("best_odds") or []:
        outcome = str(odd.get("outcome") or "").upper()
        price = as_float(odd.get("decimal_odds"))
        if price is None:
            continue

        if market == "1x2":
            if outcome == "HOME":
                normalized["home_odds"] = price
                normalized["odds_1"] = price
                normalized["home_bookmaker"] = odd.get("bookmaker_name") or odd.get("bookmaker_slug")
            elif outcome == "DRAW":
                normalized["draw_odds"] = price
                normalized["odds_x"] = price
                normalized["draw_bookmaker"] = odd.get("bookmaker_name") or odd.get("bookmaker_slug")
            elif outcome == "AWAY":
                normalized["away_odds"] = price
                normalized["odds_2"] = price
                normalized["away_bookmaker"] = odd.get("bookmaker_name") or odd.get("bookmaker_slug")
        elif market.startswith("over_under"):
            if outcome == "OVER":
                normalized["over_odds"] = price
                normalized["odds_over"] = price
            elif outcome == "UNDER":
                normalized["under_odds"] = price
                normalized["odds_under"] = price
        elif market == "btts":
            if outcome == "YES":
                normalized["yes_odds"] = price
                normalized["odds_yes"] = price
            elif outcome == "NO":
                normalized["no_odds"] = price
                normalized["odds_no"] = price

    return normalized


# ─────────────────────────────────────────────────────────────────────────────
# [1/6] PREDICTIONS
# ─────────────────────────────────────────────────────────────────────────────
def fetch_predictions() -> None:
    print("\n[1/6] Predictions (global + paginated)...")
    all_preds: List[Dict[str, Any]] = []
    seen: set[Any] = set()

    for base in [BASE_V2, BASE_V1]:
        url = f"{base}/predictions/"
        print(f"  → {url}...")
        batch = get_all_pages(url, {"limit": 200}, max_pages=30, label="predictions")
        for p in batch:
            pid = p.get("id") or (p.get("event") or {}).get("id")
            if pid and pid in seen:
                continue
            if pid:
                seen.add(pid)
            all_preds.append(enrich_analytics(normalize_pred(p)))
        if all_preds:
            print(f"  global OK: {len(all_preds)} predicții")
            break

    if not all_preds:
        print("  fallback: per ligă...")
        for lid, lname in list(LEAGUES.items())[:20]:
            for url, param_name in [(f"{BASE_V2}/predictions/", "league_id"), (f"{BASE_V1}/predictions/", "league")]:
                batch = get_all_pages(url, {param_name: lid, "limit": 100}, max_pages=5, label=f"predictions_league_{lid}")
                cnt = 0
                for p in batch:
                    pid = p.get("id") or (p.get("event") or {}).get("id")
                    if pid and pid in seen:
                        continue
                    if pid:
                        seen.add(pid)
                    all_preds.append(enrich_analytics(normalize_pred(p, lid, lname)))
                    cnt += 1
                if cnt:
                    print(f"  {lname}: {cnt}")
                    break

    n_p = sum(1 for p in all_preds if p.get("home_win_probability") is not None)
    n_g = sum(1 for p in all_preds if p.get("quality_grade") not in (None, "—"))
    print(f"  TOTAL: {len(all_preds)} | prob:{n_p} | grade:{n_g}")
    save("predictions.json", {"updated_at": now_iso(), "count": len(all_preds), "results": all_preds}, protect_empty=True, job_name="predictions")


# ─────────────────────────────────────────────────────────────────────────────
# [2/6] BSD VALUE BETS
# ─────────────────────────────────────────────────────────────────────────────
def normalize_value_bet(item: Dict[str, Any], source: str) -> Dict[str, Any]:
    ev = item.get("event") or {}
    lid = ev.get("league_id") or item.get("league_id")
    market = item.get("market", "")
    edge = as_float(item.get("edge"))
    edge_pct_value = edge * 100 if edge is not None and abs(edge) <= 1 else edge

    return {
        "source": source,
        "confidence": as_float(item.get("confidence") or item.get("conf"), 0) or 0,
        "tier": item.get("tier", "neutral"),
        "market": market,
        "market_label": MARKET_LABELS.get(market, market),
        "market_odds": as_float(item.get("market_odds") or item.get("odds") or item.get("decimal_odds")),
        "model_probability": as_pct(item.get("model_probability") or item.get("model_prob")),
        "market_probability": as_pct(item.get("market_probability") or item.get("market_prob") or item.get("implied_probability")),
        "edge": edge,
        "edge_pct": f"+{edge_pct_value:.1f}%" if edge_pct_value is not None and edge_pct_value > 0 else (f"{edge_pct_value:.1f}%" if edge_pct_value is not None else "—"),
        "fair_odd": as_float(item.get("fair_odd")),
        "event_id": ev.get("id") or item.get("event_id"),
        "home_team": ev.get("home_team") or item.get("home_team") or "—",
        "away_team": ev.get("away_team") or item.get("away_team") or "—",
        "home_team_id": ev.get("home_team_id") or item.get("home_team_id"),
        "away_team_id": ev.get("away_team_id") or item.get("away_team_id"),
        "league": ev.get("league_name") or item.get("league_name") or LEAGUES.get(int(lid) if lid else 0, ""),
        "league_id": lid,
        "event_date": ev.get("event_date") or item.get("event_date"),
        "raw": item,
    }


def fetch_value_bets() -> None:
    print("\n[2/6] BSD Value Bets...")
    bsd_vb: List[Dict[str, Any]] = []
    endpoint_reports: List[Dict[str, Any]] = []

    candidate_urls = [
        f"{BASE_V2}/value-bets/",
        f"{BASE_V1}/value-bets/",
        f"{BASE_V2}/odds/value/",
        f"{BASE_V2}/recommendations/",
    ]

    for url in candidate_urls:
        items = get_all_pages(url, {"limit": 200}, max_pages=10, label="value_bets")
        endpoint_reports.append({"url": url, "count": len(items)})
        if not items:
            continue
        bsd_vb = [normalize_value_bet(item, "bsd") for item in items]
        bsd_vb = [x for x in bsd_vb if x.get("event_id") or x.get("home_team") != "—"]
        if bsd_vb:
            print(f"  BSD Value Bets OK: {len(bsd_vb)} picks via {url}")
            bsd_vb.sort(key=lambda x: -(x.get("confidence") or 0))
            save_debug("value_bets_debug.json", {"updated_at": now_iso(), "endpoints": endpoint_reports, "selected_url": url, "count": len(bsd_vb)})
            save("value_bets.json", {"source": "bsd", "updated_at": now_iso(), "count": len(bsd_vb), "results": bsd_vb}, protect_empty=True, job_name="value_bets")
            return

    save_debug("value_bets_debug.json", {"updated_at": now_iso(), "endpoints": endpoint_reports, "selected_url": None, "count": 0, "fallback": "local"})
    print("  BSD Value Bets indisponibil → calcul local din predictions + best_odds...")
    _compute_value_bets_local()


def _compute_value_bets_local() -> None:
    pred_path = DATA_DIR / "predictions.json"
    odds_path = DATA_DIR / "best_odds.json"
    if not pred_path.exists():
        warn("Nu există predictions.json pentru fallback value bets")
        save("value_bets.json", {"updated_at": now_iso(), "count": 0, "results": [], "source": "local_disciplined", "reason": "missing_predictions"}, protect_empty=True, job_name="value_bets")
        return

    preds = json.loads(pred_path.read_text(encoding="utf-8")).get("results", [])
    odds_idx: Dict[str, Dict[str, Dict[str, Any]]] = {}
    if odds_path.exists():
        for o in json.loads(odds_path.read_text(encoding="utf-8")).get("results", []):
            eid = ((o.get("event") or {}).get("id") if isinstance(o.get("event"), dict) else None) or o.get("event_id")
            if eid:
                odds_idx.setdefault(str(eid), {})[o.get("_market", "1x2")] = o

    # Filtrele sunt intenționat stricte. Un value bet profesional nu este același lucru cu
    # „orice cotă mare unde modelul pare peste piață”. Evităm long-shot-uri extreme și odds estimate.
    rules = {
        "min_confidence": 55.0,
        "min_edge_pp": 3.0,
        "min_ev": 0.03,
        "max_ev": 0.35,
        "max_items": 60,
    }
    rejected = {
        "missing_real_odds": 0,
        "low_confidence": 0,
        "probability_floor": 0,
        "odds_range": 0,
        "low_edge": 0,
        "ev_range": 0,
    }

    vbs: List[Dict[str, Any]] = []
    for pred in preds:
        ev = pred.get("event") or {}
        eid = str(ev.get("id", ""))
        if not eid:
            continue

        confidence = max(as_float(pred.get("smartbet_score"), 0) or 0, (as_float(pred.get("confidence"), 0) or 0) * 100)
        if confidence < rules["min_confidence"]:
            rejected["low_confidence"] += 1
            continue

        markets = get_all_markets(pred)
        candidates = [
            ("1", "homeWin", markets.get("homeWin", 0), "Victorie acasă", 0.38, 1.25, 4.50),
            ("X", "draw", markets.get("draw", 0), "Egal", 0.22, 2.40, 4.75),
            ("2", "awayWin", markets.get("awayWin", 0), "Victorie deplasare", 0.32, 1.25, 4.75),
            ("over15", "over15", markets.get("over15", 0), "Over 1.5G", 0.68, 1.15, 1.95),
            ("over25", "over25", markets.get("over25", 0), "Over 2.5G", 0.55, 1.35, 2.35),
            ("under25", "under25", markets.get("under25", 0), "Under 2.5G", 0.55, 1.35, 2.35),
            ("under35", "under35", markets.get("under35", 0), "Under 3.5G", 0.68, 1.15, 1.95),
            ("btts", "btts", markets.get("btts", 0), "BTTS Da", 0.55, 1.35, 2.35),
        ]

        for market_id, internal_key, prob, mk_label, min_prob, odd_min, odd_max in candidates:
            if not prob or prob < min_prob:
                rejected["probability_floor"] += 1
                continue

            odd, is_real, odds_market = market_price(odds_idx, eid, internal_key, prob, allow_estimated=False)
            if not is_real:
                rejected["missing_real_odds"] += 1
                continue
            if odd < odd_min or odd > odd_max:
                rejected["odds_range"] += 1
                continue

            market_prob = 1 / odd
            edge_pp = (prob - market_prob) * 100
            ev_val = prob * odd - 1
            if edge_pp < rules["min_edge_pp"]:
                rejected["low_edge"] += 1
                continue
            if ev_val < rules["min_ev"] or ev_val > rules["max_ev"]:
                rejected["ev_range"] += 1
                continue

            kf = min(0.05, max(0, (prob * odd - 1) / (odd - 1))) if odd > 1 else 0
            tier = "strong" if confidence >= 75 and edge_pp >= 5 and ev_val <= 0.25 else "neutral"
            vbs.append(
                {
                    "source": "local_disciplined",
                    "confidence": round(confidence, 1),
                    "tier": tier,
                    "market": market_id,
                    "market_label": mk_label,
                    "market_odds": round(odd, 2),
                    "model_probability": round(prob * 100, 1),
                    "market_probability": round(market_prob * 100, 1),
                    "edge": round(ev_val, 4),
                    "edge_pct": f"+{ev_val * 100:.1f}%",
                    "fair_odd": round(1 / (prob * 1.02), 2) if prob > 0.05 else None,
                    "event_id": int(eid) if eid.isdigit() else eid,
                    "home_team": ev.get("home_team", "—"),
                    "away_team": ev.get("away_team", "—"),
                    "home_team_id": ev.get("home_team_id"),
                    "away_team_id": ev.get("away_team_id"),
                    "league": pred.get("_league_name", "—"),
                    "league_id": pred.get("_league_id"),
                    "event_date": ev.get("event_date"),
                    "kelly_pct": f"{kf * 100:.1f}%",
                    "quality_grade": pred.get("quality_grade", "—"),
                    "edge_nv_pp": round(edge_pp, 2),
                    "odds_source": "bookmaker",
                    "odds_market": odds_market,
                    "risk_note": "cote reale + edge controlat" if tier == "strong" else "semnal moderat, verifică contextul",
                }
            )

    # Evităm să umplem UI-ul cu zeci de variații pe același meci. Păstrăm cel mai bun semnal/eveniment.
    by_event: Dict[Any, Dict[str, Any]] = {}
    for item in sorted(vbs, key=lambda x: (x["tier"] == "strong", x["confidence"], x["edge_nv_pp"]), reverse=True):
        eid = item.get("event_id")
        if eid not in by_event:
            by_event[eid] = item
    final_vbs = list(by_event.values())[: rules["max_items"]]
    final_vbs.sort(key=lambda x: (x["tier"] == "strong", x["confidence"], x["edge_nv_pp"]), reverse=True)

    save_debug(
        "local_value_bets_debug.json",
        {
            "updated_at": now_iso(),
            "source": "local_disciplined",
            "raw_candidates": len(vbs),
            "deduped_count": len(final_vbs),
            "rules": rules,
            "rejected": rejected,
        },
    )
    save("value_bets.json", {"source": "local_disciplined", "updated_at": now_iso(), "count": len(final_vbs), "results": final_vbs}, protect_empty=True, job_name="value_bets")

# ─────────────────────────────────────────────────────────────────────────────
# [3/6] MATCHES TODAY
# ─────────────────────────────────────────────────────────────────────────────
def fetch_matches_today() -> None:
    print("\n[3/6] Meciuri azi...")
    today = today_iso()
    all_m = get_all_pages(f"{BASE_V2}/events/", {"date_from": today, "date_to": today, "limit": 200}, max_pages=10, label="matches_today")

    if not all_m:
        warn("Lista globală de evenimente pentru azi e goală; încerc fallback per ligă")
        for lid, lname in list(LEAGUES.items())[:20]:
            ms = get_all_pages(f"{BASE_V2}/events/", {"date_from": today, "date_to": today, "league_id": lid, "limit": 100}, max_pages=5, label=f"matches_league_{lid}")
            for m in ms:
                m["_league_name"] = lname
                m["_league_id"] = lid
            all_m.extend(ms)

    for m in all_m:
        htid = m.get("home_team_id")
        atid = m.get("away_team_id")
        lid = m.get("league_id")
        m["_team_logo_home"] = logo_url("team", htid)
        m["_team_logo_away"] = logo_url("team", atid)
        m["_league_logo"] = logo_url("league", lid)
        m["_league_name"] = m.get("league_name") or m.get("_league_name") or LEAGUES.get(int(lid) if lid else 0, "")

    all_m.sort(key=lambda m: m.get("event_date") or "")
    save("matches_today.json", {"date": today, "updated_at": now_iso(), "count": len(all_m), "results": all_m}, protect_empty=True, job_name="matches_today")


# ─────────────────────────────────────────────────────────────────────────────
# [4/6] BEST ODDS — BSD v2 corect: /odds/best/
# ─────────────────────────────────────────────────────────────────────────────
def fetch_best_odds() -> None:
    print("\n[4/6] Best Odds BSD v2...")
    all_odds: List[Dict[str, Any]] = []
    start, end = date_window(days=7)
    market_reports: List[Dict[str, Any]] = []

    for market in ["1x2", "over_under_15", "over_under_25", "over_under_35", "btts"]:
        params = {"date_from": start, "date_to": end, "market": market, "limit": 200}
        items = get_all_pages(f"{BASE_V2}/odds/best/", params, max_pages=10, label=f"best_odds_{market}")
        market_reports.append({"market": market, "count": len(items)})
        for item in items:
            all_odds.append(_best_odds_to_fields(item))

    save_debug("odds_debug.json", {"updated_at": now_iso(), "date_from": start, "date_to": end, "markets": market_reports, "total": len(all_odds)})
    save("best_odds.json", {"updated_at": now_iso(), "count": len(all_odds), "results": all_odds, "source": "bsd_v2_odds_best"}, protect_empty=True, job_name="best_odds")


# ─────────────────────────────────────────────────────────────────────────────
# [5/6] STANDINGS
# ─────────────────────────────────────────────────────────────────────────────
def fetch_standings() -> None:
    print("\n[5/6] Clasamente...")
    data: Dict[str, Any] = {}
    priority = [23, 1, 7, 3, 4, 5, 6, 8, 2, 10, 27, 12]

    for lid in priority:
        lname = LEAGUES.get(lid, f"Liga {lid}")
        for url, params in [
            (f"{BASE_V2}/leagues/{lid}/standings/", None),
            (f"{BASE_V2}/standings/{lid}/", None),
            (f"{BASE_V2}/standings/", {"league_id": lid}),
            (f"{BASE_V1}/standings/", {"league_id": lid}),
        ]:
            d = get(url, params, label=f"standings_{lid}")
            if not d:
                continue
            rows = d.get("standings") or d.get("results") or []
            if rows:
                data[str(lid)] = {"league_name": lname, "league_id": lid, "standings": rows, "league_logo": logo_url("league", lid)}
                print(f"  {lname}: {len(rows)} echipe")
                break

    save("standings.json", {"updated_at": now_iso(), "leagues": data, "count": len(data)}, protect_empty=True, job_name="standings")


# ─────────────────────────────────────────────────────────────────────────────
# [6/6] SIGNALS
# ─────────────────────────────────────────────────────────────────────────────
def compute_signals() -> None:
    print("\n[6/6] Signals...")
    pred_path = DATA_DIR / "predictions.json"
    odds_path = DATA_DIR / "best_odds.json"

    if not pred_path.exists():
        warn("Nu există predictions.json pentru compute_signals")
        save("signals.json", {"updated_at": now_iso(), "count": 0, "signals": [], "by_strategy": {}, "strategy_stats": {}}, protect_empty=True, job_name="signals")
        return

    preds = json.loads(pred_path.read_text(encoding="utf-8")).get("results", [])
    odds_idx: Dict[str, Dict[str, Dict[str, Any]]] = {}
    if odds_path.exists():
        for o in json.loads(odds_path.read_text(encoding="utf-8")).get("results", []):
            eid = ((o.get("event") or {}).get("id") if isinstance(o.get("event"), dict) else None) or o.get("event_id")
            if eid:
                odds_idx.setdefault(str(eid), {})[o.get("_market", "1x2")] = o

    signals, by_strat = compute_signals_from_preds(preds, odds_idx)
    strat_stats = {
        sk: {
            "label": STRATEGIES[sk]["label"],
            "icon": STRATEGIES[sk]["icon"],
            "color": STRATEGIES[sk]["color"],
            "count": len(sigs),
            "avg_score": round(sum(s["smartbet_score"] for s in sigs) / len(sigs), 1) if sigs else 0,
        }
        for sk, sigs in by_strat.items()
    }
    print(f"  TOTAL: {len(signals)} | " + ", ".join(f"{sk}:{len(v)}" for sk, v in by_strat.items()))
    save("signals.json", {"updated_at": now_iso(), "count": len(signals), "signals": signals, "by_strategy": by_strat, "strategy_stats": strat_stats}, protect_empty=True, job_name="signals")


# ─────────────────────────────────────────────────────────────────────────────
# [7/7] MATCH CONTEXT — metadata, lineups, stats, incidents, shotmap
# ─────────────────────────────────────────────────────────────────────────────
def read_json_file(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        warn("Nu pot citi JSON pentru context", path=str(path), error=str(exc))
    return default


def compact_count(payload: Any) -> int:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("results", "events", "incidents", "lineups", "players", "shots", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return len(value)
            if isinstance(value, dict):
                return len(value)
        # un obiect non-gol e o resursă validă, chiar dacă nu are listă internă
        return 1 if payload else 0
    return 0


def first_payload(event_id: Any, resource: str, candidates: List[Tuple[str, Optional[Dict[str, Any]]]]) -> Tuple[Optional[Any], Dict[str, Any]]:
    """Încearcă mai multe forme de endpoint fără să oprească pipeline-ul la 404."""
    report = {"resource": resource, "selected_url": None, "count": 0, "attempts": []}
    for url, params in candidates:
        payload = get(url, params, label=f"context_{resource}_{event_id}")
        cnt = compact_count(payload)
        report["attempts"].append({"url": url, "params": params or {}, "count": cnt})
        if payload is not None and cnt > 0:
            report["selected_url"] = url
            report["count"] = cnt
            return payload, report
    return None, report


def seed_context_events(limit: int) -> List[Dict[str, Any]]:
    """Alege evenimente cu prioritate mare: value bets, signals, apoi meciuri de azi/predicții."""
    seeds: Dict[str, Dict[str, Any]] = {}

    def add(eid: Any, source: str, payload: Dict[str, Any], score: float = 0) -> None:
        if not eid:
            return
        key = str(eid)
        existing = seeds.get(key)
        base = existing or {"event_id": eid, "sources": [], "priority_score": 0}
        if source not in base["sources"]:
            base["sources"].append(source)
        base["priority_score"] = max(float(base.get("priority_score") or 0), float(score or 0))
        for field in ("home_team", "away_team", "home_team_id", "away_team_id", "league", "league_id", "event_date"):
            if not base.get(field) and payload.get(field) is not None:
                base[field] = payload.get(field)
        seeds[key] = base

    value_payload = read_json_file(DATA_DIR / "value_bets.json", {})
    for idx, vb in enumerate(value_payload.get("results", [])[:40]):
        add(vb.get("event_id"), "value_bets", vb, (vb.get("confidence") or 0) + max(0, 40 - idx))

    signals_payload = read_json_file(DATA_DIR / "signals.json", {})
    for idx, sig in enumerate(signals_payload.get("signals", [])[:60]):
        add(sig.get("event_id"), "signals", sig, (sig.get("smartbet_score") or 0) + max(0, 30 - idx))

    matches_payload = read_json_file(DATA_DIR / "matches_today.json", {})
    for idx, m in enumerate(matches_payload.get("results", [])[:40]):
        add(m.get("id") or m.get("event_id"), "matches_today", {
            "home_team": m.get("home_team"),
            "away_team": m.get("away_team"),
            "home_team_id": m.get("home_team_id"),
            "away_team_id": m.get("away_team_id"),
            "league": m.get("league_name") or m.get("_league_name"),
            "league_id": m.get("league_id") or m.get("_league_id"),
            "event_date": m.get("event_date"),
        }, 10 - idx / 10)

    preds_payload = read_json_file(DATA_DIR / "predictions.json", {})
    preds = sorted(preds_payload.get("results", []), key=lambda p: p.get("smartbet_score") or 0, reverse=True)
    for idx, pred in enumerate(preds[:40]):
        ev = pred.get("event") or {}
        add(ev.get("id"), "predictions", {
            "home_team": ev.get("home_team"),
            "away_team": ev.get("away_team"),
            "home_team_id": ev.get("home_team_id"),
            "away_team_id": ev.get("away_team_id"),
            "league": pred.get("_league_name") or ev.get("league_name"),
            "league_id": pred.get("_league_id") or ev.get("league_id"),
            "event_date": ev.get("event_date"),
        }, pred.get("smartbet_score") or 0)

    ordered = sorted(seeds.values(), key=lambda x: x.get("priority_score") or 0, reverse=True)
    return ordered[:limit]


def extract_lineup_status(lineups: Any) -> str:
    if isinstance(lineups, dict):
        for key in ("status", "lineup_status", "availability", "type"):
            if lineups.get(key):
                return str(lineups.get(key))
        # Unele răspunsuri au status separat pe home/away.
        for side in ("home", "away"):
            obj = lineups.get(side)
            if isinstance(obj, dict):
                for key in ("status", "lineup_status"):
                    if obj.get(key):
                        return str(obj.get(key))
    return "unknown"


def fetch_match_context() -> None:
    print("\n[7/7] Match Context BSD v2...")
    limit = int(os.environ.get("BETPREDICT_CONTEXT_LIMIT", "24") or 24)
    seeds = seed_context_events(limit)
    contexts: List[Dict[str, Any]] = []
    reports: List[Dict[str, Any]] = []

    for seed in seeds:
        event_id = seed.get("event_id")
        if not event_id:
            continue
        print(f"  → context event {event_id}: {seed.get('home_team','—')} vs {seed.get('away_team','—')}")

        detail, detail_report = first_payload(event_id, "detail", [
            (f"{BASE_V2}/events/{event_id}/", None),
        ])
        stats, stats_report = first_payload(event_id, "stats", [
            (f"{BASE_V2}/events/{event_id}/stats/", None),
            (f"{BASE_V2}/stats/", {"event": event_id}),
            (f"{BASE_V2}/stats/", {"event_id": event_id}),
        ])
        incidents, incidents_report = first_payload(event_id, "incidents", [
            (f"{BASE_V2}/events/{event_id}/incidents/", None),
            (f"{BASE_V2}/incidents/", {"event": event_id}),
            (f"{BASE_V2}/incidents/", {"event_id": event_id}),
        ])
        lineups, lineups_report = first_payload(event_id, "lineups", [
            (f"{BASE_V2}/events/{event_id}/lineups/", None),
            (f"{BASE_V2}/lineups/", {"event": event_id}),
            (f"{BASE_V2}/lineups/", {"event_id": event_id}),
        ])
        player_stats, player_report = first_payload(event_id, "player_stats", [
            (f"{BASE_V2}/player-stats/", {"event": event_id}),
            (f"{BASE_V2}/player-stats/", {"event_id": event_id}),
            (f"{BASE_V2}/events/{event_id}/player-stats/", None),
        ])
        shotmap, shotmap_report = first_payload(event_id, "shotmap", [
            (f"{BASE_V2}/events/{event_id}/shotmap/", None),
            (f"{BASE_V2}/shotmap/", {"event": event_id}),
            (f"{BASE_V2}/shotmap/", {"event_id": event_id}),
        ])

        resource_reports = [detail_report, stats_report, incidents_report, lineups_report, player_report, shotmap_report]
        reports.append({"event_id": event_id, "resources": resource_reports})

        context = {
            "event_id": event_id,
            "sources": seed.get("sources", []),
            "priority_score": round(float(seed.get("priority_score") or 0), 2),
            "home_team": seed.get("home_team"),
            "away_team": seed.get("away_team"),
            "home_team_id": seed.get("home_team_id"),
            "away_team_id": seed.get("away_team_id"),
            "league": seed.get("league"),
            "league_id": seed.get("league_id"),
            "event_date": seed.get("event_date"),
            "detail": detail,
            "stats": stats,
            "incidents": extract_results(incidents) if incidents is not None else [],
            "lineups": lineups,
            "lineup_status": extract_lineup_status(lineups),
            "player_stats": extract_results(player_stats) if player_stats is not None else [],
            "shotmap": shotmap,
            "counts": {
                "detail": compact_count(detail),
                "stats": compact_count(stats),
                "incidents": compact_count(incidents),
                "lineups": compact_count(lineups),
                "player_stats": compact_count(player_stats),
                "shotmap": compact_count(shotmap),
            },
        }
        context["coverage_score"] = sum(1 for v in context["counts"].values() if v > 0)
        contexts.append(context)

    summary = {
        "events_requested": len(seeds),
        "events_saved": len(contexts),
        "with_detail": sum(1 for c in contexts if c["counts"].get("detail", 0) > 0),
        "with_stats": sum(1 for c in contexts if c["counts"].get("stats", 0) > 0),
        "with_incidents": sum(1 for c in contexts if c["counts"].get("incidents", 0) > 0),
        "with_lineups": sum(1 for c in contexts if c["counts"].get("lineups", 0) > 0),
        "with_player_stats": sum(1 for c in contexts if c["counts"].get("player_stats", 0) > 0),
        "with_shotmap": sum(1 for c in contexts if c["counts"].get("shotmap", 0) > 0),
    }
    save_debug("match_context_debug.json", {"updated_at": now_iso(), "limit": limit, "summary": summary, "reports": reports})
    save("match_context.json", {"updated_at": now_iso(), "count": len(contexts), "results": contexts, "_summary": summary, "source": "bsd_v2_context"}, protect_empty=True, job_name="match_context")



# ─────────────────────────────────────────────────────────────────────────────
# [8/10] RECENT RESULTS — scoruri finalizate pentru evaluare
# ─────────────────────────────────────────────────────────────────────────────
def _date_only_utc(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def fetch_recent_results() -> None:
    """Cache pentru rezultate recente. Este baza reală pentru evaluarea jurnalului."""
    print("\n[8/10] Recent Results / settled cache...")
    days_back = int(os.environ.get("BETPREDICT_RESULTS_DAYS", "14") or 14)
    end = datetime.now(timezone.utc) + timedelta(hours=4)
    start = end - timedelta(days=days_back)
    date_from = _date_only_utc(start)
    date_to = _date_only_utc(end)

    all_events: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def add_events(items: List[Dict[str, Any]], source: str) -> None:
        for ev in items:
            eid = ev.get("id") or ev.get("event_id")
            if not eid:
                continue
            key = str(eid)
            if key in seen:
                continue
            seen.add(key)
            ev["_results_source"] = source
            all_events.append(ev)

    global_items = get_all_pages(
        f"{BASE_V2}/events/",
        {"date_from": date_from, "date_to": date_to, "limit": 200},
        max_pages=20,
        label="recent_results_global",
    )
    add_events(global_items, "global")

    if len(all_events) < 80:
        priority = [1, 3, 4, 5, 6, 7, 8, 12, 16, 17, 22, 23, 28, 29, 30, 34, 35, 36, 38, 52]
        for lid in priority:
            items = get_all_pages(
                f"{BASE_V2}/events/",
                {"date_from": date_from, "date_to": date_to, "league_id": lid, "limit": 200},
                max_pages=10,
                label=f"recent_results_league_{lid}",
            )
            for ev in items:
                ev.setdefault("league_id", lid)
                ev.setdefault("league_name", LEAGUES.get(lid))
            add_events(items, f"league_{lid}")

    settled = []
    partial = []
    for ev in all_events:
        hs, aw = _event_scores(ev)
        status = str(ev.get("status") or ev.get("status_short") or ev.get("state") or "").lower()
        if _is_settled(ev):
            settled.append(ev)
        elif hs is not None and aw is not None and status:
            partial.append(ev)

    payload = {
        "updated_at": now_iso(),
        "source": "bsd_v2_events_history",
        "date_from": date_from,
        "date_to": date_to,
        "days_back": days_back,
        "count": len(settled),
        "total_events_scanned": len(all_events),
        "partial_score_events": len(partial),
        "results": settled,
    }
    save_debug("recent_results_debug.json", {
        "updated_at": now_iso(),
        "date_from": date_from,
        "date_to": date_to,
        "events_scanned": len(all_events),
        "settled": len(settled),
        "partial_score_events": len(partial),
    })
    save("recent_results.json", payload, protect_empty=True, job_name="recent_results")


# ─────────────────────────────────────────────────────────────────────────────
# [9/10] SELECTION JOURNAL — arhivă persistentă de semnale publicate
# ─────────────────────────────────────────────────────────────────────────────
def _selection_key(source: str, event_id: Any, strategy: str, market: str) -> str:
    return f"{source}|{event_id}|{strategy}|{market}"


def _event_identity_from_selection(sel: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "event_id": sel.get("event_id"),
        "home_team": sel.get("home_team"),
        "away_team": sel.get("away_team"),
        "home_team_id": sel.get("home_team_id"),
        "away_team_id": sel.get("away_team_id"),
        "league": sel.get("league"),
        "league_id": sel.get("league_id"),
        "event_date": sel.get("event_date"),
    }


def _results_index() -> Dict[str, Dict[str, Any]]:
    idx: Dict[str, Dict[str, Any]] = {}
    for name in ("recent_results.json", "matches_today.json"):
        data = _read_json_file(name, {"results": []})
        for ev in data.get("results", []) if isinstance(data, dict) else []:
            eid = ev.get("id") or ev.get("event_id")
            if eid:
                idx[str(eid)] = ev
    context_data = _read_json_file("match_context.json", {"results": []})
    for ctx in context_data.get("results", []) if isinstance(context_data, dict) else []:
        eid = ctx.get("event_id")
        detail = ctx.get("detail") or {}
        if eid and isinstance(detail, dict):
            merged = dict(idx.get(str(eid), {}))
            merged.update(detail)
            idx[str(eid)] = merged
    return idx


def _normalize_journal_item(source: str, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    event_id = item.get("event_id")
    market = item.get("market")
    if not event_id or not market:
        return None
    if source == "value_bets":
        strategy = "value_bets"
        odds = as_float(item.get("market_odds") or item.get("best_odds"))
        probability = as_float(item.get("model_probability"))
        if probability and probability > 1:
            probability /= 100
        score = as_float(item.get("confidence"))
    else:
        strategy = item.get("strategy") or "signal"
        odds = as_float(item.get("odds"))
        probability = as_float(item.get("adj_prob"))
        if probability and probability > 1:
            probability /= 100
        score = as_float(item.get("smartbet_score"))

    if not odds or odds <= 1:
        return None
    key = _selection_key(source, event_id, strategy, market)
    base = _event_identity_from_selection(item)
    base.update({
        "key": key,
        "source": source,
        "strategy": strategy,
        "strategy_label": item.get("strategy_label") or ("Value Bets" if source == "value_bets" else strategy),
        "market": market,
        "market_label": item.get("market_label") or MARKET_LABELS.get(str(market), str(market)),
        "odds": round(float(odds), 2),
        "model_probability": round(float(probability), 4) if probability else None,
        "score": score,
        "first_seen_at": now_iso(),
        "last_seen_at": now_iso(),
        "status": "pending",
        "result": None,
        "profit_units": None,
        "market_canonical": _canonical_market(market),
        "actual_score": None,
        "settlement_reason": None,
    })
    return base


def update_selection_journal() -> None:
    print("\n[9/10] Selection Journal...")
    current = _read_json_file("selection_journal.json", {"results": []})
    existing: Dict[str, Dict[str, Any]] = {}
    for item in current.get("results", []) if isinstance(current, dict) else []:
        if item.get("key"):
            existing[item["key"]] = item

    signals_payload = _read_json_file("signals.json", {"signals": []})
    value_payload = _read_json_file("value_bets.json", {"results": []})
    signals = signals_payload.get("signals", []) if isinstance(signals_payload, dict) else []
    vbs = value_payload.get("results", []) if isinstance(value_payload, dict) else []
    added = 0
    refreshed = 0

    for source, items in (("signals", signals), ("value_bets", vbs)):
        for raw in items[:120]:
            normalized = _normalize_journal_item(source, raw)
            if not normalized:
                continue
            key = normalized["key"]
            if key in existing:
                old = existing[key]
                old["last_seen_at"] = now_iso()
                for field in ("score", "model_probability", "odds", "market_label", "strategy_label"):
                    if normalized.get(field) is not None:
                        old[field] = normalized[field]
                refreshed += 1
            else:
                existing[key] = normalized
                added += 1

    results_idx = _results_index()
    updated_results = 0
    for item in existing.values():
        if item.get("status") == "settled":
            continue
        ev = results_idx.get(str(item.get("event_id")))
        if not ev or not _is_settled(ev):
            continue
        hs, aw = _event_scores(ev)
        if hs is None or aw is None:
            continue
        won = _market_won(item.get("market"), hs, aw)
        if won is None:
            item["settlement_reason"] = _settlement_reason(item.get("market"), hs, aw, None)
            item["market_canonical"] = _canonical_market(item.get("market"))
            continue
        odds = as_float(item.get("odds")) or 0
        profit = odds - 1 if won else -1
        item.update({
            "status": "settled",
            "settled_at": now_iso(),
            "home_score": hs,
            "away_score": aw,
            "score_ft": f"{hs}-{aw}",
            "actual_score": f"{hs}-{aw}",
            "actual_total_goals": hs + aw,
            "actual_btts": bool(hs > 0 and aw > 0),
            "actual_1x2": _actual_outcome_1x2(hs, aw),
            "market_canonical": _canonical_market(item.get("market")),
            "result": "WIN" if won else "LOSS",
            "profit_units": round(profit, 2),
            "settlement_reason": _settlement_reason(item.get("market"), hs, aw, won),
        })
        updated_results += 1

    ordered = sorted(existing.values(), key=lambda x: (x.get("status") == "settled", x.get("last_seen_at") or x.get("first_seen_at") or ""), reverse=True)[:1500]
    payload = {
        "updated_at": now_iso(),
        "source": "selection_journal_v2_settlement",
        "count": len(ordered),
        "pending": sum(1 for x in ordered if x.get("status") != "settled"),
        "settled": sum(1 for x in ordered if x.get("status") == "settled"),
        "results": ordered,
    }
    save_debug("selection_journal_debug.json", {
        "updated_at": now_iso(),
        "before": len(current.get("results", [])) if isinstance(current, dict) else 0,
        "after": len(ordered),
        "added": added,
        "refreshed": refreshed,
        "updated_results": updated_results,
        "unsettleable_markets": sum(1 for x in ordered if x.get("settlement_reason") and str(x.get("settlement_reason")).startswith("Piață neacoperită")),
        "pending": payload["pending"],
        "settled": payload["settled"],
    })
    save("selection_journal.json", payload, protect_empty=False, job_name="selection_journal")


# ─────────────────────────────────────────────────────────────────────────────
# [10/10] PERFORMANCE MEMORY — Backtesting Lite
# ─────────────────────────────────────────────────────────────────────────────
FINAL_STATUSES = {
    "finished", "finish", "ft", "fulltime", "full_time", "ended", "complete", "completed",
    "afterextra", "after_extra", "aet", "afterpen", "after_penalties", "penalties", "closed"
}


def _read_json_file(name: str, default: Any) -> Any:
    path = DATA_DIR / name
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        warn(f"Nu pot citi {name} pentru performance memory", error=str(exc))
    return default


def _event_scores(ev: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    if not isinstance(ev, dict):
        return None, None

    def pick(keys: Iterable[str]) -> Optional[int]:
        for key in keys:
            value = ev.get(key)
            if value is None and isinstance(ev.get("score"), dict):
                value = ev["score"].get(key)
            if value is None:
                continue
            try:
                return int(value)
            except Exception:
                continue
        return None

    home = pick(["home_score", "home_goals", "score_home", "home", "home_ft", "ft_home"])
    away = pick(["away_score", "away_goals", "score_away", "away", "away_ft", "ft_away"])
    return home, away


def _is_settled(ev: Dict[str, Any]) -> bool:
    if not isinstance(ev, dict):
        return False
    status = str(ev.get("status") or ev.get("state") or ev.get("period") or "").lower().replace(" ", "_")
    hs, aw = _event_scores(ev)
    return (status in FINAL_STATUSES and hs is not None and aw is not None) or (hs is not None and aw is not None and status in FINAL_STATUSES)


def _actual_outcome_1x2(home: int, away: int) -> str:
    if home > away:
        return "homeWin"
    if home < away:
        return "awayWin"
    return "draw"


def _canonical_market(market: Any) -> str:
    raw = str(market or "").strip()
    compact = raw.lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "1": "homeWin", "homewin": "homeWin", "home_win": "homeWin", "home": "homeWin", "h": "homeWin", "winner_home": "homeWin",
        "x": "draw", "draw": "draw", "draw_result": "draw", "d": "draw", "tie": "draw",
        "2": "awayWin", "awaywin": "awayWin", "away_win": "awayWin", "away": "awayWin", "a": "awayWin", "winner_away": "awayWin",
        "over15": "over15", "over_15": "over15", "over_1_5": "over15", "o15": "over15", "o1_5": "over15", "over_under_15_over": "over15",
        "over25": "over25", "over_25": "over25", "over_2_5": "over25", "o25": "over25", "o2_5": "over25", "over_under_25_over": "over25",
        "over35": "over35", "over_35": "over35", "over_3_5": "over35", "o35": "over35", "o3_5": "over35", "over_under_35_over": "over35",
        "under15": "under15", "under_15": "under15", "under_1_5": "under15", "u15": "under15", "u1_5": "under15", "over_under_15_under": "under15",
        "under25": "under25", "under_25": "under25", "under_2_5": "under25", "u25": "under25", "u2_5": "under25", "over_under_25_under": "under25",
        "under35": "under35", "under_35": "under35", "under_3_5": "under35", "u35": "under35", "u3_5": "under35", "over_under_35_under": "under35",
        "btts": "btts", "btts_yes": "btts", "both_teams_to_score": "btts", "gg": "btts", "yes_btts": "btts",
        "btts_no": "bttsNo", "no_btts": "bttsNo", "ng": "bttsNo",
    }
    return aliases.get(compact, aliases.get(raw, raw))


def _market_won(market: str, home: int, away: int) -> Optional[bool]:
    total = home + away
    m = _canonical_market(market)
    if m == "homeWin":
        return home > away
    if m == "draw":
        return home == away
    if m == "awayWin":
        return home < away
    if m == "over15":
        return total > 1.5
    if m == "over25":
        return total > 2.5
    if m == "over35":
        return total > 3.5
    if m == "under15":
        return total < 1.5
    if m == "under25":
        return total < 2.5
    if m == "under35":
        return total < 3.5
    if m == "btts":
        return home > 0 and away > 0
    if m == "bttsNo":
        return home == 0 or away == 0
    return None


def _settlement_reason(market: Any, home: int, away: int, won: Optional[bool]) -> str:
    total = home + away
    score = f"{home}-{away}"
    m = _canonical_market(market)
    prefix = "WIN" if won is True else ("LOSS" if won is False else "UNKNOWN")
    if m in ("homeWin", "draw", "awayWin"):
        actual = _actual_outcome_1x2(home, away)
        label = {"homeWin": "1", "draw": "X", "awayWin": "2"}.get(m, m)
        actual_label = {"homeWin": "1", "draw": "X", "awayWin": "2"}.get(actual, actual)
        return f"{prefix} — scor {score}, piață {label}, rezultat final {actual_label}."
    if m.startswith("over"):
        line = {"over15": 1.5, "over25": 2.5, "over35": 3.5}.get(m)
        if line is not None:
            return f"{prefix} — scor {score}, total goluri {total}; Over {line} {'validat' if won else 'invalidat'}."
    if m.startswith("under"):
        line = {"under15": 1.5, "under25": 2.5, "under35": 3.5}.get(m)
        if line is not None:
            return f"{prefix} — scor {score}, total goluri {total}; Under {line} {'validat' if won else 'invalidat'}."
    if m == "btts":
        return f"{prefix} — scor {score}; BTTS {'validat' if won else 'invalidat'} ({'ambele au marcat' if home > 0 and away > 0 else 'cel puțin o echipă nu a marcat'})."
    if m == "bttsNo":
        return f"{prefix} — scor {score}; BTTS Nu {'validat' if won else 'invalidat'} ({'cel puțin o echipă nu a marcat' if home == 0 or away == 0 else 'ambele au marcat'})."
    return f"Piață neacoperită pentru settlement: {market}. Scor final {score}."


def _prob_for_market(pred: Dict[str, Any], market: str) -> Optional[float]:
    markets = get_all_markets(pred)
    key = _canonical_market(market)
    value = markets.get(key)
    return float(value) if value is not None and value > 0 else None


def _add_bucket(bucket: Dict[str, Any], key: str, won: bool, profit: float, prob: Optional[float] = None) -> None:
    item = bucket.setdefault(key, {"sample": 0, "wins": 0, "profit_units": 0.0, "prob_sum": 0.0, "prob_n": 0})
    item["sample"] += 1
    item["wins"] += 1 if won else 0
    item["profit_units"] += float(profit)
    if prob is not None:
        item["prob_sum"] += float(prob)
        item["prob_n"] += 1


def _finalize_bucket(bucket: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for key, item in sorted(bucket.items(), key=lambda kv: (-kv[1].get("sample", 0), kv[0])):
        sample = item.get("sample", 0) or 0
        wins = item.get("wins", 0) or 0
        profit = round(float(item.get("profit_units", 0.0)), 2)
        avg_prob = round((item.get("prob_sum", 0.0) / item.get("prob_n", 1)) * 100, 1) if item.get("prob_n") else None
        out[key] = {
            "sample": sample,
            "wins": wins,
            "losses": sample - wins,
            "win_rate": round(wins / sample * 100, 1) if sample else 0,
            "profit_units": profit,
            "roi_pct": round(profit / sample * 100, 1) if sample else 0,
            "avg_model_probability": avg_prob,
            "label": ("sample mic" if sample < 30 else "sample relevant") if sample else "fără sample",
        }
    return out


def compute_performance_summary() -> None:
    print("\n[10/10] Performance Memory / Backtesting Lite...")
    preds_data = _read_json_file("predictions.json", {"results": []})
    signals_data = _read_json_file("signals.json", {"signals": []})
    value_data = _read_json_file("value_bets.json", {"results": []})
    context_data = _read_json_file("match_context.json", {"results": []})
    results_data = _read_json_file("recent_results.json", {"results": []})
    journal_data = _read_json_file("selection_journal.json", {"results": []})

    preds = preds_data.get("results", []) if isinstance(preds_data, dict) else []
    signals = signals_data.get("signals", []) if isinstance(signals_data, dict) else []
    vbs = value_data.get("results", []) if isinstance(value_data, dict) else []
    contexts = context_data.get("results", []) if isinstance(context_data, dict) else []
    recent_results = results_data.get("results", []) if isinstance(results_data, dict) else []
    journal_items = journal_data.get("results", []) if isinstance(journal_data, dict) else []

    events: Dict[str, Dict[str, Any]] = {}
    pred_by_event: Dict[str, Dict[str, Any]] = {}
    for pred in preds:
        ev = pred.get("event") or {}
        eid = str(ev.get("id") or "")
        if eid:
            events.setdefault(eid, ev)
            pred_by_event[eid] = pred
    for ctx in contexts:
        eid = str(ctx.get("event_id") or "")
        detail = ctx.get("detail") or {}
        if eid and isinstance(detail, dict):
            merged = dict(events.get(eid, {}))
            merged.update(detail)
            events[eid] = merged
    for ev in recent_results:
        eid = str(ev.get("id") or ev.get("event_id") or "")
        if eid:
            merged = dict(events.get(eid, {}))
            merged.update(ev)
            events[eid] = merged

    settled_events = {eid: ev for eid, ev in events.items() if _is_settled(ev)}

    # 1X2 model calibration / Brier score from settled predictions.
    brier_items: List[float] = []
    model_1x2_rows: List[Dict[str, Any]] = []
    for eid, ev in settled_events.items():
        pred = pred_by_event.get(eid)
        if not pred:
            continue
        hs, aw = _event_scores(ev)
        if hs is None or aw is None:
            continue
        p_home = _prob_for_market(pred, "homeWin")
        p_draw = _prob_for_market(pred, "draw")
        p_away = _prob_for_market(pred, "awayWin")
        if p_home is None or p_draw is None or p_away is None:
            continue
        actual = _actual_outcome_1x2(hs, aw)
        brier = (p_home - (1 if actual == "homeWin" else 0)) ** 2 + (p_draw - (1 if actual == "draw" else 0)) ** 2 + (p_away - (1 if actual == "awayWin" else 0)) ** 2
        brier_items.append(brier)
        predicted = max([("homeWin", p_home), ("draw", p_draw), ("awayWin", p_away)], key=lambda x: x[1])[0]
        model_1x2_rows.append({
            "event_id": eid,
            "score": f"{hs}-{aw}",
            "predicted": predicted,
            "actual": actual,
            "hit": predicted == actual,
            "brier": round(brier, 4),
        })

    by_strategy: Dict[str, Any] = {}
    by_market: Dict[str, Any] = {}
    examples: List[Dict[str, Any]] = []

    def evaluate_selection(sel: Dict[str, Any], strategy_key: str, market_key: str, odds_key: str = "odds") -> None:
        eid = str(sel.get("event_id") or "")
        ev = settled_events.get(eid)
        if not ev:
            return
        hs, aw = _event_scores(ev)
        if hs is None or aw is None:
            return
        won = _market_won(market_key, hs, aw)
        if won is None:
            return
        odds = as_float(sel.get(odds_key) or sel.get("market_odds") or sel.get("best_odds")) or 0
        if odds <= 1:
            return
        profit = odds - 1 if won else -1
        pred = pred_by_event.get(eid) or {}
        prob = _prob_for_market(pred, market_key)
        _add_bucket(by_strategy, strategy_key, won, profit, prob)
        _add_bucket(by_market, _canonical_market(market_key), won, profit, prob)
        if len(examples) < 12:
            examples.append({
                "event_id": eid,
                "home_team": sel.get("home_team") or ev.get("home_team"),
                "away_team": sel.get("away_team") or ev.get("away_team"),
                "market": market_key,
                "strategy": strategy_key,
                "odds": round(odds, 2),
                "score": f"{hs}-{aw}",
                "result": "WIN" if won else "LOSS",
                "profit_units": round(profit, 2),
            })

    journal_settled = [x for x in journal_items if x.get("status") == "settled"]
    if journal_settled:
        for item in journal_settled:
            won = item.get("result") == "WIN"
            profit = as_float(item.get("profit_units"), 0) or 0
            prob = as_float(item.get("model_probability"))
            _add_bucket(by_strategy, item.get("strategy") or item.get("source") or "journal", won, profit, prob)
            _add_bucket(by_market, item.get("market_canonical") or _canonical_market(item.get("market")) or "unknown", won, profit, prob)
            if len(examples) < 12:
                examples.append({
                    "event_id": item.get("event_id"),
                    "home_team": item.get("home_team"),
                    "away_team": item.get("away_team"),
                    "market": item.get("market"),
                    "strategy": item.get("strategy") or item.get("source"),
                    "odds": item.get("odds"),
                    "score": item.get("score_ft"),
                    "result": item.get("result"),
                    "profit_units": item.get("profit_units"),
                })
    else:
        for sig in signals:
            evaluate_selection(sig, sig.get("strategy") or "signal", sig.get("market") or "", "odds")
        for vb in vbs:
            evaluate_selection(vb, "value_bets", vb.get("market") or "", "market_odds")

    final_strategy = _finalize_bucket(by_strategy)
    final_market = _finalize_bucket(by_market)
    total_sample = sum(x.get("sample", 0) for x in final_strategy.values())
    total_wins = sum(x.get("wins", 0) for x in final_strategy.values())
    total_profit = round(sum(float(x.get("profit_units", 0)) for x in final_strategy.values()), 2)
    summary = {
        "updated_at": now_iso(),
        "source": "local_backtesting_lite",
        "count": total_sample,
        "settled_events": len(settled_events),
        "model_1x2_sample": len(brier_items),
        "model_1x2_brier": round(sum(brier_items) / len(brier_items), 4) if brier_items else None,
        "journal": {
            "total": len(journal_items),
            "pending": sum(1 for x in journal_items if x.get("status") != "settled"),
            "settled": sum(1 for x in journal_items if x.get("status") == "settled"),
        },
        "overall": {
            "sample": total_sample,
            "wins": total_wins,
            "losses": total_sample - total_wins,
            "win_rate": round(total_wins / total_sample * 100, 1) if total_sample else 0,
            "profit_units": total_profit,
            "roi_pct": round(total_profit / total_sample * 100, 1) if total_sample else 0,
            "label": "sample mic" if total_sample < 30 else "sample relevant",
        },
        "by_strategy": final_strategy,
        "by_market": final_market,
        "recent_examples": examples,
        "model_1x2_recent": model_1x2_rows[:20],
        "notes": [
            "Backtesting Lite folosește doar evenimente cu scor final disponibil în cache.",
            "ROI este calculat la miză fixă 1u per selecție, fără taxe și fără cash-out.",
            "Sample mic trebuie tratat ca orientativ, nu ca dovadă statistică solidă.",
        ],
    }
    save_debug("performance_debug.json", {
        "updated_at": now_iso(),
        "predictions_loaded": len(preds),
        "signals_loaded": len(signals),
        "value_bets_loaded": len(vbs),
        "contexts_loaded": len(contexts),
        "recent_results_loaded": len(recent_results),
        "journal_loaded": len(journal_items),
        "journal_settled": sum(1 for x in journal_items if x.get("status") == "settled"),
        "journal_pending": sum(1 for x in journal_items if x.get("status") != "settled"),
        "settled_events": len(settled_events),
        "selection_sample": total_sample,
        "model_1x2_sample": len(brier_items),
    })
    save("performance_summary.json", summary, protect_empty=False, job_name="performance_summary")


# ── Main ─────────────────────────────────────────────────────────────────────
def main() -> int:
    DEBUG["started_at"] = now_iso()
    if not API_KEY:
        warn("BSD_API_KEY nu este setat")
        save_all_debug()
        print("BSD_API_KEY nu este setat!")
        return 1

    print(f"=== BetPredict Pro v13 Settlement Logic — {today_iso()} (AC: {'YES' if HAS_AC else 'NO'}) ===")
    try:
        fetch_predictions()
        fetch_best_odds()
        fetch_value_bets()
        fetch_matches_today()
        fetch_standings()
        compute_signals()
        fetch_match_context()
        fetch_recent_results()
        update_selection_journal()
        compute_performance_summary()
        print("\nGata!")
        return 0
    finally:
        save_all_debug()


if __name__ == "__main__":
    raise SystemExit(main())
