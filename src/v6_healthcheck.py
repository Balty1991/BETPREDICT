#!/usr/bin/env python3
"""
src/v6_healthcheck.py
=====================
BetPredict Pro v6.0 — Health Check & Diagnostics

Ruleaza DUPA compute_signals_v6.py si valideaza fiecare layer v6:
  1. ML Ensemble       (ml_predictions.json + models/ml_ensemble_v6.pkl)
  2. Calibration       (calibration_report.json + models/calibrators_v6.pkl)
  3. Adaptive Thresh.  (adaptive_thresholds.json)
  4. Consensus         (consensus.json)
  5. Signals v6        (signals.json cu _v6_enhanced + signals_v6.json)

Output:
  data/v6_health.json   - status overall + per layer pentru UI dashboard
  data/debug/v6_healthcheck_debug.json

Status overall:
  GREEN   - toate layerele functionale
  YELLOW  - cateva warnings (date insuficiente, identity calibrators etc.)
  RED     - layer critic lipseste / esuat

Output v6_health.json este citit de v6_ui.js pentru a afisa semafor in dash.
"""

from __future__ import annotations
import json
import pickle
import sys
import warnings
import traceback
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

warnings.filterwarnings("ignore")

# ============================================================
# CAI
# ============================================================

ROOT_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = ROOT_DIR / "data"
MODELS_DIR = ROOT_DIR / "models"
DEBUG_DIR = DATA_DIR / "debug"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

OUT_HEALTH = DATA_DIR / "v6_health.json"
OUT_DEBUG = DEBUG_DIR / "v6_healthcheck_debug.json"

# Praguri health
MAX_AGE_HOURS = 24       # date mai vechi de 24h = warning
MIN_TRAINING = 80
MIN_CALIBRATORS = 3
MIN_SIGNALS_V6 = 10

MODEL_VERSION = "v6.0-healthcheck"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _load(path: Path) -> Optional[Any]:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _file_age_hours(path: Path) -> Optional[float]:
    if not path.exists():
        return None
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        return (_now() - mtime).total_seconds() / 3600
    except Exception:
        return None


