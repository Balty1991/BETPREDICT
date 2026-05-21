#!/usr/bin/env python3
"""BetPredict Context Entity Hardening v1.

Folosește data/context_intelligence.json pentru audit/hardening pe:
- referee
- venue
- managers

Scop sigur:
- adaugă bloc context_entity_hardening în predictions.json;
- generează data/context_entity_hardening.json + debug;
- NU modifică smartbet_score, ca să nu dubleze Context Engine-ul deja existent.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DEBUG_DIR = DATA_DIR / "debug"
VERSION = "context_entity_hardening_v1"

TACTICAL_RISK = {
    "attacking": 0.16,
    "high_press": 0.14,
    "direct": 0.10,
    "balanced": 0.00,
    "possession": -0.03,
    "counter": -0.05,
    "defensive": -0.13,
    "low_block": -0.17,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def num(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        x = float(v)
        return x if math.isfinite(x) else default
    except Exception:
        return default


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


def event_id_from_pred(pred: Dict[str, Any]) -> str:
    ev = pred.get("event") if isinstance(pred.get("event"), dict) else {}
    return str(ev.get("id") or pred.get("event_id") or "")


def build_index(payload: Any) -> Dict[str, Dict[str, Any]]:
    rows = payload.get("results") if isinstance(payload, dict) else []
    out: Dict[str, Dict[str, Any]] = {}
    if isinstance(rows, list):
        for r in rows:
            if isinstance(r, dict) and r.get("event_id") is not None:
                out[str(r.get("event_id"))] = r
    return out


def manager_signal(mgr: Dict[str, Any]) -> Dict[str, Any]:
    if not mgr:
        return {"available": False}
    profile = str(mgr.get("tactical_profile") or "").lower().strip()
    matches = num(mgr.get("matches_total"), 0)
    win_pct = num(mgr.get("win_pct"), 0)
    over25 = num(mgr.get("over_25_pct"), 0)
    btts = num(mgr.get("btts_pct"), 0)
    gf = num(mgr.get("avg_goals_scored"), 0)
    ga = num(mgr.get("avg_goals_conceded"), 0)
    reliability = clamp(matches / 40.0, 0.0, 1.0)
    goal_tilt = TACTICAL_RISK.get(profile, 0.0)
    attacking_index = clamp((gf * 0.30 + over25 / 100.0 * 0.40 + btts / 100.0 * 0.18 + goal_tilt) * reliability, -0.25, 1.25)
    defensive_risk = clamp((ga * 0.35 + (1.0 - win_pct / 100.0) * 0.22) * reliability, 0.0, 1.25)
    return {
        "available": True,
        "name": mgr.get("short_name") or mgr.get("name"),
        "profile": profile or None,
        "formation": mgr.get("preferred_formation"),
        "matches_total": int(matches),
        "win_pct": round(win_pct, 1),
        "reliability": round(reliability, 3),
        "attacking_index": round(attacking_index, 3),
        "defensive_risk": round(defensive_risk, 3),
    }


def venue_signal(ctx: Dict[str, Any], pred: Dict[str, Any]) -> Dict[str, Any]:
    venue = ctx.get("venue") if isinstance(ctx.get("venue"), dict) else {}
    summary = ctx.get("venue_summary") if isinstance(ctx.get("venue_summary"), dict) else {}
    if not venue and not summary:
        return {"available": False}
    ev = pred.get("event") if isinstance(pred.get("event"), dict) else {}
    home_id = ev.get("home_team_id") or ctx.get("home_team_id")
    venue_home_id = venue.get("home_team_id") or summary.get("home_team_id")
    capacity = num(venue.get("capacity") or summary.get("capacity"), 0)
    pitch_l = num(venue.get("pitch_length_m") or summary.get("pitch_length_m"), 0)
    pitch_w = num(venue.get("pitch_width_m") or summary.get("pitch_width_m"), 0)
    home_ground = bool(home_id and venue_home_id and str(home_id) == str(venue_home_id))
    capacity_factor = clamp(math.log10(max(capacity, 1000.0)) / 5.0, 0.0, 1.0)
    pitch_area = pitch_l * pitch_w if pitch_l and pitch_w else 0.0
    pitch_factor = clamp((pitch_area - 6800.0) / 800.0, -0.5, 0.5) if pitch_area else 0.0
    return {
        "available": True,
        "name": venue.get("name") or summary.get("name"),
        "city": venue.get("city") or summary.get("city"),
        "country": venue.get("country") or summary.get("country"),
        "capacity": int(capacity) if capacity else None,
        "home_ground_match": home_ground,
        "capacity_factor": round(capacity_factor, 3),
        "pitch_factor": round(pitch_factor, 3),
    }


def referee_signal(ctx: Dict[str, Any]) -> Dict[str, Any]:
    risk = ctx.get("referee_risk") if isinstance(ctx.get("referee_risk"), dict) else {}
    if not risk:
        return {"available": False}
    cards = num(risk.get("cards_risk_score"), 0)
    fouls = num(risk.get("avg_fouls_per_match"), 0)
    goals = num(risk.get("avg_goals_per_match"), 0)
    strictness = clamp(cards / 100.0 * 0.65 + fouls / 35.0 * 0.25, 0.0, 1.25)
    flow_index = clamp(goals / 3.2 - fouls / 45.0, -0.5, 0.8)
    return {
        "available": True,
        "name": ctx.get("referee_name"),
        "label": risk.get("label"),
        "cards_risk_score": round(cards, 1),
        "avg_fouls_per_match": round(fouls, 2),
        "strictness": round(strictness, 3),
        "flow_index": round(flow_index, 3),
    }


def compute_hardening(pred: Dict[str, Any], ctx: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    ev = pred.get("event") if isinstance(pred.get("event"), dict) else {}
    if not ctx:
        return {
            "available": False,
            "source": VERSION,
            "event_id": ev.get("id"),
            "coverage_score": 0,
            "reliability": 0.0,
            "warnings": ["missing_context_entities"],
        }
    home_mgr = manager_signal(ctx.get("home_manager") if isinstance(ctx.get("home_manager"), dict) else {})
    away_mgr = manager_signal(ctx.get("away_manager") if isinstance(ctx.get("away_manager"), dict) else {})
    venue = venue_signal(ctx, pred)
    referee = referee_signal(ctx)
    coverage = sum(1 for x in (home_mgr, away_mgr, venue, referee) if x.get("available"))
    reliability = clamp(coverage / 4.0 * 0.65 + min(num(home_mgr.get("reliability"), 0), num(away_mgr.get("reliability"), 0)) * 0.35, 0.0, 1.0)
    warnings: List[str] = []
    if not referee.get("available"):
        warnings.append("referee_missing")
    if not venue.get("available"):
        warnings.append("venue_missing")
    if not home_mgr.get("available") or not away_mgr.get("available"):
        warnings.append("manager_missing")
    if venue.get("available") and not venue.get("home_ground_match"):
        warnings.append("neutral_or_uncertain_venue")

    manager_win_delta = num(home_mgr.get("win_pct"), 0) - num(away_mgr.get("win_pct"), 0) if home_mgr.get("available") and away_mgr.get("available") else 0.0
    manager_attack_delta = num(home_mgr.get("attacking_index"), 0) - num(away_mgr.get("attacking_index"), 0) if home_mgr.get("available") and away_mgr.get("available") else 0.0
    venue_home_edge = 0.12 if venue.get("home_ground_match") else 0.0
    referee_goal_drag = -0.05 if num(referee.get("strictness"), 0) > 0.72 else 0.0
    confidence_note = "strong" if reliability >= 0.70 else "partial" if reliability > 0 else "missing"

    return {
        "available": coverage > 0,
        "source": VERSION,
        "event_id": ev.get("id"),
        "home_team": ev.get("home_team") or ctx.get("home_team"),
        "away_team": ev.get("away_team") or ctx.get("away_team"),
        "coverage_score": coverage,
        "reliability": round(reliability, 3),
        "confidence_note": confidence_note,
        "home_manager": home_mgr,
        "away_manager": away_mgr,
        "venue": venue,
        "referee": referee,
        "deltas": {
            "manager_win_pct": round(manager_win_delta, 2),
            "manager_attack_index": round(manager_attack_delta, 3),
            "venue_home_edge": venue_home_edge,
            "referee_goal_drag": referee_goal_drag,
        },
        "warnings": warnings,
    }


def main() -> int:
    pred_path = DATA_DIR / "predictions.json"
    preds_payload = read_json(pred_path, {})
    preds = preds_payload.get("results") if isinstance(preds_payload, dict) else None
    if not isinstance(preds, list):
        write_json(DEBUG_DIR / "context_entity_hardening_debug.json", {"updated_at": now_iso(), "source": VERSION, "error": "missing_predictions"})
        return 0

    ctx_idx = build_index(read_json(DATA_DIR / "context_intelligence.json", {}))
    rows: List[Dict[str, Any]] = []
    enriched: List[Dict[str, Any]] = []
    available = strong = warnings_total = 0

    for pred in preds:
        if not isinstance(pred, dict):
            enriched.append(pred)
            continue
        eid = event_id_from_pred(pred)
        hard = compute_hardening(pred, ctx_idx.get(eid))
        pred["context_entity_hardening"] = hard
        pred["_context_entity_hardening_engine"] = VERSION
        if hard.get("available"):
            available += 1
        if hard.get("reliability", 0) >= 0.70:
            strong += 1
        warnings_total += len(hard.get("warnings") or [])
        rows.append({
            "event_id": eid,
            "match": f"{hard.get('home_team', '—')} vs {hard.get('away_team', '—')}",
            "available": hard.get("available"),
            "coverage_score": hard.get("coverage_score"),
            "reliability": hard.get("reliability"),
            "confidence_note": hard.get("confidence_note"),
            "deltas": hard.get("deltas"),
            "warnings": hard.get("warnings"),
        })
        enriched.append(pred)

    preds_payload["results"] = enriched
    preds_payload["count"] = len(enriched)
    preds_payload["updated_at"] = now_iso()
    preds_payload["_context_entity_hardening_engine"] = VERSION
    write_json(pred_path, preds_payload)
    summary = {
        "total_predictions": len(enriched),
        "context_events_indexed": len(ctx_idx),
        "available_predictions": available,
        "strong_reliability_predictions": strong,
        "warnings_total": warnings_total,
        "score_impact": "none_safe_audit_only",
    }
    payload = {"updated_at": now_iso(), "source": VERSION, "count": len(rows), "summary": summary, "results": rows}
    write_json(DATA_DIR / "context_entity_hardening.json", payload)
    write_json(DEBUG_DIR / "context_entity_hardening_debug.json", {"updated_at": now_iso(), "source": VERSION, "summary": summary, "sample": rows[:30]})
    print(f"Context Entity Hardening: available={available}/{len(enriched)} strong={strong} warnings={warnings_total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
