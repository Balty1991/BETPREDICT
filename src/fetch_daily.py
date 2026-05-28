#!/usr/bin/env python3
"""
BetPredict Pro — Daily Data Fetcher (v20B Odds Comparison Fix)
==================================================
Pasul 21: Full BSD Photo Pack — comparison odds, line movement, odds/best, predictions v2, predicted lineups și AI preview.

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
  - construiește data/api_coverage_report.json pentru inventarierea endpointurilor BSD v2
  - construiește data/team_intelligence.json, team_profiles.json, team_squads.json și team_fixtures.json
  - construiește data/context_intelligence.json cu referee, venue și manageri pentru meciuri prioritare
  - construiește data/qa_report.json pentru verificare finală de stabilitate și producție
  - construiește data/team_form.json, h2h_context.json și xg_context.json pentru forma recentă, directe și xG/xA
  - repară Market Intelligence: folosește /events/{id}/odds/comparison/ pentru 14 books + Polymarket și /events/{id}/odds/ ca fallback consensus
  - expune previous_decimal_odds/is_max_quote pentru mișcarea cotelor direct în UI
  - extrage ai_preview și predicted_lineup din match detail/lineups pentru Match Detail
  - îmbogățește static images: team/league/player/manager/venue prin /img/{type}/{id}/
  - normalizează weather codes 0-5 în label + icon pentru UI
"""

from __future__ import annotations

import json
import os
import sys
import time
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
WEATHER_CODES = {
    0: {"label": "necunoscut / acoperit", "icon": "🏟️"},
    1: {"label": "senin", "icon": "☀️"},
    2: {"label": "înnorat", "icon": "☁️"},
    3: {"label": "ploaie", "icon": "🌧️"},
    4: {"label": "ninsoare", "icon": "❄️"},
    5: {"label": "extrem", "icon": "⛈️"},
}
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
    53: "USL Championship",
}

