#!/usr/bin/env python3
"""BetPredict Lineup Intelligence v1.

Folosește data/event_lineups.json pentru a calcula impactul lineup-urilor
predicted/confirmed asupra predicțiilor.

Design:
- fără API calls;
- fără dependențe externe;
- idempotent: nu aplică bonusul de mai multe ori;
- impact mic și plafonat, mai ales pentru lineup predicted/beta;
- nu penalizează SmartBet direct, dar marchează când lineup-ul contrazice direcția principală;
- regenerează signals/value_bets/selection_journal/performance_summary/qa_report.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DEBUG_DIR = DATA_DIR / "debug"
VERSION = "lineup_intelligence_v1"

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


def avg(values: List[float], default: Optional[float] = None) -> Optional[float]:
    vals = [v for v in values if isinstance(v, (int, float)) and math.isfinite(v)]
    return sum(vals) / len(vals) if vals else default


def clean_pos(v: Any) -> str:
    p = str(v or "").strip().upper()
    if not p:
        return "?"
    if p.startswith("G"):
        return "G"
    if p.startswith("D") or p in ("CB", "LB", "RB", "LWB", "RWB"):
        return "D"
    if p.startswith("M") or p in ("CM", "DM", "AM", "LM", "RM"):
        return "M"
    if p.startswith("F") or p.startswith("A") or p in ("ST", "CF", "LW", "RW", "FW"):
        return "F"
    return p[:1]


def extract_raw_lineup(row: Dict[str, Any]) -> Dict[str, Any]:
    raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
    if raw:
        return raw
    if isinstance(row.get("lineups"), dict):
        return row
    return {}


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
    previous_base = pred.get("smartbet_score_before_lineup_intelligence")
    previous_bonus = num(pred.get("lineup_intelligence_bonus"), 0)
    if previous_base is not None:
        before = num(previous_base, current)
        if abs(current - (before + previous_bonus)) <= 0.08:
            return before
    return current


def player_ai(p: Dict[str, Any]) -> float:
    return clamp(num(p.get("ai_score"), 0.0), 0.0, 1.0)


def side_metrics(side: Dict[str, Any]) -> Dict[str, Any]:
    starters = [p for p in side.get("players", []) if isinstance(p, dict)]
    subs = [p for p in side.get("substitutes", []) if isinstance(p, dict)]

    pos_counts = {"G": 0, "D": 0, "M": 0, "F": 0, "?": 0}
    for p in starters:
        pos = clean_pos(p.get("position"))
        if pos not in pos_counts:
            pos = "?"
        pos_counts[pos] += 1

    starter_scores = [player_ai(p) for p in starters]
    sub_scores = [player_ai(p) for p in subs]
    top3 = sorted(starter_scores, reverse=True)[:3]
    attack_scores = [player_ai(p) for p in starters if clean_pos(p.get("position")) in ("M", "F")]
    defense_scores = [player_ai(p) for p in starters if clean_pos(p.get("position")) in ("G", "D")]

    starters_count = len(starters)
    completeness = clamp(starters_count / 11.0, 0.0, 1.0)
    formation = str(side.get("formation") or "—")
    conf = clamp(num(side.get("confidence"), 0.0), 0.0, 1.0)

    avg_ai = avg(starter_scores, 0.0) or 0.0
    top_ai = avg(top3, avg_ai) or avg_ai
    attack_ai = avg(attack_scores, avg_ai) or avg_ai
    defense_ai = avg(defense_scores, avg_ai) or avg_ai
    bench_ai = avg(sorted(sub_scores, reverse=True)[:5], 0.0) or 0.0

    structure_score = 0.0
    structure_score += 0.25 if pos_counts["G"] >= 1 else 0.0
    structure_score += 0.25 if pos_counts["D"] >= 3 else 0.0
    structure_score += 0.25 if pos_counts["M"] >= 2 else 0.0
    structure_score += 0.25 if (pos_counts["M"] + pos_counts["F"]) >= 4 else 0.0

    lineup_score = (
        42.0
        + avg_ai * 33.0
        + top_ai * 8.0
        + attack_ai * 5.0
        + defense_ai * 3.0
        + bench_ai * 2.0
        + structure_score * 5.0
    )

    return {
        "team_id": side.get("team_id"),
        "team_name": side.get("team_name"),
        "formation": formation,
        "confidence": round(conf, 3),
        "starters_count": starters_count,
        "substitutes_count": len(subs),
        "completeness": round(completeness, 3),
        "pos_counts": pos_counts,
        "avg_ai": round(avg_ai, 3),
        "top_ai": round(top_ai, 3),
        "attack_ai": round(attack_ai, 3),
        "defense_ai": round(defense_ai, 3),
        "bench_ai": round(bench_ai, 3),
        "structure_score": round(structure_score, 3),
        "lineup_score": round(clamp(lineup_score, 30.0, 92.0), 2),
        "top_starters": sorted(
            [
                {
                    "id": p.get("id"),
                    "name": p.get("short_name") or p.get("name"),
                    "position": clean_pos(p.get("position")),
                    "ai_score": round(player_ai(p), 3),
                    "jersey_number": p.get("jersey_number"),
                }
                for p in starters
            ],
            key=lambda x: x.get("ai_score") or 0,
            reverse=True,
        )[:5],
    }


def build_lineup_index(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    idx: Dict[str, Dict[str, Any]] = {}
    rows = payload.get("results") if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        return idx

    for row in rows:
        if not isinstance(row, dict):
            continue
        eid = str(row.get("event_id") or "")
        raw = extract_raw_lineup(row)
        lineups = raw.get("lineups") if isinstance(raw.get("lineups"), dict) else {}
        if not eid or not lineups:
            continue

        home = lineups.get("home") if isinstance(lineups.get("home"), dict) else {}
        away = lineups.get("away") if isinstance(lineups.get("away"), dict) else {}
        status = str(raw.get("lineup_status") or row.get("lineup_status") or "unknown").lower()
        beta = bool(raw.get("beta", False))

        if not home or not away:
            continue

        idx[eid] = {
            "event_id": row.get("event_id"),
            "home_team": row.get("home_team"),
            "away_team": row.get("away_team"),
            "league": row.get("league"),
            "lineup_status": status,
            "beta": beta,
            "home": side_metrics(home),
            "away": side_metrics(away),
        }
    return idx


def compute_lineup_impact(pred: Dict[str, Any], lineup: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    ev = pred.get("event") if isinstance(pred.get("event"), dict) else {}
    if not lineup:
        return {
            "available": False,
            "source": VERSION,
            "event_id": ev.get("id"),
            "alignment": "missing_lineup_data",
            "smartbet_bonus": 0.0,
            "adjustment_pp": {"home": 0.0, "draw": 0.0, "away": 0.0},
        }

    h = lineup.get("home", {})
    a = lineup.get("away", {})
    status = str(lineup.get("lineup_status") or "unknown").lower()
    beta = bool(lineup.get("beta"))

    h_score = num(h.get("lineup_score"), 0)
    a_score = num(a.get("lineup_score"), 0)
    delta = h_score - a_score

    h_comp = num(h.get("completeness"), 0)
    a_comp = num(a.get("completeness"), 0)
    h_conf = num(h.get("confidence"), 0)
    a_conf = num(a.get("confidence"), 0)

    status_factor = 1.0 if "confirmed" in status else 0.62 if "predicted" in status else 0.42
    if beta:
        status_factor *= 0.88

    reliability = clamp(min(h_comp, a_comp) * ((h_conf + a_conf) / 2.0) * status_factor, 0.0, 0.92)
    predicted = "predicted" in status or beta
    cap_pp = 0.75 if predicted else 1.45

    normalized_delta = clamp(delta / 18.0, -1.0, 1.0)
    home_pp = clamp(normalized_delta * reliability * 1.25, -cap_pp, cap_pp)
    away_pp = -home_pp
    draw_pp = -abs(home_pp) * 0.18

    best = best_1x2(pred)
    aligned = (best == "home" and home_pp > 0.08) or (best == "away" and away_pp > 0.08)
    contradiction = (best == "home" and home_pp < -0.18) or (best == "away" and away_pp < -0.18)

    bonus = 0.0
    if aligned and reliability >= 0.22:
        bonus = clamp(abs(home_pp) * (0.70 if predicted else 1.0), 0.0, 0.55 if predicted else 1.10)

    if contradiction:
        alignment = "lineup_contradicts_main_side"
    elif aligned:
        alignment = "lineup_supports_main_side"
    elif predicted:
        alignment = "predicted_lineup_neutral"
    else:
        alignment = "confirmed_lineup_neutral"

    return {
        "available": True,
        "source": VERSION,
        "event_id": ev.get("id"),
        "home_team": ev.get("home_team") or lineup.get("home_team"),
        "away_team": ev.get("away_team") or lineup.get("away_team"),
        "lineup_status": status,
        "beta": beta,
        "predicted": predicted,
        "home": h,
        "away": a,
        "delta_score": round(delta, 2),
        "normalized_delta": round(normalized_delta, 3),
        "reliability": round(reliability, 3),
        "cap_pp": round(cap_pp, 2),
        "best_1x2": best,
        "alignment": alignment,
        "adjustment_pp": {
            "home": round(home_pp, 3),
            "draw": round(draw_pp, 3),
            "away": round(away_pp, 3),
        },
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
            print(f"  ⚠ lineup_intelligence regenerate {name} failed: {exc}")
    return report


def main() -> int:
    pred_path = DATA_DIR / "predictions.json"
    preds_payload = read_json(pred_path, {})
    lineups_payload = read_json(DATA_DIR / "event_lineups.json", {})

    preds = preds_payload.get("results") if isinstance(preds_payload, dict) else None
    if not isinstance(preds, list):
        write_json(DEBUG_DIR / "lineup_intelligence_debug.json", {"updated_at": now_iso(), "source": VERSION, "error": "missing_predictions"})
        print("Lineup Intelligence: predictions missing; skip")
        return 0

    idx = build_lineup_index(lineups_payload if isinstance(lineups_payload, dict) else {})
    if not idx:
        write_json(DEBUG_DIR / "lineup_intelligence_debug.json", {"updated_at": now_iso(), "source": VERSION, "error": "missing_lineups", "total_predictions": len(preds)})
        print("Lineup Intelligence: no lineup index; skip")
        return 0

    rows: List[Dict[str, Any]] = []
    enriched: List[Dict[str, Any]] = []
    available = 0
    boosted = 0
    contradicted = 0
    predicted_count = 0
    max_bonus = 0.0

    for pred in preds:
        if not isinstance(pred, dict):
            enriched.append(pred)
            continue

        eid = event_id_from_pred(pred)
        impact = compute_lineup_impact(pred, idx.get(eid))
        base = current_base_score(pred)
        bonus = num(impact.get("smartbet_bonus"), 0)
        new_score = clamp(base + bonus, 0.0, 100.0)

        pred["lineup_intelligence"] = impact
        pred["smartbet_score_before_lineup_intelligence"] = round(base, 2)
        pred["lineup_intelligence_bonus"] = round(bonus, 2)
        pred["smartbet_score"] = round(new_score, 2)
        pred["quality_grade"] = quality_from_score(new_score)
        pred["_lineup_intelligence_engine"] = VERSION

        if impact.get("available"):
            available += 1
        if impact.get("predicted"):
            predicted_count += 1
        if "contradicts" in str(impact.get("alignment", "")):
            contradicted += 1
        if bonus > 0:
            boosted += 1
            max_bonus = max(max_bonus, bonus)

        ev = pred.get("event") if isinstance(pred.get("event"), dict) else {}
        rows.append({
            "event_id": ev.get("id") or eid,
            "match": f"{ev.get('home_team', '—')} vs {ev.get('away_team', '—')}",
            "available": impact.get("available"),
            "lineup_status": impact.get("lineup_status"),
            "beta": impact.get("beta"),
            "home_score": impact.get("home", {}).get("lineup_score"),
            "away_score": impact.get("away", {}).get("lineup_score"),
            "delta_score": impact.get("delta_score"),
            "reliability": impact.get("reliability"),
            "cap_pp": impact.get("cap_pp"),
            "alignment": impact.get("alignment"),
            "adjustment_pp": impact.get("adjustment_pp"),
            "smartbet_before": round(base, 2),
            "smartbet_bonus": round(bonus, 2),
            "smartbet_after": round(new_score, 2),
        })
        enriched.append(pred)

    preds_payload["results"] = enriched
    preds_payload["count"] = len(enriched)
    preds_payload["updated_at"] = now_iso()
    preds_payload["_lineup_intelligence_engine"] = VERSION
    write_json(pred_path, preds_payload)

    summary = {
        "total_predictions": len(enriched),
        "lineup_events_indexed": len(idx),
        "available_predictions": available,
        "predicted_lineups": predicted_count,
        "contradicted_predictions": contradicted,
        "boosted_predictions": boosted,
        "max_smartbet_bonus": round(max_bonus, 2),
        "avg_reliability": round(sum(num(r.get("reliability"), 0) for r in rows) / max(len(rows), 1), 4),
        "avg_abs_delta_score": round(sum(abs(num(r.get("delta_score"), 0)) for r in rows if r.get("available")) / max(available, 1), 3),
    }
    payload = {
        "updated_at": now_iso(),
        "source": VERSION,
        "count": len(rows),
        "summary": summary,
        "results": rows,
    }
    write_json(DATA_DIR / "lineup_intelligence.json", payload)

    regen = regenerate_dependents()
    debug = {
        "updated_at": now_iso(),
        "source": VERSION,
        "summary": summary,
        "sample": rows[:30],
        "regenerated": regen,
    }
    write_json(DEBUG_DIR / "lineup_intelligence_debug.json", debug)

    print(
        "Lineup Intelligence: "
        f"available={available}/{len(enriched)} predicted={predicted_count} "
        f"boosted={boosted} max_bonus={round(max_bonus, 2)} "
        f"regen_errors={len(regen.get('errors') or [])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
