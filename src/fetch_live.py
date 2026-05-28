#!/usr/bin/env python3
"""
BetPredict Pro — Live Scores Fetcher (v23 Exact Live Window)
============================================================

Implementare conform BSD API v2 docs:
  - GET /api/v2/events/live/
  - query params API-side: league_id, season_id, team_id
  - ignoră date_from/date_to/status pentru live, conform docs
  - fiecare row păstrează last_updated
  - dacă last_updated nu s-a schimbat, refolosim enrichment-ul vechi
  - enrich doar când e necesar: stats / incidents / lineups
"""

from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

API_KEY = os.environ.get("BSD_API_KEY", "").strip()
BASE_V2 = "https://sports.bzzoiro.com/api/v2"
IMG_BASE = "https://sports.bzzoiro.com/img"
HEADERS = {"Authorization": f"Token {API_KEY}"} if API_KEY else {}
DATA_DIR = Path(__file__).parent.parent / "data"
DEBUG_DIR = DATA_DIR / "debug"

# Set gol = toate ligile live. Dacă vrei filtre API-side, setează env:
# BETPREDICT_LIVE_LEAGUE_ID, BETPREDICT_LIVE_SEASON_ID, BETPREDICT_LIVE_TEAM_ID.
# 32 = Copa Libertadores, 33 = Copa Sudamericana — incluse explicit pentru
# acoperire sud-americană (BSD live feed ratează aceste meciuri).
WATCHED_LEAGUE_IDS = {1, 2, 3, 4, 5, 6, 7, 8, 10, 17, 18, 20, 23, 28, 30, 32, 33, 52}
LIVE_ENRICH_LIMIT = int(os.environ.get("BETPREDICT_LIVE_ENRICH_LIMIT", "18") or 18)
LIVE_BACKFILL_LIMIT = int(os.environ.get("BETPREDICT_LIVE_BACKFILL_LIMIT", "10") or 10)
# Status values that count as "currently being played" pe BSD v2.
INPROGRESS_STATUSES = {"inprogress", "in_progress", "live", "1st_half", "2nd_half", "halftime", "ht", "et", "extra_time", "penalty", "pen"}

