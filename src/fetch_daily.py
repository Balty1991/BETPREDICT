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

# ── Config ─────────────────────────────────────────────────────────────────────────────
API_KEY = os.environ.get("BSD_API_KEY", "").strip()
BASE_V2 = "https://sports.bzzoiro.com/api/v2"
BASE_V1 = "https://sports.bzzoiro.com/api"
IMG_BASE = "https://sports.bzzoiro.com/img"  # FREE, no auth
WEATHER_CODES = {
    0: {"label": "necunoscut / acoperit", "icon": "🏙️"},
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

# ── Pipeline time budget (global) ───────────────────────────────────────────────────────────────────
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


# ── Helpers ─────────────────────────────────────────────────────────────────────────────
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


# ── HTTP ──────────────────────────────────────────────────────────────────────────────
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


# ── Pasul 3: League Strength Engine ────────────────────────────────────────────────────────────────────────────
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

    # Fallback pentru instalările unde Pasul 1 încă nu a regenerat league_metadata cu rows.
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


# ── Normalize BSD v2 prediction ───────────────────────────────────────────────────────────────────────────
ndef normalize_pred(p: Dict[str, Any], fallback_lid: Optional[int] = None, fallback_lname: str = "") -> Dict[str, Any]:
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
