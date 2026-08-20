#!/usr/bin/env python3
"""
BetPredict Pro — BSD v2 Exact Events Hardening (Pasul 23)
========================================================

Implementează exact comportamentul din documentația BSD v2 pentru:
  1) GET /api/v2/events/
     - paginat
     - date_from/date_to
     - league_id / season_id / team_id / team_name / status
     - fără days=N
  2) GET /api/v2/events/{id}/
     - core event detail pentru match cards/headers
     - foreign keys expuse ca ID-uri
     - fallback venue_id -> home team's venue
     - weather code -> label + icon
     - static images team/league/manager/venue
  3) Complement pentru /events/live/
     - pregătește meta/debug comun cu live pipeline

Acest script rulează după src/fetch_daily.py în workflow-ul daily și NU înlocuiește
pipeline-ul existent; doar produce cache-uri exacte și defensive.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

API_KEY = os.environ.get("BSD_API_KEY", "").strip()
BASE_V2 = "https://sports.bzzoiro.com/api/v2"
IMG_BASE = "https://sports.bzzoiro.com/img"
HEADERS = {"Authorization": f"Token {API_KEY}"} if API_KEY else {}
ROOT = Path(__file__).parent.parent.resolve()
DATA_DIR = ROOT / "data"
DEBUG_DIR = DATA_DIR / "debug"

WEATHER_CODES = {
    0: {"label": "necunoscut / acoperit", "icon": "🏟️"},
    1: {"label": "senin", "icon": "☀️"},
    2: {"label": "înnorat", "icon": "☁️"},
    3: {"label": "ploaie", "icon": "🌧️"},
    4: {"label": "ninsoare", "icon": "❄️"},
    5: {"label": "extrem", "icon": "⛈️"},
}

ODDS_MARKETS = tuple(
    item.strip() for item in os.environ.get(
        "BETPREDICT_ODDS_MARKETS",
        "1x2,over_under_15,over_under_25,over_under_35,btts,double_chance",
    ).split(",") if item.strip()
)
QUOTA_EXHAUSTED = False
QUOTA_STATE: Dict[str, Any] = {"status": "unknown", "remaining": None, "reset_seconds": None}

DEBUG: Dict[str, Any] = {
    "started_at": None,
    "finished_at": None,
    "has_api_key": bool(API_KEY),
    "requests": [],
    "warnings": [],
    "jobs": {},
    "quota": QUOTA_STATE,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_ro() -> str:
    # GitHub Actions rulează UTC; +4h evită rularea înaintea zilei curente RO.
    return (datetime.now(timezone.utc) + timedelta(hours=4)).strftime("%Y-%m-%d")


def date_default_to(days_ahead: int = 7) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=4 + 24 * days_ahead)).strftime("%Y-%m-%d")


def img_url(kind: str, ident: Any) -> Optional[str]:
    return f"{IMG_BASE}/{kind}/{ident}/" if ident not in (None, "", "null") else None


def safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        warn("Nu pot citi JSON", path=str(path), error=str(exc))
    return default


def save_json(filename: str, payload: Any) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / filename
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    print(f"  ✓ {filename} ({count_payload(payload)})")


def save_debug(filename: str, payload: Any) -> None:
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    (DEBUG_DIR / filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def warn(message: str, **context: Any) -> None:
    DEBUG["warnings"].append({"message": message, "context": context, "time": now_iso()})
    print(f"  ⚠ {message}")


def count_payload(payload: Any) -> int:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        if isinstance(payload.get("count"), int):
            return int(payload["count"])
        for key in ("results", "events", "items", "details"):
            value = payload.get(key)
            if isinstance(value, list):
                return len(value)
            if isinstance(value, dict):
                return len(value)
        return 1 if payload else 0
    return 0


def _record_quota(resp: requests.Response) -> None:
    """Păstrează limitele furnizate de API pentru pașii următori ai pipeline-ului."""
    global QUOTA_EXHAUSTED
    rate = resp.headers.get("RateLimit", "")
    retry_after = resp.headers.get("Retry-After")
    remaining = None
    reset_seconds = None
    for part in rate.split(";"):
        key, _, value = part.strip().partition("=")
        if key == "r":
            try:
                remaining = int(value)
            except ValueError:
                pass
        elif key == "t":
            try:
                reset_seconds = int(value)
            except ValueError:
                pass
    if retry_after:
        try:
            reset_seconds = int(retry_after)
        except ValueError:
            pass
    if remaining is not None:
        QUOTA_STATE["remaining"] = remaining
    if reset_seconds is not None:
        QUOTA_STATE["reset_seconds"] = reset_seconds
        QUOTA_STATE["reset_at"] = (datetime.now(timezone.utc) + timedelta(seconds=reset_seconds)).isoformat()
    try:
        body = resp.json() if resp.status_code == 429 else {}
    except ValueError:
        body = {}
    if resp.status_code == 429 and isinstance(body, dict) and body.get("code") == "taster_exhausted":
        QUOTA_EXHAUSTED = True
        QUOTA_STATE["status"] = "exhausted"
        QUOTA_STATE["reason"] = "taster_exhausted"
    elif remaining is not None:
        QUOTA_STATE["status"] = "limited" if remaining < 500 else "healthy"


def get(url: str, params: Optional[Dict[str, Any]] = None, label: str = "") -> Optional[Any]:
    global QUOTA_EXHAUSTED
    params = {k: v for k, v in (params or {}).items() if v not in (None, "", [])}
    if QUOTA_EXHAUSTED:
        DEBUG["requests"].append({"label": label, "url": url, "params": params, "status": "skipped_quota"})
        return None
    started = datetime.now(timezone.utc)
    try:
        resp = requests.get(url, headers=HEADERS, params=params or None, timeout=30)
        _record_quota(resp)
        elapsed_ms = round((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        DEBUG["requests"].append({
            "label": label,
            "url": url,
            "params": params,
            "status": resp.status_code,
            "elapsed_ms": elapsed_ms,
        })
        if resp.status_code in (401, 403):
            warn("Auth BSD eșuat — verifică BSD_API_KEY", url=url, status=resp.status_code)
            return None
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        elapsed_ms = round((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        DEBUG["requests"].append({
            "label": label,
            "url": url,
            "params": params,
            "status": None,
            "elapsed_ms": elapsed_ms,
            "error": str(exc)[:220],
        })
        warn("Request BSD eșuat", label=label, url=url, error=str(exc)[:220])
        return None


def extract_list(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("results", "events", "data", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def get_all_paginated(url: str, params: Dict[str, Any], label: str, max_pages: int = 25) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Parcurge wrapperul v2 `count/next/results` fără a continua după quota 429."""
    page_url: Optional[str] = url
    page_params = dict(params)
    page_params.setdefault("limit", 200)
    page_params.setdefault("offset", 0)

    results: List[Dict[str, Any]] = []
    pages: List[Dict[str, Any]] = []
    seen_urls: set[str] = set()
    page = 0

    while page_url and page < max_pages and page_url not in seen_urls:
        seen_urls.add(page_url)
        payload = get(page_url, page_params if page_url == url else None, label=f"{label}_p{page + 1}")
        if not isinstance(payload, dict):
            break

        batch = extract_list(payload)
        results.extend(batch)
        pages.append({
            "page": page + 1,
            "count": len(batch),
            "total_count": payload.get("count"),
            "next": bool(payload.get("next")),
            "previous": bool(payload.get("previous")),
        })

        page += 1
        next_url = payload.get("next")
        if next_url:
            page_url = next_url
            page_params = {}
            continue

        # fallback offset dacă API-ul nu expune next dar count > fetched
        total = safe_int(payload.get("count"), 0) or 0
        if total > len(results):
            page_params = dict(params)
            page_params["limit"] = 200
            page_params["offset"] = len(results)
            page_url = url
            continue
        break

    meta = {"params": params, "pages": pages, "fetched": len(results), "quota": dict(QUOTA_STATE)}
    return results, meta


