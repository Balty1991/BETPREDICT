#!/usr/bin/env python3
"""League Strength / Standings Strength Safety Calibration.

Rulează după src/fetch_daily.py. Este idempotent: recalibrează mereu din
pre_league_home/pre_league_draw/pre_league_away și păstrează ajustarea brută în
league_strength.raw_adjustment_pp.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DEBUG_DIR = DATA_DIR / "debug"
for p in (ROOT, ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

try:
    from analytics_core import quality_grade as analytics_quality_grade
except Exception:
    analytics_quality_grade = None

try:
    import fetch_daily as fd
except Exception as exc:
    fd = None
    FETCH_DAILY_IMPORT_ERROR = str(exc)
else:
    FETCH_DAILY_IMPORT_ERROR = ""

CAPS_PP = {"home": 4.0, "draw": 2.0, "away": 4.0}
UNRELIABLE_COMPETITION_RE = re.compile(
    r"\b(cup|cupa|copa|coppa|coupe|pokal|trophy|friendly|qualification|qualifying|playoff|play\s*off|knockout)\b",
    re.IGNORECASE,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fnum(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


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


def prob(pred: Dict[str, Any], primary: str, fallbacks: Iterable[str]) -> Optional[float]:
    value = fnum(pred.get(primary))
    if value is not None and value > 0:
        return value
    for key in fallbacks:
        value = fnum(pred.get(key))
        if value is not None and value > 0:
            return value
    return None


def norm3(h: float, d: float, a: float) -> Tuple[float, float, float]:
    total = h + d + a
    if total <= 0:
        return h, d, a
    return h / total, d / total, a / total


def adjustment_dict(value: Any) -> Dict[str, float]:
    if not isinstance(value, dict):
        return {"home": 0.0, "draw": 0.0, "away": 0.0}
    return {side: fnum(value.get(side), 0.0) or 0.0 for side in ("home", "draw", "away")}


def team_played(team: Any) -> Optional[float]:
    if not isinstance(team, dict):
        return None
    for key in ("played", "matches_played", "games_played", "played_matches", "matches"):
        value = fnum(team.get(key))
        if value is not None:
            return value
    return None


def competition_text(pred: Dict[str, Any], ls: Dict[str, Any]) -> str:
    ev = pred.get("event") if isinstance(pred.get("event"), dict) else {}
    parts = [
        pred.get("_league_name"), ev.get("league_name"), ev.get("competition_name"),
        ev.get("tournament_name"), ls.get("league_name"), ls.get("season_name"), ls.get("country"),
    ]
    return " ".join(str(x) for x in parts if x not in (None, ""))


def reliability(pred: Dict[str, Any], ls: Dict[str, Any]) -> Dict[str, Any]:
    text = competition_text(pred, ls)
    home_played = team_played(ls.get("home"))
    away_played = team_played(ls.get("away"))
    known = [x for x in (home_played, away_played) if x is not None]
    sample_min = min(known) if known else None

    base = {
        "competition_text": text,
        "home_played": home_played,
        "away_played": away_played,
        "sample_min": sample_min,
    }
    if UNRELIABLE_COMPETITION_RE.search(text or ""):
        return {**base, "scale": 0.0, "reason": "competition_unreliable_type"}
    if sample_min is None:
        return {**base, "scale": 0.65, "reason": "sample_unknown"}
    if sample_min < 4:
        return {**base, "scale": 0.0, "reason": "sample_under_4"}
    if 4 <= sample_min <= 7:
        return {**base, "scale": 0.5, "reason": "sample_4_to_7_partial"}
    return {**base, "scale": 1.0, "reason": "sample_8_plus_full"}


def raw_adjustment(pred: Dict[str, Any], base: Dict[str, float], ls: Dict[str, Any]) -> Dict[str, float]:
    if isinstance(ls.get("raw_adjustment_pp"), dict):
        return adjustment_dict(ls.get("raw_adjustment_pp"))
    if isinstance(ls.get("adjustment_pp"), dict):
        return adjustment_dict(ls.get("adjustment_pp"))
    return {
        "home": ((fnum(pred.get("blended_home"), base["home"]) or base["home"]) - base["home"]) * 100.0,
        "draw": ((fnum(pred.get("blended_draw"), base["draw"]) or base["draw"]) - base["draw"]) * 100.0,
        "away": ((fnum(pred.get("blended_away"), base["away"]) or base["away"]) - base["away"]) * 100.0,
    }


def cap_weight_balance(raw_pp: Dict[str, float], scale: float) -> Tuple[Dict[str, float], Dict[str, float], bool]:
    capped = {side: clamp(raw_pp.get(side, 0.0), -CAPS_PP[side], CAPS_PP[side]) for side in CAPS_PP}
    capped_any = any(abs(raw_pp.get(side, 0.0) - capped[side]) > 1e-9 for side in CAPS_PP)
    final = {side: capped[side] * scale for side in CAPS_PP}

    residual = -sum(final.values())
    for side in ("draw", "home", "away"):
        if abs(residual) <= 1e-9:
            break
        if residual > 0:
            move = min(CAPS_PP[side] - final[side], residual)
            if move > 0:
                final[side] += move
                residual -= move
        else:
            move = min(CAPS_PP[side] + final[side], -residual)
            if move > 0:
                final[side] -= move
                residual += move
    return capped, final, capped_any


def grade(score: float) -> str:
    if analytics_quality_grade:
        try:
            return analytics_quality_grade(score)
        except Exception:
            pass
    if score >= 82:
        return "A+"
    if score >= 74:
        return "A"
    if score >= 66:
        return "B+"
    if score >= 58:
        return "B"
    if score >= 50:
        return "C"
    return "D"


def recompute_score_fields(pred: Dict[str, Any], scale: float) -> None:
    p_h = fnum(pred.get("blended_home"), 0.0) or 0.0
    p_d = fnum(pred.get("blended_draw"), 0.0) or 0.0
    p_a = fnum(pred.get("blended_away"), 0.0) or 0.0
    best_p = max(p_h, p_d, p_a)
    edge_pp = (best_p - 0.5) * 100.0
    base_score = min(
        100.0,
        min(100.0, max(0.0, (best_p - 0.5) / 0.3 * 100.0)) * 0.6
        + min(100.0, max(0.0, edge_pp / 15.0 * 100.0)) * 0.4,
    )

    ls = pred.get("league_strength") if isinstance(pred.get("league_strength"), dict) else {}
    bonus = 0.0
    if ls.get("available"):
        delta = abs(fnum(ls.get("delta_strength"), 0.0) or 0.0)
        bonus = clamp((delta - 8.0) / 35.0 * 4.0, 0.0, 4.0) * scale

    pred["league_strength_bonus"] = round(bonus, 2)
    pred["smartbet_score"] = round(min(100.0, base_score + bonus), 1)
    pred["edge_pp"] = round(edge_pp, 2)
    confidence = fnum(pred.get("confidence"), None)
    confidence_part = (confidence if confidence is not None else best_p) * 100.0
    pred["quality_grade"] = grade(confidence_part * 0.58 + pred["smartbet_score"] * 0.42)


def calibrate_prediction(pred: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    ls = pred.get("league_strength") if isinstance(pred.get("league_strength"), dict) else {}
    if not ls.get("available"):
        pred["league_strength_safety"] = {
            "applied": False,
            "reason": ls.get("reason") or "league_strength_unavailable",
            "updated_at": now_iso(),
        }
        return False, {"available": False, "calibrated": False}

    pre_h = prob(pred, "pre_league_home", ("home_win_probability", "blended_home"))
    pre_d = prob(pred, "pre_league_draw", ("draw_probability", "blended_draw"))
    pre_a = prob(pred, "pre_league_away", ("away_win_probability", "blended_away"))
    if pre_h is None or pre_d is None or pre_a is None or pre_h + pre_d + pre_a <= 0.2:
        pred["league_strength_safety"] = {
            "applied": False,
            "reason": "missing_pre_league_probabilities",
            "updated_at": now_iso(),
        }
        return False, {"available": True, "calibrated": False}

    pre_h, pre_d, pre_a = norm3(pre_h, pre_d, pre_a)
    pred["pre_league_home"] = round(pre_h, 4)
    pred["pre_league_draw"] = round(pre_d, 4)
    pred["pre_league_away"] = round(pre_a, 4)

    base = {"home": pre_h, "draw": pre_d, "away": pre_a}
    raw_pp = raw_adjustment(pred, base, ls)
    rel = reliability(pred, ls)
    scale = fnum(rel.get("scale"), 0.0) or 0.0
    capped_pp, final_pp, capped_any = cap_weight_balance(raw_pp, scale)

    new_h = pre_h + final_pp["home"] / 100.0
    new_d = pre_d + final_pp["draw"] / 100.0
    new_a = pre_a + final_pp["away"] / 100.0
    if min(new_h, new_d, new_a) <= 0 or new_h + new_d + new_a <= 0:
        final_pp = {"home": 0.0, "draw": 0.0, "away": 0.0}
        new_h, new_d, new_a = pre_h, pre_d, pre_a
        rel = {**rel, "reason": f"{rel.get('reason')}_invalid_probability_guard"}
        scale = 0.0

    pred["blended_home"] = round(new_h, 4)
    pred["blended_draw"] = round(new_d, 4)
    pred["blended_away"] = round(new_a, 4)

    raw_clean = {side: round(raw_pp.get(side, 0.0), 2) for side in CAPS_PP}
    capped_clean = {side: round(capped_pp.get(side, 0.0), 2) for side in CAPS_PP}
    final_clean = {
        "home": round((new_h - pre_h) * 100.0, 2),
        "draw": round((new_d - pre_d) * 100.0, 2),
        "away": round((new_a - pre_a) * 100.0, 2),
    }
    weighted_clean = {side: round(capped_pp[side] * scale, 2) for side in CAPS_PP}

    calibration = {
        "version": "league_strength_safety_v1",
        "updated_at": now_iso(),
        "idempotent_from": "pre_league_home/pre_league_draw/pre_league_away",
        "scale": round(scale, 2),
        "reason": rel.get("reason"),
        "caps_pp": CAPS_PP,
        "competition_text": rel.get("competition_text"),
        "home_played": rel.get("home_played"),
        "away_played": rel.get("away_played"),
        "sample_min": rel.get("sample_min"),
        "raw_adjustment_pp": raw_clean,
        "capped_adjustment_pp": capped_clean,
        "weighted_before_rebalance_pp": weighted_clean,
        "final_adjustment_pp": final_clean,
        "capped": capped_any,
    }

    ls["raw_adjustment_pp"] = raw_clean
    ls["adjustment_pp"] = final_clean
    ls["calibration"] = calibration
    pred["league_strength"] = ls
    pred["league_strength_safety"] = {
        "applied": True,
        "scale": round(scale, 2),
        "reason": rel.get("reason"),
        "capped": capped_any,
        "sample_min": rel.get("sample_min"),
        "raw_max_abs_pp": round(max(abs(v) for v in raw_pp.values()), 2),
        "final_max_abs_pp": round(max(abs(v) for v in final_clean.values()), 2),
    }
    recompute_score_fields(pred, scale)

    return True, {
        "available": True,
        "calibrated": True,
        "scale": scale,
        "capped": capped_any,
        "raw_max_abs_pp": max(abs(v) for v in raw_pp.values()),
        "final_max_abs_pp": max(abs(v) for v in final_clean.values()),
    }


def sample_row(pred: Dict[str, Any]) -> Dict[str, Any]:
    ev = pred.get("event") if isinstance(pred.get("event"), dict) else {}
    ls = pred.get("league_strength") if isinstance(pred.get("league_strength"), dict) else {}
    cal = ls.get("calibration") if isinstance(ls.get("calibration"), dict) else {}
    return {
        "event_id": ev.get("id") or pred.get("id"),
        "match": f"{ev.get('home_team', '—')} vs {ev.get('away_team', '—')}",
        "league": pred.get("_league_name") or ev.get("league_name") or ls.get("league_name"),
        "scale": cal.get("scale"),
        "reason": cal.get("reason"),
        "sample_min": cal.get("sample_min"),
        "raw_adjustment_pp": ls.get("raw_adjustment_pp"),
        "final_adjustment_pp": ls.get("adjustment_pp"),
        "league_strength_bonus": pred.get("league_strength_bonus"),
        "smartbet_score": pred.get("smartbet_score"),
        "quality_grade": pred.get("quality_grade"),
    }


def local_value_bets_allowed() -> bool:
    payload = read_json(DATA_DIR / "value_bets.json", {})
    source = str(payload.get("source") or "").strip().lower() if isinstance(payload, dict) else ""
    return not source or source in {"local", "local_disciplined"} or not source.startswith("bsd")


def regenerate_dependents() -> Dict[str, Any]:
    report = {
        "signals": False,
        "value_bets": False,
        "selection_journal": False,
        "performance_summary": False,
        "qa_report": False,
        "errors": [],
    }
    if fd is None:
        report["errors"].append(f"fetch_daily import failed: {FETCH_DAILY_IMPORT_ERROR}")
        return report

    steps = [("signals", fd.compute_signals)]
    if local_value_bets_allowed():
        steps.append(("value_bets", fd._compute_value_bets_local))
    steps += [
        ("selection_journal", fd.update_selection_journal),
        ("performance_summary", fd.compute_performance_summary),
        ("qa_report", fd.fetch_production_qa_report),
    ]
    for name, fn in steps:
        try:
            fn()
            report[name] = True
        except Exception as exc:
            report["errors"].append(f"{name}: {exc}")
            print(f"  ⚠ regenerate {name} failed: {exc}")
    return report


def main() -> int:
    payload = read_json(DATA_DIR / "predictions.json", {})
    preds = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(preds, list):
        write_json(DEBUG_DIR / "league_strength_debug.json", {
            "updated_at": now_iso(),
            "error": "missing_or_invalid_predictions_json",
            "total_predictions": 0,
        })
        return 1

    stats = {
        "total_predictions": len(preds),
        "available_predictions": 0,
        "calibrated_predictions": 0,
        "capped_adjustments": 0,
        "skipped_unreliable": 0,
        "partial_weighted": 0,
    }
    raw_max: List[float] = []
    final_max: List[float] = []
    sample: List[Dict[str, Any]] = []

    for pred in preds:
        if not isinstance(pred, dict):
            continue
        applied, meta = calibrate_prediction(pred)
        if meta.get("available"):
            stats["available_predictions"] += 1
        if meta.get("calibrated"):
            stats["calibrated_predictions"] += 1
            raw_max.append(float(meta.get("raw_max_abs_pp") or 0.0))
            final_max.append(float(meta.get("final_max_abs_pp") or 0.0))
            if meta.get("capped"):
                stats["capped_adjustments"] += 1
            scale = fnum(meta.get("scale"), 0.0) or 0.0
            if scale <= 0:
                stats["skipped_unreliable"] += 1
            elif scale < 1:
                stats["partial_weighted"] += 1
            if applied and len(sample) < 20:
                sample.append(sample_row(pred))

    payload["results"] = preds
    payload["count"] = len(preds)
    payload["updated_at"] = now_iso()
    payload["_league_strength_safety_version"] = "league_strength_safety_v1"
    write_json(DATA_DIR / "predictions.json", payload)

    debug = {
        "updated_at": now_iso(),
        **stats,
        "avg_adjustment_pp": round(sum(final_max) / len(final_max), 3) if final_max else 0.0,
        "avg_raw_adjustment_pp": round(sum(raw_max) / len(raw_max), 3) if raw_max else 0.0,
        "max_adjustment_pp": round(max(final_max), 3) if final_max else 0.0,
        "max_raw_adjustment_pp": round(max(raw_max), 3) if raw_max else 0.0,
        "sample": sample,
    }
    write_json(DEBUG_DIR / "league_strength_debug.json", debug)

    debug["regenerated"] = regenerate_dependents()
    write_json(DEBUG_DIR / "league_strength_debug.json", debug)

    print(
        "League Strength Safety: "
        f"total={stats['total_predictions']} available={stats['available_predictions']} "
        f"calibrated={stats['calibrated_predictions']} capped={stats['capped_adjustments']} "
        f"skipped={stats['skipped_unreliable']} partial={stats['partial_weighted']}"
    )
    return 2 if debug["regenerated"].get("errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