STRATEGIES = {
    "engine_overall": {
        "label": "Engine Overall",
        "icon": "🎯",
        "markets": ["homeWin", "draw", "awayWin", "under25", "under35"],
        "min_adj": 70.0,
        "min_edge": 8.0,
        "odd_min": 1.25,
        "odd_max": 1.80,
        "color": "#00e87a",
    },
    "best_single": {
        "label": "Evenimentul zilei",
        "icon": "⭐",
        "markets": ["homeWin", "over25", "under35", "btts"],
        "min_adj": 76.0,
        "min_edge": 8.0,
        "odd_min": 1.25,
        "odd_max": 2.10,
        "color": "#ffb830",
    },
    "conservative": {
        "label": "Bilet conservator",
        "icon": "🛡️",
        "markets": ["homeWin", "under35"],
        "min_adj": 80.0,
        "min_edge": 6.0,
        "odd_min": 1.25,
        "odd_max": 1.65,
        "color": "#4a9eff",
    },
    "smart_ev": {
        "label": "Smart EV",
        "icon": "💡",
        "markets": ["homeWin", "awayWin", "btts", "over25", "under35"],
        "min_adj": 68.0,
        "min_edge": 1.5,
        "odd_min": 1.25,
        "odd_max": 2.50,
        "color": "#a78bfa",
    },
    "over15_specialist": {
        "label": "Over 1.5G",
        "icon": "⚽",
        "markets": ["over15"],
        "min_adj": 82.0,
        "min_edge": 10.0,
        "odd_min": 1.43,
        "odd_max": 1.65,
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

# ── Pipeline time budget (global) ───────────────────────────────────────────
# Setat în main(). Permite funcțiilor interne să se oprească devreme dacă
# bugetul de 18 min al fetch_daily.py este pe cale să fie depășit. Fără asta,
# loop-uri ca fetch_team_intelligence (42 echipe × 3 HTTP) pot consuma singure
# 30+ min pe API slow, blocând restul pipeline-ului de 12 scripturi.
_PIPELINE_START: Optional[float] = None


def _pipeline_elapsed_sec() -> float:
    if _PIPELINE_START is None:
        return 0.0
    return time.monotonic() - _PIPELINE_START


def _pipeline_over_budget(threshold_sec: float) -> bool:
    """True dacă pipeline-ul rulează deja de mai mult de `threshold_sec`."""
    return _pipeline_elapsed_sec() > threshold_sec


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


def weather_context(weather: Any, pitch_condition: Any = None) -> Dict[str, Any]:
    """Normalizează weather.code din BSD în label/icon stabil pentru UI."""
    raw = weather if isinstance(weather, dict) else {}
    code = raw.get("code")
    try:
        code_i = int(code) if code is not None else None
    except Exception:
        code_i = None
    meta = WEATHER_CODES.get(code_i, WEATHER_CODES[0])
    return {
        "code": code_i,
        "label": raw.get("description") or meta["label"],
        "icon": meta["icon"],
        "temperature_c": raw.get("temperature_c"),
        "wind_speed": raw.get("wind_speed"),
        "pitch_condition": pitch_condition,
    }


def decorate_player_image(player: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(player, dict):
        return {}
    pid = player.get("id") or player.get("player_id")
    out = dict(player)
    out["player_id"] = pid
    out["image_url"] = out.get("image_url") or out.get("photo_url") or logo_url("player", pid)
    return out


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
        data.setdefault("_pipeline_version", "v22-league-strength-engine")

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


# ── Pasul 3: League Strength Engine ─────────────────────────────────────────
LEAGUE_STRENGTH_CACHE: Dict[str, Any] = {"loaded": False}


def _clamp_num(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _norm_text(value: Any) -> str:
    import unicodedata
    text = unicodedata.normalize("NFD", str(value or "").lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join("".join(ch if ch.isalnum() else " " for ch in text).split())


def _read_json_quiet(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        warn("Nu pot citi JSON pentru League Strength", path=str(path), error=str(exc))
    return default


def _safe_ratio(num: Any, den: Any, default: float = 0.0) -> float:
    n = as_float(num, None)
    d = as_float(den, None)
    if n is None or d is None or d <= 0:
        return default
    return float(n) / float(d)


def _form_score(form: Any) -> Optional[float]:
    text = str(form or "").strip().upper()
    vals = []
    for ch in text:
        if ch == "W":
            vals.append(1.0)
        elif ch == "D":
            vals.append(0.5)
        elif ch == "L":
            vals.append(0.0)
    if not vals:
        return None
    return sum(vals) / len(vals) * 100.0


def _row_team_name(row: Dict[str, Any]) -> str:
    team = row.get("team") if isinstance(row.get("team"), dict) else {}
    return str(row.get("team_name") or team.get("name") or row.get("name") or "")


def _row_team_id(row: Dict[str, Any]) -> Optional[int]:
    team = row.get("team") if isinstance(row.get("team"), dict) else {}
    val = row.get("team_id") or team.get("id")
    try:
        return int(val) if val not in (None, "") else None
    except Exception:
        return None


def _score_row_strength(row: Dict[str, Any], league_size: int) -> Dict[str, Any]:
    pos = int(as_float(row.get("position") or row.get("rank"), league_size) or league_size)
    played = int(as_float(row.get("played"), 0) or 0)
    pts = as_float(row.get("pts") or row.get("points"), 0) or 0
    gf = as_float(row.get("gf"), 0) or 0
    ga = as_float(row.get("ga"), 0) or 0
    gd = as_float(row.get("gd"), gf - ga) or 0
    xgf = as_float(row.get("xgf"), None)
    xga = as_float(row.get("xga"), None)
    xgd = as_float(row.get("xgd"), None)
    xg_games = as_float(row.get("xg_games"), 0) or 0

    rank_score = 50.0 if league_size <= 1 else (league_size - pos) / max(1, league_size - 1) * 100.0
    ppg = _safe_ratio(pts, played, 0.0)
    ppg_score = _clamp_num(ppg / 3.0 * 100.0, 0.0, 100.0)
    gd_pg = _safe_ratio(gd, played, 0.0)
    gd_score = _clamp_num(50.0 + gd_pg * 32.0, 0.0, 100.0)
    form_score = _form_score(row.get("form"))
    if xgd is not None and (xg_games or played):
        xgd_pg = _safe_ratio(xgd, xg_games or played, 0.0)
        xgd_score = _clamp_num(50.0 + xgd_pg * 35.0, 0.0, 100.0)
    else:
        xgd_pg = None
        xgd_score = None

    components = [
        (rank_score, 0.34),
        (ppg_score, 0.26),
        (gd_score, 0.20),
        (xgd_score, 0.10),
        (form_score, 0.10),
    ]
    num = sum(v * w for v, w in components if v is not None)
    den = sum(w for v, w in components if v is not None)
    strength = num / den if den else 50.0

    attack_xg = _safe_ratio(xgf, xg_games or played, 0.0) if xgf is not None else None
    defense_xga = _safe_ratio(xga, xg_games or played, 0.0) if xga is not None else None
    gf_pg = _safe_ratio(gf, played, 0.0)
    ga_pg = _safe_ratio(ga, played, 0.0)
    attack_score = _clamp_num(45.0 + gf_pg * 18.0 + (attack_xg or 0.0) * 8.0, 0.0, 100.0)
    defense_score = _clamp_num(70.0 - ga_pg * 18.0 - (defense_xga or 0.0) * 7.0, 0.0, 100.0)

    return {
        "team_id": _row_team_id(row),
        "team_name": _row_team_name(row),
        "position": pos,
        "played": played,
        "pts": round(pts, 2),
        "ppg": round(ppg, 3),
        "gf": round(gf, 2),
        "ga": round(ga, 2),
        "gd": round(gd, 2),
        "gd_pg": round(gd_pg, 3),
        "xgd_pg": round(xgd_pg, 3) if xgd_pg is not None else None,
        "form": row.get("form"),
        "form_score": round(form_score, 1) if form_score is not None else None,
        "rank_score": round(rank_score, 1),
        "strength_score": round(strength, 1),
        "attack_score": round(attack_score, 1),
        "defense_score": round(defense_score, 1),
    }


def load_league_strength_context() -> Dict[str, Any]:
    if LEAGUE_STRENGTH_CACHE.get("loaded"):
        return LEAGUE_STRENGTH_CACHE

    meta = _read_json_quiet(DATA_DIR / "league_metadata.json", {})
    fallback_standings = _read_json_quiet(DATA_DIR / "standings.json", {})
    by_league: Dict[str, Any] = {}
    by_team_id: Dict[str, Any] = {}
    by_team_name: Dict[str, Any] = {}

    records = meta.get("results") if isinstance(meta, dict) else []
    if isinstance(records, list) and records:
        for lg in records:
            if not isinstance(lg, dict):
                continue
            lid = lg.get("id")
            standings = lg.get("standings") if isinstance(lg.get("standings"), dict) else {}
            rows = standings.get("rows") or standings.get("sample") or []
            if not lid or not isinstance(rows, list) or not rows:
                continue
            league_size = int(standings.get("teams") or len(rows) or 0)
            lctx = {
                "league_id": lid,
                "league_name": lg.get("name"),
                "country": lg.get("country"),
                "season_id": lg.get("season_id"),
                "season_name": (lg.get("current_season") or {}).get("name"),
                "league_size": league_size,
                "source": "league_metadata.standings.rows" if standings.get("rows") else "league_metadata.standings.sample",
                "teams": [],
            }
            for row in rows:
                if not isinstance(row, dict):
                    continue
                t = _score_row_strength(row, league_size)
                t.update({k: lctx[k] for k in ("league_id", "league_name", "country", "season_id", "season_name", "league_size", "source")})
                lctx["teams"].append(t)
                if t.get("team_id") is not None:
                    by_team_id[str(t["team_id"])] = t
                name_key = _norm_text(t.get("team_name"))
                if name_key:
                    by_team_name[f"{lid}|{name_key}"] = t
            by_league[str(lid)] = lctx

    # Fallback pentru instalările unde Pasul 1 încă nu a regenerat league_metadata cu rows.
    if not by_league and isinstance(fallback_standings, dict):
        leagues = fallback_standings.get("leagues") or {}
        for lid, block in leagues.items():
            if not isinstance(block, dict):
                continue
            rows = block.get("standings") or []
            if not isinstance(rows, list) or not rows:
                continue
            league_size = len(rows)
            lctx = {"league_id": lid, "league_name": block.get("league_name"), "league_size": league_size, "source": "standings.json", "teams": []}
            for row in rows:
                t = _score_row_strength(row, league_size)
                t.update({"league_id": lid, "league_name": block.get("league_name"), "league_size": league_size, "source": "standings.json"})
                lctx["teams"].append(t)
                if t.get("team_id") is not None:
                    by_team_id[str(t["team_id"])] = t
                name_key = _norm_text(t.get("team_name"))
                if name_key:
                    by_team_name[f"{lid}|{name_key}"] = t
            by_league[str(lid)] = lctx

    LEAGUE_STRENGTH_CACHE.update({
        "loaded": True,
        "by_league": by_league,
        "by_team_id": by_team_id,
        "by_team_name": by_team_name,
        "summary": {
            "leagues": len(by_league),
            "teams_by_id": len(by_team_id),
            "teams_by_name": len(by_team_name),
            "meta_updated_at": meta.get("updated_at") if isinstance(meta, dict) else None,
        },
    })
    return LEAGUE_STRENGTH_CACHE


def _find_strength_team(lid: Any, team_id: Any, team_name: Any) -> Optional[Dict[str, Any]]:
    ctx = load_league_strength_context()
    if team_id not in (None, ""):
        found = ctx.get("by_team_id", {}).get(str(team_id))
        if found:
            return found
    key = f"{lid}|{_norm_text(team_name)}"
    return ctx.get("by_team_name", {}).get(key)


def apply_league_strength_adjustment(p: Dict[str, Any]) -> Dict[str, Any]:
    ev = p.get("event") or {}
    lid = p.get("_league_id") or ev.get("league_id")
    home = _find_strength_team(lid, ev.get("home_team_id") or p.get("_home_team_id"), ev.get("home_team"))
    away = _find_strength_team(lid, ev.get("away_team_id") or p.get("_away_team_id"), ev.get("away_team"))

    pH = as_float(p.get("blended_home") if p.get("blended_home") is not None else p.get("home_win_probability"), 0.0) or 0.0
    pD = as_float(p.get("blended_draw") if p.get("blended_draw") is not None else p.get("draw_probability"), 0.0) or 0.0
    pA = as_float(p.get("blended_away") if p.get("blended_away") is not None else p.get("away_win_probability"), 0.0) or 0.0
    if not home or not away or pH + pD + pA <= 0.2:
        p["league_strength"] = {
            "available": False,
            "league_id": lid,
            "reason": "missing_team_standings_or_probabilities",
            "context_summary": load_league_strength_context().get("summary", {}),
        }
        return p

    home_strength = float(home.get("strength_score") or 50.0)
    away_strength = float(away.get("strength_score") or 50.0)
    # Home advantage mic, controlat. Nu rescrie modelul BSD, doar îl calibrează contextual.
    delta = (home_strength + 3.0) - away_strength
    abs_delta = abs(delta)
    home_shift = _clamp_num(delta * 0.00115, -0.065, 0.065)
    away_shift = -home_shift
    draw_shift = 0.012 if abs_delta <= 5 else -_clamp_num(abs_delta * 0.00055, 0.0, 0.035)

    new_h = max(0.015, pH + home_shift)
    new_d = max(0.050, pD + draw_shift)
    new_a = max(0.015, pA + away_shift)
    total = new_h + new_d + new_a
    new_h, new_d, new_a = new_h / total, new_d / total, new_a / total

    p["pre_league_home"] = round(pH, 4)
    p["pre_league_draw"] = round(pD, 4)
    p["pre_league_away"] = round(pA, 4)
    p["blended_home"] = round(new_h, 4)
    p["blended_draw"] = round(new_d, 4)
    p["blended_away"] = round(new_a, 4)
    p["league_strength_home"] = round(home_strength, 1)
    p["league_strength_away"] = round(away_strength, 1)
    p["league_strength_delta"] = round(delta, 1)
    p["league_strength"] = {
        "available": True,
        "source": home.get("source") or away.get("source"),
        "league_id": lid,
        "league_name": home.get("league_name") or p.get("_league_name"),
        "country": home.get("country"),
        "season_id": home.get("season_id"),
        "season_name": home.get("season_name"),
        "league_size": home.get("league_size") or away.get("league_size"),
        "home": home,
        "away": away,
        "home_strength": round(home_strength, 1),
        "away_strength": round(away_strength, 1),
        "delta_strength": round(delta, 1),
        "adjustment_pp": {
            "home": round((new_h - pH) * 100, 2),
            "draw": round((new_d - pD) * 100, 2),
            "away": round((new_a - pA) * 100, 2),
        },
    }
    return p


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

    p = apply_league_strength_adjustment(p)

    best_p = max(p.get("blended_home") or pH, p.get("blended_draw") or pD, p.get("blended_away") or pA)
    edge_pp = (best_p - 0.5) * 100
    base_score = min(100, min(100, max(0, (best_p - 0.5) / 0.3 * 100)) * 0.6 + min(100, max(0, edge_pp / 15 * 100)) * 0.4)
    ls = p.get("league_strength") if isinstance(p.get("league_strength"), dict) else {}
    ls_bonus = 0.0
    if ls.get("available"):
        delta = abs(as_float(ls.get("delta_strength"), 0.0) or 0.0)
        ls_bonus = _clamp_num((delta - 8.0) / 35.0 * 4.0, 0.0, 4.0)
    p["league_strength_bonus"] = round(ls_bonus, 2)
    p["smartbet_score"] = round(min(100.0, base_score + ls_bonus), 1)
    p["edge_pp"] = round(edge_pp, 2)
    gs = (p.get("confidence") or best_p or 0) * 100 * 0.58 + p["smartbet_score"] * 0.42
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

                # Praguri per-piață (adaptive: reabilitare / înăsprire selectivă)
                mkov = (strat.get("_market_overrides") or {}).get(mk)
                eff_min_adj = (mkov or {}).get("min_adj", strat["min_adj"])
                eff_min_edge = (mkov or {}).get("min_edge", strat["min_edge"])
                eff_odd_min = (mkov or {}).get("odd_min", strat["odd_min"])
                eff_odd_max = (mkov or {}).get("odd_max", strat["odd_max"])

                if adj < eff_min_adj:
                    rejected["low_probability"] += 1
                    continue

                # Pasul 2: semnalele publice se bazează pe cote reale BSD, nu pe cote estimate.
                odd, is_real, odds_market = market_price(odds_idx, eid, mk, prob01, allow_estimated=False)
                if not is_real:
                    rejected["missing_real_odds"] += 1
                    continue
                if odd < eff_odd_min or odd > eff_odd_max:
                    rejected["odds_range"] += 1
                    continue

                ev_val = prob01 * odd - 1
                if ev_val <= 0:
                    rejected["non_positive_ev"] += 1
                    continue
                edge_pp = (prob01 - 1 / odd) * 100 if odd > 1 else 0
                if edge_pp < eff_min_edge:
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
                        "league_strength": pred.get("league_strength"),
                        "league_strength_delta": pred.get("league_strength_delta"),
                        "league_strength_bonus": pred.get("league_strength_bonus"),
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
    n_ls = sum(1 for p in all_preds if isinstance(p.get("league_strength"), dict) and p["league_strength"].get("available"))
    print(f"  TOTAL: {len(all_preds)} | prob:{n_p} | grade:{n_g} | league-strength:{n_ls}")
    save_debug("league_strength_debug.json", {
        "updated_at": now_iso(),
        "applied_predictions": n_ls,
        "total_predictions": len(all_preds),
        "context": load_league_strength_context().get("summary", {}),
        "sample": [
            {
                "event_id": (p.get("event") or {}).get("id"),
                "match": f"{(p.get('event') or {}).get('home_team')} vs {(p.get('event') or {}).get('away_team')}",
                "league": p.get("_league_name"),
                "home_strength": p.get("league_strength_home"),
                "away_strength": p.get("league_strength_away"),
                "delta": p.get("league_strength_delta"),
                "adjustment_pp": (p.get("league_strength") or {}).get("adjustment_pp") if isinstance(p.get("league_strength"), dict) else None,
            }
            for p in all_preds if isinstance(p.get("league_strength"), dict) and p["league_strength"].get("available")
        ][:12],
    })
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


def _vb_adaptive_market_map() -> Optional[Dict[str, Optional[Dict[str, Any]]]]:
    """Returnează override-uri per piață pentru value bets din adaptive_thresholds.json.
    None ca valoare = piața e eliminată. Dict = folosiți aceste valori în loc de hardcoded.
    Returnează None global la orice eroare → se folosesc defaults.
    """
    at_path = DATA_DIR / "adaptive_thresholds.json"
    if not at_path.exists():
        return None
    try:
        at = json.loads(at_path.read_text(encoding="utf-8"))
        by_market: Dict[str, Any] = at.get("by_market") or {}
        if not by_market:
            return None

        result: Dict[str, Optional[Dict[str, Any]]] = {}
        for m in ["homeWin", "draw", "awayWin", "over15", "over25", "under25", "under35", "btts"]:
            mdata = by_market.get(m) or {}
            rec = mdata.get("recommended") or {}
            edge_bkts = mdata.get("edge_buckets") or []
            odds_bkts = mdata.get("odds_buckets") or []

            if not rec or rec.get("use_defaults"):
                result[m] = {}  # date insuficiente → defaults
                continue

            prof_edge = [b for b in edge_bkts if (b.get("roi_pct") or 0) > 0 and (b.get("n") or 0) >= 3]
            prof_odds = [b for b in odds_bkts if (b.get("roi_pct") or 0) > 0 and (b.get("n") or 0) >= 3]
            market_roi = (mdata.get("stats") or {}).get("roi_pct") or 0
            market_n = (mdata.get("stats") or {}).get("n") or 0
            needs_rehab = (not prof_edge) and (market_roi < 0) and (market_n >= 10)

            if (rec.get("blacklisted") or needs_rehab) and not prof_edge:
                result[m] = None  # eliminată — nicio fereastră profitabilă
            elif (rec.get("blacklisted") or needs_rehab) and prof_edge:
                top_edge = [b for b in prof_edge if (b.get("roi_pct") or 0) > 10]
                best = top_edge or prof_edge
                result[m] = {
                    "min_edge": round(min(b["range_lo"] for b in best), 1),
                    "min_prob": round(rec.get("min_prob_pct", 66.0) / 100, 4),
                    "odd_min": round(min(b["range_lo"] for b in prof_odds), 2) if prof_odds else None,
                    "odd_max": round(max(b["range_hi"] for b in prof_odds), 2) if prof_odds else None,
                }
            else:
                result[m] = {
                    "min_edge": rec.get("min_edge_pp"),
                    "min_prob": round(rec.get("min_prob_pct", 0) / 100, 4) if rec.get("min_prob_pct") else None,
                }
        return result
    except Exception as exc:
        warn(f"adaptive value bets map: eroare ({exc}), defaults hardcoded")
        return None


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

    # Adaptive overrides per piată (încărcate o singură dată, folosite în toți candidații)
    _at_vb = _vb_adaptive_market_map()

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
            # ── Aplică logica adaptivă per piață ──────────────────────────────
            eff_min_edge = rules["min_edge_pp"]
            if _at_vb is not None:
                at_ov = _at_vb.get(internal_key)
                if at_ov is None:
                    # Piată eliminată de sistemul adaptiv (zero ferestre profitabile)
                    continue
                if at_ov.get("min_prob") is not None:
                    min_prob = max(min_prob, at_ov["min_prob"])
                if at_ov.get("min_edge") is not None:
                    eff_min_edge = max(eff_min_edge, at_ov["min_edge"])
                if at_ov.get("odd_min") is not None:
                    odd_min = max(odd_min, at_ov["odd_min"])
                if at_ov.get("odd_max") is not None:
                    odd_max = min(odd_max, at_ov["odd_max"])
                    odd_max = max(odd_max, odd_min + 0.20)  # marjă minimă

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
            if edge_pp < eff_min_edge:
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
                    "league_strength": pred.get("league_strength"),
                    "league_strength_delta": pred.get("league_strength_delta"),
                    "league_strength_bonus": pred.get("league_strength_bonus"),
                    "risk_note": "cote reale + standings strength + edge controlat" if tier == "strong" else "semnal moderat, verifică contextul/standings",
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
    print("\n[5/6] Clasamente season-aware...")
    data: Dict[str, Any] = {}
    meta = _read_json_quiet(DATA_DIR / "league_metadata.json", {})
    records = meta.get("results") if isinstance(meta, dict) else []

    if isinstance(records, list) and records:
        for lg in records:
            if not isinstance(lg, dict):
                continue
            lid = lg.get("id")
            if not lid:
                continue
            season_id = lg.get("season_id") or (lg.get("current_season") or {}).get("id")
            lname = lg.get("name") or LEAGUES.get(int(lid) if str(lid).isdigit() else 0, f"Liga {lid}")
            d = get(f"{BASE_V2}/leagues/{lid}/standings/", {"season_id": season_id} if season_id else {}, label=f"standings_season_{lid}")
            rows = (d or {}).get("standings") or (d or {}).get("results") or []
            groups = (d or {}).get("groups") if isinstance(d, dict) else None
            if not rows and isinstance(groups, dict):
                for group_rows in groups.values():
                    if isinstance(group_rows, list):
                        rows.extend(group_rows)
            if rows:
                data[str(lid)] = {
                    "league_name": lname,
                    "league_id": lid,
                    "country": lg.get("country"),
                    "season_id": season_id,
                    "season_name": (lg.get("current_season") or {}).get("name"),
                    "standings": rows,
                    "league_logo": logo_url("league", lid),
                    "source": "league_metadata_current_season",
                }
                print(f"  {lname}: {len(rows)} echipe · sezon {season_id or '—'}")

    if not data:
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
                    data[str(lid)] = {"league_name": lname, "league_id": lid, "standings": rows, "league_logo": logo_url("league", lid), "source": "legacy_fallback"}
                    print(f"  {lname}: {len(rows)} echipe")
                    break

    save("standings.json", {"updated_at": now_iso(), "leagues": data, "count": len(data), "source": "season_aware"}, protect_empty=True, job_name="standings")


# ─────────────────────────────────────────────────────────────────────────────
# ADAPTIVE THRESHOLDS — conectare cu adaptive_thresholds.py
# ─────────────────────────────────────────────────────────────────────────────
def _apply_adaptive_thresholds(strategies: Dict[str, Any]) -> Dict[str, Any]:
    """Aplică recomandările din adaptive_thresholds.json pe STRATEGIES.

    Principiu (în ordine):
      1. Încearcă reabilitarea piețelor neprofitabile prin criterii strict per-piață
         (găsește sub-coșurile edge/odds profitabile și aplică-le ca filtru).
      2. Elimină piața doar dacă NU există niciun sub-coș profitabil (ultima opțiune).
      3. Piețele profitabile primesc și ele criterii înăsprite unde datele o cer.
    Sigur: orice eroare → returnează strategies neschimbat (hardcoded defaults).
    """
    at_path = DATA_DIR / "adaptive_thresholds.json"
    transparency: Dict[str, Any] = {"updated_at": now_iso(), "applied": False, "reason": "pending", "changes": []}
    try:
        if not at_path.exists():
            transparency["reason"] = "adaptive_thresholds.json lipsa"
            save("strategy_thresholds_applied.json", transparency, protect_empty=False)
            return strategies

        at = json.loads(at_path.read_text(encoding="utf-8"))
        by_market: Dict[str, Any] = at.get("by_market") or {}
        if not by_market:
            transparency["reason"] = "by_market gol — date insuficiente"
            save("strategy_thresholds_applied.json", transparency, protect_empty=False)
            return strategies

        _aliases: Dict[str, str] = {
            "homeWin": "homeWin", "home_win": "homeWin",
            "draw": "draw",
            "awayWin": "awayWin", "away_win": "awayWin",
            "over15": "over15", "over25": "over25",
            "under25": "under25", "under35": "under35",
            "btts": "btts",
        }

        out: Dict[str, Any] = {}
        changes: List[Dict[str, Any]] = []

        for strat_name, strat_cfg in strategies.items():
            nc = dict(strat_cfg)
            orig_markets = list(strat_cfg.get("markets", []))
            new_markets: List[str] = []
            market_overrides: Dict[str, Dict[str, Any]] = {}

            for m in orig_markets:
                mc = _aliases.get(m, m)
                mdata = by_market.get(mc) or {}
                rec = mdata.get("recommended") or {}
                edge_bkts = mdata.get("edge_buckets") or []
                odds_bkts = mdata.get("odds_buckets") or []

                if not rec or rec.get("use_defaults"):
                    # Date insuficiente → păstrează piața cu defaults
                    new_markets.append(m)
                    continue

                # Sub-coșuri profitabile indiferent de verdict
                prof_edge = [b for b in edge_bkts if (b.get("roi_pct") or 0) > 0 and (b.get("n") or 0) >= 3]
                prof_odds = [b for b in odds_bkts if (b.get("roi_pct") or 0) > 0 and (b.get("n") or 0) >= 3]
                market_roi = (mdata.get("stats") or {}).get("roi_pct") or 0
                market_n = (mdata.get("stats") or {}).get("n") or 0

                # Piețe fără niciun sub-coș profitabil + ROI negativ + date suficiente
                # → same treatment as blacklisted, indiferent de flag-ul din adaptive_thresholds
                needs_rehab = (not prof_edge) and (market_roi < 0) and (market_n >= 10)

                if rec.get("blacklisted") or needs_rehab:
                    if prof_edge:
                        # ── Reabilitare: pierderi globale dar există ferestre profitabile ──
                        # Preferă cosuri cu ROI > 10% dacă există, altfel orice > 0%
                        top_edge = [b for b in prof_edge if (b.get("roi_pct") or 0) > 10]
                        best_buckets = top_edge or prof_edge
                        rehab_edge = max(
                            strat_cfg.get("min_edge", 5.0),
                            min(b["range_lo"] for b in best_buckets),
                        )
                        rehab_adj = max(
                            strat_cfg.get("min_adj", 66.0),
                            rec.get("min_prob_pct", 70.0),
                        )
                        rehab_odd_min = strat_cfg.get("odd_min", 1.20)
                        rehab_odd_max = strat_cfg.get("odd_max", 2.20)
                        if prof_odds:
                            rehab_odd_min = max(rehab_odd_min, min(b["range_lo"] for b in prof_odds))
                            rehab_odd_max = min(rehab_odd_max, max(b["range_hi"] for b in prof_odds))
                            rehab_odd_max = max(rehab_odd_max, rehab_odd_min + 0.30)  # marjă minimă

                        ov: Dict[str, Any] = {
                            "min_edge": round(rehab_edge, 1),
                            "min_adj": round(rehab_adj, 1),
                            "odd_min": round(rehab_odd_min, 2),
                            "odd_max": round(rehab_odd_max, 2),
                        }
                        market_overrides[m] = ov
                        new_markets.append(m)
                        changes.append({
                            "strategy": strat_name, "market": m,
                            "action": "rehabilitated",
                            "rehab_overrides": ov,
                            "profitable_edge_buckets": len(prof_edge),
                        })
                    else:
                        # ── Eliminare — ultima opțiune: ROI negativ + zero ferestre profitabile ──
                        changes.append({
                            "strategy": strat_name, "market": m,
                            "action": "removed_no_rehab_path",
                            "reason": rec.get("verdict") or f"roi={market_roi:+.1f}% fara bucket profitabil",
                            "market_roi": market_roi,
                            "market_n": market_n,
                        })
                        # market-ul NU se adaugă în new_markets

                else:
                    # ── Piață normală: înăsprire selectivă unde datele o cer ──
                    new_markets.append(m)
                    eff_edge = round(max(strat_cfg.get("min_edge", 5.0), rec.get("min_edge_pp", 0)), 1)
                    eff_adj = round(max(strat_cfg.get("min_adj", 66.0), rec.get("min_prob_pct", 0)), 1)
                    # Păstrăm override doar dacă schimbă ceva față de defaults strategiei
                    if eff_edge != strat_cfg.get("min_edge") or eff_adj != strat_cfg.get("min_adj"):
                        ov = {
                            "min_edge": eff_edge,
                            "min_adj": eff_adj,
                            "odd_min": strat_cfg.get("odd_min", 1.20),
                            "odd_max": strat_cfg.get("odd_max", 2.20),
                        }
                        market_overrides[m] = ov
                        changes.append({
                            "strategy": strat_name, "market": m,
                            "action": "thresholds_tightened",
                            "overrides": ov,
                        })

            nc["markets"] = new_markets
            nc["_market_overrides"] = market_overrides
            nc["_adaptive_applied"] = True
            out[strat_name] = nc

        n_rehab = sum(1 for c in changes if c["action"] == "rehabilitated")
        n_removed = sum(1 for c in changes if c["action"] == "removed_no_rehab_path")
        n_tight = sum(1 for c in changes if c["action"] == "thresholds_tightened")
        transparency.update({
            "applied": True,
            "reason": "ok",
            "changes": changes,
            "summary": {"rehabilitated": n_rehab, "removed_last_resort": n_removed, "tightened": n_tight},
            "markets_in_by_market": list(by_market.keys()),
            "source_updated_at": at.get("updated_at"),
            "overall_roi": (at.get("overall") or {}).get("overall_roi_pct"),
            "strategies_after": {
                k: {
                    "markets": v.get("markets"),
                    "_market_overrides": v.get("_market_overrides"),
                }
                for k, v in out.items()
            },
        })
        save("strategy_thresholds_applied.json", transparency, protect_empty=False)
        print(f"  adaptive_thresholds: {n_tight} inasprite, {n_rehab} reabilitate, {n_removed} eliminate (ultima optiune)")
        return out

    except Exception as exc:
        warn("adaptive_thresholds: eroare la aplicare, pastrare defaults", error=str(exc))
        transparency["reason"] = f"eroare: {exc}"
        try:
            save("strategy_thresholds_applied.json", transparency, protect_empty=False)
        except Exception:
            pass
        return strategies


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

    # Aplica adaptive thresholds înainte de calculul semnalelor
    global STRATEGIES
    STRATEGIES = _apply_adaptive_thresholds(STRATEGIES)

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


def extract_ai_preview(detail: Any) -> Dict[str, Any]:
    """Extrage ai_preview din detail, indiferent de schema BSD exactă."""
    if not isinstance(detail, dict):
        return {"available": False, "text": None, "source": None}
    candidates = [
        ("ai_preview", detail.get("ai_preview")),
        ("preview_ai", detail.get("preview_ai")),
        ("match_preview", detail.get("match_preview")),
        ("preview", detail.get("preview")),
        ("ai", (detail.get("ai") or {}).get("preview") if isinstance(detail.get("ai"), dict) else None),
    ]
    for source, value in candidates:
        if isinstance(value, str) and value.strip():
            return {"available": True, "text": value.strip(), "source": source}
        if isinstance(value, dict):
            for key in ("text", "summary", "preview", "content", "haiku", "message"):
                txt = value.get(key)
                if isinstance(txt, str) and txt.strip():
                    return {"available": True, "text": txt.strip(), "source": f"{source}.{key}", "raw": value}
    return {"available": False, "text": None, "source": None}


def _players_preview_from_side(side_obj: Any, limit: int = 11) -> List[Dict[str, Any]]:
    if not isinstance(side_obj, dict):
        return []
    players = side_obj.get("players") or side_obj.get("starting") or side_obj.get("starting_xi") or side_obj.get("lineup") or []
    if isinstance(players, dict):
        players = list(players.values())
    out: List[Dict[str, Any]] = []
    for p in players if isinstance(players, list) else []:
        if not isinstance(p, dict):
            continue
        pid = p.get("id") or p.get("player_id")
        out.append({
            "id": pid,
            "player_id": pid,
            "name": p.get("name") or p.get("player_name") or p.get("short_name"),
            "short_name": p.get("short_name") or p.get("name") or p.get("player_name"),
            "position": p.get("position") or p.get("pos"),
            "shirt_number": p.get("shirt_number") or p.get("jersey_number") or p.get("number"),
            "jersey_number": p.get("jersey_number") or p.get("shirt_number") or p.get("number"),
            "image_url": logo_url("player", pid),
        })
        if len(out) >= limit:
            break
    return out


def extract_predicted_lineup(lineups: Any) -> Dict[str, Any]:
    """Normalizează predicted_lineup/confirmed_lineup într-un obiect compact pentru UI."""
    status = extract_lineup_status(lineups)
    if not isinstance(lineups, dict):
        return {"available": False, "status": status, "home": {}, "away": {}}
    home = (lineups.get("lineups") or {}).get("home") if isinstance(lineups.get("lineups"), dict) else None
    away = (lineups.get("lineups") or {}).get("away") if isinstance(lineups.get("lineups"), dict) else None
    home = home or lineups.get("home") or lineups.get("home_lineup") or {}
    away = away or lineups.get("away") or lineups.get("away_lineup") or {}
    predicted = {
        "available": bool(home or away),
        "status": status,
        "is_predicted": str(status).lower() == "predicted" or bool(lineups.get("predicted_lineup")),
        "is_confirmed": str(status).lower() == "confirmed",
        "home": {
            "formation": home.get("formation") if isinstance(home, dict) else None,
            "confidence": home.get("confidence") if isinstance(home, dict) else None,
            "players": _players_preview_from_side(home),
        },
        "away": {
            "formation": away.get("formation") if isinstance(away, dict) else None,
            "confidence": away.get("confidence") if isinstance(away, dict) else None,
            "players": _players_preview_from_side(away),
        },
    }
    return predicted


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
            "ai_preview": extract_ai_preview(detail),
            "weather_context": weather_context((detail or {}).get("weather") if isinstance(detail, dict) else {}, (detail or {}).get("pitch_condition") if isinstance(detail, dict) else None),
            "image_assets": {
                "home_team_logo": logo_url("team", seed.get("home_team_id")),
                "away_team_logo": logo_url("team", seed.get("away_team_id")),
                "league_logo": logo_url("league", seed.get("league_id")),
                "venue_photo": logo_url("venue", (detail or {}).get("venue_id") if isinstance(detail, dict) else None),
                "home_manager_photo": logo_url("manager", (detail or {}).get("home_coach_id") or (detail or {}).get("home_manager_id") if isinstance(detail, dict) else None),
                "away_manager_photo": logo_url("manager", (detail or {}).get("away_coach_id") or (detail or {}).get("away_manager_id") if isinstance(detail, dict) else None),
            },
            "stats": stats,
            "incidents": extract_results(incidents) if incidents is not None else [],
            "lineups": lineups,
            "lineup_status": extract_lineup_status(lineups),
            "predicted_lineup": extract_predicted_lineup(lineups),
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
        "with_predicted_lineup": sum(1 for c in contexts if c.get("predicted_lineup", {}).get("available")),
        "with_ai_preview": sum(1 for c in contexts if c.get("ai_preview", {}).get("available")),
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



# ── API Coverage Scanner ─────────────────────────────────────────────────────
def _coverage_count(payload: Any) -> int:
    if payload is None:
        return 0
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        if isinstance(payload.get("count"), int):
            return int(payload.get("count") or 0)
        for key in ("results", "events", "data", "items", "leagues", "players", "teams", "standings", "fixtures", "value_bets", "picks"):
            value = payload.get(key)
            if isinstance(value, list):
                return len(value)
            if isinstance(value, dict):
                return len(value)
        # detail endpoints usually return one structured object without count/results
        return 1 if payload else 0
    return 0


def _coverage_shape(payload: Any) -> Dict[str, Any]:
    if payload is None:
        return {"type": "null", "keys": []}
    if isinstance(payload, list):
        sample = payload[0] if payload and isinstance(payload[0], dict) else None
        return {"type": "list", "keys": list(sample.keys())[:12] if sample else [], "sample_type": type(payload[0]).__name__ if payload else None}
    if isinstance(payload, dict):
        keys = list(payload.keys())[:18]
        sample_keys: List[str] = []
        for key in ("results", "events", "data", "items"):
            value = payload.get(key)
            if isinstance(value, list) and value and isinstance(value[0], dict):
                sample_keys = list(value[0].keys())[:12]
                break
        return {"type": "dict", "keys": keys, "sample_keys": sample_keys}
    return {"type": type(payload).__name__, "keys": []}


def _coverage_probe(name: str, url: str, params: Optional[Dict[str, Any]] = None, category: str = "other") -> Dict[str, Any]:
    params = {k: v for k, v in (params or {}).items() if v is not None}
    started = datetime.now(timezone.utc)
    entry: Dict[str, Any] = {
        "name": name,
        "category": category,
        "url": url,
        "params": params,
        "status": None,
        "ok": False,
        "count": 0,
        "shape": {"type": "unknown", "keys": []},
        "elapsed_ms": None,
        "note": "",
    }
    try:
        response = requests.get(url, headers=HEADERS, params=params or None, timeout=22)
        elapsed_ms = round((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        entry["status"] = response.status_code
        entry["elapsed_ms"] = elapsed_ms
        DEBUG["requests"].append({
            "label": f"api_coverage_{name}",
            "url": url,
            "params": params,
            "status": response.status_code,
            "attempt": 1,
            "elapsed_ms": elapsed_ms,
        })
        if response.status_code in (401, 403):
            entry["note"] = "auth_failed"
            return entry
        if response.status_code == 404:
            entry["note"] = "not_found"
            return entry
        if response.status_code >= 500:
            entry["note"] = "server_error"
            return entry
        response.raise_for_status()
        payload = response.json()
        count = _coverage_count(payload)
        entry.update({
            "ok": True,
            "count": count,
            "shape": _coverage_shape(payload),
            "note": "ok" if count else "ok_empty",
        })
        return entry
    except Exception as exc:
        elapsed_ms = round((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        entry["elapsed_ms"] = elapsed_ms
        entry["note"] = f"error: {str(exc)[:180]}"
        DEBUG["requests"].append({
            "label": f"api_coverage_{name}",
            "url": url,
            "params": params,
            "status": entry.get("status"),
            "attempt": 1,
            "elapsed_ms": elapsed_ms,
            "error": str(exc)[:180],
        })
        return entry


def _sample_ids_for_coverage() -> Dict[str, Any]:
    preds = _read_json_file("predictions.json", {"results": []})
    matches = _read_json_file("matches_today.json", {"results": []})
    contexts = _read_json_file("match_context.json", {"results": []})
    candidates: List[Dict[str, Any]] = []
    for p in preds.get("results", []) if isinstance(preds, dict) else []:
        ev = p.get("event") if isinstance(p, dict) else None
        if isinstance(ev, dict):
            candidates.append(ev)
    for m in matches.get("results", []) if isinstance(matches, dict) else []:
        if isinstance(m, dict):
            candidates.append(m.get("event") if isinstance(m.get("event"), dict) else m)
    for c in contexts.get("results", []) if isinstance(contexts, dict) else []:
        if isinstance(c, dict):
            candidates.append({
                "id": c.get("event_id"),
                "league_id": c.get("league_id"),
                "home_team_id": c.get("home_team_id"),
                "away_team_id": c.get("away_team_id"),
            })
    sample: Dict[str, Any] = {"event_id": None, "league_id": None, "team_id": None}
    for ev in candidates:
        if not isinstance(ev, dict):
            continue
        sample["event_id"] = sample["event_id"] or ev.get("id") or ev.get("event_id")
        sample["league_id"] = sample["league_id"] or ev.get("league_id")
        sample["team_id"] = sample["team_id"] or ev.get("home_team_id") or ev.get("away_team_id")
        if sample["event_id"] and sample["league_id"] and sample["team_id"]:
            break
    return sample


def fetch_api_coverage() -> None:
    print("\n🔎 API Coverage Scanner...")
    start_iso, end_iso = date_window(7)
    day = today_iso()
    sample = _sample_ids_for_coverage()
    event_id = sample.get("event_id")
    league_id = sample.get("league_id")
    team_id = sample.get("team_id")

    probes: List[Tuple[str, str, Dict[str, Any], str]] = [
        ("events", f"{BASE_V2}/events/", {"date_from": day, "date_to": day, "limit": 3}, "core"),
        ("events_live", f"{BASE_V2}/events/live/", {}, "core"),
        ("predictions", f"{BASE_V2}/predictions/", {"limit": 3}, "core"),
        ("odds_best_1x2", f"{BASE_V2}/odds/best/", {"date_from": start_iso, "date_to": end_iso, "market": "1x2", "limit": 3}, "core"),
        ("odds_best_ou25", f"{BASE_V2}/odds/best/", {"date_from": start_iso, "date_to": end_iso, "market": "over_under_25", "limit": 3}, "core"),
        ("leagues", f"{BASE_V2}/leagues/", {"limit": 5}, "reference"),
        ("teams", f"{BASE_V2}/teams/", {"limit": 5}, "reference"),
        ("players", f"{BASE_V2}/players/", {"limit": 5}, "reference"),
        ("referees", f"{BASE_V2}/referees/", {"limit": 5}, "reference"),
        ("venues", f"{BASE_V2}/venues/", {"limit": 5}, "reference"),
        ("managers", f"{BASE_V2}/managers/", {"limit": 5}, "reference"),
        ("broadcasts", f"{BASE_V2}/broadcasts/", {"limit": 5}, "reference"),
        ("tv_channels", f"{BASE_V2}/tv-channels/", {"limit": 5}, "reference"),
        ("social", f"{BASE_V2}/social/", {"limit": 5}, "reference"),
        ("value_bets_v2", f"{BASE_V2}/value-bets/", {"limit": 5}, "business"),
        ("odds_value", f"{BASE_V2}/odds/value/", {"limit": 5}, "business"),
    ]
    if event_id:
        probes.extend([
            ("event_detail", f"{BASE_V2}/events/{event_id}/", {}, "event_subresource"),
            ("event_odds_consensus", f"{BASE_V2}/events/{event_id}/odds/", {}, "odds"),
            ("event_odds_comparison", f"{BASE_V2}/events/{event_id}/odds/comparison/", {}, "odds"),
            ("event_prediction", f"{BASE_V2}/events/{event_id}/prediction/", {}, "ml_ai"),
            ("event_stats", f"{BASE_V2}/events/{event_id}/stats/", {}, "event_subresource"),
            ("event_incidents", f"{BASE_V2}/events/{event_id}/incidents/", {}, "event_subresource"),
            ("event_lineups", f"{BASE_V2}/events/{event_id}/lineups/", {}, "event_subresource"),
            ("event_player_stats", f"{BASE_V2}/events/{event_id}/player-stats/", {}, "event_subresource"),
            ("event_shotmap", f"{BASE_V2}/events/{event_id}/shotmap/", {}, "event_subresource"),
        ])
    if league_id:
        probes.append(("league_standings", f"{BASE_V2}/leagues/{league_id}/standings/", {}, "reference"))
    if team_id:
        probes.extend([
            ("team_detail", f"{BASE_V2}/teams/{team_id}/", {}, "team_subresource"),
            ("team_squad", f"{BASE_V2}/teams/{team_id}/squad/", {}, "team_subresource"),
            ("team_fixtures", f"{BASE_V2}/teams/{team_id}/fixtures/", {"limit": 5}, "team_subresource"),
        ])

    results = [_coverage_probe(name, url, params, category) for name, url, params, category in probes]
    summary = {
        "total": len(results),
        "ok": sum(1 for r in results if r.get("ok") and r.get("count", 0) > 0),
        "ok_empty": sum(1 for r in results if r.get("ok") and r.get("count", 0) == 0),
        "not_found": sum(1 for r in results if r.get("status") == 404),
        "auth_failed": sum(1 for r in results if r.get("status") in (401, 403)),
        "errors": sum(1 for r in results if not r.get("ok") and r.get("status") not in (401, 403, 404)),
    }
    by_category: Dict[str, Dict[str, int]] = {}
    for r in results:
        cat = r.get("category") or "other"
        bucket = by_category.setdefault(cat, {"total": 0, "ok": 0, "empty": 0, "not_found": 0, "errors": 0})
        bucket["total"] += 1
        if r.get("ok") and r.get("count", 0) > 0:
            bucket["ok"] += 1
        elif r.get("ok"):
            bucket["empty"] += 1
        elif r.get("status") == 404:
            bucket["not_found"] += 1
        else:
            bucket["errors"] += 1

    integrated = {
        "predictions": True,
        "events": True,
        "events_live": True,
        "odds_best_1x2": True,
        "odds_best_ou25": True,
        "event_detail": True,
        "event_stats": True,
        "event_lineups": True,
        "event_player_stats": True,
        "league_standings": True,
        "event_incidents": True,
        "event_shotmap": True,
        "event_prediction": True,
        "teams": True,
        "players": True,
        "referees": True,
        "venues": True,
        "managers": True,
        "broadcasts": True,
        "tv_channels": True,
        "social": False,
        "value_bets_v2": False,
        "odds_value": False,
    }
    opportunities = []
    blockers = []
    for r in results:
        name = r.get("name")
        if r.get("ok") and r.get("count", 0) > 0 and integrated.get(name) is False:
            opportunities.append(name)
        if r.get("status") == 404:
            blockers.append(name)

    report = {
        "updated_at": now_iso(),
        "source": "api_coverage_scanner_v1",
        "base_url": BASE_V2,
        "sample": sample,
        "summary": summary,
        "by_category": by_category,
        "results": results,
        "opportunities": opportunities,
        "blockers_404": blockers,
        "websocket_note": "WebSocket live trebuie integrat separat în frontend/backend; nu este evaluat prin HTTP GET static.",
        "next_actions": [
            "Integrează doar endpointurile cu status 200 și count > 0.",
            "Pentru endpointurile 404, nu adăuga cod UI până nu există path confirmat în docs sau OpenAPI.",
            "Separă Live WebSocket de fetch_daily, fiind flux push, nu batch static.",
        ],
    }
    print(f"  coverage: {summary['ok']} ok, {summary['ok_empty']} empty, {summary['not_found']} 404, {summary['errors']} errors")
    save("api_coverage_report.json", report, protect_empty=False, job_name="api_coverage")
    save_debug("api_coverage_report.json", report)
    save_debug("api_coverage_debug.json", {"updated_at": now_iso(), "summary": summary, "opportunities": opportunities, "blockers_404": blockers})


# ── Main ─────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# [12/12] TEAM INTELLIGENCE — profil echipă, lot și fixtures
# ─────────────────────────────────────────────────────────────────────────────
def seed_priority_teams(limit: int = 18) -> List[Dict[str, Any]]:
    """Alege echipe prioritare din context, value bets, signals și predicții.

    Nu indexăm toate cele ~1900 echipe la fiecare workflow. Pentru GitHub Actions
    este mai sigur să cache-uim echipele care apar în semnale și meciuri relevante.
    """
    teams: Dict[str, Dict[str, Any]] = {}

    def add(team_id: Any, name: Any, side: str, source: str, score: float = 1.0, event_id: Any = None) -> None:
        if not team_id:
            return
        key = str(team_id)
        row = teams.setdefault(key, {
            "team_id": int(team_id) if str(team_id).isdigit() else team_id,
            "name": name or f"Team {team_id}",
            "sources": [],
            "event_ids": [],
            "priority_score": 0.0,
            "sides": [],
        })
        if source not in row["sources"]:
            row["sources"].append(source)
        if side and side not in row["sides"]:
            row["sides"].append(side)
        if event_id and event_id not in row["event_ids"]:
            row["event_ids"].append(event_id)
        row["priority_score"] += float(score or 0)
        if name and (not row.get("name") or str(row.get("name")).startswith("Team ")):
            row["name"] = name

    # Cele mai importante: echipele din contextul deja prioritar.
    ctx = _read_json_file("match_context.json", {"results": []})
    for i, c in enumerate(ctx.get("results", [])[:36]):
        score = max(1.0, float(c.get("priority_score") or 0) / 10.0) + max(0, 20 - i) / 10.0
        add(c.get("home_team_id"), c.get("home_team"), "home", "match_context", score, c.get("event_id"))
        add(c.get("away_team_id"), c.get("away_team"), "away", "match_context", score, c.get("event_id"))

    vb = _read_json_file("value_bets.json", {"results": []})
    for i, v in enumerate(vb.get("results", [])[:30]):
        score = 8.0 + max(0, 20 - i) / 5.0
        add(v.get("home_team_id"), v.get("home_team"), "home", "value_bets", score, v.get("event_id"))
        add(v.get("away_team_id"), v.get("away_team"), "away", "value_bets", score, v.get("event_id"))

    sigs = _read_json_file("signals.json", {"signals": []})
    for i, s in enumerate(sigs.get("signals", [])[:40]):
        score = 5.0 + max(0, 25 - i) / 8.0
        add(s.get("home_team_id"), s.get("home_team"), "home", "signals", score, s.get("event_id"))
        add(s.get("away_team_id"), s.get("away_team"), "away", "signals", score, s.get("event_id"))

    preds = _read_json_file("predictions.json", {"results": []})
    for i, p in enumerate(sorted(preds.get("results", []), key=lambda x: x.get("smartbet_score") or 0, reverse=True)[:30]):
        ev = p.get("event") or {}
        score = max(1.0, float(p.get("smartbet_score") or 0) / 25.0)
        add(ev.get("home_team_id"), ev.get("home_team"), "home", "predictions", score, ev.get("id"))
        add(ev.get("away_team_id"), ev.get("away_team"), "away", "predictions", score, ev.get("id"))

    out = sorted(teams.values(), key=lambda x: x.get("priority_score") or 0, reverse=True)
    for row in out:
        row["priority_score"] = round(float(row.get("priority_score") or 0), 2)
        row["event_ids"] = row.get("event_ids", [])[:10]
    return out[:limit]


def fetch_team_intelligence() -> None:
    print("\n[12/13] Team Intelligence BSD v2...")
    limit = int(os.environ.get("BETPREDICT_TEAM_LIMIT", "18") or 18)
    seeds = seed_priority_teams(limit)
    profiles: List[Dict[str, Any]] = []
    squads: List[Dict[str, Any]] = []
    fixtures: List[Dict[str, Any]] = []
    combined: List[Dict[str, Any]] = []
    reports: List[Dict[str, Any]] = []

    # Hard safety: oprește iterații noi dacă pipeline-ul depășește 9 min total.
    # Lasă timp pentru context_intelligence + form_h2h + broadcasts/BSD preds.
    _team_intel_budget_sec = 9 * 60
    for seed in seeds:
        if _pipeline_over_budget(_team_intel_budget_sec):
            print(f"  [skip] team_intelligence: pipeline elapsed {_pipeline_elapsed_sec():.0f}s > {_team_intel_budget_sec}s, opresc iterații noi")
            break
        team_id = seed.get("team_id")
        if not team_id:
            continue
        print(f"  → team {team_id}: {seed.get('name','—')}")
        profile = get(f"{BASE_V2}/teams/{team_id}/", label="team_detail") or {}
        squad = get(f"{BASE_V2}/teams/{team_id}/squad/", label="team_squad") or {}
        fixture_payload = get(f"{BASE_V2}/teams/{team_id}/fixtures/", {"limit": 10}, label="team_fixtures") or {}

        squad_players = []
        if isinstance(squad, dict):
            squad_players = squad.get("players") or squad.get("results") or []
        elif isinstance(squad, list):
            squad_players = squad
        if isinstance(squad_players, list):
            squad_players = [decorate_player_image(x) for x in squad_players if isinstance(x, dict)]
        fixture_rows = extract_results(fixture_payload)

        profile_row = {
            "team_id": team_id,
            "seed": seed,
            "profile": profile if isinstance(profile, dict) else {},
            "name": (profile or {}).get("name") if isinstance(profile, dict) else seed.get("name"),
            "short_name": (profile or {}).get("short_name") if isinstance(profile, dict) else None,
            "country": (profile or {}).get("country") if isinstance(profile, dict) else None,
            "venue_id": (profile or {}).get("venue_id") if isinstance(profile, dict) else None,
            "logo_url": logo_url("team", team_id),
        }
        squad_row = {
            "team_id": team_id,
            "name": profile_row.get("name") or seed.get("name"),
            "count": len(squad_players) if isinstance(squad_players, list) else compact_count(squad),
            "players": squad_players[:40] if isinstance(squad_players, list) else [],
        }
        fixtures_row = {
            "team_id": team_id,
            "name": profile_row.get("name") or seed.get("name"),
            "count": len(fixture_rows),
            "results": fixture_rows[:10],
        }
        combined_row = {
            "team_id": team_id,
            "name": profile_row.get("name") or seed.get("name"),
            "short_name": profile_row.get("short_name"),
            "country": profile_row.get("country"),
            "venue_id": profile_row.get("venue_id"),
            "logo_url": profile_row.get("logo_url"),
            "priority_score": seed.get("priority_score"),
            "sources": seed.get("sources", []),
            "event_ids": seed.get("event_ids", []),
            "profile": profile_row.get("profile") or {},
            "squad_count": squad_row["count"],
            "squad_preview": squad_row["players"][:12],
            "fixtures_count": fixtures_row["count"],
            "fixtures_preview": fixtures_row["results"][:6],
        }
        profiles.append(profile_row)
        squads.append(squad_row)
        fixtures.append(fixtures_row)
        combined.append(combined_row)
        reports.append({
            "team_id": team_id,
            "name": combined_row["name"],
            "profile_count": compact_count(profile),
            "squad_count": squad_row["count"],
            "fixtures_count": fixtures_row["count"],
            "sources": seed.get("sources", []),
        })

    summary = {
        "teams_requested": len(seeds),
        "teams_saved": len(combined),
        "with_profile": sum(1 for r in reports if r.get("profile_count", 0) > 0),
        "with_squad": sum(1 for r in reports if r.get("squad_count", 0) > 0),
        "with_fixtures": sum(1 for r in reports if r.get("fixtures_count", 0) > 0),
    }
    payload = {"updated_at": now_iso(), "source": "team_intelligence_v1", "count": len(combined), "summary": summary, "results": combined}
    save("team_intelligence.json", payload, protect_empty=True, job_name="team_intelligence")
    save("team_profiles.json", {"updated_at": now_iso(), "source": "team_profiles_v1", "count": len(profiles), "results": profiles}, protect_empty=True, job_name="team_profiles")
    save("team_squads.json", {"updated_at": now_iso(), "source": "team_squads_v1", "count": len(squads), "results": squads}, protect_empty=True, job_name="team_squads")
    save("team_fixtures.json", {"updated_at": now_iso(), "source": "team_fixtures_v1", "count": len(fixtures), "results": fixtures}, protect_empty=True, job_name="team_fixtures")
    save_debug("team_intelligence_debug.json", {"updated_at": now_iso(), "limit": limit, "summary": summary, "reports": reports})


# ─────────────────────────────────────────────────────────────────────────────
# [13/13] REFEREE + VENUE + MANAGER INTELLIGENCE
# ─────────────────────────────────────────────────────────────────────────────
def _entity_name(payload: Any, fallback: str = "—") -> str:
    if isinstance(payload, dict):
        return str(payload.get("name") or payload.get("short_name") or fallback)
    return fallback


def seed_context_entities(limit: int = 18) -> List[Dict[str, Any]]:
    """Extrage arbitri, stadioane și manageri din match_context.

    Contextul de meci conține deja event detail; aici nu ghicim, ci pornim din
    meciurile prioritare care au trecut prin filtrele Value/Signals/Predictions.
    """
    ctx = _read_json_file("match_context.json", {"results": []})
    rows: List[Dict[str, Any]] = []
    for c in (ctx.get("results") or [])[:limit] if isinstance(ctx, dict) else []:
        if not isinstance(c, dict):
            continue
        d = c.get("detail") if isinstance(c.get("detail"), dict) else {}
        event_id = c.get("event_id") or d.get("id")
        if not event_id:
            continue
        rows.append({
            "event_id": event_id,
            "home_team": c.get("home_team") or d.get("home_team"),
            "away_team": c.get("away_team") or d.get("away_team"),
            "home_team_id": c.get("home_team_id") or d.get("home_team_id"),
            "away_team_id": c.get("away_team_id") or d.get("away_team_id"),
            "league": c.get("league") or d.get("league_name"),
            "league_id": c.get("league_id") or d.get("league_id"),
            "event_date": c.get("event_date") or d.get("event_date"),
            "priority_score": c.get("priority_score") or 0,
            "referee_id": d.get("referee_id") or c.get("referee_id"),
            "venue_id": d.get("venue_id") or c.get("venue_id"),
            "home_manager_id": d.get("home_coach_id") or d.get("home_manager_id") or c.get("home_coach_id"),
            "away_manager_id": d.get("away_coach_id") or d.get("away_manager_id") or c.get("away_coach_id"),
        })
    rows.sort(key=lambda x: float(x.get("priority_score") or 0), reverse=True)
    return rows[:limit]


def profile_cache_get(cache: Dict[str, Any], entity_type: str, entity_id: Any, url: str) -> Dict[str, Any]:
    if not entity_id:
        return {}
    key = str(entity_id)
    if key not in cache:
        payload = get(url, label=f"{entity_type}_{entity_id}") or {}
        cache[key] = payload if isinstance(payload, dict) else {}
    return cache[key]


def referee_risk(ref: Dict[str, Any]) -> Dict[str, Any]:
    yellow = as_float(ref.get("avg_yellow_per_match"), 0) or 0
    red = as_float(ref.get("avg_red_per_match"), 0) or 0
    fouls = as_float(ref.get("avg_fouls_per_match"), 0) or 0
    goals = as_float(ref.get("avg_goals_per_match"), 0) or 0
    cards_score = min(100, yellow * 14 + red * 35)
    tempo_score = min(100, fouls * 2 + goals * 8)
    if cards_score >= 70:
        label = "strict / cards risk"
    elif cards_score >= 45:
        label = "mediu cards"
    else:
        label = "low cards"
    return {
        "avg_yellow_per_match": round(yellow, 2),
        "avg_red_per_match": round(red, 2),
        "avg_fouls_per_match": round(fouls, 2),
        "avg_goals_per_match": round(goals, 2),
        "cards_risk_score": round(cards_score, 1),
        "tempo_score": round(tempo_score, 1),
        "label": label,
    }


def manager_summary(mgr: Dict[str, Any]) -> Dict[str, Any]:
    matches = as_float(mgr.get("matches_total"), 0) or 0
    win_pct = as_float(mgr.get("win_pct"), None)
    if win_pct is None and matches:
        wins = as_float(mgr.get("wins"), 0) or 0
        win_pct = wins / matches * 100
    mid = mgr.get("id") or mgr.get("manager_id")
    return {
        "id": mid,
        "name": mgr.get("name") or mgr.get("short_name"),
        "country": mgr.get("country"),
        "tactical_profile": mgr.get("tactical_profile"),
        "preferred_formation": mgr.get("preferred_formation"),
        "matches_total": int(matches) if matches else 0,
        "win_pct": round(win_pct, 1) if win_pct is not None else None,
        "photo_url": logo_url("manager", mid),
    }


def venue_summary(venue: Dict[str, Any]) -> Dict[str, Any]:
    vid = venue.get("id") or venue.get("venue_id")
    return {
        "id": vid,
        "name": venue.get("name"),
        "city": venue.get("city"),
        "country": venue.get("country"),
        "capacity": venue.get("capacity"),
        "pitch_length_m": venue.get("pitch_length_m"),
        "pitch_width_m": venue.get("pitch_width_m"),
        "built_year": venue.get("built_year"),
        "home_team_id": venue.get("home_team_id"),
        "photo_url": logo_url("venue", vid),
    }


def fetch_context_intelligence() -> None:
    print("\n[13/13] Referee + Venue + Manager Intelligence BSD v2...")
    limit = int(os.environ.get("BETPREDICT_CONTEXT_INTEL_LIMIT", "18") or 18)
    seeds = seed_context_entities(limit)
    ref_cache: Dict[str, Dict[str, Any]] = {}
    venue_cache: Dict[str, Dict[str, Any]] = {}
    manager_cache: Dict[str, Dict[str, Any]] = {}
    combined: List[Dict[str, Any]] = []
    reports: List[Dict[str, Any]] = []

    # Hard safety: oprește iterații noi dacă pipeline-ul depășește 13 min total.
    _ctx_intel_budget_sec = 13 * 60
    for seed in seeds:
        if _pipeline_over_budget(_ctx_intel_budget_sec):
            print(f"  [skip] context_intelligence: pipeline elapsed {_pipeline_elapsed_sec():.0f}s > {_ctx_intel_budget_sec}s, opresc iterații noi")
            break
        event_id = seed.get("event_id")
        print(f"  → context intel event {event_id}: {seed.get('home_team','—')} vs {seed.get('away_team','—')}")
        rid = seed.get("referee_id")
        vid = seed.get("venue_id")
        hm_id = seed.get("home_manager_id")
        am_id = seed.get("away_manager_id")

        referee = profile_cache_get(ref_cache, "referee", rid, f"{BASE_V2}/referees/{rid}/") if rid else {}
        venue = profile_cache_get(venue_cache, "venue", vid, f"{BASE_V2}/venues/{vid}/") if vid else {}
        home_mgr = profile_cache_get(manager_cache, "manager", hm_id, f"{BASE_V2}/managers/{hm_id}/") if hm_id else {}
        away_mgr = profile_cache_get(manager_cache, "manager", am_id, f"{BASE_V2}/managers/{am_id}/") if am_id else {}

        row = {
            "event_id": event_id,
            "home_team": seed.get("home_team"),
            "away_team": seed.get("away_team"),
            "home_team_id": seed.get("home_team_id"),
            "away_team_id": seed.get("away_team_id"),
            "league": seed.get("league"),
            "league_id": seed.get("league_id"),
            "event_date": seed.get("event_date"),
            "priority_score": seed.get("priority_score"),
            "referee_id": rid,
            "venue_id": vid,
            "home_manager_id": hm_id,
            "away_manager_id": am_id,
            "referee": referee,
            "referee_name": _entity_name(referee, "—") if referee else None,
            "referee_risk": referee_risk(referee) if referee else {},
            "venue": venue,
            "venue_summary": venue_summary(venue) if venue else {},
            "home_manager": home_mgr,
            "away_manager": away_mgr,
            "home_manager_summary": manager_summary(home_mgr) if home_mgr else {},
            "away_manager_summary": manager_summary(away_mgr) if away_mgr else {},
        }
        row["coverage_score"] = sum(1 for k in ("referee", "venue", "home_manager", "away_manager") if row.get(k))
        combined.append(row)
        reports.append({
            "event_id": event_id,
            "referee_id": rid,
            "venue_id": vid,
            "home_manager_id": hm_id,
            "away_manager_id": am_id,
            "referee_count": compact_count(referee),
            "venue_count": compact_count(venue),
            "home_manager_count": compact_count(home_mgr),
            "away_manager_count": compact_count(away_mgr),
            "coverage_score": row["coverage_score"],
        })

    referee_profiles = [{"id": k, **v, "risk": referee_risk(v)} for k, v in ref_cache.items() if v]
    venue_profiles = [{"id": k, **v} for k, v in venue_cache.items() if v]
    manager_profiles = [{"id": k, **v, "summary": manager_summary(v)} for k, v in manager_cache.items() if v]
    summary = {
        "events_requested": len(seeds),
        "events_saved": len(combined),
        "with_referee": sum(1 for r in combined if r.get("referee")),
        "with_venue": sum(1 for r in combined if r.get("venue")),
        "with_home_manager": sum(1 for r in combined if r.get("home_manager")),
        "with_away_manager": sum(1 for r in combined if r.get("away_manager")),
        "referees_cached": len(referee_profiles),
        "venues_cached": len(venue_profiles),
        "managers_cached": len(manager_profiles),
    }
    save("context_intelligence.json", {"updated_at": now_iso(), "source": "context_intelligence_v1", "count": len(combined), "summary": summary, "results": combined}, protect_empty=True, job_name="context_intelligence")
    save("referee_profiles.json", {"updated_at": now_iso(), "source": "referee_profiles_v1", "count": len(referee_profiles), "results": referee_profiles}, protect_empty=False, job_name="referee_profiles")
    save("venue_profiles.json", {"updated_at": now_iso(), "source": "venue_profiles_v1", "count": len(venue_profiles), "results": venue_profiles}, protect_empty=False, job_name="venue_profiles")
    save("manager_profiles.json", {"updated_at": now_iso(), "source": "manager_profiles_v1", "count": len(manager_profiles), "results": manager_profiles}, protect_empty=False, job_name="manager_profiles")
    save_debug("context_intelligence_debug.json", {"updated_at": now_iso(), "limit": limit, "summary": summary, "reports": reports})




# ─────────────────────────────────────────────────────────────────────────────
# [14/15] FORM + H2H + xG — formă echipe, directe și panou xG/xA
# ─────────────────────────────────────────────────────────────────────────────
def _event_id(ev: Dict[str, Any]) -> Optional[Any]:
    return ev.get("event_id") or ev.get("id")


def _event_date_sort(ev: Dict[str, Any]) -> str:
    return str(ev.get("event_date") or ev.get("date") or ev.get("start_time") or "")


def _team_ids_from_event(ev: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    return (
        int(ev.get("home_team_id")) if ev.get("home_team_id") is not None else None,
        int(ev.get("away_team_id")) if ev.get("away_team_id") is not None else None,
    )


def _team_name_from_event(ev: Dict[str, Any], team_id: Any) -> str:
    try:
        tid = int(team_id)
    except Exception:
        return "—"
    hid, aid = _team_ids_from_event(ev)
    if tid == hid:
        return str(ev.get("home_team") or "—")
    if tid == aid:
        return str(ev.get("away_team") or "—")
    return "—"


def _result_for_team(ev: Dict[str, Any], team_id: Any) -> Optional[str]:
    hs, aw = _event_scores(ev)
    if hs is None or aw is None:
        return None
    try:
        tid = int(team_id)
    except Exception:
        return None
    hid, aid = _team_ids_from_event(ev)
    if tid == hid:
        gf, ga = hs, aw
    elif tid == aid:
        gf, ga = aw, hs
    else:
        return None
    if gf > ga:
        return "W"
    if gf < ga:
        return "L"
    return "D"


def _goals_for_team(ev: Dict[str, Any], team_id: Any) -> Tuple[Optional[int], Optional[int]]:
    hs, aw = _event_scores(ev)
    if hs is None or aw is None:
        return None, None
    try:
        tid = int(team_id)
    except Exception:
        return None, None
    hid, aid = _team_ids_from_event(ev)
    if tid == hid:
        return hs, aw
    if tid == aid:
        return aw, hs
    return None, None


def _is_team_event(ev: Dict[str, Any], team_id: Any) -> bool:
    try:
        tid = int(team_id)
    except Exception:
        return False
    hid, aid = _team_ids_from_event(ev)
    return tid == hid or tid == aid


def _is_pair_event(ev: Dict[str, Any], home_id: Any, away_id: Any) -> bool:
    try:
        a, b = int(home_id), int(away_id)
    except Exception:
        return False
    hid, aid = _team_ids_from_event(ev)
    return {hid, aid} == {a, b}


def _score_label(ev: Dict[str, Any]) -> str:
    hs, aw = _event_scores(ev)
    return f"{hs}-{aw}" if hs is not None and aw is not None else "—"


def _short_result_row(ev: Dict[str, Any], team_id: Any = None) -> Dict[str, Any]:
    row = {
        "event_id": _event_id(ev),
        "event_date": ev.get("event_date"),
        "league_id": ev.get("league_id"),
        "league": ev.get("league_name") or LEAGUES.get(int(ev.get("league_id") or 0), ""),
        "home_team_id": ev.get("home_team_id"),
        "away_team_id": ev.get("away_team_id"),
        "home_team": ev.get("home_team"),
        "away_team": ev.get("away_team"),
        "score": _score_label(ev),
        "status": ev.get("status"),
    }
    if team_id is not None:
        gf, ga = _goals_for_team(ev, team_id)
        row.update({"result": _result_for_team(ev, team_id), "gf": gf, "ga": ga})
    return row


def _form_summary(team_id: Any, events: List[Dict[str, Any]], limit: int = 5) -> Dict[str, Any]:
    team_events = [ev for ev in events if _is_team_event(ev, team_id) and _is_settled(ev)]
    team_events.sort(key=_event_date_sort, reverse=True)
    last = team_events[:limit]
    form = "".join((_result_for_team(ev, team_id) or "?") for ev in last)
    wins = form.count("W")
    draws = form.count("D")
    losses = form.count("L")
    gf = ga = over15 = over25 = btts = 0
    for ev in last:
        f, a = _goals_for_team(ev, team_id)
        if f is None or a is None:
            continue
        gf += f; ga += a
        total = f + a
        if total >= 2: over15 += 1
        if total >= 3: over25 += 1
        if f > 0 and a > 0: btts += 1
    n = len(last)
    return {
        "team_id": team_id,
        "team_name": _team_name_from_event(last[0], team_id) if last else None,
        "sample": n,
        "form": form or "—",
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "gf": gf,
        "ga": ga,
        "avg_gf": round(gf / n, 2) if n else None,
        "avg_ga": round(ga / n, 2) if n else None,
        "over15_pct": round(over15 * 100 / n, 1) if n else None,
        "over25_pct": round(over25 * 100 / n, 1) if n else None,
        "btts_pct": round(btts * 100 / n, 1) if n else None,
        "last_results": [_short_result_row(ev, team_id) for ev in last],
    }


def _h2h_summary(home_id: Any, away_id: Any, events: List[Dict[str, Any]], limit: int = 10) -> Dict[str, Any]:
    pair_events = [ev for ev in events if _is_pair_event(ev, home_id, away_id) and _is_settled(ev)]
    pair_events.sort(key=_event_date_sort, reverse=True)
    last = pair_events[:limit]
    home_w = away_w = draws = goals = over15 = over25 = btts = 0
    for ev in last:
        hs, aw = _event_scores(ev)
        if hs is None or aw is None:
            continue
        hid, aid = _team_ids_from_event(ev)
        if hs == aw:
            draws += 1
        elif int(home_id) == hid and hs > aw:
            home_w += 1
        elif int(home_id) == aid and aw > hs:
            home_w += 1
        else:
            away_w += 1
        total = hs + aw
        goals += total
        if total >= 2: over15 += 1
        if total >= 3: over25 += 1
        if hs > 0 and aw > 0: btts += 1
    n = len(last)
    return {
        "sample": n,
        "home_wins": home_w,
        "away_wins": away_w,
        "draws": draws,
        "avg_goals": round(goals / n, 2) if n else None,
        "over15_pct": round(over15 * 100 / n, 1) if n else None,
        "over25_pct": round(over25 * 100 / n, 1) if n else None,
        "btts_pct": round(btts * 100 / n, 1) if n else None,
        "matches": [_short_result_row(ev) for ev in last],
    }


def _priority_events_for_form(limit: int = 24) -> List[Dict[str, Any]]:
    by_id: Dict[str, Dict[str, Any]] = {}

    def add(eid: Any, row: Dict[str, Any], score: float = 0) -> None:
        if not eid:
            return
        k = str(eid)
        item = dict(by_id.get(k, {}))
        item.update({kk: vv for kk, vv in row.items() if vv is not None})
        item["event_id"] = eid
        item["priority_score"] = max(as_float(item.get("priority_score"), 0) or 0, score)
        by_id[k] = item

    signals = _read_json_file("signals.json", {"signals": []}).get("signals", [])
    for s in signals[:80]:
        add(s.get("event_id"), s, as_float(s.get("smartbet_score"), 0) or 0)
    value = _read_json_file("value_bets.json", {"results": []}).get("results", [])
    for v in value[:80]:
        add(v.get("event_id"), v, as_float(v.get("confidence"), 0) or 0)
    ctx = _read_json_file("match_context.json", {"results": []}).get("results", [])
    for c in ctx[:80]:
        add(c.get("event_id"), c, as_float(c.get("priority_score"), 0) or 0)
    preds = _read_json_file("predictions.json", {"results": []}).get("results", [])
    for p in preds[:120]:
        ev = p.get("event") or {}
        row = {
            "event_id": ev.get("id") or p.get("event_id"),
            "home_team": ev.get("home_team"),
            "away_team": ev.get("away_team"),
            "home_team_id": ev.get("home_team_id"),
            "away_team_id": ev.get("away_team_id"),
            "league_id": ev.get("league_id") or p.get("_league_id"),
            "league": ev.get("league_name") or p.get("_league_name"),
            "event_date": ev.get("event_date"),
        }
        add(row.get("event_id"), row, as_float(p.get("smartbet_score"), 0) or 0)
    rows = list(by_id.values())
    rows.sort(key=lambda r: (as_float(r.get("priority_score"), 0) or 0), reverse=True)
    return rows[:limit]


def _fetch_team_history(team_ids: Iterable[Any], league_ids: Iterable[Any], days_back: int) -> List[Dict[str, Any]]:
    end = datetime.now(timezone.utc) + timedelta(hours=4)
    start = end - timedelta(days=days_back)
    date_from, date_to = _date_only_utc(start), _date_only_utc(end)
    all_events: Dict[str, Dict[str, Any]] = {}
    team_ids_clean = [int(t) for t in team_ids if t]

    # Pornim de la cache-ul recent existent.
    recent = _read_json_file("recent_results.json", {"results": []}).get("results", [])
    for ev in recent:
        eid = _event_id(ev)
        if eid:
            all_events[str(eid)] = ev

    # Încercăm istoric pe echipă. Dacă API-ul ignoră team_id, filtrăm client-side.
    max_teams = int(os.environ.get("BETPREDICT_FORM_TEAM_LIMIT", "18") or 18)
    # Hard safety: oprește dacă pipeline-ul depășește 15 min total.
    _form_budget_sec = 15 * 60
    for tid in team_ids_clean[:max_teams]:
        if _pipeline_over_budget(_form_budget_sec):
            print(f"  [skip] form_team_history: pipeline elapsed {_pipeline_elapsed_sec():.0f}s > {_form_budget_sec}s, opresc iterații noi")
            break
        items = get_all_pages(
            f"{BASE_V2}/events/",
            {"team_id": tid, "date_from": date_from, "date_to": date_to, "limit": 100},
            max_pages=2,
            label=f"form_team_{tid}",
        )
        kept = 0
        for ev in items:
            if not _is_team_event(ev, tid) or not _is_settled(ev):
                continue
            eid = _event_id(ev)
            if eid:
                ev["_results_source"] = f"team_{tid}"
                all_events[str(eid)] = ev
                kept += 1
        if kept == 0:
            warn("Nu am găsit istoric filtrat pe team_id", team_id=tid)

    # Fallback pe ligi prioritare, pentru H2H unde team_id poate să nu fie suportat.
    for lid in [int(x) for x in league_ids if x][:8]:
        if _pipeline_over_budget(_form_budget_sec):
            print(f"  [skip] form_league_history: pipeline elapsed {_pipeline_elapsed_sec():.0f}s > {_form_budget_sec}s, opresc iterații noi")
            break
        items = get_all_pages(
            f"{BASE_V2}/events/",
            {"league_id": lid, "date_from": date_from, "date_to": date_to, "limit": 200},
            max_pages=2,
            label=f"form_league_{lid}",
        )
        for ev in items:
            if not _is_settled(ev):
                continue
            hid, aid = _team_ids_from_event(ev)
            if hid in team_ids_clean or aid in team_ids_clean:
                eid = _event_id(ev)
                if eid:
                    ev["_results_source"] = f"league_{lid}"
                    all_events[str(eid)] = ev

    return list(all_events.values())


def _prediction_xg_index() -> Dict[str, Dict[str, Any]]:
    idx: Dict[str, Dict[str, Any]] = {}
    preds = _read_json_file("predictions.json", {"results": []}).get("results", [])
    for p in preds:
        ev = p.get("event") or {}
        eid = ev.get("id") or p.get("event_id")
        if not eid:
            continue
        markets = p.get("markets") or {}
        ex = markets.get("expected_goals") or {}
        hx = as_float(p.get("predicted_home_goals") or ex.get("home"))
        ax = as_float(p.get("predicted_away_goals") or ex.get("away"))
        if hx is None and ax is None:
            continue
        idx[str(eid)] = {
            "event_id": eid,
            "xg_home": round(hx, 2) if hx is not None else None,
            "xg_away": round(ax, 2) if ax is not None else None,
            "xg_total": round((hx or 0) + (ax or 0), 2) if hx is not None or ax is not None else None,
            "source": "predictions.expected_goals",
        }
    return idx


def _signal_xg_index() -> Dict[str, Dict[str, Any]]:
    idx: Dict[str, Dict[str, Any]] = {}
    for s in _read_json_file("signals.json", {"signals": []}).get("signals", []):
        eid = s.get("event_id")
        hx, ax = as_float(s.get("xg_home")), as_float(s.get("xg_away"))
        if not eid or (hx is None and ax is None):
            continue
        idx[str(eid)] = {
            "event_id": eid,
            "xg_home": round(hx, 2) if hx is not None else None,
            "xg_away": round(ax, 2) if ax is not None else None,
            "xg_total": round((hx or 0) + (ax or 0), 2) if hx is not None or ax is not None else None,
            "source": "signals.poisson_xg",
        }
    return idx


def _actual_xg_from_context(ctx: Dict[str, Any]) -> Dict[str, Any]:
    st = ctx.get("stats") or {}
    stats = st.get("stats") if isinstance(st, dict) else {}
    if not isinstance(stats, dict):
        return {}
    home = stats.get("home") or {}
    away = stats.get("away") or {}
    hx = home.get("xg")
    ax = away.get("xg")
    if isinstance(hx, dict): hx = hx.get("actual")
    if isinstance(ax, dict): ax = ax.get("actual")
    hx, ax = as_float(hx), as_float(ax)
    if hx is None and ax is None:
        return {}
    return {
        "actual_xg_home": round(hx, 2) if hx is not None else None,
        "actual_xg_away": round(ax, 2) if ax is not None else None,
        "actual_xg_total": round((hx or 0) + (ax or 0), 2) if hx is not None or ax is not None else None,
        "actual_source": "events/{id}/stats",
    }


def _extract_xa_summary(player_stats: Any) -> Dict[str, Any]:
    """Caută xA/expected_assists în schema player-stats fără să presupună un format fix."""
    players: List[Dict[str, Any]] = []
    if isinstance(player_stats, dict):
        for key in ("player_stats", "results", "players", "stats"):
            val = player_stats.get(key)
            if isinstance(val, list):
                players.extend([x for x in val if isinstance(x, dict)])
        # Uneori e dict pe home/away.
        for side in ("home", "away"):
            val = player_stats.get(side)
            if isinstance(val, list):
                players.extend([x for x in val if isinstance(x, dict)])
            elif isinstance(val, dict):
                for k in ("players", "player_stats", "results"):
                    if isinstance(val.get(k), list):
                        players.extend([x for x in val[k] if isinstance(x, dict)])
    elif isinstance(player_stats, list):
        players = [x for x in player_stats if isinstance(x, dict)]

    xa_keys = ("xa", "xA", "expected_assists", "expected_assist", "x_assists")
    xg_keys = ("xg", "xG", "expected_goals")
    xa_values = []
    xg_values = []
    for p in players:
        for k in xa_keys:
            v = as_float(p.get(k))
            if v is not None:
                xa_values.append(v)
                break
        for k in xg_keys:
            v = as_float(p.get(k))
            if v is not None:
                xg_values.append(v)
                break
    return {
        "player_stats_count": len(players),
        "xa_available": bool(xa_values),
        "xa_total": round(sum(xa_values), 2) if xa_values else None,
        "xg_player_total": round(sum(xg_values), 2) if xg_values else None,
        "note": "xA disponibil în player-stats" if xa_values else "xA indisponibil în schema player-stats curentă",
    }


def fetch_form_h2h_xg_context() -> None:
    print("\n[14/15] Form + H2H + xG Context...")
    priority_events = _priority_events_for_form(limit=int(os.environ.get("BETPREDICT_FORM_EVENT_LIMIT", "24") or 24))
    team_ids = []
    league_ids = []
    for ev in priority_events:
        for tid in (ev.get("home_team_id"), ev.get("away_team_id")):
            if tid and int(tid) not in team_ids:
                team_ids.append(int(tid))
        lid = ev.get("league_id")
        if lid and int(lid) not in league_ids:
            league_ids.append(int(lid))

    days_back = int(os.environ.get("BETPREDICT_FORM_DAYS", "730") or 730)
    history = _fetch_team_history(team_ids, league_ids, days_back=days_back)
    history = [ev for ev in history if _is_settled(ev)]

    # Index formă pe echipă
    team_form_results = []
    form_by_team: Dict[str, Dict[str, Any]] = {}
    for tid in team_ids:
        summary = _form_summary(tid, history, limit=5)
        summary["history_sample_available"] = sum(1 for ev in history if _is_team_event(ev, tid))
        form_by_team[str(tid)] = summary
        team_form_results.append(summary)

    # H2H pe eveniment prioritar
    h2h_results = []
    for ev in priority_events:
        hid, aid = ev.get("home_team_id"), ev.get("away_team_id")
        if not hid or not aid:
            continue
        h2h = _h2h_summary(hid, aid, history, limit=10)
        h2h_results.append({
            "event_id": ev.get("event_id"),
            "home_team_id": hid,
            "away_team_id": aid,
            "home_team": ev.get("home_team"),
            "away_team": ev.get("away_team"),
            "league_id": ev.get("league_id"),
            "event_date": ev.get("event_date"),
            **h2h,
        })

    # xG/xA pe eveniment prioritar
    pred_xg = _prediction_xg_index()
    sig_xg = _signal_xg_index()
    ctx_payload = _read_json_file("match_context.json", {"results": []})
    ctx_idx = {str(c.get("event_id")): c for c in ctx_payload.get("results", []) if c.get("event_id")}
    xg_results = []
    for ev in priority_events:
        eid = ev.get("event_id")
        if not eid:
            continue
        base = {
            "event_id": eid,
            "home_team": ev.get("home_team"),
            "away_team": ev.get("away_team"),
            "home_team_id": ev.get("home_team_id"),
            "away_team_id": ev.get("away_team_id"),
            "league_id": ev.get("league_id"),
            "event_date": ev.get("event_date"),
        }
        xg = dict(pred_xg.get(str(eid)) or {})
        if str(eid) in sig_xg:
            xg.update(sig_xg[str(eid)])
            xg["source"] = sig_xg[str(eid)].get("source")
        ctx = ctx_idx.get(str(eid)) or {}
        xg.update(_actual_xg_from_context(ctx))
        xa = _extract_xa_summary(ctx.get("player_stats")) if ctx else {"xa_available": False, "note": "player-stats indisponibil"}
        xg_results.append({**base, **xg, "xa": xa})

    save("team_form.json", {
        "updated_at": now_iso(),
        "source": "team_form_v1",
        "days_back": days_back,
        "count": len(team_form_results),
        "results": team_form_results,
    }, protect_empty=True, job_name="team_form")
    save("h2h_context.json", {
        "updated_at": now_iso(),
        "source": "h2h_context_v1",
        "days_back": days_back,
        "count": len(h2h_results),
        "results": h2h_results,
        "note": "H2H este derivat din evenimentele istorice disponibile în BSD /events/; dacă sample=0, API-ul nu are directe în fereastra scanată.",
    }, protect_empty=True, job_name="h2h_context")
    save("xg_context.json", {
        "updated_at": now_iso(),
        "source": "xg_context_v1",
        "count": len(xg_results),
        "results": xg_results,
        "note": "xG estimat vine din predictions/signals; xG actual apare doar live/post-match. xA apare doar dacă player-stats îl expune explicit.",
    }, protect_empty=True, job_name="xg_context")

    save_debug("form_h2h_debug.json", {
        "updated_at": now_iso(),
        "days_back": days_back,
        "priority_events": len(priority_events),
        "teams": len(team_ids),
        "leagues": league_ids,
        "history_events_loaded": len(history),
        "team_form_count": len(team_form_results),
        "h2h_count": len(h2h_results),
        "h2h_with_sample": sum(1 for h in h2h_results if h.get("sample", 0) > 0),
        "xg_count": len(xg_results),
        "xg_with_estimate": sum(1 for x in xg_results if x.get("xg_home") is not None or x.get("xg_away") is not None),
        "xa_available_events": sum(1 for x in xg_results if (x.get("xa") or {}).get("xa_available")),
    })


# ─────────────────────────────────────────────────────────────────────────────
# [14/14] STABILITY QA — production health report
# ─────────────────────────────────────────────────────────────────────────────
def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _age_minutes(value: Any) -> Optional[float]:
    dt = _parse_dt(value)
    if not dt:
        return None
    return round((datetime.now(timezone.utc) - dt).total_seconds() / 60, 1)


def qa_file_report(filename: str, min_count: int = 0, max_age_minutes: Optional[int] = None, critical: bool = False) -> Dict[str, Any]:
    path = DATA_DIR / filename
    report: Dict[str, Any] = {
        "file": filename,
        "exists": path.exists(),
        "critical": critical,
        "status": "ok",
        "count": 0,
        "updated_at": None,
        "age_minutes": None,
        "size_bytes": 0,
        "notes": [],
    }
    if not path.exists():
        report["status"] = "error" if critical else "warn"
        report["notes"].append("missing")
        return report
    try:
        report["size_bytes"] = path.stat().st_size
        data = json.loads(path.read_text(encoding="utf-8"))
        report["count"] = count_payload(data)
        if isinstance(data, dict):
            report["updated_at"] = data.get("updated_at")
            report["age_minutes"] = _age_minutes(data.get("updated_at"))
            report["source"] = data.get("source")
        if report["size_bytes"] < 8:
            report["status"] = "error" if critical else "warn"
            report["notes"].append("tiny_file")
        if report["count"] < min_count:
            report["status"] = "error" if critical else "warn"
            report["notes"].append(f"count_below_{min_count}")
        if max_age_minutes is not None and report["age_minutes"] is not None and report["age_minutes"] > max_age_minutes:
            # Live files stale are warnings, daily critical files stale become warnings not hard errors.
            report["status"] = "warn" if report["status"] == "ok" else report["status"]
            report["notes"].append(f"stale_over_{max_age_minutes}m")
    except Exception as exc:
        report["status"] = "error" if critical else "warn"
        report["notes"].append(f"invalid_json: {exc}")
    return report


def qa_workflow_report(path_str: str, must_contain: Optional[List[str]] = None) -> Dict[str, Any]:
    path = _ROOT / path_str
    must_contain = must_contain or []
    report = {"file": path_str, "exists": path.exists(), "status": "ok", "notes": []}
    if not path.exists():
        report["status"] = "error"
        report["notes"].append("missing_workflow")
        return report
    text = path.read_text(encoding="utf-8", errors="ignore")
    for token in must_contain:
        if token not in text:
            report["status"] = "warn"
            report["notes"].append(f"missing_token:{token}")
    return report



# ─────────────────────────────────────────────────────────────────────────────
# [13/14] MARKET INTELLIGENCE — compare odds, movement, Polymarket context
# ─────────────────────────────────────────────────────────────────────────────
def _event_identity_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    ev = row.get("event") if isinstance(row.get("event"), dict) else {}
    return {
        "event_id": row.get("event_id") or row.get("id") or ev.get("id"),
        "home_team": row.get("home_team") or ev.get("home_team"),
        "away_team": row.get("away_team") or ev.get("away_team"),
        "home_team_id": row.get("home_team_id") or ev.get("home_team_id"),
        "away_team_id": row.get("away_team_id") or ev.get("away_team_id"),
        "league_id": row.get("league_id") or ev.get("league_id") or row.get("_league_id"),
        "league": row.get("league") or row.get("league_name") or ev.get("league_name") or row.get("_league_name"),
        "event_date": row.get("event_date") or ev.get("event_date"),
    }


def _priority_market_events(limit: int = 40) -> List[Dict[str, Any]]:
    """Evenimente prioritare pentru compare odds/Polymarket: value bets, signals, predictions, context."""
    candidates: Dict[str, Dict[str, Any]] = {}

    def add(row: Dict[str, Any], source: str, score: float = 0) -> None:
        ident = _event_identity_from_row(row)
        eid = ident.get("event_id")
        if eid is None:
            return
        key = str(eid)
        old = candidates.get(key, {})
        merged = {**old, **{k: v for k, v in ident.items() if v not in (None, "")}}
        sources = set(old.get("sources", []))
        sources.add(source)
        merged["sources"] = sorted(sources)
        merged["priority_score"] = round(max(as_float(old.get("priority_score"), 0) or 0, score), 2)
        candidates[key] = merged

    vb = _read_json_file("value_bets.json", {"results": []}).get("results", [])
    sig = _read_json_file("signals.json", {"signals": []}).get("signals", [])
    pred = _read_json_file("predictions.json", {"results": []}).get("results", [])
    ctx = _read_json_file("match_context.json", {"results": []}).get("results", [])

    for i, row in enumerate(vb[:30]):
        add(row, "value_bets", 100 - i + (as_float(row.get("confidence"), 0) or 0))
    for i, row in enumerate(sig[:60]):
        add(row, "signals", 80 - i / 2 + (as_float(row.get("smartbet_score"), 0) or 0))
    for i, row in enumerate(ctx[:40]):
        add(row, "match_context", as_float(row.get("priority_score"), 0) or (40 - i))
    for i, row in enumerate(pred[:80]):
        add(row, "predictions", as_float(row.get("smartbet_score"), 0) or as_float(row.get("confidence"), 0) or (20 - i / 5))

    rows = sorted(candidates.values(), key=lambda r: r.get("priority_score", 0), reverse=True)
    return rows[:limit]


COMPARISON_CACHE: Dict[str, Dict[str, Any]] = {}

MARKET_COMPARISON_CODES = {
    "1x2": {
        "HOME": ["HOME", "home", "1", "home_win"],
        "DRAW": ["DRAW", "draw", "X"],
        "AWAY": ["AWAY", "away", "2", "away_win"],
    },
    "over_under_15": {
        "OVER 1.50": ["over", "OVER", "over_15_goals", "Over 1.5"],
        "UNDER 1.50": ["under", "UNDER", "under_15_goals", "Under 1.5"],
    },
    "over_under_25": {
        "OVER 2.50": ["over", "OVER", "over_25_goals", "Over 2.5"],
        "UNDER 2.50": ["under", "UNDER", "under_25_goals", "Under 2.5"],
    },
    "over_under_35": {
        "OVER 3.50": ["over", "OVER", "over_35_goals", "Over 3.5"],
        "UNDER 3.50": ["under", "UNDER", "under_35_goals", "Under 3.5"],
    },
    "btts": {
        "YES": ["yes", "YES", "btts_yes", "BTTS Yes"],
        "NO": ["no", "NO", "btts_no", "BTTS No"],
    },
}

CONSENSUS_ODDS_MAP = {
    "1x2": [("HOME", "home_win"), ("DRAW", "draw"), ("AWAY", "away_win")],
    "over_under_15": [("OVER 1.50", "over_15_goals"), ("UNDER 1.50", "under_15_goals")],
    "over_under_25": [("OVER 2.50", "over_25_goals"), ("UNDER 2.50", "under_25_goals")],
    "over_under_35": [("OVER 3.50", "over_35_goals"), ("UNDER 3.50", "under_35_goals")],
    "btts": [("YES", "btts_yes"), ("NO", "btts_no")],
}


def _movement_from_prices(current: Optional[float], previous: Optional[float], raw: Any = None) -> str:
    raw_label = str(raw or "").strip().upper()
    if raw_label in {"SHORTENING", "DRIFTING", "STABLE", "NEW"}:
        return raw_label
    if current is None or previous is None:
        return ""
    delta = round(float(current) - float(previous), 4)
    if delta <= -0.005:
        return "SHORTENING"
    if delta >= 0.005:
        return "DRIFTING"
    return "STABLE"


def _candidate_values_for_key(d: Dict[str, Any], keys: Iterable[str]) -> Any:
    if not isinstance(d, dict):
        return None
    for k in keys:
        if k in d and d.get(k) is not None:
            return d.get(k)
    lower = {str(k).lower(): v for k, v in d.items()}
    for k in keys:
        lk = str(k).lower()
        if lk in lower and lower.get(lk) is not None:
            return lower.get(lk)
    return None


def _normalize_bookmaker_rows(outcome_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalizează quote-urile side-by-side din /events/{id}/odds/comparison/."""
    rows: List[Dict[str, Any]] = []
    books = outcome_data.get("bookmakers") or outcome_data.get("books") or outcome_data.get("quotes")

    if isinstance(books, dict):
        iterator = books.items()
    elif isinstance(books, list):
        iterator = [(None, x) for x in books]
    else:
        iterator = []

    for slug, b in iterator:
        if not isinstance(b, dict):
            continue
        price = as_float(
            b.get("decimal_odds")
            or b.get("decimal")
            or b.get("odds")
            or b.get("price")
            or b.get("current_decimal_odds")
        )
        if price is None or price < 1.01:
            continue
        previous = as_float(
            b.get("previous_decimal_odds")
            or b.get("previous_odds")
            or b.get("opening_decimal_odds")
            or b.get("old_decimal_odds")
        )
        bookmaker = b.get("bookmaker_name") or b.get("bookmaker") or b.get("name") or slug or "bookmaker"
        slug_value = b.get("bookmaker_slug") or b.get("slug") or slug or bookmaker
        rows.append(
            {
                "bookmaker": str(bookmaker),
                "bookmaker_slug": str(slug_value),
                "decimal_odds": round(price, 3),
                "previous_decimal_odds": round(previous, 3) if previous is not None else None,
                "movement": _movement_from_prices(price, previous, b.get("movement") or b.get("odds_movement")),
                "is_max_quote": bool(b.get("is_max_quote") or b.get("is_best") or b.get("is_best_price")),
                "implied_probability": b.get("implied_probability"),
            }
        )
    rows.sort(key=lambda x: x.get("decimal_odds") or 0, reverse=True)
    return rows


def _normalise_outcome_block(outcome_key: str, outcome_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    rows = _normalize_bookmaker_rows(outcome_data)
    best_price = as_float(
        outcome_data.get("best_odds")
        or outcome_data.get("best_decimal_odds")
        or outcome_data.get("decimal_odds")
        or outcome_data.get("odds")
    )
    previous_best = as_float(
        outcome_data.get("previous_decimal_odds")
        or outcome_data.get("previous_odds")
        or outcome_data.get("opening_decimal_odds")
    )
    best_book = (
        outcome_data.get("best_bookmaker_slug")
        or outcome_data.get("best_bookmaker")
        or outcome_data.get("bookmaker_slug")
        or outcome_data.get("bookmaker")
    )
    if best_price is not None and not rows:
        rows.append(
            {
                "bookmaker": str(best_book or "consensus"),
                "bookmaker_slug": str(best_book or "consensus"),
                "decimal_odds": round(best_price, 3),
                "previous_decimal_odds": round(previous_best, 3) if previous_best is not None else None,
                "movement": _movement_from_prices(best_price, previous_best, outcome_data.get("movement")),
                "is_max_quote": True,
            }
        )
    if not rows:
        return None
    rows.sort(key=lambda x: x.get("decimal_odds") or 0, reverse=True)
    best = rows[0]
    return {
        "best_odds": best.get("decimal_odds"),
        "best_bookmaker": best.get("bookmaker_slug") or best.get("bookmaker"),
        "bookmakers_count": len(rows),
        "shortening_count": sum(1 for r in rows if r.get("movement") == "SHORTENING"),
        "drifting_count": sum(1 for r in rows if r.get("movement") == "DRIFTING"),
        "stable_count": sum(1 for r in rows if r.get("movement") == "STABLE"),
        "bookmakers": rows[:20],
    }


def _extract_comparison_all(payload: Any) -> Dict[str, Dict[str, Any]]:
    """
    Parser pentru endpointul real din BSD docs:
      GET /api/v2/events/{id}/odds/comparison/
    Acesta poate returna 14 books + Polymarket side-by-side și previous_decimal_odds pe fiecare quote.
    """
    if not isinstance(payload, dict):
        return {}
    root = payload.get("markets") if isinstance(payload.get("markets"), dict) else payload
    if not isinstance(root, dict):
        return {}

    normalized: Dict[str, Dict[str, Any]] = {}
    for market, outcome_aliases in MARKET_COMPARISON_CODES.items():
        market_block = root.get(market)
        if not isinstance(market_block, dict):
            continue
        outcomes: Dict[str, Any] = {}
        bookmaker_slugs = set()
        for display_outcome, aliases in outcome_aliases.items():
            outcome_data = _candidate_values_for_key(market_block, aliases)
            if not isinstance(outcome_data, dict):
                continue
            block = _normalise_outcome_block(display_outcome, outcome_data)
            if not block:
                continue
            for b in block.get("bookmakers", []):
                if b.get("bookmaker_slug"):
                    bookmaker_slugs.add(str(b.get("bookmaker_slug")))
            outcomes[display_outcome] = block
        if outcomes:
            normalized[market] = {
                "market": market,
                "outcomes": outcomes,
                "bookmakers_count": len(bookmaker_slugs),
                "shortening_count": sum(v.get("shortening_count", 0) for v in outcomes.values()),
                "drifting_count": sum(v.get("drifting_count", 0) for v in outcomes.values()),
                "source_shape": "odds_comparison",
                "endpoint": "odds/comparison",
            }
    return normalized


def _extract_consensus_all(payload: Any) -> Dict[str, Dict[str, Any]]:
    """Fallback corect pentru GET /api/v2/events/{id}/odds/ — consensus odds, nu bookmaker matrix."""
    if not isinstance(payload, dict):
        return {}
    odds = payload.get("odds") if isinstance(payload.get("odds"), dict) else payload
    if not isinstance(odds, dict):
        return {}
    normalized: Dict[str, Dict[str, Any]] = {}
    for market, pairs in CONSENSUS_ODDS_MAP.items():
        outcomes: Dict[str, Any] = {}
        for display, field in pairs:
            price = as_float(odds.get(field))
            if price is None or price < 1.01:
                continue
            outcomes[display] = {
                "best_odds": round(price, 3),
                "best_bookmaker": "BSD consensus",
                "bookmakers_count": 1,
                "shortening_count": 0,
                "drifting_count": 0,
                "stable_count": 0,
                "bookmakers": [
                    {
                        "bookmaker": "BSD consensus",
                        "bookmaker_slug": "bsd_consensus",
                        "decimal_odds": round(price, 3),
                        "previous_decimal_odds": None,
                        "movement": "",
                        "is_max_quote": True,
                    }
                ],
            }
        if outcomes:
            normalized[market] = {
                "market": market,
                "outcomes": outcomes,
                "bookmakers_count": 1,
                "shortening_count": 0,
                "drifting_count": 0,
                "source_shape": "bsd_consensus_odds",
                "endpoint": "events/{id}/odds",
            }
    return normalized


def _fetch_event_odds_bundle(event_id: Any) -> Dict[str, Dict[str, Any]]:
    key = str(event_id)
    if key in COMPARISON_CACHE:
        return COMPARISON_CACHE[key]
    attempts: List[Dict[str, Any]] = []

    # 1) Endpointul corect găsit în BSD docs: 14 top books + Polymarket + previous_decimal_odds.
    cmp_url = f"{BASE_V2}/events/{event_id}/odds/comparison/"
    payload = get(cmp_url, None, label=f"odds_comparison_{event_id}")
    attempts.append({"url": cmp_url, "params": None, "ok": bool(payload), "kind": "comparison"})
    bundle = _extract_comparison_all(payload)
    if bundle:
        for m in bundle.values():
            m["endpoint"] = cmp_url
            m["attempts"] = attempts[:]
        COMPARISON_CACHE[key] = bundle
        return bundle

    # 2) Fallback oficial din docs: consensus odds.
    consensus_url = f"{BASE_V2}/events/{event_id}/odds/"
    payload = get(consensus_url, None, label=f"odds_consensus_{event_id}")
    attempts.append({"url": consensus_url, "params": None, "ok": bool(payload), "kind": "consensus"})
    bundle = _extract_consensus_all(payload)
    if bundle:
        for m in bundle.values():
            m["endpoint"] = consensus_url
            m["attempts"] = attempts[:]
        COMPARISON_CACHE[key] = bundle
        return bundle

    COMPARISON_CACHE[key] = {}
    return {}


def _best_odds_fallback_for_event(event_id: Any, market: str, best_rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for row in best_rows:
        if str(row.get("event_id") or row.get("event", {}).get("id")) == str(event_id) and str(row.get("_market") or row.get("market")) == str(market):
            normalized = _extract_consensus_all({"odds": {}}).get(market) or None
            # Păstrăm fallback-ul vechi doar pentru compatibilitate cu best_odds.json.
            old = _extract_best_odds_row(row, market)
            if old:
                old["source_shape"] = "best_odds_fallback"
                return old
            return normalized
    return None


def _extract_best_odds_row(row: Dict[str, Any], market: str) -> Optional[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for b in row.get("best_odds") or []:
        if not isinstance(b, dict):
            continue
        outcome = str(b.get("outcome") or b.get("outcome_name") or "").upper()
        price = as_float(b.get("decimal_odds") or b.get("odds"))
        if not outcome or price is None:
            continue
        slug = str(b.get("bookmaker_slug") or b.get("bookmaker_name") or b.get("bookmaker") or "best")
        grouped.setdefault(outcome, []).append({"bookmaker": b.get("bookmaker_name") or slug, "bookmaker_slug": slug, "decimal_odds": round(price, 3), "movement": str(b.get("movement") or "").upper()})
    if not grouped:
        return None
    outcomes = {}
    slugs = set()
    for outcome, rows in grouped.items():
        rows.sort(key=lambda x: x.get("decimal_odds") or 0, reverse=True)
        slugs.update(str(r.get("bookmaker_slug")) for r in rows if r.get("bookmaker_slug"))
        outcomes[outcome] = {"best_odds": rows[0]["decimal_odds"], "best_bookmaker": rows[0].get("bookmaker_slug"), "bookmakers_count": len(rows), "shortening_count": 0, "drifting_count": 0, "bookmakers": rows[:20]}
    return {"market": market, "outcomes": outcomes, "bookmakers_count": len(slugs), "shortening_count": 0, "drifting_count": 0, "source_shape": "best_odds_fallback"}


def _fetch_event_compare_odds(event_id: Any, market: str, best_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    bundle = _fetch_event_odds_bundle(event_id)
    if market in bundle and (bundle[market].get("outcomes") or {}):
        return bundle[market]
    fallback = _best_odds_fallback_for_event(event_id, market, best_rows)
    if fallback:
        fallback["endpoint"] = "data/best_odds.json"
        return fallback
    return {"market": market, "outcomes": {}, "bookmakers_count": 0, "shortening_count": 0, "drifting_count": 0, "endpoint": None, "attempts": [], "source_shape": "missing"}

def _flatten_market_snapshot(compare_rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    snap: Dict[str, Dict[str, Any]] = {}
    for ev in compare_rows:
        eid = ev.get("event_id")
        for market, m in (ev.get("markets") or {}).items():
            for outcome, out in (m.get("outcomes") or {}).items():
                price = as_float(out.get("best_odds"))
                if price is None:
                    continue
                key = f"{eid}|{market}|{outcome}"
                snap[key] = {
                    "event_id": eid,
                    "market": market,
                    "outcome": outcome,
                    "decimal_odds": round(price, 3),
                    "bookmaker": out.get("best_bookmaker"),
                    "bookmakers_count": out.get("bookmakers_count", 0),
                }
    return snap


def _build_odds_movement(current_snapshot: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    prev_payload = _read_json_file("odds_snapshot.json", {"snapshot": {}})
    previous = prev_payload.get("snapshot") if isinstance(prev_payload, dict) else {}
    movements: List[Dict[str, Any]] = []
    summary = {"shortening": 0, "drifting": 0, "stable": 0, "new": 0, "removed": 0}
    for key, cur in current_snapshot.items():
        old = previous.get(key) if isinstance(previous, dict) else None
        old_price = as_float(old.get("decimal_odds")) if isinstance(old, dict) else None
        cur_price = as_float(cur.get("decimal_odds"))
        if old_price is None or cur_price is None:
            label = "NEW"
            delta = None
            summary["new"] += 1
        else:
            delta = round(cur_price - old_price, 3)
            if delta <= -0.01:
                label = "SHORTENING"
                summary["shortening"] += 1
            elif delta >= 0.01:
                label = "DRIFTING"
                summary["drifting"] += 1
            else:
                label = "STABLE"
                summary["stable"] += 1
        movements.append({**cur, "previous_odds": old_price, "delta": delta, "movement": label})
    if isinstance(previous, dict):
        for key, old in previous.items():
            if key not in current_snapshot:
                summary["removed"] += 1
    movements.sort(key=lambda r: (0 if r.get("movement") in ("SHORTENING", "DRIFTING") else 1, abs(as_float(r.get("delta"), 0) or 0)), reverse=False)
    return {"updated_at": now_iso(), "source": "odds_movement_v1", "summary": summary, "count": len(movements), "results": movements[:500]}


def _fetch_polymarket_for_event(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    eid = event.get("event_id")
    endpoints = [
        (f"{BASE_V2}/events/{eid}/polymarket/", None),
        (f"{BASE_V2}/polymarket/", {"event": eid}),
        (f"{BASE_V2}/odds/polymarket/", {"event": eid}),
    ]
    attempts = []
    for url, params in endpoints:
        payload = get(url, params, label=f"polymarket_{eid}")
        attempts.append({"url": url, "params": params, "ok": bool(payload)})
        if isinstance(payload, dict) and (payload.get("markets") or payload.get("results") or payload.get("data")):
            return {**event, "data": payload, "attempts": attempts, "status": "ok"}
    return None


def _polymarket_probabilities(poly: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not poly:
        return {}
    data = poly.get("data") if isinstance(poly.get("data"), dict) else poly
    markets = data.get("markets") if isinstance(data, dict) else {}
    if not isinstance(markets, dict):
        return {}
    return {
        "match_result": markets.get("1x2") or markets.get("match_result") or {},
        "btts": markets.get("btts") or {},
        "over_under": markets.get("over_under") or markets.get("over_under_25") or {},
    }


def _build_market_event(row: Dict[str, Any], compare: Optional[Dict[str, Any]], poly: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    markets = compare.get("markets", {}) if compare else {}
    all_bookmakers = 0
    shortening = 0
    drifting = 0
    best_examples = []
    for market, m in markets.items():
        all_bookmakers = max(all_bookmakers, m.get("bookmakers_count", 0) or 0)
        shortening += m.get("shortening_count", 0) or 0
        drifting += m.get("drifting_count", 0) or 0
        for outcome, out in (m.get("outcomes") or {}).items():
            top_book = (out.get("bookmakers") or [{}])[0] if isinstance(out.get("bookmakers"), list) else {}
            best_examples.append({
                "market": market,
                "outcome": outcome,
                "best_odds": out.get("best_odds"),
                "bookmaker": out.get("best_bookmaker"),
                "bookmakers_count": out.get("bookmakers_count", 0),
                "previous_decimal_odds": top_book.get("previous_decimal_odds"),
                "movement": top_book.get("movement") or "",
                "is_max_quote": top_book.get("is_max_quote"),
            })
    best_examples.sort(key=lambda x: x.get("bookmakers_count") or 0, reverse=True)
    movement_label = "SHORTENING" if shortening > drifting and shortening > 0 else ("DRIFTING" if drifting > shortening and drifting > 0 else "STABLE/NO HISTORY")
    return {
        **row,
        "bookmakers_count": all_bookmakers,
        "markets_count": len(markets),
        "shortening_count": shortening,
        "drifting_count": drifting,
        "movement_label": movement_label,
        "market_depth": "strong" if all_bookmakers >= 10 else ("medium" if all_bookmakers >= 4 else "thin"),
        "markets": markets,
        "best_examples": best_examples[:12],
        "polymarket": _polymarket_probabilities(poly),
        "polymarket_available": bool(poly),
    }


def fetch_market_intelligence() -> None:
    print("\n[14/14] Market Intelligence — compare odds + movement + Polymarket...")
    events = _priority_market_events(limit=int(os.environ.get("BETPREDICT_MARKET_EVENT_LIMIT", "32") or 32))
    best_rows = _read_json_file("best_odds.json", {"results": []}).get("results", [])
    markets_to_fetch = ["1x2", "over_under_15", "over_under_25", "over_under_35", "btts"]

    compare_results: List[Dict[str, Any]] = []
    endpoint_debug: List[Dict[str, Any]] = []
    # Hard safety: oprește iterații noi dacă pipeline-ul depășește 17 min total.
    # Asigură că rămân ~1 min pentru compute_signals + qa_report înainte de 18-min budget.
    _market_intel_budget_sec = 17 * 60
    for event in events:
        if _pipeline_over_budget(_market_intel_budget_sec):
            print(f"  [skip] market_intelligence: pipeline elapsed {_pipeline_elapsed_sec():.0f}s > {_market_intel_budget_sec}s, opresc iterații noi (procesate {len(compare_results)}/{len(events)})")
            break
        eid = event.get("event_id")
        if eid is None:
            continue
        event_compare = {**event, "markets": {}}
        for market in markets_to_fetch:
            m = _fetch_event_compare_odds(eid, market, best_rows)
            event_compare["markets"][market] = m
            endpoint_debug.append({"event_id": eid, "market": market, "endpoint": m.get("endpoint"), "source_shape": m.get("source_shape"), "bookmakers_count": m.get("bookmakers_count", 0), "outcomes": len(m.get("outcomes") or {})})
        compare_results.append(event_compare)

    current_snapshot = _flatten_market_snapshot(compare_results)
    movement_payload = _build_odds_movement(current_snapshot)
    save("odds_movement.json", movement_payload, protect_empty=False, job_name="odds_movement")
    save("odds_snapshot.json", {"updated_at": now_iso(), "source": "odds_snapshot_v1", "count": len(current_snapshot), "snapshot": current_snapshot}, protect_empty=False, job_name="odds_snapshot")

    polymarket_rows: List[Dict[str, Any]] = []
    for event in events[: int(os.environ.get("BETPREDICT_POLYMARKET_LIMIT", "14") or 14)]:
        if _pipeline_over_budget(_market_intel_budget_sec):
            print(f"  [skip] polymarket fetch: pipeline elapsed {_pipeline_elapsed_sec():.0f}s > {_market_intel_budget_sec}s")
            break
        poly = _fetch_polymarket_for_event(event)
        if poly:
            polymarket_rows.append(poly)

    compare_payload = {"updated_at": now_iso(), "source": "compare_odds_cache_v1", "count": len(compare_results), "events": compare_results, "results": compare_results}
    poly_payload = {"updated_at": now_iso(), "source": "polymarket_context_v1", "count": len(polymarket_rows), "results": polymarket_rows}
    save("compare_odds_cache.json", compare_payload, protect_empty=False, job_name="compare_odds_cache")
    save("polymarket_context.json", poly_payload, protect_empty=True, job_name="polymarket_context")
    # Compatibilitate cu implementări mai vechi care caută data/polymarket.json.
    save("polymarket.json", poly_payload, protect_empty=True, job_name="polymarket")

    poly_by_event = {str(p.get("event_id")): p for p in polymarket_rows}
    compare_by_event = {str(c.get("event_id")): c for c in compare_results}
    market_events = []
    for event in events:
        eid = str(event.get("event_id"))
        market_events.append(_build_market_event(event, compare_by_event.get(eid), poly_by_event.get(eid)))

    summary = {
        "priority_events": len(events),
        "compare_events": len(compare_results),
        "markets_checked": len(compare_results) * len(markets_to_fetch),
        "events_with_bookmakers": sum(1 for e in market_events if e.get("bookmakers_count", 0) > 0),
        "events_with_10plus_bookmakers": sum(1 for e in market_events if e.get("bookmakers_count", 0) >= 10),
        "polymarket_events": len(polymarket_rows),
        "shortening_rows": movement_payload.get("summary", {}).get("shortening", 0),
        "drifting_rows": movement_payload.get("summary", {}).get("drifting", 0),
    }
    market_payload = {
        "updated_at": now_iso(),
        "source": "market_intelligence_v1",
        "summary": summary,
        "count": len(market_events),
        "events": market_events,
        "results": market_events,
        "notes": [
            "Compare odds folosește /events/{id}/odds/comparison/; fallback corect este /events/{id}/odds/ consensus și /odds/best/.",
            "SHORTENING/DRIFTING real apare după minimum două rulări, prin comparație cu odds_snapshot.json.",
            "Polymarket este folosit ca semnal de piață separat, nu ca garanție de rezultat.",
        ],
    }
    save("market_intelligence.json", market_payload, protect_empty=False, job_name="market_intelligence")
    save_debug("market_intelligence_debug.json", {"updated_at": now_iso(), "summary": summary, "endpoint_debug": endpoint_debug[:500], "movement_summary": movement_payload.get("summary", {})})

# ─────────────────────────────────────────────────────────────────────────────
# [16/16] BROADCASTS — program TV per meci
# ─────────────────────────────────────────────────────────────────────────────
def fetch_broadcasts() -> None:
    """GET /api/v2/broadcasts/ — canale TV care transmit meciurile zilei."""
    print("\n[16/16] Broadcasts TV...")
    start_iso, end_iso = date_window(7)

    rows = get_all_pages(
        f"{BASE_V2}/broadcasts/",
        {"date_from": start_iso, "date_to": end_iso, "limit": 200},
        max_pages=3,
        label="broadcasts",
    )
    if not rows:
        rows = get_all_pages(
            f"{BASE_V2}/broadcasts/",
            {"limit": 200},
            max_pages=2,
            label="broadcasts_nodate",
        )

    # Fetch TV-channels lookup table (small, reference data)
    tv_channels = get_all_pages(
        f"{BASE_V2}/tv-channels/",
        {"limit": 200},
        max_pages=1,
        label="tv_channels",
    )
    channel_lookup: Dict[Any, Dict[str, Any]] = {}
    for ch in tv_channels:
        cid = ch.get("id")
        if cid is not None:
            channel_lookup[str(cid)] = ch

    by_event: Dict[str, List[Dict[str, Any]]] = {}
    channels_seen: set = set()
    normalized_rows: List[Dict[str, Any]] = []

    for row in rows:
        eid = row.get("event_id") or row.get("event")
        if isinstance(eid, dict):
            eid = eid.get("id")
        eid_str = str(eid) if eid is not None else ""

        ch_id = row.get("channel_id") or row.get("channel")
        if isinstance(ch_id, dict):
            ch_id = ch_id.get("id")
        # dict.get returnează None implicit dacă lipsește cheia; `or {}` garantează dict.
        ch_meta = (channel_lookup.get(str(ch_id)) or {}) if ch_id is not None else {}

        channel = {
            "name": row.get("channel_name") or ch_meta.get("name") or row.get("name") or row.get("broadcaster"),
            "country": row.get("country") or ch_meta.get("country") or row.get("country_code"),
            "language": row.get("language") or ch_meta.get("language"),
            "type": row.get("type") or ch_meta.get("type") or row.get("broadcast_type"),
            "url": row.get("url") or ch_meta.get("url") or row.get("stream_url"),
            "logo": row.get("logo") or ch_meta.get("logo") or row.get("channel_logo"),
        }
        channel = {k: v for k, v in channel.items() if v}
        if not channel.get("name"):
            continue

        n_row = {
            "event_id": eid,
            "channel": channel,
            "start_time": row.get("start_time") or row.get("broadcast_time"),
            "league_id": row.get("league_id"),
            "raw": row,
        }
        normalized_rows.append(n_row)
        if eid_str:
            by_event.setdefault(eid_str, []).append(channel)
        channels_seen.add(channel.get("name", ""))

    payload = {
        "updated_at": now_iso(),
        "source": "broadcasts_v1",
        "endpoint": "/api/v2/broadcasts/",
        "count": len(normalized_rows),
        "events_with_broadcasts": len(by_event),
        "unique_channels": len(channels_seen),
        "by_event": by_event,
        "tv_channels_count": len(tv_channels),
        "results": normalized_rows,
    }
    save("broadcasts.json", payload, protect_empty=False, job_name="broadcasts")
    print(f"  broadcasts: {len(normalized_rows)} rows, {len(by_event)} events, {len(channels_seen)} channels unique")


# ─────────────────────────────────────────────────────────────────────────────
# [17/17] BSD EVENT PREDICTIONS — consensul API per meci
# ─────────────────────────────────────────────────────────────────────────────
def fetch_bsd_event_predictions() -> None:
    """GET /api/v2/events/{id}/prediction/ — predicții BSD per eveniment.

    Stochează probabilitățile BSD alături de ML-ul local pentru cross-validare.
    Dacă BSD și ML sunt de acord (delta < 8pp), semnalul este mai puternic.
    """
    print("\n[17/17] BSD Event Predictions...")
    preds_raw = _read_json_file("predictions.json", {"results": []})
    pred_rows = preds_raw.get("results", []) if isinstance(preds_raw, dict) else []
    pred_rows = sorted(pred_rows, key=lambda x: as_float(x.get("smartbet_score"), 0) or 0, reverse=True)

    priority: List[Dict[str, Any]] = []
    seen: set = set()
    for row in pred_rows:
        ev = row.get("event") if isinstance(row.get("event"), dict) else {}
        eid = ev.get("id") or row.get("event_id")
        if not eid or eid in seen:
            continue
        seen.add(eid)
        priority.append({
            "event_id": eid,
            "home_team": ev.get("home_team") or row.get("home_team"),
            "away_team": ev.get("away_team") or row.get("away_team"),
            "league_id": row.get("_league_id") or ev.get("league_id"),
            "ml_home_win": as_float(row.get("home_win_probability")),
            "ml_draw": as_float(row.get("draw_probability")),
            "ml_away_win": as_float(row.get("away_win_probability")),
            "ml_over25": as_float(row.get("over_25_probability") or row.get("over25_probability")),
            "ml_btts": as_float(row.get("btts_probability")),
        })

    limit = int(os.environ.get("BETPREDICT_BSD_PRED_LIMIT", "10") or 10)
    budget_sec = 90  # hard time budget: stop after 90s regardless
    results: List[Dict[str, Any]] = []
    t_start = time.monotonic()

    for i, event in enumerate(priority[:limit]):
        if time.monotonic() - t_start > budget_sec:
            print(f"  BSD preds: time budget {budget_sec}s exceeded at event {i}, stopping")
            break
        eid = event.get("event_id")
        if i:
            time.sleep(0.1)
        payload = get(f"{BASE_V2}/events/{eid}/prediction/", {}, label=f"bsd_pred_{eid}")
        if not isinstance(payload, dict):
            continue

        bsd_home = as_float(payload.get("home_win") or payload.get("home_win_probability") or payload.get("home"))
        bsd_draw = as_float(payload.get("draw") or payload.get("draw_probability"))
        bsd_away = as_float(payload.get("away_win") or payload.get("away_win_probability") or payload.get("away"))
        bsd_over25 = as_float(payload.get("over_25") or payload.get("over_under_25") or payload.get("over25") or payload.get("over_2_5"))
        bsd_btts = as_float(payload.get("btts") or payload.get("both_teams_to_score") or payload.get("both_to_score"))

        ml_home = event.get("ml_home_win") or 0
        ml_draw = event.get("ml_draw") or 0
        ml_away = event.get("ml_away_win") or 0

        def consensus_delta(a: float, b: float) -> Optional[float]:
            if not a or not b:
                return None
            return round(abs(a - b), 2)

        delta_home = consensus_delta(bsd_home, ml_home)
        delta_draw = consensus_delta(bsd_draw, ml_draw)
        delta_away = consensus_delta(bsd_away, ml_away)
        consensus_level = "none"
        if delta_home is not None and delta_home < 5 and delta_draw is not None and delta_draw < 5:
            consensus_level = "strong"
        elif delta_home is not None and delta_home < 10:
            consensus_level = "moderate"
        elif delta_home is not None:
            consensus_level = "weak"

        results.append({
            "event_id": eid,
            "home_team": event.get("home_team"),
            "away_team": event.get("away_team"),
            "league_id": event.get("league_id"),
            "bsd_home_win": bsd_home if bsd_home else None,
            "bsd_draw": bsd_draw if bsd_draw else None,
            "bsd_away_win": bsd_away if bsd_away else None,
            "bsd_over25": bsd_over25 if bsd_over25 else None,
            "bsd_btts": bsd_btts if bsd_btts else None,
            "ml_home_win": ml_home if ml_home else None,
            "ml_draw": ml_draw if ml_draw else None,
            "ml_away_win": ml_away if ml_away else None,
            "delta_home": delta_home,
            "delta_draw": delta_draw,
            "delta_away": delta_away,
            "consensus_level": consensus_level,
        })

    strong = sum(1 for r in results if r.get("consensus_level") == "strong")
    moderate = sum(1 for r in results if r.get("consensus_level") == "moderate")
    save("bsd_event_predictions.json", {
        "updated_at": now_iso(),
        "source": "bsd_event_predictions_v1",
        "endpoint": "/api/v2/events/{id}/prediction/",
        "count": len(results),
        "consensus_strong": strong,
        "consensus_moderate": moderate,
        "results": results,
    }, protect_empty=False, job_name="bsd_event_predictions")
    print(f"  bsd_event_predictions: {len(results)}/{len(priority[:limit])} events · strong={strong} moderate={moderate}")

def fetch_production_qa_report() -> None:
    print("\n[15/15] Production QA Report...")
    required_files = [
        ("predictions.json", 1, 24 * 60, True),
        ("best_odds.json", 1, 24 * 60, True),
        ("signals.json", 1, 24 * 60, True),
        ("value_bets.json", 1, 24 * 60, False),
        ("matches_today.json", 0, 24 * 60, False),
        ("standings.json", 1, 7 * 24 * 60, False),
        ("match_context.json", 1, 24 * 60, False),
        ("selection_journal.json", 0, 7 * 24 * 60, False),
        ("recent_results.json", 1, 7 * 24 * 60, False),
        ("performance_summary.json", 0, 7 * 24 * 60, False),
        ("api_coverage_report.json", 1, 7 * 24 * 60, False),
        ("team_intelligence.json", 1, 7 * 24 * 60, False),
        ("context_intelligence.json", 1, 7 * 24 * 60, False),
        ("team_form.json", 1, 7 * 24 * 60, False),
        ("h2h_context.json", 1, 7 * 24 * 60, False),
        ("xg_context.json", 1, 7 * 24 * 60, False),
        ("market_intelligence.json", 1, 24 * 60, False),
        ("compare_odds_cache.json", 1, 24 * 60, False),
        ("odds_movement.json", 1, 24 * 60, False),
        ("polymarket_context.json", 0, 24 * 60, False),
        ("broadcasts.json", 0, 24 * 60, False),
        ("bsd_event_predictions.json", 0, 24 * 60, False),
        ("live.json", 0, 60, False),
        ("live_intelligence.json", 0, 60, False),
    ]
    file_reports = [qa_file_report(*args) for args in required_files]
    workflows = [
        qa_workflow_report(".github/workflows/fetch_daily.yml", ["git add data/ -f", "python src/fetch_daily.py"]),
        qa_workflow_report(".github/workflows/fetch_live.yml", ["data/live_intelligence.json", "data/debug/live_intelligence_debug.json", "python src/fetch_live.py"]),
    ]
    critical_errors = [r for r in file_reports if r.get("critical") and r.get("status") == "error"]
    errors = [r for r in file_reports + workflows if r.get("status") == "error"]
    warnings = [r for r in file_reports + workflows if r.get("status") == "warn"]
    score = max(0, 100 - len(critical_errors) * 25 - (len(errors) - len(critical_errors)) * 12 - len(warnings) * 4)
    status = "production_ready" if not critical_errors and score >= 85 else ("attention" if not critical_errors else "blocked")
    report = {
        "updated_at": now_iso(),
        "source": "production_qa_v1",
        "status": status,
        "score": score,
        "summary": {
            "files_checked": len(file_reports),
            "workflows_checked": len(workflows),
            "critical_errors": len(critical_errors),
            "errors": len(errors),
            "warnings": len(warnings),
            "ok": sum(1 for r in file_reports + workflows if r.get("status") == "ok"),
        },
        "files": file_reports,
        "workflows": workflows,
        "recommendations": [
            "Rulează Fetch Daily Data după modificări de pipeline.",
            "Rulează Fetch Live Scores după modificări de live center.",
            "Dacă un fișier critic are count 0, verifică data/debug/*.json înainte de UI.",
            "Value Bets oficial rămâne blocat până există endpoint BSD confirmat; se folosește fallback local disciplinat.",
        ],
        "_pipeline_version": "v22-full-bsd-coverage",
    }
    save("qa_report.json", report, protect_empty=False, job_name="qa_report")
    save_debug("qa_debug.json", report)
    print(f"  ✓ qa_report.json status={status} score={score} warnings={len(warnings)} errors={len(errors)}")

def main() -> int:
    global _PIPELINE_START
    DEBUG["started_at"] = now_iso()
    _PIPELINE_START = time.monotonic()
    _pipeline_start = _PIPELINE_START

    if not API_KEY:
        warn("BSD_API_KEY nu este setat")
        save_all_debug()
        print("BSD_API_KEY nu este setat!")
        return 1

    print(f"=== BetPredict Pro v22 Full BSD Coverage — {today_iso()} (AC: {'YES' if HAS_AC else 'NO'}) ===")
    try:
        fetch_predictions()
        fetch_best_odds()
        fetch_value_bets()
        fetch_matches_today()
        fetch_standings()
        fetch_match_context()
        fetch_recent_results()
        update_selection_journal()
        compute_performance_summary()
        fetch_api_coverage()
        fetch_team_intelligence()
        fetch_context_intelligence()
        fetch_form_h2h_xg_context()
        _elapsed = time.monotonic() - _pipeline_start
        # fetch_daily.py trebuie să termine în max 18 min (1080s)
        # pentru a lăsa timp celorlalte ~12 script-uri din pipeline
        _remaining = 1080 - _elapsed
        print(f"  [timer] elapsed={_elapsed:.0f}s remaining={_remaining:.0f}s (budget 18min)")
        if _remaining > 150:  # >2.5 min → rulăm broadcasts (max 105s worst-case)
            fetch_broadcasts()
        else:
            print("  [skip] fetch_broadcasts: timp insuficient")
        if _remaining > 100:  # >1.7 min → rulăm BSD preds (90s budget intern)
            fetch_bsd_event_predictions()
        else:
            print("  [skip] fetch_bsd_event_predictions: timp insuficient")
        fetch_market_intelligence()
        compute_signals()
        fetch_production_qa_report()
        print("\nGata!")
        return 0
    finally:
        save_all_debug()


if __name__ == "__main__":
    raise SystemExit(main())
