#!/usr/bin/env python3
"""
BetPredict Pro — Match Data Pack Exact (Pasul 25)
=================================================

Implementează exact endpointurile BSD v2 din documentația atașată:
  - GET /api/v2/events/{id}/stats/
  - GET /api/v2/events/{id}/incidents/
  - GET /api/v2/events/{id}/lineups/
  - GET /api/v2/events/{id}/metadata/
  - GET /api/v2/events/{id}/player-stats/

Output:
  - data/match_data_pack.json
  - data/debug/match_data_pack_debug.json

Scop:
  - normalizare defensivă pentru UI;
  - player stats cu xG/xA;
  - timeline incidents;
  - metadata: jerseys, funfacts, ai_preview;
  - stats: shotmap, momentum, average_positions, xg_per_minute.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
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

DEBUG: Dict[str, Any] = {
    "started_at": None,
    "finished_at": None,
    "has_api_key": bool(API_KEY),
    "requests": [],
    "warnings": [],
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def img_url(kind: str, ident: Any) -> Optional[str]:
    return f"{IMG_BASE}/{kind}/{ident}/" if ident not in (None, "", "null") else None


def warn(message: str, **ctx: Any) -> None:
    DEBUG["warnings"].append({"message": message, "context": ctx, "time": now_iso()})
    print(f"  ⚠ {message}")


def as_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def as_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def pct(value: Any) -> Optional[float]:
    f = as_float(value)
    if f is None:
        return None
    return round(f, 1)


def get(url: str, label: str = "") -> Optional[Any]:
    started = datetime.now(timezone.utc)
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        elapsed_ms = round((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        DEBUG["requests"].append({
            "label": label,
            "url": url,
            "status": r.status_code,
            "elapsed_ms": elapsed_ms,
        })
        if r.status_code in (401, 403):
            warn("Auth BSD eșuat — verifică BSD_API_KEY", status=r.status_code, url=url)
            return None
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        elapsed_ms = round((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        DEBUG["requests"].append({
            "label": label,
            "url": url,
            "status": None,
            "elapsed_ms": elapsed_ms,
            "error": str(exc)[:220],
        })
        warn("Request eșuat", label=label, error=str(exc)[:220])
        return None


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
    print(f"  ✓ {filename}")


def save_debug(filename: str, payload: Any) -> None:
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    (DEBUG_DIR / filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def extract_list(payload: Any, keys: Tuple[str, ...] = ("results", "events", "data", "items")) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def compact_count(payload: Any) -> int:
    if payload is None:
        return 0
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        if isinstance(payload.get("count"), int):
            return int(payload.get("count") or 0)
        for key in ("results", "events", "player_stats", "incidents", "shotmap", "momentum", "xg_per_minute"):
            if isinstance(payload.get(key), list):
                return len(payload[key])
        return 1 if payload else 0
    return 0


def collect_priority_events(limit: int) -> List[Dict[str, Any]]:
    seeds: Dict[str, Dict[str, Any]] = {}

    def add(eid: Any, source: str, info: Optional[Dict[str, Any]] = None, score: float = 0) -> None:
        if eid in (None, "", "null"):
            return
        key = str(eid)
        row = seeds.setdefault(key, {"event_id": as_int(eid, 0), "sources": [], "priority_score": 0})
        if source not in row["sources"]:
            row["sources"].append(source)
        row["priority_score"] = max(row["priority_score"], score or 0)
        if info:
            for k, v in info.items():
                if v not in (None, "", []):
                    row[k] = v

    # match_context rămâne sursa principală, fiind deja prioritizat.
    ctx = load_json(DATA_DIR / "match_context.json", {})
    for item in extract_list(ctx):
        add(item.get("event_id") or item.get("id"), "match_context", {
            "home_team": item.get("home_team"),
            "away_team": item.get("away_team"),
            "home_team_id": item.get("home_team_id"),
            "away_team_id": item.get("away_team_id"),
            "league": item.get("league"),
            "league_id": item.get("league_id"),
            "event_date": item.get("event_date"),
        }, item.get("priority_score") or 0)

    for fname, source in (("value_bets.json", "value_bets"), ("signals.json", "signals")):
        payload = load_json(DATA_DIR / fname, {})
        for item in extract_list(payload):
            add(item.get("event_id") or item.get("id"), source, {
                "home_team": item.get("home_team"),
                "away_team": item.get("away_team"),
                "home_team_id": item.get("home_team_id"),
                "away_team_id": item.get("away_team_id"),
                "league": item.get("league") or item.get("league_name"),
                "league_id": item.get("league_id"),
                "event_date": item.get("event_date"),
            }, item.get("smartbet_score") or item.get("confidence") or 0)

    preds = load_json(DATA_DIR / "predictions.json", {})
    for item in extract_list(preds):
        ev = item.get("event") if isinstance(item.get("event"), dict) else {}
        add(ev.get("id") or item.get("event_id"), "predictions", {
            "home_team": ev.get("home_team"),
            "away_team": ev.get("away_team"),
            "home_team_id": ev.get("home_team_id"),
            "away_team_id": ev.get("away_team_id"),
            "league": item.get("_league_name") or ev.get("league_name"),
            "league_id": item.get("_league_id") or ev.get("league_id"),
            "event_date": ev.get("event_date"),
        }, item.get("smartbet_score") or 0)

    return sorted(seeds.values(), key=lambda x: x.get("priority_score") or 0, reverse=True)[:limit]


def normalize_metadata(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "available": False,
            "jerseys": None,
            "funfacts": [],
            "ai_preview": {"available": False, "text": None, "generated_at": None},
            "raw": None,
        }

    ai = payload.get("ai_preview")
    ai_obj: Dict[str, Any] = {"available": False, "text": None, "generated_at": None}
    if isinstance(ai, dict):
        txt = ai.get("text") or ai.get("summary") or ai.get("preview") or ai.get("content")
        ai_obj = {
            "available": bool(txt),
            "text": txt,
            "generated_at": ai.get("generated_at") or ai.get("created_at"),
            "raw": ai,
        }
    elif isinstance(ai, str):
        ai_obj = {"available": bool(ai.strip()), "text": ai.strip(), "generated_at": None}

    funfacts = payload.get("funfacts") or payload.get("pre_match_facts") or payload.get("facts") or []
    if isinstance(funfacts, dict):
        funfacts = [funfacts]
    if not isinstance(funfacts, list):
        funfacts = []

    return {
        "available": True,
        "jerseys": payload.get("jerseys"),
        "funfacts": funfacts,
        "funfacts_count": len(funfacts),
        "ai_preview": ai_obj,
        "raw": payload,
    }


def normalize_lineups(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "available": False,
            "lineup_status": "unavailable",
            "beta": False,
            "home": None,
            "away": None,
            "unavailable_players": None,
            "updated_at": None,
        }

    status = payload.get("lineup_status") or payload.get("status") or "unknown"
    lineups = payload.get("lineups") if isinstance(payload.get("lineups"), dict) else payload

    def side(which: str) -> Dict[str, Any]:
        obj = lineups.get(which) if isinstance(lineups, dict) else {}
        if not isinstance(obj, dict):
            obj = {}
        players = obj.get("players") or obj.get("starting") or obj.get("starting_xi") or []
        subs = obj.get("substitutes") or obj.get("bench") or []
        return {
            "team_id": obj.get("team_id"),
            "team_name": obj.get("team_name"),
            "formation": obj.get("formation"),
            "confidence": obj.get("confidence"),
            "players": [normalize_lineup_player(p) for p in players if isinstance(p, dict)],
            "substitutes": [normalize_lineup_player(p) for p in subs if isinstance(p, dict)],
        }

    return {
        "available": status != "unavailable" and bool(payload.get("lineups") or payload.get("home") or payload.get("away")),
        "lineup_status": status,
        "beta": bool(payload.get("beta")),
        "home": side("home"),
        "away": side("away"),
        "unavailable_players": payload.get("unavailable_players"),
        "updated_at": payload.get("updated_at"),
        "raw": payload,
    }


def normalize_lineup_player(p: Dict[str, Any]) -> Dict[str, Any]:
    pid = p.get("player_id") or p.get("id")
    return {
        "id": pid,
        "player_id": pid,
        "name": p.get("name") or p.get("player_name"),
        "short_name": p.get("short_name") or p.get("name") or p.get("player_name"),
        "position": p.get("position") or p.get("pos"),
        "jersey_number": p.get("jersey_number") or p.get("shirt_number") or p.get("number"),
        "ai_score": p.get("ai_score"),
        "image_url": img_url("player", pid),
        "raw": p,
    }


def build_player_name_map(lineups: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for side in ("home", "away"):
        obj = lineups.get(side) or {}
        for key in ("players", "substitutes"):
            for p in obj.get(key) or []:
                pid = p.get("player_id") or p.get("id")
                if pid is not None:
                    out[str(pid)] = p
    return out


def normalize_player_stats(payload: Any, lineups: Dict[str, Any]) -> Dict[str, Any]:
    rows = []
    raw_rows = extract_list(payload, ("player_stats", "results", "data", "items"))
    name_map = build_player_name_map(lineups)

    for item in raw_rows:
        pid = item.get("player_id") or item.get("id")
        ref = name_map.get(str(pid), {})
        rows.append({
            "id": item.get("id"),
            "player_id": pid,
            "event_id": item.get("event_id"),
            "team_id": item.get("team_id"),
            "name": item.get("name") or item.get("player") or ref.get("name"),
            "short_name": item.get("short_name") or ref.get("short_name") or item.get("name") or item.get("player"),
            "position": item.get("position") or ref.get("position"),
            "image_url": img_url("player", pid),
            "minutes_played": as_int(item.get("minutes_played"), 0),
            "rating": as_float(item.get("rating")),
            "goals": as_int(item.get("goals"), 0),
            "goal_assist": as_int(item.get("goal_assist") or item.get("assists"), 0),
            "expected_goals": as_float(item.get("expected_goals") or item.get("xg")),
            "expected_assists": as_float(item.get("expected_assists") or item.get("xa")),
            "total_shots": as_int(item.get("total_shots"), 0),
            "shots_on_target": as_int(item.get("shots_on_target"), 0),
            "total_pass": as_int(item.get("total_pass"), 0),
            "accurate_pass": as_int(item.get("accurate_pass"), 0),
            "pass_accuracy_pct": round((as_int(item.get("accurate_pass"), 0) or 0) / max(1, as_int(item.get("total_pass"), 0) or 0) * 100, 1) if item.get("total_pass") is not None else None,
            "key_pass": as_int(item.get("key_pass"), 0),
            "total_tackle": as_int(item.get("total_tackle"), 0),
            "interception": as_int(item.get("interception"), 0),
            "yellow_card": as_int(item.get("yellow_card"), 0),
            "red_card": as_int(item.get("red_card"), 0),
            "saves": as_int(item.get("saves")) if item.get("saves") is not None else None,
            "raw": item,
        })

    rows.sort(key=lambda r: (str(r.get("team_id") or ""), -(r.get("minutes_played") or 0), -(r.get("rating") or 0)))
    top_xg = sorted([r for r in rows if r.get("expected_goals") is not None], key=lambda r: r.get("expected_goals") or 0, reverse=True)[:5]
    top_xa = sorted([r for r in rows if r.get("expected_assists") is not None], key=lambda r: r.get("expected_assists") or 0, reverse=True)[:5]
    top_rating = sorted([r for r in rows if r.get("rating") is not None], key=lambda r: r.get("rating") or 0, reverse=True)[:5]

    return {
        "available": bool(rows),
        "count": len(rows),
        "players": rows,
        "top_xg": top_xg,
        "top_xa": top_xa,
        "top_rating": top_rating,
        "has_expected_assists": any(r.get("expected_assists") is not None for r in rows),
    }


def _extract_metric(side: Dict[str, Any], keys: Tuple[str, ...]) -> Any:
    for key in keys:
        value = side.get(key)
        if isinstance(value, dict):
            if "actual" in value:
                return value.get("actual")
            if "value" in value and ("total" in value or "pct" in value):
                return value
        if value is not None:
            return value
    return None


def normalize_stats(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "available": False,
            "home": {},
            "away": {},
            "shotmap": [],
            "momentum": [],
            "average_positions": {},
            "xg_per_minute": [],
        }

    root = payload.get("stats") if isinstance(payload.get("stats"), dict) else payload
    home = root.get("home") if isinstance(root.get("home"), dict) else {}
    away = root.get("away") if isinstance(root.get("away"), dict) else {}

    def side_summary(side: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "total_shots": _extract_metric(side, ("total_shots", "shots", "shots_total")),
            "ball_possession": _extract_metric(side, ("ball_possession", "possession", "possession_pct")),
            "crosses": _extract_metric(side, ("crosses",)),
            "dribbles": _extract_metric(side, ("dribbles",)),
            "long_balls": _extract_metric(side, ("long_balls",)),
            "attack": _extract_metric(side, ("attack", "attacks")),
            "ball_safe": _extract_metric(side, ("ball_safe",)),
            "dangerous_attack": _extract_metric(side, ("dangerous_attack", "dangerous_attacks")),
            "pass_accuracy_pct": _extract_metric(side, ("pass_accuracy_pct", "pass_accuracy")),
            "xg": _extract_metric(side, ("xg", "expected_goals")),
            "raw": side,
        }

    shotmap = payload.get("shotmap") if isinstance(payload.get("shotmap"), list) else []
    momentum = payload.get("momentum") if isinstance(payload.get("momentum"), list) else []
    average_positions = payload.get("average_positions") if isinstance(payload.get("average_positions"), dict) else {}
    xg_per_minute = payload.get("xg_per_minute") if isinstance(payload.get("xg_per_minute"), list) else []

    return {
        "available": bool(payload),
        "home": side_summary(home),
        "away": side_summary(away),
        "shotmap": shotmap,
        "shotmap_count": len(shotmap),
        "momentum": momentum,
        "momentum_count": len(momentum),
        "average_positions": average_positions,
        "average_positions_count": len(average_positions),
        "xg_per_minute": xg_per_minute,
        "xg_per_minute_count": len(xg_per_minute),
        "raw": payload,
    }


def normalize_incidents(payload: Any) -> Dict[str, Any]:
    rows = extract_list(payload, ("incidents", "results", "events", "data", "items"))
    timeline = []
    for item in rows:
        typ = item.get("type") or item.get("incident_type")
        timeline.append({
            "type": typ,
            "minute": as_int(item.get("minute") or item.get("time") or item.get("current_minute"), 0),
            "player": item.get("player"),
            "player_id": item.get("player_id"),
            "player_in": item.get("player_in"),
            "player_in_id": item.get("player_in_id"),
            "player_out": item.get("player_out"),
            "player_out_id": item.get("player_out_id"),
            "card_type": item.get("card_type"),
            "is_home": item.get("is_home"),
            "is_live": item.get("is_live"),
            "sequence": item.get("sequence"),
            "raw": item,
        })
    timeline.sort(key=lambda x: x.get("minute") or 0)
    return {
        "available": bool(timeline),
        "count": len(timeline),
        "timeline": timeline,
        "goals": [x for x in timeline if str(x.get("type") or "").lower() == "goal"],
        "cards": [x for x in timeline if str(x.get("type") or "").lower() == "card"],
        "substitutions": [x for x in timeline if str(x.get("type") or "").lower() == "substitution"],
        "var_decisions": [x for x in timeline if str(x.get("type") or "").lower() in ("vardecision", "var_decision")],
    }


def detail_from_existing(seed: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "event_id": seed.get("event_id"),
        "home_team": seed.get("home_team"),
        "away_team": seed.get("away_team"),
        "home_team_id": seed.get("home_team_id"),
        "away_team_id": seed.get("away_team_id"),
        "league": seed.get("league"),
        "league_id": seed.get("league_id"),
        "event_date": seed.get("event_date"),
        "priority_score": seed.get("priority_score"),
        "sources": seed.get("sources"),
    }


def build_pack() -> None:
    limit = int(os.environ.get("BETPREDICT_MATCH_PACK_LIMIT", "32") or 32)
    seeds = collect_priority_events(limit)

    entries: List[Dict[str, Any]] = []
    debug_entries: List[Dict[str, Any]] = []

    for seed in seeds:
        eid = seed.get("event_id")
        if not eid:
            continue
        print(f"  → pack {eid}: {seed.get('home_team','—')} vs {seed.get('away_team','—')}")

        stats_raw = get(f"{BASE_V2}/events/{eid}/stats/", f"stats_{eid}")
        incidents_raw = get(f"{BASE_V2}/events/{eid}/incidents/", f"incidents_{eid}")
        lineups_raw = get(f"{BASE_V2}/events/{eid}/lineups/", f"lineups_{eid}")
        metadata_raw = get(f"{BASE_V2}/events/{eid}/metadata/", f"metadata_{eid}")
        player_stats_raw = get(f"{BASE_V2}/events/{eid}/player-stats/", f"player_stats_{eid}")

        lineups = normalize_lineups(lineups_raw)
        player_stats = normalize_player_stats(player_stats_raw, lineups)
        stats = normalize_stats(stats_raw)
        incidents = normalize_incidents(incidents_raw)
        metadata = normalize_metadata(metadata_raw)

        row = {
            **detail_from_existing(seed),
            "stats": stats,
            "incidents": incidents,
            "lineups": lineups,
            "metadata": metadata,
            "player_stats": player_stats,
            "coverage": {
                "stats": stats.get("available"),
                "incidents": incidents.get("available"),
                "lineups": lineups.get("available"),
                "metadata": metadata.get("available"),
                "player_stats": player_stats.get("available"),
                "ai_preview": (metadata.get("ai_preview") or {}).get("available"),
                "xg_per_minute": bool(stats.get("xg_per_minute_count")),
                "shotmap": bool(stats.get("shotmap_count")),
                "average_positions": bool(stats.get("average_positions_count")),
                "expected_assists": player_stats.get("has_expected_assists"),
            },
        }
        entries.append(row)
        debug_entries.append({
            "event_id": eid,
            "counts": {
                "stats": compact_count(stats_raw),
                "incidents": compact_count(incidents_raw),
                "lineups": compact_count(lineups_raw),
                "metadata": compact_count(metadata_raw),
                "player_stats": compact_count(player_stats_raw),
            },
            "coverage": row["coverage"],
        })

    summary = {
        "events_requested": len(seeds),
        "events_saved": len(entries),
        "with_stats": sum(1 for r in entries if r["coverage"]["stats"]),
        "with_incidents": sum(1 for r in entries if r["coverage"]["incidents"]),
        "with_lineups": sum(1 for r in entries if r["coverage"]["lineups"]),
        "with_metadata": sum(1 for r in entries if r["coverage"]["metadata"]),
        "with_player_stats": sum(1 for r in entries if r["coverage"]["player_stats"]),
        "with_ai_preview": sum(1 for r in entries if r["coverage"]["ai_preview"]),
        "with_xa": sum(1 for r in entries if r["coverage"]["expected_assists"]),
        "with_shotmap": sum(1 for r in entries if r["coverage"]["shotmap"]),
        "with_xg_per_minute": sum(1 for r in entries if r["coverage"]["xg_per_minute"]),
    }

    payload = {
        "updated_at": now_iso(),
        "source": "bsd_v2_match_data_pack_exact",
        "endpoints": [
            "/api/v2/events/{id}/stats/",
            "/api/v2/events/{id}/incidents/",
            "/api/v2/events/{id}/lineups/",
            "/api/v2/events/{id}/metadata/",
            "/api/v2/events/{id}/player-stats/",
        ],
        "count": len(entries),
        "summary": summary,
        "results": entries,
        "notes": [
            "Stats, incidents și player-stats sunt cel mai utile live/post-match; pre-match pot fi goale.",
            "Metadata poate lipsi pentru meciuri care nu sunt în fereastra de AI preview.",
            "Lineups poate fi confirmed, predicted sau unavailable; UI citește lineup_status.",
        ],
    }
    save_json("match_data_pack.json", payload)
    save_debug("match_data_pack_debug.json", {
        "updated_at": now_iso(),
        "summary": summary,
        "events": debug_entries,
        "requests": DEBUG["requests"],
        "warnings": DEBUG["warnings"],
    })


def main() -> None:
    DEBUG["started_at"] = now_iso()
    if not API_KEY:
        warn("BSD_API_KEY nu este setat; endpointurile BSD nu vor funcționa.")
    build_pack()
    DEBUG["finished_at"] = now_iso()


if __name__ == "__main__":
    try:
        main()
    finally:
        DEBUG["finished_at"] = DEBUG.get("finished_at") or now_iso()
        save_debug("match_data_pack_runtime_debug.json", DEBUG)