def get_all_events(params: Dict[str, Any], label: str, max_pages: int = 25) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """GET /api/v2/events/ exact ca docs: paginare limit/offset sau next."""
    return get_all_paginated(f"{BASE_V2}/events/", params, label, max_pages=max_pages)


def normalize_best_odds_row(row: Dict[str, Any], market: str) -> Dict[str, Any]:
    """Normalizează răspunsul `/odds/best/` în schema utilizată de VEYRA."""
    event = row.get("event") if isinstance(row.get("event"), dict) else {}
    normalized: Dict[str, Any] = {
        "event_id": row.get("event_id") or event.get("id"),
        "event_date": row.get("event_date") or event.get("event_date"),
        "league_id": row.get("league_id") or event.get("league_id"),
        "league_name": row.get("league_name") or event.get("league_name"),
        "home_team_id": row.get("home_team_id") or event.get("home_team_id"),
        "home_team": row.get("home_team") or event.get("home_team"),
        "away_team_id": row.get("away_team_id") or event.get("away_team_id"),
        "away_team": row.get("away_team") or event.get("away_team"),
        "market": row.get("market") or market,
        "best_odds": row.get("best_odds") if isinstance(row.get("best_odds"), list) else [],
        "event": event,
    }
    for odd in normalized["best_odds"]:
        if not isinstance(odd, dict):
            continue
        outcome = str(odd.get("outcome") or "").upper()
        value = odd.get("decimal_odds")
        if outcome == "HOME":
            normalized["home_odds"] = normalized["odds_1"] = value
        elif outcome == "DRAW":
            normalized["draw_odds"] = normalized["odds_x"] = value
        elif outcome == "AWAY":
            normalized["away_odds"] = normalized["odds_2"] = value
        elif outcome == "OVER":
            normalized["over_odds"] = normalized["odds_over"] = value
        elif outcome == "UNDER":
            normalized["under_odds"] = normalized["odds_under"] = value
        elif outcome in {"YES", "NO", "1X", "12", "X2"}:
            normalized[f"odds_{outcome.lower()}"] = value
    return normalized


