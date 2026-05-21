#!/usr/bin/env python3
"""BetPredict API Coverage Final v1.

Raport final local: nu face requesturi API, ci agregă fișierele generate deja.
Scop: să știm ce endpointuri/module sunt implementate, goale, dezactivate sau încă lipsă.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DEBUG_DIR = DATA_DIR / "debug"
SOURCE = "api_coverage_final_v1"


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


def count_rows(payload: Any) -> int:
    if isinstance(payload, list):
        return len(payload)
    if not isinstance(payload, dict):
        return 0
    for key in ("results", "signals", "events", "items", "data"):
        if isinstance(payload.get(key), list):
            return len(payload[key])
    if isinstance(payload.get("summary"), dict) and payload.get("summary", {}).get("total_predictions") is not None:
        return int(payload.get("summary", {}).get("total_predictions") or 0)
    return int(payload.get("count") or 0) if str(payload.get("count") or "").isdigit() else 0


def status_for_file(filename: str, min_count: int = 1) -> Dict[str, Any]:
    path = DATA_DIR / filename
    payload = read_json(path, {})
    exists = path.exists() and path.stat().st_size > 5
    count = count_rows(payload)
    summary = payload.get("summary") if isinstance(payload, dict) and isinstance(payload.get("summary"), dict) else {}
    if not exists:
        status = "missing"
    elif count >= min_count:
        status = "ok"
    elif summary.get("disabled") or summary.get("resources_disabled"):
        status = "disabled_or_partial"
    else:
        status = "empty"
    return {
        "file": filename,
        "exists": exists,
        "count": count,
        "source": payload.get("source") if isinstance(payload, dict) else None,
        "updated_at": payload.get("updated_at") if isinstance(payload, dict) else None,
        "status": status,
        "summary": summary,
    }


def main() -> int:
    modules = {
        "core_predictions": ["predictions.json", "signals.json", "value_bets.json"],
        "league_strength": ["debug/league_strength_debug.json"],
        "context_engine": ["debug/context_engine_debug.json"],
        "teams_players": ["team_intelligence.json", "team_squads.json", "player_intelligence.json", "player_impact.json"],
        "event_deep_data": ["event_deep_data.json", "event_stats.json", "event_lineups.json", "event_player_stats.json", "event_incidents.json", "event_shotmap.json"],
        "lineup_intelligence": ["lineup_intelligence.json"],
        "event_match_intelligence": ["event_match_intelligence.json"],
        "context_entities": ["context_intelligence.json", "context_entity_hardening.json"],
        "market_odds": ["market_odds_audit.json", "market_intelligence.json"],
        "qa": ["qa_report.json", "performance_summary.json", "api_coverage_report.json"],
    }

    module_rows: Dict[str, List[Dict[str, Any]]] = {}
    for module, files in modules.items():
        module_rows[module] = []
        for fn in files:
            path = DATA_DIR / fn if not fn.startswith("debug/") else DATA_DIR / fn
            rel = fn
            if fn.startswith("debug/"):
                rel = fn
            module_rows[module].append(status_for_file(rel))

    implemented = []
    partial = []
    missing_or_empty = []
    disabled = []
    for module, rows in module_rows.items():
        statuses = [r.get("status") for r in rows]
        if all(s == "ok" for s in statuses):
            implemented.append(module)
        elif any(s == "ok" for s in statuses):
            partial.append(module)
        else:
            missing_or_empty.append(module)
        for r in rows:
            if r.get("status") == "disabled_or_partial":
                disabled.append({"module": module, "file": r.get("file")})

    api_report = read_json(DATA_DIR / "api_coverage_report.json", {})
    api_summary = api_report.get("summary", {}) if isinstance(api_report, dict) else {}
    api_opportunities = api_report.get("opportunities", []) if isinstance(api_report, dict) else []
    api_blockers = api_report.get("blockers_404", []) if isinstance(api_report, dict) else []

    final_summary = {
        "modules_total": len(modules),
        "implemented_modules": len(implemented),
        "partial_modules": len(partial),
        "missing_or_empty_modules": len(missing_or_empty),
        "disabled_files": disabled,
        "api_scanner_summary": api_summary,
        "api_opportunities": api_opportunities,
        "api_blockers_404": api_blockers,
    }

    next_actions = []
    if "market_odds" in partial or "market_odds" in missing_or_empty:
        next_actions.append("market_intelligence este gol/parțial; păstrează audit-only până există odds movement stabil")
    if any(x.get("file") == "event_shotmap.json" for x in disabled):
        next_actions.append("shotmap rămâne dezactivat până endpointul nu mai returnează 404")
    if "event_match_intelligence" in partial or "event_match_intelligence" in missing_or_empty:
        next_actions.append("event stats/incidents au coverage mic; nu folosi impact agresiv în scor")
    next_actions.append("după aceste rapoarte, se pot face retușuri UI pentru a afișa doar modulele cu date disponibile")

    payload = {
        "updated_at": now_iso(),
        "source": SOURCE,
        "summary": final_summary,
        "implemented_modules": implemented,
        "partial_modules": partial,
        "missing_or_empty_modules": missing_or_empty,
        "modules": module_rows,
        "next_actions": next_actions,
    }
    write_json(DATA_DIR / "api_coverage_final.json", payload)
    write_json(DEBUG_DIR / "api_coverage_final_debug.json", {
        "updated_at": payload["updated_at"],
        "source": SOURCE,
        "summary": final_summary,
        "implemented_modules": implemented,
        "partial_modules": partial,
        "missing_or_empty_modules": missing_or_empty,
        "next_actions": next_actions,
    })
    print(f"API Coverage Final: implemented={len(implemented)} partial={len(partial)} missing={len(missing_or_empty)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