def _save_atomic(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    tmp.replace(path)


# ============================================================
# LAYER CHECKS
# ============================================================

def check_ml_ensemble() -> Dict[str, Any]:
    """Verifica layer ML Ensemble."""
    path = DATA_DIR / "ml_predictions.json"
    model_path = MODELS_DIR / "ml_ensemble_v6.pkl"
    issues: List[str] = []
    metrics: Dict[str, Any] = {}

    data = _load(path)
    if data is None:
        return {
            "status": "RED",
            "layer": "ml_ensemble",
            "issues": ["ml_predictions.json lipseste"],
            "metrics": {},
        }

    n_matches = data.get("n_matches", 0)
    n_training = data.get("training_samples", 0)
    reason = data.get("reason")

    metrics["n_matches"] = n_matches
    metrics["n_training_samples"] = n_training
    metrics["age_hours"] = round(_file_age_hours(path) or 0, 1)
    metrics["model_pkl_exists"] = model_path.exists()
    metrics["markets_trained"] = list((data.get("metrics") or {}).keys())

    if reason:
        issues.append(f"reason: {reason}")

    if n_matches == 0:
        return {
            "status": "RED",
            "layer": "ml_ensemble",
            "issues": issues + ["Niciun meci procesat de ML"],
            "metrics": metrics,
        }

    if n_training < MIN_TRAINING:
        issues.append(f"Putine sample-uri antrenare: {n_training} < {MIN_TRAINING}")

    if not model_path.exists():
        issues.append("models/ml_ensemble_v6.pkl lipseste")

    if metrics["age_hours"] > MAX_AGE_HOURS:
        issues.append(f"Date vechi: {metrics['age_hours']:.1f}h")

    # AUC mediu per market (daca disponibil)
    aucs = []
    for m, met in (data.get("metrics") or {}).items():
        if isinstance(met, dict) and met.get("auc") is not None:
            aucs.append(float(met["auc"]))
    if aucs:
        metrics["avg_auc"] = round(sum(aucs) / len(aucs), 3)
        if metrics["avg_auc"] < 0.55:
            issues.append(f"AUC mediu scazut: {metrics['avg_auc']}")

    status = "GREEN" if not issues else ("YELLOW" if len(issues) <= 2 else "RED")
    return {"status": status, "layer": "ml_ensemble", "issues": issues, "metrics": metrics}


def check_calibration() -> Dict[str, Any]:
    """Verifica layer Calibration."""
    path = DATA_DIR / "calibration_report.json"
    pkl_path = MODELS_DIR / "calibrators_v6.pkl"
    issues: List[str] = []
    metrics: Dict[str, Any] = {}

    data = _load(path)
    if data is None:
        return {
            "status": "RED",
            "layer": "calibration",
            "issues": ["calibration_report.json lipseste"],
            "metrics": {},
        }

    overall = data.get("overall") or {}
    markets = data.get("markets") or {}

    n_calibrators = overall.get("n_markets_calibrated", 0)
    n_identity = overall.get("n_markets_identity", 0)
    total_settled = data.get("n_total_settled", 0)

    metrics["n_calibrators_active"] = n_calibrators
    metrics["n_calibrators_identity"] = n_identity
    metrics["n_total_settled"] = total_settled
    metrics["age_hours"] = round(_file_age_hours(path) or 0, 1)
    metrics["pkl_exists"] = pkl_path.exists()
    metrics["biggest_bias_market"] = overall.get("biggest_bias_market")
    metrics["biggest_bias_pp"] = overall.get("biggest_bias_value_pp")

    if total_settled == 0:
        return {
            "status": "YELLOW",
            "layer": "calibration",
            "issues": ["Niciun pariu settle-uit istoric — calibrarea nu poate functiona"],
            "metrics": metrics,
        }

    avg_pre = overall.get("avg_brier_pre")
    avg_post = overall.get("avg_brier_post")
    if avg_pre and avg_post:
        improvement_pct = round((avg_pre - avg_post) / avg_pre * 100, 1)
        metrics["brier_improvement_pct"] = improvement_pct
        if improvement_pct < 0:
            issues.append("Calibrarea inrautateste Brier — verifica datele")

    if n_calibrators < MIN_CALIBRATORS:
        issues.append(f"Putine calibratoare active: {n_calibrators} < {MIN_CALIBRATORS}")

    if not pkl_path.exists():
        issues.append("models/calibrators_v6.pkl lipseste")

    if metrics["age_hours"] > MAX_AGE_HOURS:
        issues.append(f"Date vechi: {metrics['age_hours']:.1f}h")

    # Bias detection
    if metrics.get("biggest_bias_pp") and abs(metrics["biggest_bias_pp"]) > 30:
        issues.append(
            f"Bias mare detectat pe {metrics['biggest_bias_market']}: "
            f"{metrics['biggest_bias_pp']:+.1f}pp"
        )

    status = "GREEN" if not issues else ("YELLOW" if len(issues) <= 2 else "RED")
    return {"status": status, "layer": "calibration", "issues": issues, "metrics": metrics}


def check_adaptive() -> Dict[str, Any]:
    """Verifica layer Adaptive Thresholds."""
    path = DATA_DIR / "adaptive_thresholds.json"
    issues: List[str] = []
    metrics: Dict[str, Any] = {}

    data = _load(path)
    if data is None:
        return {
            "status": "RED",
            "layer": "adaptive_thresholds",
            "issues": ["adaptive_thresholds.json lipseste"],
            "metrics": {},
        }

    overall = data.get("overall") or {}
    metrics["n_settled_total"] = overall.get("n_total_settled", 0)
    metrics["overall_roi_pct"] = overall.get("overall_roi_pct")
    metrics["overall_win_rate_pct"] = overall.get("overall_win_rate_pct")
    metrics["n_markets_with_overrides"] = overall.get("markets_with_overrides", 0)
    metrics["blacklisted_markets"] = overall.get("blacklisted_markets") or []
    metrics["best_market"] = overall.get("best_market")
    metrics["worst_market"] = overall.get("worst_market")
    metrics["age_hours"] = round(_file_age_hours(path) or 0, 1)

    if metrics["n_settled_total"] == 0:
        return {
            "status": "YELLOW",
            "layer": "adaptive_thresholds",
            "issues": ["Niciun pariu istoric — adaptive foloseste defaults"],
            "metrics": metrics,
        }

    if metrics["age_hours"] > MAX_AGE_HOURS:
        issues.append(f"Date vechi: {metrics['age_hours']:.1f}h")

    # ROI catastrofal global
    if metrics["overall_roi_pct"] is not None and metrics["overall_roi_pct"] < -20:
        issues.append(f"ROI istoric foarte negativ: {metrics['overall_roi_pct']:+.1f}%")

    status = "GREEN" if not issues else ("YELLOW" if len(issues) <= 2 else "RED")
    return {"status": status, "layer": "adaptive_thresholds", "issues": issues, "metrics": metrics}


def check_consensus() -> Dict[str, Any]:
    """Verifica layer Consensus."""
    path = DATA_DIR / "consensus.json"
    issues: List[str] = []
    metrics: Dict[str, Any] = {}

    data = _load(path)
    if data is None:
        return {
            "status": "RED",
            "layer": "consensus",
            "issues": ["consensus.json lipseste"],
            "metrics": {},
        }

    summary = data.get("summary") or {}
    metrics["n_matches"] = data.get("n_matches", 0)
    metrics["avg_consensus_score"] = summary.get("avg_consensus_score")
    metrics["tier_distribution"] = summary.get("tier_distribution") or {}
    metrics["age_hours"] = round(_file_age_hours(path) or 0, 1)

    if metrics["n_matches"] == 0:
        return {
            "status": "YELLOW",
            "layer": "consensus",
            "issues": ["Niciun meci procesat de consensus"],
            "metrics": metrics,
        }

    if metrics["age_hours"] > MAX_AGE_HOURS:
        issues.append(f"Date vechi: {metrics['age_hours']:.1f}h")

    # Cati au consens TOTAL?
    tiers = metrics.get("tier_distribution") or {}
    n_total_consensus = tiers.get("total", 0)
    n_contra = tiers.get("contradictoriu", 0)
    if metrics["n_matches"] > 0:
        metrics["pct_total_consensus"] = round(n_total_consensus / metrics["n_matches"] * 100, 1)
    if n_contra > metrics["n_matches"] * 0.3:
        issues.append(f"Multe meciuri contradictorii: {n_contra} (>30%)")

    status = "GREEN" if not issues else ("YELLOW" if len(issues) <= 2 else "RED")
    return {"status": status, "layer": "consensus", "issues": issues, "metrics": metrics}


def check_signals_v6() -> Dict[str, Any]:
    """Verifica layer Signal Augmentation."""
    path = DATA_DIR / "signals_v6.json"
    sig_path = DATA_DIR / "signals.json"
    issues: List[str] = []
    metrics: Dict[str, Any] = {}

    data = _load(path)
    if data is None:
        return {
            "status": "RED",
            "layer": "signals_v6",
            "issues": ["signals_v6.json lipseste"],
            "metrics": {},
        }

    summary = data.get("summary") or {}
    metrics["n_signals"] = data.get("count", 0)
    metrics["n_upgraded"] = summary.get("upgraded", 0)
    metrics["n_downgraded"] = summary.get("downgraded", 0)
    metrics["n_adjusted"] = summary.get("adjusted", 0)
    metrics["n_unchanged"] = summary.get("unchanged", 0)
    metrics["n_aplus"] = summary.get("quality_aplus", 0)
    metrics["n_a"] = summary.get("quality_a", 0)
    metrics["calibrators_applied"] = summary.get("calibrators_applied") or []
    metrics["age_hours"] = round(_file_age_hours(path) or 0, 1)

    # Verifica si daca signals.json e augmentat
    sigs_main = _load(sig_path)
    if sigs_main:
        metrics["signals_json_v6_enhanced"] = bool(sigs_main.get("_v6_enhanced"))
    else:
        metrics["signals_json_v6_enhanced"] = False

    if metrics["n_signals"] < MIN_SIGNALS_V6:
        issues.append(f"Putine semnale augmentate: {metrics['n_signals']}")

    if not metrics["calibrators_applied"]:
        issues.append("Niciun calibrator nu a fost aplicat")

    if not metrics["signals_json_v6_enhanced"]:
        issues.append("signals.json nu e marcat ca _v6_enhanced")

    if metrics["age_hours"] > MAX_AGE_HOURS:
        issues.append(f"Date vechi: {metrics['age_hours']:.1f}h")

    status = "GREEN" if not issues else ("YELLOW" if len(issues) <= 2 else "RED")
    return {"status": status, "layer": "signals_v6", "issues": issues, "metrics": metrics}


# ============================================================
# OVERALL HEALTH
# ============================================================

def compute_overall(layers: List[Dict]) -> Dict[str, Any]:
    """Combina status-urile layer-elor in overall."""
    statuses = [l["status"] for l in layers]
    n_red = statuses.count("RED")
    n_yellow = statuses.count("YELLOW")
    n_green = statuses.count("GREEN")

    if n_red >= 2:
        overall = "RED"
        message = "Mai multe layere critice esueaza"
    elif n_red == 1:
        # Daca doar 1 layer e RED dar restul sunt GREEN -> YELLOW
        overall = "YELLOW" if n_green >= 3 else "RED"
        red_layer = next(l["layer"] for l in layers if l["status"] == "RED")
        message = f"Layer {red_layer} are probleme critice"
    elif n_yellow >= 3:
        overall = "YELLOW"
        message = "Mai multe warnings — verifica datele"
    elif n_yellow >= 1:
        overall = "YELLOW"
        warn_layers = [l["layer"] for l in layers if l["status"] == "YELLOW"]
        message = f"Warnings pe: {', '.join(warn_layers)}"
    else:
        overall = "GREEN"
        message = "Toate layerele functionale"

    return {
        "status": overall,
        "message": message,
        "n_green": n_green,
        "n_yellow": n_yellow,
        "n_red": n_red,
    }


def collect_recommendations(layers: List[Dict]) -> List[str]:
    """Sumar de actiuni recomandate."""
    recs: List[str] = []
    for l in layers:
        for issue in l.get("issues", []):
            if "settle" in issue.lower() and "0" in issue:
                recs.append("Settezi pariuri pentru a activa calibration/adaptive")
            elif "putine sample" in issue.lower():
                recs.append("Asteapta sa se acumuleze mai multe date istorice")
            elif "lipseste" in issue.lower():
                recs.append(f"[{l['layer']}] Verifica logs Actions pentru erori")
            elif "vechi" in issue.lower():
                recs.append(f"[{l['layer']}] Trigger manual workflow")
    # Dedupe pastrand ordinea
    seen = set()
    out = []
    for r in recs:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


# ============================================================
# MAIN
# ============================================================

def main() -> int:
    started = _now_iso()
    print(f"[v6_health] === Health Check v6.0 — {started} ===")

    # Ruleaza fiecare check
    layers = [
        check_ml_ensemble(),
        check_calibration(),
        check_adaptive(),
        check_consensus(),
        check_signals_v6(),
    ]

    overall = compute_overall(layers)
    recommendations = collect_recommendations(layers)

    # Log per layer
    for l in layers:
        emoji = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}[l["status"]]
        print(f"[v6_health] {emoji} {l['layer']:20s} {l['status']:6s} "
              f"issues={len(l['issues'])}")
        for issue in l["issues"][:3]:
            print(f"[v6_health]     - {issue}")

    print(f"[v6_health] OVERALL: {overall['status']} - {overall['message']}")

    # Save output
    output = {
        "updated_at": _now_iso(),
        "model_version": MODEL_VERSION,
        "source": "v6_healthcheck",
        "overall": overall,
        "layers": {l["layer"]: l for l in layers},
        "recommendations": recommendations,
        "_pipeline_version": "v6.0-healthcheck",
    }
    _save_atomic(OUT_HEALTH, output)
    print(f"[v6_health] OK: v6_health.json scris")

    # Debug
    _save_atomic(OUT_DEBUG, {
        "status": overall["status"],
        "started_at": started,
        "ended_at": _now_iso(),
        "layers": {l["layer"]: {"status": l["status"], "metrics": l["metrics"]}
                   for l in layers},
        "recommendations": recommendations,
    })

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"[v6_health] CRASH: {e}")
        traceback.print_exc()
        try:
            _save_atomic(OUT_HEALTH, {
                "updated_at": _now_iso(),
                "model_version": MODEL_VERSION,
                "overall": {"status": "RED", "message": f"Crash: {e}"},
                "layers": {},
                "recommendations": ["Verifica logs Actions"],
            })
        except Exception:
            pass
        sys.exit(0)