def build_best_odds() -> None:
    """Colectează o dată pe piață cote consolidate, nu comparații individuale costisitoare."""
    date_from = os.environ.get("BETPREDICT_EVENTS_DATE_FROM") or today_ro()
    date_to = os.environ.get("BETPREDICT_ODDS_DATE_TO") or date_default_to(7)
    rows: List[Dict[str, Any]] = []
    market_counts: Dict[str, int] = {}
    for market in ODDS_MARKETS:
        batch, pagination = get_all_paginated(
            f"{BASE_V2}/odds/best/",
            {"date_from": date_from, "date_to": date_to, "market": market, "limit": 200},
            label=f"best_odds_{market}",
            max_pages=10,
        )
        normalized = [normalize_best_odds_row(row, market) for row in batch]
        rows.extend(row for row in normalized if row.get("event_id"))
        market_counts[market] = len(normalized)
        if QUOTA_EXHAUSTED:
            break
    if rows:
        save_json("best_odds.json", {
            "updated_at": now_iso(),
            "source": "bsd_v2_odds_best_incremental",
            "endpoint": "/api/v2/odds/best/",
            "params": {"date_from": date_from, "date_to": date_to, "markets": list(ODDS_MARKETS)},
            "count": len(rows),
            "market_counts": market_counts,
            "quota": dict(QUOTA_STATE),
            "results": rows,
        })
    else:
        warn("Nu au fost primite cote proaspete; păstrez ultimul cache valid", quota=QUOTA_STATE)
    DEBUG["jobs"]["best_odds"] = {"count": len(rows), "market_counts": market_counts, "quota": dict(QUOTA_STATE)}


