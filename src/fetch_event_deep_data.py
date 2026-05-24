#!/usr/bin/env python3
"""BetPredict Event Deep Data v2.

Subresurse eveniment BSD API v2:
- /events/{id}/stats/
- /events/{id}/lineups/
- /events/{id}/player-stats/
- /events/{id}/incidents/
- /events/{id}/shotmap/ doar dacă este activat explicit.

v2:
- data/event_deep_data.json este compact: summary + statusuri per event, fără payload brut mare;
- datele complete rămân în fișierele separate event_stats/event_lineups/etc.;
- shotmap este dezactivat implicit după rularea v1 unde a returnat 404 pe toate evenimentele;
- nu modifică predictions.json și nu atinge UI-ul.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DEBUG_DIR = DATA_DIR / "debug"

BASE_V2 = os.environ.get("BSD_BASE_V2", "https://sports.bzzoiro.com/api/v2").rstrip("/")
API_KEY = os.environ.get("BSD_API_KEY", "").strip()
EVENT_LIMIT = int(os.environ.get("BETPREDICT_EVENT_DEEP_LIMIT", "48") or 48)
HTTP_TIMEOUT = int(os.environ.get("BETPREDICT_EVENT_DEEP_HTTP_TIMEOUT", "18") or 18)
HTTP_SLEEP = float(os.environ.get("BETPREDICT_EVENT_DEEP_HTTP_SLEEP", "0.04") or 0.04)
ENABLE_SHOTMAP = str(os.environ.get("BETPREDICT_EVENT_DEEP_ENABLE_SHOTMAP", "0")).strip().lower() in {"1", "true", "yes", "on"}
SHOTMAP_FINISHED_STATUSES = {"ft", "aet", "pen", "fin", "finished", "after extra time", "penalties", "full time", "complete", "completed"}

SOURCE = "event_deep_data_v2"
BASE_SUBRESOURCES = {
    "stats": "stats",
    "lineups": "lineups",
    "player_stats": "player-stats",
    "incidents": "incidents",
}
SHOTMAP_RESOURCE = {"shotmap": "shotmap"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def as_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except Exception:
        return None


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def compact_count(payload: Any) -> int:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("results", "events", "items", "data", "lineups", "players", "incidents", "shots", "shotmap"):
            if isinstance(payload.get(key), list):
                return len(payload[key])
        if isinstance(payload.get("stats"), dict):
            return 1
        if "count" in payload:
            return as_int(payload.get("count")) or 0
        return 1 if payload else 0
    return 0


def extract_rows(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("results", "events", "items", "data", "lineups", "players", "incidents", "shots", "shotmap"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [x for x in rows if isinstance(x, dict)]
    return []


def short_payload(payload: Any, max_rows: int = 2) -> Any:
    if isinstance(payload, dict):
        out: Dict[str, Any] = {}
        for key, value in payload.items():
            if isinstance(value, list):
                out[key] = value[:max_rows]
            elif isinstance(value, dict):
                out[key] = {"_type": "object", "_keys": list(value.keys())[:12]}
            else:
                out[key] = value
        return out
    if isinstance(payload, list):
        return payload[:max_rows]
    return payload


def request_json(path: str, params: Optional[Dict[str, Any]] = None, label: str = "") -> Tuple[Any, Dict[str, Any]]:
    params = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
    query = urllib.parse.urlencode(params, doseq=True)
    url = f"{BASE_V2}{path}"
    if query:
        url = f"{url}?{query}"
    headers = {"Accept": "application/json", "User-Agent": "BetPredict-Event-Deep-Data/2.0"}
    if API_KEY:
        headers["Authorization"] = f"Token {API_KEY}"
    started = time.time()
    meta: Dict[str, Any] = {"label": label or path, "path": path, "params": params, "ok": False, "status": None, "count": 0, "elapsed_ms": 0}
    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
            payload = json.loads(text) if text.strip() else {}
            status = int(getattr(resp, "status", 200))
            meta.update({"ok": 200 <= status < 300, "status": status, "count": compact_count(payload), "elapsed_ms": int((time.time() - started) * 1000)})
            if HTTP_SLEEP > 0:
                time.sleep(HTTP_SLEEP)
            return payload, meta
    except urllib.error.HTTPError as exc:
        meta["status"] = int(exc.code)
        meta["elapsed_ms"] = int((time.time() - started) * 1000)
        try:
            meta["error"] = exc.read().decode("utf-8", errors="replace")[:240]
        except Exception:
            meta["error"] = str(exc)[:240]
        return {}, meta
    except Exception as exc:
        meta["status"] = "error"
        meta["elapsed_ms"] = int((time.time() - started) * 1000)
        meta["error"] = str(exc)[:240]
        return {}, meta


def add_event(events: Dict[str, Dict[str, Any]], event_id: Any, row: Dict[str, Any], source: str, score: float) -> None:
    eid = as_int(event_id)
    if not eid:
        return
    key = str(eid)
    ev = row.get("event") if isinstance(row.get("event"), dict) else row
    home = ev.get("home_team") or row.get("home_team")
    away = ev.get("away_team") or row.get("away_team")
    league = ev.get("league") or ev.get("league_name") or row.get("league") or row.get("league_name")
    item = events.setdefault(key, {"event_id": eid, "home_team": home, "away_team": away, "league": league, "league_id": ev.get("league_id") or row.get("league_id"), "event_date": ev.get("event_date") or ev.get("start_time") or row.get("event_date") or row.get("start_time"), "sources": [], "priority_score": 0.0})
    if source not in item["sources"]:
        item["sources"].append(source)
    item["priority_score"] += float(score or 0)
    for k, v in {"home_team": home, "away_team": away, "league": league, "league_id": ev.get("league_id") or row.get("league_id"), "event_date": ev.get("event_date") or ev.get("start_time") or row.get("event_date") or row.get("start_time")}.items():
        if v and not item.get(k):
            item[k] = v


def seed_priority_events(limit: int = EVENT_LIMIT) -> List[Dict[str, Any]]:
    events: Dict[str, Dict[str, Any]] = {}
    sigs = read_json(DATA_DIR / "signals.json", {"signals": []})
    for i, row in enumerate(sigs.get("signals", [])[:80] if isinstance(sigs, dict) else []):
        score = 12.0 + max(0, 35 - i) / 4.0 + as_float(row.get("smartbet_score"), 0) / 12.0
        add_event(events, row.get("event_id") or row.get("id"), row, "signals", score)
    vb = read_json(DATA_DIR / "value_bets.json", {"results": []})
    for i, row in enumerate(vb.get("results", [])[:80] if isinstance(vb, dict) else []):
        score = 9.0 + max(0, 30 - i) / 5.0 + abs(as_float(row.get("edge_pp"), 0)) / 4.0
        add_event(events, row.get("event_id") or row.get("id"), row, "value_bets", score)
    ctx = read_json(DATA_DIR / "match_context.json", {"results": []})
    for i, row in enumerate(ctx.get("results", [])[:80] if isinstance(ctx, dict) else []):
        score = 7.0 + max(0, 35 - i) / 6.0 + as_float(row.get("priority_score"), 0) / 20.0
        add_event(events, row.get("event_id") or row.get("id"), row, "match_context", score)
    preds = read_json(DATA_DIR / "predictions.json", {"results": []})
    pred_rows = preds.get("results", []) if isinstance(preds, dict) else []
    pred_rows = sorted(pred_rows, key=lambda x: as_float(x.get("smartbet_score"), 0), reverse=True)
    for i, row in enumerate(pred_rows[:100]):
        ev = row.get("event") if isinstance(row.get("event"), dict) else row
        score = 3.0 + as_float(row.get("smartbet_score"), 0) / 18.0 + max(0, 30 - i) / 10.0
        add_event(events, ev.get("id") or row.get("event_id"), row, "predictions", score)
    out = sorted(events.values(), key=lambda x: x.get("priority_score") or 0, reverse=True)
    for row in out:
        row["priority_score"] = round(float(row.get("priority_score") or 0), 2)
    return out[:limit]


def normalize_event_resource(event: Dict[str, Any], resource: str, payload: Any, meta: Dict[str, Any]) -> Dict[str, Any]:
    rows = extract_rows(payload)
    return {"event_id": event.get("event_id"), "home_team": event.get("home_team"), "away_team": event.get("away_team"), "league": event.get("league"), "league_id": event.get("league_id"), "event_date": event.get("event_date"), "priority_score": event.get("priority_score"), "sources": event.get("sources", []), "resource": resource, "ok": bool(meta.get("ok")), "status": meta.get("status"), "count": meta.get("count", len(rows)), "results": rows, "raw": payload if not rows and isinstance(payload, dict) and payload else None}


def disabled_resource_row(event: Dict[str, Any], resource: str, reason: str) -> Dict[str, Any]:
    return {"event_id": event.get("event_id"), "home_team": event.get("home_team"), "away_team": event.get("away_team"), "league": event.get("league"), "league_id": event.get("league_id"), "event_date": event.get("event_date"), "priority_score": event.get("priority_score"), "sources": event.get("sources", []), "resource": resource, "ok": False, "status": "disabled", "count": 0, "results": [], "raw": None, "disabled_reason": reason}


def compact_event_status(event: Dict[str, Any], resources: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    return {"event_id": event.get("event_id"), "home_team": event.get("home_team"), "away_team": event.get("away_team"), "league": event.get("league"), "league_id": event.get("league_id"), "event_date": event.get("event_date"), "priority_score": event.get("priority_score"), "sources": event.get("sources", []), "resources": resources}


def main() -> int:
    print("\n[Event Deep Data v2] Event subresources BSD v2...")
    events = seed_priority_events(EVENT_LIMIT)
    reports: List[Dict[str, Any]] = []
    combined: List[Dict[str, Any]] = []
    enabled_resources = dict(BASE_SUBRESOURCES)
    if ENABLE_SHOTMAP:
        enabled_resources.update(SHOTMAP_RESOURCE)
    buckets: Dict[str, List[Dict[str, Any]]] = {key: [] for key in {**BASE_SUBRESOURCES, **SHOTMAP_RESOURCE}}
    if not events:
        write_json(DEBUG_DIR / "event_deep_data_debug.json", {"updated_at": now_iso(), "source": SOURCE, "error": "no_priority_events", "limit": EVENT_LIMIT})
        print("  no priority events; skip")
        return 0
    for idx, event in enumerate(events, 1):
        event_id = event.get("event_id")
        print(f"  → event {idx}/{len(events)} #{event_id}: {event.get('home_team','—')} vs {event.get('away_team','—')}")
        statuses: Dict[str, Dict[str, Any]] = {}
        event_status_raw = str(event.get("status") or "").lower().strip()
        is_finished = event_status_raw in SHOTMAP_FINISHED_STATUSES
        for resource, endpoint_name in enabled_resources.items():
            if resource == "shotmap" and not is_finished:
                buckets["shotmap"].append(disabled_resource_row(event, "shotmap", "upcoming_event_shotmap_skipped"))
                statuses["shotmap"] = {"ok": False, "status": "skipped", "count": 0, "reason": "upcoming_event"}
                continue
            payload, meta = request_json(f"/events/{event_id}/{endpoint_name}/", {}, label=f"event_{resource}_{event_id}")
            reports.append({"event_id": event_id, "resource": resource, "ok": meta.get("ok"), "status": meta.get("status"), "count": meta.get("count"), "elapsed_ms": meta.get("elapsed_ms"), "error": meta.get("error")})
            buckets[resource].append(normalize_event_resource(event, resource, payload, meta))
            statuses[resource] = {"ok": meta.get("ok"), "status": meta.get("status"), "count": meta.get("count"), "elapsed_ms": meta.get("elapsed_ms"), "sample": short_payload(payload, max_rows=2) if int(meta.get("count") or 0) > 0 else None}
        if not ENABLE_SHOTMAP and "shotmap" not in statuses:
            buckets["shotmap"].append(disabled_resource_row(event, "shotmap", "disabled_by_env"))
            statuses["shotmap"] = {"ok": False, "status": "disabled", "count": 0, "disabled_reason": "disabled_by_env"}
        combined.append(compact_event_status(event, statuses))
    per_resource: Dict[str, Dict[str, Any]] = {}
    for resource, rows in buckets.items():
        per_resource[resource] = {"events": len(rows), "ok_with_data": sum(1 for r in rows if r.get("ok") and int(r.get("count") or 0) > 0), "ok_empty": sum(1 for r in rows if r.get("ok") and int(r.get("count") or 0) == 0), "not_found": sum(1 for r in rows if r.get("status") == 404), "disabled": sum(1 for r in rows if r.get("status") == "disabled"), "errors": sum(1 for r in rows if not r.get("ok") and r.get("status") not in (404, 401, 403, "disabled")), "total_rows": sum(int(r.get("count") or 0) for r in rows if r.get("ok"))}
    summary = {"events_requested": len(events), "resources_enabled": sorted(enabled_resources.keys()), "resources_disabled": [] if ENABLE_SHOTMAP else ["shotmap"], "resources_per_event": len(enabled_resources), "requests_total": len(reports), "ok_with_data": sum(1 for r in reports if r.get("ok") and int(r.get("count") or 0) > 0), "ok_empty": sum(1 for r in reports if r.get("ok") and int(r.get("count") or 0) == 0), "not_found": sum(1 for r in reports if r.get("status") == 404), "auth_failed": sum(1 for r in reports if r.get("status") in (401, 403)), "errors": sum(1 for r in reports if not r.get("ok") and r.get("status") not in (404, 401, 403)), "per_resource": per_resource}
    updated_at = now_iso()
    write_json(DATA_DIR / "event_deep_data.json", {"updated_at": updated_at, "source": SOURCE, "count": len(combined), "summary": summary, "events": events, "results": combined})
    file_map = {"stats": "event_stats.json", "lineups": "event_lineups.json", "player_stats": "event_player_stats.json", "shotmap": "event_shotmap.json", "incidents": "event_incidents.json"}
    for resource, filename in file_map.items():
        rows = buckets[resource]
        write_json(DATA_DIR / filename, {"updated_at": updated_at, "source": f"event_{resource}_v2", "count": len(rows), "summary": per_resource.get(resource, {}), "results": rows})
    write_json(DEBUG_DIR / "event_deep_data_debug.json", {"updated_at": updated_at, "source": SOURCE, "base_url": BASE_V2, "limits": {"event_limit": EVENT_LIMIT, "http_timeout": HTTP_TIMEOUT, "http_sleep": HTTP_SLEEP, "shotmap_enabled": ENABLE_SHOTMAP}, "summary": summary, "reports": reports[:300], "sample_events": combined[:12]})
    print(f"  event deep data v2: events={len(events)} requests={len(reports)} ok_data={summary['ok_with_data']} empty={summary['ok_empty']} 404={summary['not_found']} disabled={summary['resources_disabled']} errors={summary['errors']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
