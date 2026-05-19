#!/usr/bin/env python3
"""
BetPredict Pro — League Metadata Pack (BSD API v2)
==================================================

Implementează endpointurile de ligă din documentația BSD v2:
  - GET /api/v2/leagues/
  - GET /api/v2/leagues/{id}/
  - GET /api/v2/leagues/{id}/season/
  - GET /api/v2/leagues/{id}/seasons/
  - GET /api/v2/leagues/{id}/standings/?season_id=...
  - GET /api/v2/leagues/{id}/venues/?season_id=...
  - GET /api/v2/leagues/{id}/seasons/{season_id}/venues/

Output:
  - data/league_metadata.json
  - data/league_lookup.json
  - data/debug/league_metadata_debug.json

Pasul 3 adaugă rândurile compacte de standings pentru ca motorul să poată
calcula forța echipelor, diferența de formă și ajustarea probabilităților.

Rulează în workflow după fetch_daily.py. Nu schimbă UI-ul direct; pregătește
baza curată pentru Pasul 2: folosire în carduri/scoruri/filtre.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests


API_KEY = os.environ.get("BSD_API_KEY", "").strip()
BASE_V2 = "https://sports.bzzoiro.com/api/v2"
IMG_BASE = "https://sports.bzzoiro.com/img"
HEADERS = {"Authorization": f"Token {API_KEY}"} if API_KEY else {}

ROOT = Path(__file__).parent.parent.resolve()
DATA_DIR = ROOT / "data"
DEBUG_DIR = DATA_DIR / "debug"

REQUEST_TIMEOUT = int(os.environ.get("BETPREDICT_API_TIMEOUT", "25") or 25)
REQUEST_SLEEP_SEC = float(os.environ.get("BETPREDICT_LEAGUE_META_SLEEP", "0.08") or 0.08)
MAX_LEAGUES = int(os.environ.get("BETPREDICT_LEAGUE_META_LIMIT", "200") or 200)

DEBUG: Dict[str, Any] = {
    "started_at": None,
    "finished_at": None,
    "has_api_key": bool(API_KEY),
    "requests": [],
    "warnings": [],
    "summary": {},
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def img_url(kind: str, ident: Any) -> Optional[str]:
    return f"{IMG_BASE}/{kind}/{ident}/" if ident not in (None, "", "null") else None


def safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if value in (None, "", "null"):
            return default
        return int(float(value))
    except Exception:
        return default


def count_payload(payload: Any) -> int:
    if isinstance(payload, list):
        return len(payload)
    if not isinstance(payload, dict):
        return 0
    if isinstance(payload.get("count"), int):
        return int(payload["count"])
    for key in ("results", "standings", "seasons", "venues"):
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
        if isinstance(value, dict):
            return sum(len(v) for v in value.values() if isinstance(v, list))
    groups = payload.get("groups")
    if isinstance(groups, dict):
        return sum(len(v) for v in groups.values() if isinstance(v, list))
    return 0


def warn(message: str, **context: Any) -> None:
    DEBUG["warnings"].append({"message": message, "context": context, "time": now_iso()})
    print(f"  ⚠ {message}")


def save_json(filename: str, payload: Any) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / filename
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    print(f"  ✓ {filename} ({count_payload(payload)})")


def save_debug(filename: str, payload: Any) -> None:
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    path = DEBUG_DIR / filename
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _request_url_for_log(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        return parsed.path
    return url.replace(BASE_V2, "")


def get_json(url: str, params: Optional[Dict[str, Any]] = None, label: str = "") -> Any:
    clean_params = {k: v for k, v in (params or {}).items() if v not in (None, "", [])}
    started = time.time()
    status = None
    ok = False
    err = None

    try:
        resp = requests.get(url, headers=HEADERS, params=clean_params or None, timeout=REQUEST_TIMEOUT)
        status = resp.status_code
        ok = resp.ok
        if not resp.ok:
            err = resp.text[:220]
            return None
        if not resp.content:
            return None
        return resp.json()
    except Exception as exc:
        err = str(exc)
        warn("Request BSD eșuat", label=label, url=url, params=clean_params, error=err)
        return None
    finally:
        DEBUG["requests"].append({
            "label": label,
            "url": _request_url_for_log(url),
            "params": clean_params,
            "status": status,
            "ok": ok,
            "elapsed_ms": int((time.time() - started) * 1000),
            "error": err,
        })
        if REQUEST_SLEEP_SEC > 0:
            time.sleep(REQUEST_SLEEP_SEC)


def extract_results(payload: Any, preferred_key: str = "results") -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    value = payload.get(preferred_key)
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    for key in ("results", "seasons", "venues", "standings"):
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []


def get_all_pages(url: str, params: Optional[Dict[str, Any]] = None, label: str = "", max_pages: int = 25) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    pages = 0
    next_url = url
    page_params = dict(params or {})
    limit = safe_int(page_params.get("limit"), 200) or 200

    while next_url and pages < max_pages:
        payload = get_json(next_url, page_params, label=f"{label}_p{pages + 1}")
        pages += 1
        batch = extract_results(payload)
        results.extend(batch)

        next_from_api = payload.get("next") if isinstance(payload, dict) else None
        if next_from_api:
            next_url = str(next_from_api)
            page_params = {}
            continue

        total = payload.get("count") if isinstance(payload, dict) else None
        offset = safe_int(page_params.get("offset"), 0) or 0
        if isinstance(total, int) and len(results) < total and len(batch) >= limit:
            page_params["offset"] = offset + limit
            next_url = url
            continue

        break

    return results, {"pages": pages, "fetched": len(results), "limit": limit}


def normalize_current_season(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    season = payload.get("season") if isinstance(payload.get("season"), dict) else payload
    sid = safe_int(season.get("id"))
    return {
        "id": sid,
        "name": season.get("name"),
        "year": season.get("year"),
        "start_date": season.get("start_date"),
        "end_date": season.get("end_date"),
        "is_current": season.get("is_current"),
        "raw": season,
    } if sid else {}



def compact_standings_row(row: Dict[str, Any], group_name: Optional[str] = None) -> Dict[str, Any]:
    """Păstrează câmpurile necesare motorului, fără să umfle inutil JSON-ul."""
    team = row.get("team") if isinstance(row.get("team"), dict) else {}
    team_id = safe_int(row.get("team_id") or team.get("id"))
    played = safe_int(row.get("played"), 0) or 0
    won = safe_int(row.get("won"), 0) or 0
    drawn = safe_int(row.get("drawn"), 0) or 0
    lost = safe_int(row.get("lost"), 0) or 0
    gf = safe_int(row.get("gf"), 0) or 0
    ga = safe_int(row.get("ga"), 0) or 0
    gd = safe_int(row.get("gd"), gf - ga) or 0
    pts = safe_int(row.get("pts") or row.get("points"), 0) or 0
    xg_games = safe_int(row.get("xg_games"), 0) or 0
    return {
        "position": safe_int(row.get("position") or row.get("rank")),
        "team_id": team_id,
        "team_name": row.get("team_name") or team.get("name") or row.get("name"),
        "played": played,
        "won": won,
        "drawn": drawn,
        "lost": lost,
        "gf": gf,
        "ga": ga,
        "gd": gd,
        "pts": pts,
        "xgf": row.get("xgf"),
        "xga": row.get("xga"),
        "xgd": row.get("xgd"),
        "xg_games": xg_games,
        "form": row.get("form"),
        "live": row.get("live"),
        "group": group_name,
    }


def compact_standings_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [compact_standings_row(r) for r in rows if isinstance(r, dict)]

def summarize_standings(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {"available": False, "teams": 0, "grouped": False, "groups": 0, "rows": []}

    rows = payload.get("standings")
    groups = payload.get("groups")
    flat_rows: List[Dict[str, Any]] = []

    if isinstance(rows, list):
        flat_rows = [x for x in rows if isinstance(x, dict)]
        teams = len(flat_rows)
        sample = flat_rows[:6]
    elif isinstance(groups, dict):
        sample = []
        for group_name, group_rows in groups.items():
            if not isinstance(group_rows, list):
                continue
            for row in group_rows:
                if not isinstance(row, dict):
                    continue
                rr = dict(row)
                rr.setdefault("group", group_name)
                flat_rows.append(rr)
                if len(sample) < 6:
                    sample.append(rr)
        teams = len(flat_rows)
    else:
        teams = 0
        sample = []

    return {
        "available": teams > 0,
        "teams": teams,
        "grouped": bool(payload.get("grouped") or isinstance(groups, dict)),
        "groups": len(groups) if isinstance(groups, dict) else 0,
        "season": payload.get("season"),
        "sample": compact_standings_rows(sample)[:6],
        "rows": compact_standings_rows(flat_rows),
    }


def summarize_venues(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    host_flags = {"opening": 0, "final": 0, "third_place": 0}
    rounds: Dict[str, int] = {}
    countries: Dict[str, int] = {}
    sample: List[Dict[str, Any]] = []

    for row in rows:
        venue = row.get("venue") if isinstance(row.get("venue"), dict) else row
        if row.get("hosts_opening"):
            host_flags["opening"] += 1
        if row.get("hosts_final"):
            host_flags["final"] += 1
        if row.get("hosts_third_place"):
            host_flags["third_place"] += 1

        country = row.get("host_country_code") or venue.get("country_code") or venue.get("country")
        if country:
            countries[str(country)] = countries.get(str(country), 0) + 1

        for rd in row.get("rounds") or []:
            rounds[str(rd)] = rounds.get(str(rd), 0) + 1

        if len(sample) < 8:
            sample.append({
                "assignment_id": row.get("id"),
                "venue_id": venue.get("id") or row.get("venue_id"),
                "name": venue.get("name"),
                "city": venue.get("city"),
                "country": venue.get("country"),
                "country_code": venue.get("country_code") or row.get("host_country_code"),
                "capacity": venue.get("capacity"),
                "hosts_opening": row.get("hosts_opening"),
                "hosts_final": row.get("hosts_final"),
                "hosts_third_place": row.get("hosts_third_place"),
                "rounds": row.get("rounds"),
                "image_url": img_url("venue", venue.get("id") or row.get("venue_id")),
            })

    return {
        "available": len(rows) > 0,
        "count": len(rows),
        "host_flags": host_flags,
        "rounds": rounds,
        "countries": countries,
        "sample": sample,
    }


def first_current_season_from_sources(detail: Any, season_endpoint: Any, seasons: List[Dict[str, Any]]) -> Dict[str, Any]:
    for source in (
        normalize_current_season(season_endpoint),
        normalize_current_season((detail or {}).get("current_season") if isinstance(detail, dict) else None),
    ):
        if source.get("id"):
            return source

    for season in seasons:
        if season.get("is_current") and season.get("id"):
            return normalize_current_season(season)

    return {}


def build_league_record(league: Dict[str, Any]) -> Dict[str, Any]:
    lid = safe_int(league.get("id"))
    if not lid:
        return {}

    print(f"  → liga {lid}: {league.get('name', '—')}")

    detail = get_json(f"{BASE_V2}/leagues/{lid}/", label=f"league_detail_{lid}") or {}
    current_season_payload = get_json(f"{BASE_V2}/leagues/{lid}/season/", label=f"league_current_season_{lid}")
    seasons, seasons_meta = get_all_pages(
        f"{BASE_V2}/leagues/{lid}/seasons/",
        {"limit": 200},
        label=f"league_seasons_{lid}",
        max_pages=5,
    )

    current_season = first_current_season_from_sources(detail, current_season_payload, seasons)
    season_id = current_season.get("id")

    standings_payload = get_json(
        f"{BASE_V2}/leagues/{lid}/standings/",
        {"season_id": season_id} if season_id else {},
        label=f"league_standings_{lid}",
    ) or {}

    league_venues, league_venues_meta = get_all_pages(
        f"{BASE_V2}/leagues/{lid}/venues/",
        {"season_id": season_id, "limit": 200} if season_id else {"limit": 200},
        label=f"league_venues_{lid}",
        max_pages=5,
    )

    season_venues: List[Dict[str, Any]] = []
    season_venues_meta: Dict[str, Any] = {"pages": 0, "fetched": 0, "limit": 200}
    if season_id:
        season_venues, season_venues_meta = get_all_pages(
            f"{BASE_V2}/leagues/{lid}/seasons/{season_id}/venues/",
            {"limit": 200},
            label=f"league_season_venues_{lid}_{season_id}",
            max_pages=5,
        )

    source_league = detail if isinstance(detail, dict) and detail else league
    return {
        "id": lid,
        "name": source_league.get("name") or league.get("name"),
        "country": source_league.get("country") or league.get("country"),
        "is_women": source_league.get("is_women"),
        "is_active": source_league.get("is_active"),
        "league_logo": img_url("league", lid),
        "current_season": current_season,
        "season_id": season_id,
        "seasons": {
            "count": len(seasons),
            "pagination": seasons_meta,
            "items": seasons,
        },
        "standings": summarize_standings(standings_payload),
        "venues": {
            "league_endpoint": summarize_venues(league_venues),
            "league_endpoint_pagination": league_venues_meta,
            "season_endpoint": summarize_venues(season_venues),
            "season_endpoint_pagination": season_venues_meta,
        },
        "api_endpoints": {
            "list": "/api/v2/leagues/",
            "detail": f"/api/v2/leagues/{lid}/",
            "current_season": f"/api/v2/leagues/{lid}/season/",
            "all_seasons": f"/api/v2/leagues/{lid}/seasons/",
            "standings": f"/api/v2/leagues/{lid}/standings/?season_id={season_id}" if season_id else f"/api/v2/leagues/{lid}/standings/",
            "venues": f"/api/v2/leagues/{lid}/venues/?season_id={season_id}" if season_id else f"/api/v2/leagues/{lid}/venues/",
            "season_venues": f"/api/v2/leagues/{lid}/seasons/{season_id}/venues/" if season_id else None,
        },
    }


def build_lookup(leagues: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_id: Dict[str, Dict[str, Any]] = {}
    by_name: Dict[str, int] = {}

    for lg in leagues:
        lid = lg.get("id")
        if not lid:
            continue
        compact = {
            "id": lid,
            "name": lg.get("name"),
            "country": lg.get("country"),
            "is_active": lg.get("is_active"),
            "is_women": lg.get("is_women"),
            "league_logo": lg.get("league_logo"),
            "season_id": lg.get("season_id"),
            "season_name": (lg.get("current_season") or {}).get("name"),
            "standings_teams": (lg.get("standings") or {}).get("teams"),
            "venues_count": ((lg.get("venues") or {}).get("season_endpoint") or {}).get("count")
                or ((lg.get("venues") or {}).get("league_endpoint") or {}).get("count"),
        }
        by_id[str(lid)] = compact
        name = str(compact.get("name") or "").strip().lower()
        if name:
            by_name[name] = lid

    return {
        "updated_at": now_iso(),
        "source": "league_metadata_pack_v1",
        "count": len(by_id),
        "by_id": by_id,
        "by_name": by_name,
    }


def main() -> int:
    DEBUG["started_at"] = now_iso()
    if not API_KEY:
        warn("BSD_API_KEY nu este setat; league metadata nu poate fi actualizat.")
        save_debug("league_metadata_debug.json", DEBUG)
        return 1

    print("\n[League Metadata] BSD v2 league / season / standings / venues...")
    leagues, list_meta = get_all_pages(
        f"{BASE_V2}/leagues/",
        {"is_active": "true", "limit": 200},
        label="leagues",
        max_pages=10,
    )

    if MAX_LEAGUES > 0:
        leagues = leagues[:MAX_LEAGUES]

    records: List[Dict[str, Any]] = []
    for league in leagues:
        try:
            record = build_league_record(league)
            if record:
                records.append(record)
        except Exception as exc:
            warn("League metadata record eșuat", league_id=league.get("id"), league_name=league.get("name"), error=str(exc))

    summary = {
        "leagues_requested": len(leagues),
        "leagues_saved": len(records),
        "with_current_season": sum(1 for r in records if r.get("season_id")),
        "with_standings": sum(1 for r in records if (r.get("standings") or {}).get("available")),
        "with_league_venues": sum(1 for r in records if ((r.get("venues") or {}).get("league_endpoint") or {}).get("available")),
        "with_season_venues": sum(1 for r in records if ((r.get("venues") or {}).get("season_endpoint") or {}).get("available")),
    }

    payload = {
        "updated_at": now_iso(),
        "source": "league_metadata_pack_v1",
        "base_url": BASE_V2,
        "list_endpoint": "/api/v2/leagues/",
        "list_pagination": list_meta,
        "count": len(records),
        "summary": summary,
        "results": records,
        "notes": [
            "League metadata folosește season_id curent pentru standings și venues, ca să nu se amestece sezoanele.",
            "Endpointul /leagues/{id}/seasons/{season_id}/venues/ este preferat pentru filtre de turneu/knockout.",
            "Pasul 3: standings.rows este folosit de motorul League Strength pentru ajustarea probabilităților.",
        ],
    }

    save_json("league_metadata.json", payload)
    save_json("league_lookup.json", build_lookup(records))

    DEBUG["summary"] = summary
    DEBUG["finished_at"] = now_iso()
    save_debug("league_metadata_debug.json", DEBUG)
    print("[League Metadata] OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        DEBUG["finished_at"] = DEBUG.get("finished_at") or now_iso()
        save_debug("league_metadata_debug.json", DEBUG)
