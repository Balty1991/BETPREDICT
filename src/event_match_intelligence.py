#!/usr/bin/env python3
"""BetPredict Event Match Intelligence v1.

Folosește data/event_stats.json + data/event_incidents.json.
Scop:
- normalizează stats/incidents într-un scor compact per eveniment;
- adaugă blocul event_match_intelligence în predictions.json;
- aplică doar bonus foarte mic, doar când există date reale și susțin direcția principală;
- idempotent: bonusul nu se dublează la rulări repetate;
- regenerează fișierele dependente.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DEBUG_DIR = DATA_DIR / "debug"
VERSION = "event_match_intelligence_v1"

for p in (ROOT, ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


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


def quality_from_score(score: float) -> str:
    s = num(score, 0)
    if s >= 92:
        return "A+"
    if s >= 82:
        return "A"
    if s >= 75:
        return "B+"
    if s >= 65:
        return "B"
    if s >= 55:
        return "C"
    if s >= 45:
        return "D"
    return "E"


def event_id_from_pred(pred: Dict[str, Any]) -> str:
    ev = pred.get("event") if isinstance(pred.get("event"), dict) else {}
    return str(ev.get("id") or pred.get("event_id") or "")


def best_1x2(pred: Dict[str, Any]) -> str:
    vals = {
        "home": num(pred.get("ctx_home_win", pred.get("blended_home", pred.get("home_win_probability"))), 0),
        "draw": num(pred.get("ctx_draw", pred.get("blended_draw", pred.get("draw_probability"))), 0),
        "away": num(pred.get("ctx_away_win", pred.get("blended_away", pred.get("away_win_probability"))), 0),
    }
    return max(vals.items(), key=lambda kv: kv[1])[0]


def current_base_score(pred: Dict[str, Any]) -> float:
    current = num(pred.get("smartbet_score"), 0)
    previous_base = pred.get("smartbet_score_before_event_match_intelligence")
    previous_bonus = num(pred.get("event_match_intelligence_bonus"), 0)
    if previous_base is not None:
        before = num(previous_base, current)
        if abs(current - (before + previous_bonus)) <= 0.08:
            return before
    return current


def extract_rows(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        return [x for x in payload["results"] if isinstance(x, dict)]
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    return []


def build_index(payload: Any) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in extract_rows(payload):
        eid = str(row.get("event_id") or "")
        if eid:
            out[eid] = row
    return out


def flatten_numbers(obj: Any, prefix: str = "") -> Dict[str, float]:
    out: Dict[str, float] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            out.update(flatten_numbers(v, key))
    elif isinstance(obj, list):
        # listele mari nu sunt stats numerice agregate
        return out
    else:
        try:
            if obj is not None and obj != "":
                x = float(obj)
                if math.isfinite(x):
                    out[prefix] = x
        except Exception:
            pass
    return out


def pick_metric(flat: Dict[str, float], patterns: List[str], default: float = 0.0) -> float:
    for pat in patterns:
        pat_l = pat.lower()
        for key, val in flat.items():
            if pat_l in key.lower():
                return float(val)
    return default


def parse_stats(row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not row or not row.get("ok"):
        return {"available": False, "reason": "missing_stats"}
    raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
    stats = raw.get("stats") if isinstance(raw.get("stats"), dict) else raw
    if not isinstance(stats, dict) or not stats:
        return {"available": False, "reason": "empty_stats"}

    home_obj = stats.get("home") if isinstance(stats.get("home"), dict) else {}
    away_obj = stats.get("away") if isinstance(stats.get("away"), dict) else {}
    if not home_obj and not away_obj:
        return {"available": False, "reason": "stats_without_sides"}

    hf = flatten_numbers(home_obj)
    af = flatten_numbers(away_obj)
    metric_patterns = {
        "xg": ["xg.actual", "expected_goals", "xg"],
        "shots": ["shots.total", "total_shots", "shots"],
        "shots_on": ["shots_on", "shots.on", "on_target"],
        "corners": ["corner"],
        "possession": ["possession"],
        "cards": ["yellow", "red", "cards"],
    }
    h = {k: pick_metric(hf, pats) for k, pats in metric_patterns.items()}
    a = {k: pick_metric(af, pats) for k, pats in metric_patterns.items()}

    # Dacă toate sunt zero/null, tratăm ca empty real, nu ca semnal.
    if sum(abs(v) for v in list(h.values()) + list(a.values())) <= 1e-9:
        return {"available": False, "reason": "stats_all_zero_or_null"}

    pressure_h = h["xg"] * 2.0 + h["shots_on"] * 0.45 + h["shots"] * 0.12 + h["corners"] * 0.12 + h["possession"] * 0.015
    pressure_a = a["xg"] * 2.0 + a["shots_on"] * 0.45 + a["shots"] * 0.12 + a["corners"] * 0.12 + a["possession"] * 0.015
    tempo = clamp((h["shots"] + a["shots"] + h["corners"] + a["corners"]) / 32.0, 0.0, 1.5)
    cards_risk = clamp((h["cards"] + a["cards"]) / 8.0, 0.0, 1.5)
    return {
        "available": True,
        "home": {k: round(v, 3) for k, v in h.items()},
        "away": {k: round(v, 3) for k, v in a.items()},
        "home_pressure": round(pressure_h, 3),
        "away_pressure": round(pressure_a, 3),
        "pressure_delta": round(pressure_h - pressure_a, 3),
        "tempo_index": round(tempo, 3),
        "cards_risk": round(cards_risk, 3),
    }


def parse_incidents(row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not row or not row.get("ok"):
        return {"available": False, "reason": "missing_incidents"}
    raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
    inc = raw.get("incidents") if isinstance(raw.get("incidents"), list) else row.get("results") if isinstance(row.get("results"), list) else []
    if not inc:
        return {"available": False, "reason": "empty_incidents", "count": 0}

    counts = {"goals": 0, "cards": 0, "subs": 0, "var": 0, "other": 0}
    for it in inc:
        if not isinstance(it, dict):
            continue
        txt = " ".join(str(it.get(k, "")) for k in ("type", "incident_type", "text", "description", "name")).lower()
        if "goal" in txt or "gol" in txt:
            counts["goals"] += 1
        elif "card" in txt or "yellow" in txt or "red" in txt:
            counts["cards"] += 1
        elif "sub" in txt:
            counts["subs"] += 1
        elif "var" in txt:
            counts["var"] += 1
        else:
            counts["other"] += 1
    total = sum(counts.values())
    heat = clamp((counts["goals"] * 0.30 + counts["cards"] * 0.16 + counts["var"] * 0.18 + total * 0.035), 0.0, 1.5)
    return {"available": True, "count": total, "counts": counts, "incident_heat": round(heat, 3)}


def compute_impact(pred: Dict[str, Any], stats_row: Optional[Dict[str, Any]], incidents_row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    ev = pred.get("event") if isinstance(pred.get("event"), dict) else {}
    stats = parse_stats(stats_row)
    incidents = parse_incidents(incidents_row)
    available = bool(stats.get("available") or incidents.get("available"))
    if not available:
        return {
            "available": False,
            "source": VERSION,
            "event_id": ev.get("id"),
            "stats": stats,
            "incidents": incidents,
            "alignment": "no_event_match_data",
            "adjustment_pp": {"home": 0.0, "draw": 0.0, "away": 0.0},
            "goals_market_adj": {"over15": 1.0, "over25": 1.0, "under35": 1.0},
            "smartbet_bonus": 0.0,
        }

    pressure_delta = num(stats.get("pressure_delta"), 0.0) if stats.get("available") else 0.0
    tempo = num(stats.get("tempo_index"), 0.0) if stats.get("available") else 0.0
    heat = num(incidents.get("incident_heat"), 0.0) if incidents.get("available") else 0.0
    reliability = clamp((0.65 if stats.get("available") else 0.0) + (0.20 if incidents.get("available") else 0.0), 0.0, 0.85)

    norm_delta = clamp(pressure_delta / 4.5, -1.0, 1.0)
    home_pp = clamp(norm_delta * reliability * 0.90, -0.65, 0.65)
    away_pp = -home_pp
    draw_pp = -abs(home_pp) * 0.14

    over_adj = clamp(1.0 + (tempo - 0.75) * 0.08 + heat * 0.04, 0.94, 1.08)
    under35_adj = clamp(1.0 - (over_adj - 1.0) * 0.65, 0.95, 1.04)

    best = best_1x2(pred)
    aligned = (best == "home" and home_pp > 0.06) or (best == "away" and away_pp > 0.06)
    contradiction = (best == "home" and home_pp < -0.12) or (best == "away" and away_pp < -0.12)
    bonus = clamp(abs(home_pp) * 0.45, 0.0, 0.30) if aligned and reliability >= 0.50 else 0.0

    if contradiction:
        label = "event_stats_contradict_main_side"
    elif aligned:
        label = "event_stats_support_main_side"
    elif stats.get("available"):
        label = "event_stats_neutral"
    else:
        label = "event_incidents_only"

    return {
        "available": True,
        "source": VERSION,
        "event_id": ev.get("id"),
        "home_team": ev.get("home_team"),
        "away_team": ev.get("away_team"),
        "stats": stats,
        "incidents": incidents,
        "reliability": round(reliability, 3),
        "alignment": label,
        "adjustment_pp": {"home": round(home_pp, 3), "draw": round(draw_pp, 3), "away": round(away_pp, 3)},
        "goals_market_adj": {"over15": round(over_adj, 3), "over25": round(over_adj, 3), "under35": round(under35_adj, 3)},
        "smartbet_bonus": round(bonus, 2),
    }


def regenerate_dependents() -> Dict[str, Any]:
    report = {"signals": False, "value_bets": False, "selection_journal": False, "performance_summary": False, "qa_report": False, "errors": []}
    try:
        import fetch_daily as fd  # noqa
    except Exception as exc:
        report["errors"].append(f"fetch_daily import failed: {exc}")
        return report
    steps = [
        ("signals", getattr(fd, "compute_signals", None)),
        ("value_bets", getattr(fd, "_compute_value_bets_local", None)),
        ("selection_journal", getattr(fd, "update_selection_journal", None)),
        ("performance_summary", getattr(fd, "compute_performance_summary", None)),
        ("qa_report", getattr(fd, "fetch_production_qa_report", None)),
    ]
    for name, fn in steps:
        if not callable(fn):
            report["errors"].append(f"{name}: function missing")
            continue
        try:
            fn()
            report[name] = True
        except Exception as exc:
            report["errors"].append(f"{name}: {exc}")
    return report


def main() -> int:
    pred_path = DATA_DIR / "predictions.json"
    preds_payload = read_json(pred_path, {})
    preds = preds_payload.get("results") if isinstance(preds_payload, dict) else None
    if not isinstance(preds, list):
        write_json(DEBUG_DIR / "event_match_intelligence_debug.json", {"updated_at": now_iso(), "source": VERSION, "error": "missing_predictions"})
        return 0

    stats_idx = build_index(read_json(DATA_DIR / "event_stats.json", {}))
    inc_idx = build_index(read_json(DATA_DIR / "event_incidents.json", {}))
    rows: List[Dict[str, Any]] = []
    enriched: List[Dict[str, Any]] = []
    available = boosted = contradicted = 0
    max_bonus = 0.0

    for pred in preds:
        if not isinstance(pred, dict):
            enriched.append(pred)
            continue
        eid = event_id_from_pred(pred)
        impact = compute_impact(pred, stats_idx.get(eid), inc_idx.get(eid))
        base = current_base_score(pred)
        bonus = num(impact.get("smartbet_bonus"), 0.0)
        new_score = clamp(base + bonus, 0.0, 100.0)

        pred["event_match_intelligence"] = impact
        pred["smartbet_score_before_event_match_intelligence"] = round(base, 2)
        pred["event_match_intelligence_bonus"] = round(bonus, 2)
        pred["smartbet_score"] = round(new_score, 2)
        pred["quality_grade"] = quality_from_score(new_score)
        pred["_event_match_intelligence_engine"] = VERSION

        if impact.get("available"):
            available += 1
        if bonus > 0:
            boosted += 1
            max_bonus = max(max_bonus, bonus)
        if "contradict" in str(impact.get("alignment")):
            contradicted += 1

        ev = pred.get("event") if isinstance(pred.get("event"), dict) else {}
        rows.append({
            "event_id": ev.get("id") or eid,
            "match": f"{ev.get('home_team', '—')} vs {ev.get('away_team', '—')}",
            "available": impact.get("available"),
            "alignment": impact.get("alignment"),
            "reliability": impact.get("reliability"),
            "adjustment_pp": impact.get("adjustment_pp"),
            "goals_market_adj": impact.get("goals_market_adj"),
            "smartbet_before": round(base, 2),
            "smartbet_bonus": round(bonus, 2),
            "smartbet_after": round(new_score, 2),
        })
        enriched.append(pred)

    preds_payload["results"] = enriched
    preds_payload["count"] = len(enriched)
    preds_payload["updated_at"] = now_iso()
    preds_payload["_event_match_intelligence_engine"] = VERSION
    write_json(pred_path, preds_payload)

    summary = {
        "total_predictions": len(enriched),
        "stats_events_indexed": len(stats_idx),
        "incidents_events_indexed": len(inc_idx),
        "available_predictions": available,
        "contradicted_predictions": contradicted,
        "boosted_predictions": boosted,
        "max_smartbet_bonus": round(max_bonus, 2),
    }
    payload = {"updated_at": now_iso(), "source": VERSION, "count": len(rows), "summary": summary, "results": rows}
    write_json(DATA_DIR / "event_match_intelligence.json", payload)
    regen = regenerate_dependents()
    write_json(DEBUG_DIR / "event_match_intelligence_debug.json", {"updated_at": now_iso(), "source": VERSION, "summary": summary, "sample": rows[:30], "regenerated": regen})
    print(f"Event Match Intelligence: available={available}/{len(enriched)} boosted={boosted} max_bonus={round(max_bonus,2)} errors={len(regen.get('errors') or [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