def weather_context(weather: Any, pitch_condition: Any = None) -> Dict[str, Any]:
    weather = weather if isinstance(weather, dict) else {}
    code = safe_int(weather.get("code"), None)
    meta = WEATHER_CODES.get(code, WEATHER_CODES[0])
    return {
        "code": code,
        "label": weather.get("description") or meta["label"],
        "icon": meta["icon"],
        "wind_speed": weather.get("wind_speed"),
        "temperature_c": weather.get("temperature_c"),
        "pitch_condition": pitch_condition,
    }


def normalize_event_summary(event: Dict[str, Any]) -> Dict[str, Any]:
    eid = event.get("id") or event.get("event_id")
    lid = event.get("league_id")
    home_id = event.get("home_team_id")
    away_id = event.get("away_team_id")
    venue_id = event.get("venue_id")

    return {
        "id": eid,
        "event_id": eid,
        "league_id": lid,
        "league_name": event.get("league_name") or event.get("league"),
        "home_team_id": home_id,
        "home_team": event.get("home_team"),
        "away_team_id": away_id,
        "away_team": event.get("away_team"),
        "home_coach_id": event.get("home_coach_id") or event.get("home_manager_id"),
        "away_coach_id": event.get("away_coach_id") or event.get("away_manager_id"),
        "referee_id": event.get("referee_id"),
        "venue_id": venue_id,
        "event_date": event.get("event_date"),
        "status": event.get("status"),
        "period": event.get("period"),
        "current_minute": event.get("current_minute"),
        "home_score": event.get("home_score"),
        "away_score": event.get("away_score"),
        "home_score_ht": event.get("home_score_ht"),
        "away_score_ht": event.get("away_score_ht"),
        "is_local_derby": event.get("is_local_derby"),
        "is_neutral_ground": event.get("is_neutral_ground"),
        "travel_distance_km": event.get("travel_distance_km"),
        "weather": event.get("weather"),
        "pitch_condition": event.get("pitch_condition"),
        "attendance": event.get("attendance"),
        "live_websocket": event.get("live_websocket"),
        "image_assets": {
            "home_team_logo": img_url("team", home_id),
            "away_team_logo": img_url("team", away_id),
            "league_logo": img_url("league", lid),
            "venue_photo": img_url("venue", venue_id),
            "home_manager_photo": img_url("manager", event.get("home_coach_id") or event.get("home_manager_id")),
            "away_manager_photo": img_url("manager", event.get("away_coach_id") or event.get("away_manager_id")),
        },
        "weather_context": weather_context(event.get("weather"), event.get("pitch_condition")),
        "raw": event,
    }


_TEAM_DETAIL_CACHE: Dict[str, Dict[str, Any]] = {}
_VENUE_DETAIL_CACHE: Dict[str, Dict[str, Any]] = {}


def get_team_detail(team_id: Any) -> Dict[str, Any]:
    if team_id in (None, "", "null"):
        return {}
    key = str(team_id)
    if key not in _TEAM_DETAIL_CACHE:
        payload = get(f"{BASE_V2}/teams/{team_id}/", label=f"team_detail_{team_id}")
        _TEAM_DETAIL_CACHE[key] = payload if isinstance(payload, dict) else {}
    return _TEAM_DETAIL_CACHE[key]


def get_venue_detail(venue_id: Any) -> Dict[str, Any]:
    if venue_id in (None, "", "null"):
        return {}
    key = str(venue_id)
    if key not in _VENUE_DETAIL_CACHE:
        payload = get(f"{BASE_V2}/venues/{venue_id}/", label=f"venue_detail_{venue_id}")
        _VENUE_DETAIL_CACHE[key] = payload if isinstance(payload, dict) else {}
    return _VENUE_DETAIL_CACHE[key]


