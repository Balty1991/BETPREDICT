#!/usr/bin/env python3
"""
BetPredict Pro — Live Scores Fetcher (v17 Live Intelligence)
============================================================
Pasul 17: Live Intelligence — live center cu momentum, incidents, stats și semnale explicabile.

Rulează frecvent via GitHub Actions.
Endpointuri folosite:
  - GET /api/v2/events/live/
  - GET /api/v2/events/{event_id}/stats/
  - GET /api/v2/events/{event_id}/incidents/
  - GET /api/v2/events/{event_id}/lineups/
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

API_KEY = os.environ.get("BSD_API_KEY", "").strip()
BASE_V2 = "https://sports.bzzoiro.com/api/v2"
HEADERS = {"Authorization": f"Token {API_KEY}"} if API_KEY else {}
DATA_DIR = Path(__file__).parent.parent / "data"
DEBUG_DIR = DATA_DIR / "debug"

# Ligi urmărite. Set gol = toate ligile live.
WATCHED_LEAGUE_IDS = {1, 2, 3, 4, 5, 6, 7, 8, 10, 23, 17, 18, 20, 28, 30, 52}
LIVE_ENRICH_LIMIT = int(os.environ.get("BETPREDICT_LIVE_ENRICH_LIMIT", "18") or 18)

DEBUG: Dict[str, Any] = {
    "started_at": None,
    "finished_at": None,
    "has_api_key": bool(API_KEY),
    "requests": [],
    "warnings": [],
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def as_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def get_minute(ev: Dict[str, Any]) -> int:
    candidates = [ev.get("current_minute"), ev.get("minute"), ev.get("time_elapsed"), ev.get("elapsed")]
    t = ev.get("time")
    if isinstance(t, dict):
        candidates.extend([t.get("current"), t.get("elapsed")])
    for v in candidates:
        n = as_int(v, -1)
        if n >= 0:
            return n
    return 0


def count_payload(data: Any) -> int:
    if isinstance(data, list):
        return len(data)
    if not isinstance(data, dict):
        return 0
    if isinstance(data.get("count"), int):
        return int(data.get("count") or 0)
    for key in ("events", "results", "incidents", "lineups", "player_stats", "stats", "shotmap", "items"):
        v = data.get(key)
        if isinstance(v, list):
            return len(v)
        if isinstance(v, dict):
            return 1 if v else 0
    return 1 if data else 0


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
    (DEBUG_DIR / filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get(url: str, params: Optional[Dict[str, Any]] = None, label: str = "") -> Optional[Any]:
    params = {k: v for k, v in (params or {}).items() if v is not None}
    started = datetime.now(timezone.utc)
    try:
        r = requests.get(url, headers=HEADERS, params=params or None, timeout=25)
        elapsed_ms = round((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        DEBUG["requests"].append({
            "label": label,
            "url": url,
            "params": params,
            "status": r.status_code,
            "elapsed_ms": elapsed_ms,
        })
        if r.status_code in (401, 403):
            warn("Auth BSD eșuat — verifică BSD_API_KEY", url=url, status=r.status_code)
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
            "params": params,
            "status": None,
            "elapsed_ms": elapsed_ms,
            "error": str(exc)[:180],
        })
        warn("Request live eșuat", label=label, error=str(exc)[:180])
        return None


def extract_events(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("events", "results", "data"):
            v = payload.get(key)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    return []


def normalize_event(ev: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(ev)
    out.setdefault("id", ev.get("event_id"))
    out.setdefault("event_id", ev.get("id"))
    out["event_id"] = out.get("event_id") or out.get("id")
    out.setdefault("home_score", ev.get("score_home") if ev.get("score_home") is not None else ev.get("home_goals"))
    out.setdefault("away_score", ev.get("score_away") if ev.get("score_away") is not None else ev.get("away_goals"))
    out["home_score"] = as_int(out.get("home_score"), 0)
    out["away_score"] = as_int(out.get("away_score"), 0)
    out["minute"] = get_minute(out)
    lg = ev.get("league") if isinstance(ev.get("league"), dict) else {}
    out["league_id"] = ev.get("league_id") or lg.get("id")
    out["league_name"] = ev.get("league_name") or lg.get("name")
    return out


def flatten_stats(stats_payload: Any) -> Dict[str, Any]:
    """Extrage valori uzuale fără să depindem de o singură schemă BSD."""
    if not isinstance(stats_payload, dict):
        return {}
    root = stats_payload.get("stats") if isinstance(stats_payload.get("stats"), dict) else stats_payload
    home = root.get("home") if isinstance(root.get("home"), dict) else {}
    away = root.get("away") if isinstance(root.get("away"), dict) else {}

    def pick(side: Dict[str, Any], keys: List[str]) -> Optional[float]:
        for k in keys:
            v = as_float(side.get(k))
            if v is not None:
                return v
        return None

    # fallback: unele API-uri trimit direct xg_home / shots_on_target_home
    xg_h = pick(home, ["xg", "expected_goals", "expectedGoals"]) or as_float(root.get("xg_home"))
    xg_a = pick(away, ["xg", "expected_goals", "expectedGoals"]) or as_float(root.get("xg_away"))
    sot_h = pick(home, ["shots_on_target", "shotsOnTarget", "sot"]) or as_float(root.get("shots_on_target_home"))
    sot_a = pick(away, ["shots_on_target", "shotsOnTarget", "sot"]) or as_float(root.get("shots_on_target_away"))
    shots_h = pick(home, ["shots", "total_shots", "shotsTotal"]) or as_float(root.get("shots_home"))
    shots_a = pick(away, ["shots", "total_shots", "shotsTotal"]) or as_float(root.get("shots_away"))
    poss_h = pick(home, ["possession", "possession_pct", "ball_possession"]) or as_float(root.get("possession_home"))
    poss_a = pick(away, ["possession", "possession_pct", "ball_possession"]) or as_float(root.get("possession_away"))
    attacks_h = pick(home, ["dangerous_attacks", "dangerousAttacks"]) or as_float(root.get("dangerous_attacks_home"))
    attacks_a = pick(away, ["dangerous_attacks", "dangerousAttacks"]) or as_float(root.get("dangerous_attacks_away"))

    if poss_h is not None and poss_a is None:
        poss_a = max(0, 100 - poss_h)

    momentum = stats_payload.get("momentum") if isinstance(stats_payload.get("momentum"), list) else []
    xg_per_minute = stats_payload.get("xg_per_minute") if isinstance(stats_payload.get("xg_per_minute"), list) else []
    shotmap = stats_payload.get("shotmap") if isinstance(stats_payload.get("shotmap"), list) else []

    return {
        "xg_home": xg_h,
        "xg_away": xg_a,
        "shots_on_target_home": sot_h,
        "shots_on_target_away": sot_a,
        "shots_home": shots_h,
        "shots_away": shots_a,
        "possession_home": poss_h,
        "possession_away": poss_a,
        "dangerous_attacks_home": attacks_h,
        "dangerous_attacks_away": attacks_a,
        "momentum_points": len(momentum),
        "xg_per_minute_points": len(xg_per_minute),
        "shotmap_count": len(shotmap),
    }


def extract_incidents(inc_payload: Any) -> List[Dict[str, Any]]:
    if isinstance(inc_payload, list):
        return [x for x in inc_payload if isinstance(x, dict)]
    if isinstance(inc_payload, dict):
        v = inc_payload.get("incidents") or inc_payload.get("results") or inc_payload.get("events")
        if isinstance(v, list):
            return [x for x in v if isinstance(x, dict)]
    return []


def lineup_status(lineups_payload: Any) -> str:
    if not isinstance(lineups_payload, dict):
        return "unavailable"
    return str(lineups_payload.get("lineup_status") or lineups_payload.get("status") or "available")


def pressure_side(stats: Dict[str, Any]) -> Tuple[str, float]:
    xg_h = as_float(stats.get("xg_home"), 0) or 0
    xg_a = as_float(stats.get("xg_away"), 0) or 0
    sot_h = as_float(stats.get("shots_on_target_home"), 0) or 0
    sot_a = as_float(stats.get("shots_on_target_away"), 0) or 0
    da_h = as_float(stats.get("dangerous_attacks_home"), 0) or 0
    da_a = as_float(stats.get("dangerous_attacks_away"), 0) or 0
    score = (xg_h - xg_a) * 38 + (sot_h - sot_a) * 7 + (da_h - da_a) * 0.35
    if abs(score) < 8:
        return "balanced", round(score, 1)
    return ("home" if score > 0 else "away"), round(score, 1)


def live_phase(minute: int, period: str = "") -> str:
    p = str(period or "").upper()
    if "HT" in p:
        return "half-time"
    if minute < 30:
        return "early"
    if minute < 60:
        return "mid-game"
    if minute < 80:
        return "late build-up"
    return "endgame"


def build_live_signals(ev: Dict[str, Any], stats: Dict[str, Any], incidents: List[Dict[str, Any]], lstatus: str) -> List[Dict[str, Any]]:
    signals: List[Dict[str, Any]] = []
    minute = get_minute(ev)
    hs, aw = as_int(ev.get("home_score"), 0), as_int(ev.get("away_score"), 0)
    total_goals = hs + aw
    xg_h = as_float(stats.get("xg_home"), 0) or 0
    xg_a = as_float(stats.get("xg_away"), 0) or 0
    sot_h = as_float(stats.get("shots_on_target_home"), 0) or 0
    sot_a = as_float(stats.get("shots_on_target_away"), 0) or 0
    side, score = pressure_side(stats)
    cards = [i for i in incidents if str(i.get("type") or i.get("incident_type") or "").lower() in ("yellow_card", "red_card", "card")]
    goals = [i for i in incidents if "goal" in str(i.get("type") or i.get("incident_type") or "").lower()]

    if side != "balanced" and abs(score) >= 18:
        signals.append({
            "type": "momentum",
            "level": "strong" if abs(score) >= 30 else "medium",
            "label": "presiune acasă" if side == "home" else "presiune deplasare",
            "note": f"Momentum {side}: xG {xg_h:.2f}-{xg_a:.2f}, SOT {int(sot_h)}-{int(sot_a)}.",
        })
    elif xg_h + xg_a >= 1.4 and total_goals <= 1 and minute >= 45:
        signals.append({
            "type": "goals_pressure",
            "level": "medium",
            "label": "xG peste scor",
            "note": f"xG total {xg_h + xg_a:.2f} la scor {hs}-{aw}; meci cu potențial de gol suplimentar.",
        })

    if minute >= 65 and abs(hs - aw) <= 1:
        signals.append({
            "type": "late_game",
            "level": "watch",
            "label": "final strâns",
            "note": f"Minut {minute}, diferență mică de scor; volatilitate live crescută.",
        })

    if len(cards) >= 4:
        signals.append({
            "type": "cards",
            "level": "watch",
            "label": "meci tensionat",
            "note": f"{len(cards)} cartonașe detectate în timeline.",
        })

    if lstatus and lstatus not in ("unavailable", "available"):
        signals.append({
            "type": "lineups",
            "level": "info",
            "label": f"lineup {lstatus}",
            "note": "Status lineup disponibil pentru context live.",
        })

    if not signals:
        signals.append({
            "type": "neutral",
            "level": "low",
            "label": "fără semnal live major",
            "note": "Datele live nu indică încă presiune clară sau edge operațional.",
        })
    return signals[:5]


def enrich_live_event(ev: Dict[str, Any]) -> Dict[str, Any]:
    eid = ev.get("event_id") or ev.get("id")
    stats_payload = get(f"{BASE_V2}/events/{eid}/stats/", label=f"live_stats_{eid}") if eid else None
    inc_payload = get(f"{BASE_V2}/events/{eid}/incidents/", label=f"live_incidents_{eid}") if eid else None
    lineup_payload = get(f"{BASE_V2}/events/{eid}/lineups/", label=f"live_lineups_{eid}") if eid else None

    stats = flatten_stats(stats_payload)
    incidents = extract_incidents(inc_payload)
    lstatus = lineup_status(lineup_payload)
    phase = live_phase(get_minute(ev), ev.get("period") or ev.get("status"))
    side, pressure = pressure_side(stats)
    signals = build_live_signals(ev, stats, incidents, lstatus)

    return {
        "event_id": eid,
        "home_team": ev.get("home_team"),
        "away_team": ev.get("away_team"),
        "home_team_id": ev.get("home_team_id"),
        "away_team_id": ev.get("away_team_id"),
        "league_id": ev.get("league_id"),
        "league_name": ev.get("league_name"),
        "event_date": ev.get("event_date"),
        "status": ev.get("status"),
        "period": ev.get("period"),
        "current_minute": get_minute(ev),
        "home_score": ev.get("home_score"),
        "away_score": ev.get("away_score"),
        "event": ev,
        "phase": phase,
        "pressure_side": side,
        "pressure_score": pressure,
        "stats_summary": stats,
        "incidents_count": len(incidents),
        "recent_incidents": incidents[-6:],
        "lineup_status": lstatus,
        "resources": {
            "stats": count_payload(stats_payload),
            "incidents": len(incidents),
            "lineups": count_payload(lineup_payload),
        },
        "live_signals": signals,
        "coverage_score": sum(1 for v in (stats, incidents, lineup_payload) if count_payload(v) > 0),
    }


def save_empty() -> None:
    payload = {"updated_at": now_iso(), "count": 0, "events": [], "source": "bsd_v2_events_live"}
    save_json("live.json", payload)
    save_json("live_intelligence.json", {
        "updated_at": now_iso(),
        "source": "live_intelligence_v1",
        "count": 0,
        "events": [],
        "summary": {"live_events": 0, "enriched_events": 0, "with_stats": 0, "with_incidents": 0, "with_lineups": 0, "strong_signals": 0},
        "notes": ["Nu există meciuri live la ultima rulare."],
    })


def fetch_live() -> None:
    print("🔴 Live Scores + Intelligence...")
    payload = get(f"{BASE_V2}/events/live/", label="events_live")
    events = extract_events(payload)
    normalized: List[Dict[str, Any]] = []
    for ev in events:
        row = normalize_event(ev)
        league_id = row.get("league_id")
        if not WATCHED_LEAGUE_IDS or league_id in WATCHED_LEAGUE_IDS:
            normalized.append(row)

    save_json("live.json", {
        "updated_at": now_iso(),
        "source": "bsd_v2_events_live",
        "count": len(normalized),
        "events": normalized,
    })

    enriched: List[Dict[str, Any]] = []
    for ev in normalized[:LIVE_ENRICH_LIMIT]:
        eid = ev.get("event_id") or ev.get("id")
        print(f"  → live intel {eid}: {ev.get('home_team','—')} vs {ev.get('away_team','—')}")
        enriched.append(enrich_live_event(ev))

    summary = {
        "live_events": len(normalized),
        "enriched_events": len(enriched),
        "with_stats": sum(1 for r in enriched if r.get("resources", {}).get("stats", 0) > 0),
        "with_incidents": sum(1 for r in enriched if r.get("resources", {}).get("incidents", 0) > 0),
        "with_lineups": sum(1 for r in enriched if r.get("resources", {}).get("lineups", 0) > 0),
        "strong_signals": sum(1 for r in enriched for s in r.get("live_signals", []) if s.get("level") == "strong"),
    }
    save_json("live_intelligence.json", {
        "updated_at": now_iso(),
        "source": "live_intelligence_v1",
        "count": len(enriched),
        "summary": summary,
        "events": enriched,
        "notes": [
            "Live Intelligence folosește snapshot-uri HTTP statice; WebSocket push se implementează separat.",
            "Semnalele live sunt suport decizional, nu recomandări garantate.",
        ],
    })
    save_debug("live_intelligence_debug.json", {
        "updated_at": now_iso(),
        "limit": LIVE_ENRICH_LIMIT,
        "summary": summary,
        "events": [{
            "event_id": r.get("event_id"),
            "score": f"{r.get('home_score')}-{r.get('away_score')}",
            "minute": r.get("current_minute"),
            "pressure_side": r.get("pressure_side"),
            "pressure_score": r.get("pressure_score"),
            "resources": r.get("resources"),
            "signals": r.get("live_signals"),
        } for r in enriched],
        "requests": DEBUG["requests"],
        "warnings": DEBUG["warnings"],
    })


if __name__ == "__main__":
    DEBUG["started_at"] = now_iso()
    try:
        if not API_KEY:
            print("✗ BSD_API_KEY nu este setat!")
            save_empty()
            sys.exit(1)
        fetch_live()
    finally:
        DEBUG["finished_at"] = now_iso()
        save_debug("live_debug.json", DEBUG)
