#!/usr/bin/env python3
"""BetPredict API Coverage Final v2.

Raport final local: nu face requesturi API, ci agregă fișierele generate deja.

v2 fixează raportările fals-negative:
- debug/league_strength_debug.json are câmpuri root-level, nu count/results;
- debug/context_engine_debug.json are processed_predictions / with_context_confidence;
- fișierele audit-only pot fi OK chiar dacă nu modifică scoruri;
- fișierele disabled, cum e shotmap, sunt marcate separat.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DEBUG_DIR = DATA_DIR / "debug"
SOURCE = "api_coverage_final_v2"


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


def as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def first_positive(*values: Any) -> int:
    for value in values:
        n = as_int(value, 0)
        if n > 0:
            return n
    return 0


def count_rows(payload: Any) -> int:
    """Returnează un count robust pentru fișiere cu forme diferite.

    Unele debug-uri nu au `count`, ci:
    - total_predictions / processed_predictions / calibrated_predictions;
    - summary.total_predictions;
    - summary.events_requested;
    - results/signals/events list.
    """
    if isinstance(payload, list):
        return len(payload)
    if not isinstance(payload, dict):
        return 0

    for key in ("results", "signals", "events", "items", "data"):
        if isinstance(payload.get(key), list):
            return len(payload[key])

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}

    return first_positive(
        payload.get("count"),
        payload.get("processed_predictions"),
        payload.get("calibrated_predictions"),
        payload.get("total_predictions"),
        payload.get("available_predictions"),
        payload.get("with_context_confidence"),
        summary.get("count"),
        summary.get("total_predictions"),
        summary.get("processed_predictions"),
        summary.get("calibrated_predictions"),
        summary.get("available_predictions"),
        summary.get("events_requested"),
        summary.get("teams_saved"),
        summary.get("players_saved"),
        summary.get("lineup_events_indexed"),
        summary.get("ok_with_data"),
        summary.get("ok"),
    )


def disabled_count(payload: Any) -> int:
    if not isinstance(payload, dict):
        return 0
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if isinstance(summary.get("resources_disabled"), list) and summary.get("resources_disabled"):
        return len(summary.get("resources_disabled"))
    if "disabled" in summary:
        return as_int(summary.get("disabled"), 0)
    per_resource = summary.get("per_resource") if isinstance(summary.get("per_resource"), dict) else {}
    return sum(as_int(v.get("disabled"), 0) for v in per_resource.values() if isinstance(v, dict))


def has_errors(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        return True
    if as_int(payload.get("error_count"), 0) > 0:
        return True
    if as_int(summary.get("errors"), 0) > 0:
        return True
    regenerated = payload.get("regenerated") if isinstance(payload.get("regenerated"), dict) else {}
    if isinstance(regenerated.get("errors"), list) and regenerated.get("errors"):
        return True
    return False


def status_for_file(filename: str, min_count: int = 1) -> Dict[str, Any]:
    path = DATA_DIR / filename
    payload = read_json(path, {})
    exists = path.exists() and path.stat().st_size > 5
    count = count_rows(payload)
    summary = payload.get("summary") if isinstance(payload, dict) and isinstance(payload.get("summary"), dict) else {}
    disabled = disabled_count(payload)
    err = has_errors(payload)

    if not exists:
        status = "missing"
    elif err:
        status = "warning"
    elif count >= min_count:
        status = "ok"
    elif disabled > 0:
        status = "disabled"
    else:
        status = "empty"

    return {
        "file": filename,
        "exists": exists,
        "count": count,
        "disabled_count": disabled,
        "source": payload.get("source") if isinstance(payload, dict) else None,
        "updated_at": payload.get("updated_at") if isinstance(payload, dict) else None,
        "status": status,
        "summary": summary,
    }


def module_status(rows: List[Dict[str, Any]]) -> str:
    statuses = [r.get("status") for r in rows]
    if statuses and all(s == "ok" for s in statuses):
        return "ok"
    if any(s == "warning" for s in statuses) and any(s == "ok" for s in statuses):
        return "partial_warning"
    if any(s == "ok" for s in statuses):
        return "partial"
    if any(s == "disabled" for s in statuses) and not any(s in ("missing", "warning") for s in statuses):
        return "disabled"
    if any(s == "disabled" for s in statuses):
        return "disabled_or_partial"
    if any(s == "warning" for s in statuses):
        return "warning"
    return "missing_or_empty"


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
        "ml_v6": ["signals_v6.json", "v6_health.json", "v6_backtest_report.json"],
        "bsd_extended": ["broadcasts.json", "bsd_event_predictions.json"],
    }

    module_rows: Dict[str, List[Dict[str, Any]]] = {
        module: [status_for_file(fn) for fn in files]
        for module, files in modules.items()
    }

    module_statuses = {module: module_status(rows) for module, rows in module_rows.items()}

    implemented = [m for m, s in module_statuses.items() if s == "ok"]
    partial = [m for m, s in module_statuses.items() if s in ("partial", "partial_warning")]
    disabled = []
    missing_or_empty = [m for m, s in module_statuses.items() if s in ("missing_or_empty", "warning", "disabled_or_partial", "disabled")]
    warnings = [m for m, s in module_statuses.items() if "warning" in s]

    for module, rows in module_rows.items():
        for r in rows:
            if r.get("status") == "disabled":
                disabled.append({"module": module, "file": r.get("file"), "disabled_count": r.get("disabled_count")})

    api_report = read_json(DATA_DIR / "api_coverage_report.json", {})
    api_summary = api_report.get("summary", {}) if isinstance(api_report, dict) else {}
    api_opportunities = api_report.get("opportunities", []) if isinstance(api_report, dict) else []
    api_blockers = api_report.get("blockers_404", []) if isinstance(api_report, dict) else []

    final_summary = {
        "modules_total": len(modules),
        "implemented_modules": len(implemented),
        "partial_modules": len(partial),
        "missing_or_empty_modules": len(missing_or_empty),
        "warning_modules": len(warnings),
        "disabled_files": disabled,
        "api_scanner_summary": api_summary,
        "api_opportunities": api_opportunities,
        "api_blockers_404": api_blockers,
    }

    next_actions: List[str] = []
    if "league_strength" in missing_or_empty or "context_engine" in missing_or_empty:
        next_actions.append("verifică debug counters pentru League/Context; acestea nu ar trebui să fie missing după v2")
    if "market_odds" in partial or "market_odds" in missing_or_empty:
        next_actions.append("market_intelligence este gol/parțial; păstrează market layer audit-only până există odds movement stabil")
    if any(x.get("file") == "event_shotmap.json" for x in disabled):
        next_actions.append("shotmap activat: se obțin date doar pentru meciuri terminate (status FT/AET/PEN)")
    if "event_match_intelligence" in partial or "event_match_intelligence" in missing_or_empty:
        next_actions.append("event stats/incidents au coverage mic; nu folosi impact agresiv în scor")
    next_actions.append("afișează în UI doar modulele cu date pentru meciul curent; restul compact ca status")

    payload = {
        "updated_at": now_iso(),
        "source": SOURCE,
        "summary": final_summary,
        "module_statuses": module_statuses,
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
        "module_statuses": module_statuses,
        "implemented_modules": implemented,
        "partial_modules": partial,
        "missing_or_empty_modules": missing_or_empty,
        "next_actions": next_actions,
    })
    print(
        "API Coverage Final v2: "
        f"implemented={len(implemented)} partial={len(partial)} "
        f"missing={len(missing_or_empty)} disabled_files={len(disabled)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
