"""Calibration Health Monitor — Pilon 2.

Citește data/calibration_report.json (deja calculat de calibration_engine.py)
și emite per-market un status ∈ {HEALTHY, DRIFT, CRITICAL, NO_DATA} pe care UI-ul
îl afișează ca badge.

Regulile de status sunt explicit conservatoare:
  HEALTHY  : ECE post ≤ 0.05 ȘI n ≥ 20
  DRIFT    : ECE post 0.05–0.10 SAU n în 10–19 SAU type ∈ {shift, identity}
  CRITICAL : ECE post > 0.10 SAU |bias_pp| > 15
  NO_DATA  : n < 10

Output: data/calibration_health.json — consumat de Dashboard UI și (opțional) de
pyramid_assistant pentru a filtra semnalele din market-uri CRITICAL.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

THRESHOLDS = {
    "healthy_ece":   0.05,
    "drift_ece":     0.10,
    "critical_bias_pp": 15.0,
    "min_n_healthy": 20,
    "min_n_drift":   10,
}

MARKET_LABELS = {
    "homeWin": "Home Win", "draw": "Draw", "awayWin": "Away Win",
    "btts": "BTTS", "over15": "Over 1.5", "over25": "Over 2.5", "over35": "Over 3.5",
    "under25": "Under 2.5", "under35": "Under 3.5",
}

def _load(p: Path, default):
    try: return json.loads(p.read_text("utf-8"))
    except Exception: return default

def _save(p: Path, payload: Any):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), "utf-8")

def classify(market_record: Dict[str, Any]) -> Dict[str, Any]:
    pre  = market_record.get("pre") or {}
    post = market_record.get("post") or {}
    n    = int(market_record.get("n_samples") or 0)
    mtype = str(market_record.get("type") or "")
    ece_post = post.get("ece"); ece_pre = pre.get("ece")
    bias_pp  = pre.get("bias_pp")
    try: ece_post_f = float(ece_post) if ece_post is not None else None
    except Exception: ece_post_f = None
    try: bias_f = abs(float(bias_pp)) if bias_pp is not None else None
    except Exception: bias_f = None

    # Decision tree (cel mai sever câștigă)
    status, reason = "HEALTHY", "OK"
    if n < THRESHOLDS["min_n_drift"]:
        status = "NO_DATA"
        reason = f"sample n={n} < {THRESHOLDS['min_n_drift']}"
    elif ece_post_f is not None and ece_post_f > THRESHOLDS["drift_ece"]:
        status = "CRITICAL"
        reason = f"ECE post {ece_post_f:.3f} > {THRESHOLDS['drift_ece']}"
    elif bias_f is not None and bias_f > THRESHOLDS["critical_bias_pp"]:
        status = "CRITICAL"
        reason = f"|bias| {bias_f:.1f}pp > {THRESHOLDS['critical_bias_pp']}pp"
    elif mtype in ("shift", "identity"):
        # Fallback strategy = nu avem un calibrator real → marchează drift
        status = "DRIFT"
        reason = f"fallback calibrator '{mtype}'"
    elif ece_post_f is not None and ece_post_f > THRESHOLDS["healthy_ece"]:
        status = "DRIFT"
        reason = f"ECE post {ece_post_f:.3f} > {THRESHOLDS['healthy_ece']}"
    elif n < THRESHOLDS["min_n_healthy"]:
        status = "DRIFT"
        reason = f"sample n={n} < {THRESHOLDS['min_n_healthy']}"

    return {
        "status": status,
        "reason": reason,
        "n": n,
        "type": mtype,
        "ece_pre":  ece_pre,
        "ece_post": ece_post,
        "brier_pre": pre.get("brier"),
        "brier_post": post.get("brier"),
        "bias_pp": bias_pp,
        "experimental": status in ("CRITICAL", "NO_DATA"),
    }

def main():
    print("[calibration_health] start")
    report = _load(DATA / "calibration_report.json", {})
    mkts = report.get("markets") or {}
    out: Dict[str, Any] = {}
    counter = {"HEALTHY": 0, "DRIFT": 0, "CRITICAL": 0, "NO_DATA": 0}
    for mk, rec in mkts.items():
        cls = classify(rec)
        cls["label"] = MARKET_LABELS.get(mk, mk)
        out[mk] = cls
        counter[cls["status"]] += 1
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "calibration_health.py",
        "thresholds": THRESHOLDS,
        "summary": {
            "n_markets": len(out),
            **counter,
            "healthy_share": round(counter["HEALTHY"] / max(1, len(out)), 3),
        },
        "per_market": out,
    }
    _save(DATA / "calibration_health.json", payload)
    print(f"[calibration_health] {len(out)} markets · "
          f"HEALTHY={counter['HEALTHY']} DRIFT={counter['DRIFT']} "
          f"CRITICAL={counter['CRITICAL']} NO_DATA={counter['NO_DATA']}")

if __name__ == "__main__":
    main()