def normalize_event_detail(detail: Dict[str, Any]) -> Dict[str, Any]:
    row = normalize_event_summary(detail)
    home_team_id = row.get("home_team_id")
    original_venue_id = row.get("venue_id")
    effective_venue_id = original_venue_id
    fallback_applied = False
    home_team_detail: Dict[str, Any] = {}

    if effective_venue_id in (None, "", "null"):
        home_team_detail = get_team_detail(home_team_id)
        effective_venue_id = home_team_detail.get("venue_id")
        fallback_applied = effective_venue_id not in (None, "", "null")

    venue_detail = get_venue_detail(effective_venue_id) if effective_venue_id else {}
    row["venue_id_effective"] = effective_venue_id
    row["venue_fallback_applied"] = fallback_applied
    row["home_team_venue_source"] = "home_team.venue_id" if fallback_applied else "event.venue_id"
    row["home_team_detail_for_fallback"] = {
        "id": home_team_detail.get("id"),
        "name": home_team_detail.get("name"),
        "venue_id": home_team_detail.get("venue_id"),
    } if home_team_detail else {}

    row["venue_summary"] = {
        "id": venue_detail.get("id") or effective_venue_id,
        "name": venue_detail.get("name"),
        "city": venue_detail.get("city"),
        "country": venue_detail.get("country"),
        "capacity": venue_detail.get("capacity"),
        "pitch_length_m": venue_detail.get("pitch_length_m"),
        "pitch_width_m": venue_detail.get("pitch_width_m"),
        "built_year": venue_detail.get("built_year"),
        "photo_url": img_url("venue", effective_venue_id),
    }
    row["image_assets"]["venue_photo"] = img_url("venue", effective_venue_id)
    return row


def collect_priority_event_ids(limit: int = 50) -> List[int]:
    ids: List[int] = []
    seen: set[int] = set()

    def add(value: Any) -> None:
        eid = safe_int(value)
        if eid and eid not in seen:
            seen.add(eid)
            ids.append(eid)

    # match_context deja conține selecțiile prioritare.
    ctx = load_json(DATA_DIR / "match_context.json", {})
    for item in extract_list(ctx):
        add(item.get("event_id") or item.get("id"))

    # signals/value_bets adaugă evenimente comerciale.
    for fname in ("value_bets.json", "signals.json"):
        payload = load_json(DATA_DIR / fname, {})
        for item in extract_list(payload):
            add(item.get("event_id") or item.get("id"))

    # predictions acoperă restul meciurilor principale.
    preds = load_json(DATA_DIR / "predictions.json", {})
    for item in extract_list(preds):
        ev = item.get("event") if isinstance(item.get("event"), dict) else {}
        add(ev.get("id") or item.get("event_id") or item.get("id"))

    return ids[:limit]


def build_events_window() -> None:
    date_from = os.environ.get("BETPREDICT_EVENTS_DATE_FROM") or today_ro()
    date_to = os.environ.get("BETPREDICT_EVENTS_DATE_TO") or date_default_to(30)
    params: Dict[str, Any] = {
        "date_from": date_from,
        "date_to": date_to,
        "league_id": os.environ.get("BETPREDICT_EVENTS_LEAGUE_ID"),
        "season_id": os.environ.get("BETPREDICT_EVENTS_SEASON_ID"),
        "team_id": os.environ.get("BETPREDICT_EVENTS_TEAM_ID"),
        "team_name": os.environ.get("BETPREDICT_EVENTS_TEAM_NAME"),
        "status": os.environ.get("BETPREDICT_EVENTS_STATUS"),
        "limit": 200,
    }

    print("\n[Pas 23] GET /api/v2/events/ exact window...")
    events, meta = get_all_events(params, "events_window", max_pages=25)
    normalized = [normalize_event_summary(ev) for ev in events]
    payload = {
        "updated_at": now_iso(),
        "source": "bsd_v2_events_exact",
        "endpoint": "/api/v2/events/",
        "params": {k: v for k, v in params.items() if v not in (None, "", [])},
        "count": len(normalized),
        "results": normalized,
        "pagination": meta,
        "notes": [
            "Folosește date_from/date_to conform BSD v2; fără days=N.",
            "Dacă nu setezi env, fereastra implicită este astăzi + 30 zile.",
        ],
    }
    save_json("events_window.json", payload)
    DEBUG["jobs"]["events_window"] = {"count": len(normalized), "params": payload["params"]}