DEBUG: Dict[str, Any] = {
    "started_at": None,
    "finished_at": None,
    "has_api_key": bool(API_KEY),
    "requests": [],
    "warnings": [],
    "cache": {"reused": 0, "refetched": 0},
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def img_url(kind: str, ident: Any) -> Optional[str]:
    return f"{IMG_BASE}/{kind}/{ident}/" if ident not in (None, "", "null") else None


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


def load_json(filename: str, default: Any) -> Any:
    path = DATA_DIR / filename
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        warn("Nu pot citi JSON", filename=filename, error=str(exc))
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


def get(url: str, params: Optional[Dict[str, Any]] = None, label: str = "") -> Optional[Any]:
    params = {k: v for k, v in (params or {}).items() if v not in (None, "", [])}
    started = datetime.now(timezone.utc)
    try:
        r = requests.get(url, headers=HEADERS, params=params or None, timeout=10)
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


def live_params() -> Dict[str, Any]:
    return {
        "league_id": os.environ.get("BETPREDICT_LIVE_LEAGUE_ID"),
        "season_id": os.environ.get("BETPREDICT_LIVE_SEASON_ID"),
        "team_id": os.environ.get("BETPREDICT_LIVE_TEAM_ID"),
    }


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
    out["last_updated"] = ev.get("last_updated") or ev.get("updated_at")
    out["image_assets"] = {
        "home_team_logo": img_url("team", ev.get("home_team_id")),
        "away_team_logo": img_url("team", ev.get("away_team_id")),
        "league_logo": img_url("league", out.get("league_id")),
    }
    return out


def flatten_stats(stats_payload: Any) -> Dict[str, Any]:
    if not isinstance(stats_payload, dict):
        return {}
    root = stats_payload.get("stats") if isinstance(stats_payload.get("stats"), dict) else stats_payload
    home = root.get("home") if isinstance(root.get("home"), dict) else {}
    away = root.get("away") if isinstance(root.get("away"), dict) else {}

    def pick(side: Dict[str, Any], keys: List[str]) -> Optional[float]:
        for k in keys:
            v = side.get(k)
            if isinstance(v, dict) and "actual" in v:
                v = v.get("actual")
            f = as_float(v)
            if f is not None:
                return f
        return None

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
        "shotmap": shotmap,
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


def previous_cache() -> Dict[str, Dict[str, Any]]:
    prev = load_json("live_intelligence.json", {})
    events = prev.get("events") if isinstance(prev, dict) else []
    if not isinstance(events, list):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for row in events:
        if not isinstance(row, dict):
            continue
        eid = row.get("event_id")
        if eid is not None:
            out[str(eid)] = row
    return out


def can_reuse(prev: Dict[str, Any], ev: Dict[str, Any]) -> bool:
    if not prev:
        return False
    new_last = ev.get("last_updated")
    old_last = ((prev.get("event") or {}).get("last_updated") or prev.get("last_updated"))
    return bool(new_last and old_last and str(new_last) == str(old_last))


def enrich_live_event(ev: Dict[str, Any], old: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    eid = ev.get("event_id") or ev.get("id")
    if old and can_reuse(old, ev):
        DEBUG["cache"]["reused"] += 1
        reused = dict(old)
        reused["cache_status"] = "reused_last_updated"
        reused["event"] = ev
        reused["last_updated"] = ev.get("last_updated")
        return reused

    DEBUG["cache"]["refetched"] += 1
    # Fetch stats/incidents/lineups în paralel — reduce latența per meci de la ~3×RTT la ~1×RTT
    def _fetch(path: str, label: str) -> Any:
        return get(f"{BASE_V2}/events/{eid}/{path}/", label=label) if eid else None
    with ThreadPoolExecutor(max_workers=3) as ex:
        f_stats = ex.submit(_fetch, "stats", f"live_stats_{eid}")
        f_inc   = ex.submit(_fetch, "incidents", f"live_incidents_{eid}")
        f_lu    = ex.submit(_fetch, "lineups", f"live_lineups_{eid}")
        stats_payload  = f_stats.result()
        inc_payload    = f_inc.result()
        lineup_payload = f_lu.result()

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
        "last_updated": ev.get("last_updated"),
        "event": ev,
        "phase": phase,
        "pressure_side": side,
        "pressure_score": pressure,
        "stats_summary": stats,
        "shotmap": stats.get("shotmap", []),
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
        "cache_status": "refetched",
    }


def save_empty(params: Dict[str, Any]) -> None:
    payload = {
        "updated_at": now_iso(),
        "count": 0,
        "events": [],
        "source": "bsd_v2_events_live",
        "endpoint": "/api/v2/events/live/",
        "params": params,
    }
    save_json("live.json", payload)
    save_json("live_window.json", payload)
    save_json("live_intelligence.json", {
        "updated_at": now_iso(),
        "source": "live_intelligence_v23",
        "count": 0,
        "events": [],
        "summary": {"live_events": 0, "enriched_events": 0, "with_stats": 0, "with_incidents": 0, "with_lineups": 0, "strong_signals": 0, "reused_cache": 0, "refetched": 0},
        "notes": ["Nu există meciuri live la ultima rulare."],
    })


def candidate_event_ids_in_play_window() -> List[int]:
    """Returnează event_id-uri din predictions.json cu event_date în ultimele 110 min.

    Acoperă cazul în care /events/live/ nu listează un meci (gap BSD), dar
    știm din program că ar trebui să fie în desfășurare.
    """
    preds_path = DATA_DIR / "predictions.json"
    if not preds_path.exists():
        return []
    try:
        preds = json.loads(preds_path.read_text(encoding="utf-8"))
    except Exception as e:
        DEBUG["warnings"].append(f"backfill: cannot read predictions.json ({e})")
        return []
    now = datetime.now(timezone.utc)
    win_start = now - timedelta(minutes=110)
    win_end = now + timedelta(minutes=10)
    out: List[int] = []
    for r in (preds.get("results") or []):
        ev = r.get("event") or {}
        eid = ev.get("id") or ev.get("event_id")
        if not eid:
            continue
        dt_str = ev.get("event_date") or ""
        try:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except Exception:
            continue
        if win_start <= dt <= win_end:
            try:
                out.append(int(eid))
            except (TypeError, ValueError):
                continue
    return out


def backfill_inplay_events(already_have: set) -> List[Dict[str, Any]]:
    """Pentru event_id-uri din window-ul de joc dar lipsă din /events/live/,
    apelează /events/{id}/ și include în output dacă status indică inprogress.
    """
    candidates = [eid for eid in candidate_event_ids_in_play_window() if eid not in already_have]
    if not candidates:
        return []
    to_fetch = candidates[:LIVE_BACKFILL_LIMIT]
    print(f"  → backfill: {len(to_fetch)} eveniment(e) din window lipsesc din /events/live/")
    backfilled: List[Dict[str, Any]] = []
    for eid in to_fetch:
        payload = get(f"{BASE_V2}/events/{eid}/", label=f"backfill_event_{eid}")
        if not isinstance(payload, dict):
            continue
        ev = payload.get("event") if isinstance(payload.get("event"), dict) else payload
        if not isinstance(ev, dict):
            continue
        status = str(ev.get("status") or "").lower().strip()
        if status not in INPROGRESS_STATUSES:
            continue
        row = normalize_event(ev)
        row["_backfilled"] = True
        backfilled.append(row)
        print(f"     + {row.get('home_team','—')} vs {row.get('away_team','—')} @ {row.get('current_minute','?')}'")
    return backfilled


def fetch_live() -> None:
    print("🔴 Live Scores + Intelligence v23...")
    params = {k: v for k, v in live_params().items() if v not in (None, "", [])}
    payload = get(f"{BASE_V2}/events/live/", params=params, label="events_live")
    events = extract_events(payload)

    normalized: List[Dict[str, Any]] = []
    for ev in events:
        row = normalize_event(ev)
        league_id = row.get("league_id")
        # Dacă nu ai setat filtre API-side, păstrăm filtrarea locală pentru app.
        if params or not WATCHED_LEAGUE_IDS or league_id in WATCHED_LEAGUE_IDS:
            normalized.append(row)

    # Backfill: meciuri din window-ul de joc pe care /events/live/ nu le listează.
    # Acoperă gap-ul BSD pentru competițiile sud-americane (Libertadores, Sudamericana).
    have_ids: set = set()
    for row in normalized:
        eid = row.get("event_id") or row.get("id")
        if eid is not None:
            try:
                have_ids.add(int(eid))
            except (TypeError, ValueError):
                continue
    backfilled = backfill_inplay_events(have_ids)
    if backfilled:
        normalized.extend(backfilled)

    backfill_count = len(backfilled)
    source_label = "bsd_v2_events_live+backfill" if backfill_count else "bsd_v2_events_live"
    notes = [
        "Conform BSD v2, live window ignoră date_from/date_to/status.",
        "Folosește league_id/season_id/team_id ca filtre API-side dacă sunt setate în env.",
    ]
    if backfill_count:
        notes.append(f"Backfill: {backfill_count} eveniment(e) adăugate via /events/{{id}}/ pentru meciuri ratate de /events/live/.")

    live_payload = {
        "updated_at": now_iso(),
        "source": source_label,
        "endpoint": "/api/v2/events/live/",
        "params": params,
        "count": len(normalized),
        "backfill_count": backfill_count,
        "events": normalized,
        "notes": notes,
    }
    save_json("live.json", live_payload)
    save_json("live_window.json", live_payload)

    old_by_id = previous_cache()
    to_enrich = normalized[:LIVE_ENRICH_LIMIT]
    enriched: List[Dict[str, Any]] = []
    # Paralelizăm enrichment-ul cross-event: meciuri independente → ThreadPool
    max_workers = min(len(to_enrich), 6) if to_enrich else 1
    def _enrich(ev: Dict[str, Any]) -> Dict[str, Any]:
        eid = ev.get("event_id") or ev.get("id")
        print(f"  → live intel {eid}: {ev.get('home_team','—')} vs {ev.get('away_team','—')}")
        return enrich_live_event(ev, old_by_id.get(str(eid)))
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_enrich, ev): ev for ev in to_enrich}
        for fut in as_completed(futures):
            try:
                enriched.append(fut.result())
            except Exception as exc:
                ev = futures[fut]
                warn("Enrichment eșuat", event_id=ev.get("event_id"), error=str(exc))

    summary = {
        "live_events": len(normalized),
        "enriched_events": len(enriched),
        "with_stats": sum(1 for r in enriched if r.get("resources", {}).get("stats", 0) > 0),
        "with_incidents": sum(1 for r in enriched if r.get("resources", {}).get("incidents", 0) > 0),
        "with_lineups": sum(1 for r in enriched if r.get("resources", {}).get("lineups", 0) > 0),
        "strong_signals": sum(1 for r in enriched for s in r.get("live_signals", []) if s.get("level") == "strong"),
        "reused_cache": DEBUG["cache"]["reused"],
        "refetched": DEBUG["cache"]["refetched"],
    }
    save_json("live_intelligence.json", {
        "updated_at": now_iso(),
        "source": "live_intelligence_v23",
        "endpoint": "/api/v2/events/live/",
        "params": params,
        "count": len(enriched),
        "summary": summary,
        "events": enriched,
        "notes": [
            "Live Intelligence folosește HTTP live window; WebSocket push rămâne add-on separat.",
            "Dacă last_updated nu s-a schimbat, enrichment-ul vechi este refolosit pentru a nu lovi inutil stats/incidents/lineups.",
            "Semnalele live sunt suport decizional, nu recomandări garantate.",
        ],
    })
    save_json("live_state_cache.json", {
        "updated_at": now_iso(),
        "source": "live_last_updated_cache",
        "count": len(normalized),
        "events": [
            {
                "event_id": ev.get("event_id"),
                "last_updated": ev.get("last_updated"),
                "status": ev.get("status"),
                "current_minute": ev.get("current_minute"),
                "home_score": ev.get("home_score"),
                "away_score": ev.get("away_score"),
            }
            for ev in normalized
        ],
    })
    save_debug("live_intelligence_debug.json", {
        "updated_at": now_iso(),
        "limit": LIVE_ENRICH_LIMIT,
        "params": params,
        "summary": summary,
        "events": [{
            "event_id": r.get("event_id"),
            "score": f"{r.get('home_score')}-{r.get('away_score')}",
            "minute": r.get("current_minute"),
            "last_updated": r.get("last_updated"),
            "cache_status": r.get("cache_status"),
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
            save_empty({})
            sys.exit(1)
        fetch_live()
    finally:
        DEBUG["finished_at"] = now_iso()
        save_debug("live_debug.json", DEBUG)