def build_event_details() -> None:
    print("\n[Pas 23] GET /api/v2/events/{id}/ exact details...")
    detail_limit = int(os.environ.get("BETPREDICT_EVENT_DETAIL_LIMIT", "0") or 0)
    if detail_limit <= 0:
        DEBUG["jobs"]["event_detail_index"] = {"requested": 0, "saved": 0, "skipped": "light_collection_mode"}
        print("  details skip în modul light; folosim cache-ul existent")
        return
    event_ids = collect_priority_event_ids(limit=detail_limit)
    details: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for eid in event_ids:
        detail = get(f"{BASE_V2}/events/{eid}/", label=f"event_detail_{eid}")
        if not isinstance(detail, dict):
            errors.append({"event_id": eid, "reason": "missing_or_invalid_detail"})
            continue
        details.append(normalize_event_detail(detail))

    with_fallback = sum(1 for d in details if d.get("venue_fallback_applied"))
    with_weather = sum(1 for d in details if (d.get("weather_context") or {}).get("code") is not None)
    with_live_ws = sum(1 for d in details if d.get("live_websocket") is True)

    payload = {
        "updated_at": now_iso(),
        "source": "bsd_v2_event_detail_exact",
        "endpoint": "/api/v2/events/{id}/",
        "count": len(details),
        "summary": {
            "requested": len(event_ids),
            "saved": len(details),
            "errors": len(errors),
            "with_venue_fallback": with_fallback,
            "with_weather_code": with_weather,
            "with_live_websocket_true": with_live_ws,
        },
        "details": details,
        "errors": errors,
        "notes": [
            "Event detail este sursa core pentru carduri/header și foreign keys.",
            "Dacă venue_id este null, se folosește fallback home team venue_id conform documentației.",
        ],
    }
    save_json("event_detail_index.json", payload)
    save_debug("event_detail_exact_debug.json", {
        "updated_at": now_iso(),
        "event_ids": event_ids,
        "summary": payload["summary"],
        "errors": errors,
    })
    DEBUG["jobs"]["event_detail_index"] = payload["summary"]


def build_live_window_meta() -> None:
    """Pregătește un fișier mic care documentează exact parametrii live folosiți de fetch_live."""
    params = {
        "league_id": os.environ.get("BETPREDICT_LIVE_LEAGUE_ID"),
        "season_id": os.environ.get("BETPREDICT_LIVE_SEASON_ID"),
        "team_id": os.environ.get("BETPREDICT_LIVE_TEAM_ID"),
    }
    payload = {
        "updated_at": now_iso(),
        "source": "bsd_v2_live_window_meta",
        "endpoint": "/api/v2/events/live/",
        "query_parameters_supported": ["league_id", "season_id", "team_id"],
        "active_params": {k: v for k, v in params.items() if v not in (None, "", [])},
        "cache_rule": "live rows carry last_updated; fetch_live.py reuses enriched data when last_updated is unchanged.",
    }
    save_json("live_window_meta.json", payload)
    DEBUG["jobs"]["live_window_meta"] = {"active_params": payload["active_params"]}


def main() -> None:
    DEBUG["started_at"] = now_iso()
    if not API_KEY:
        warn("BSD_API_KEY nu este setat; scriptul nu poate interoga BSD.")
    build_events_window()
    build_best_odds()
    build_event_details()
    build_live_window_meta()
    QUOTA_STATE["updated_at"] = now_iso()
    save_json("api_quota.json", QUOTA_STATE)
    DEBUG["finished_at"] = now_iso()
    save_debug("bsd_v2_exact_debug.json", DEBUG)
    print("\nPasul 23 BSD v2 exact: OK")


if __name__ == "__main__":
    try:
        main()
    finally:
        DEBUG["finished_at"] = DEBUG.get("finished_at") or now_iso()
        save_debug("bsd_v2_exact_debug.json", DEBUG)
