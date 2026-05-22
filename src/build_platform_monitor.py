#!/usr/bin/env python3
"""
src/build_platform_monitor.py
==============================
BetPredict Platform Monitor v1

Script de autodiagnostic zilnic. Auditează calitatea ieşirilor platformei:
  1. Integritate format JSON (schema validation)
  2. Logica datelor (cote lipsă, scoruri invalide, erori temporale)
  3. Calitatea modelului de predicţie (ROI per ligă şi per piaţă)

Output:
  data/platform_monitor.json  - raport structurat cu scor sănătate
  data/debug/platform_monitor_debug.json  - detalii extinse pentru debugging

Scorul global de sănătate (0-100) este calculat pe baza numărului şi
severităţii erorilor identificate în fiecare categorie.
"""

from __future__ import annotations
import json
import logging
import sys
import traceback
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DEBUG = DATA / "debug"
DEBUG.mkdir(exist_ok=True)

NOW_UTC = datetime.now(timezone.utc).isoformat()


def _load(fname: str) -> Optional[Any]:
    try:
        return json.loads((DATA / fname).read_text(encoding="utf-8"))
    except Exception:
        return None


def _save(fname: str, obj: Any) -> None:
    (DATA / fname).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 1. Integritate format ──────────────────────────────────────────────────────

REQUIRED_KEYS: Dict[str, List[str]] = {
    "signals.json":            ["signals", "updated_at"],
    "predictions.json":        ["predictions"],
    "value_bets.json":         ["value_bets"],
    "recent_results.json":     ["results"],
    "selection_journal.json":  ["results"],
    "clv_tracker.json":        ["summary"],
    "performance_heatmap.json":["summary"],
    "v6_health.json":          ["overall"],
}


def check_schema() -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    files_ok = 0
    for fname, keys in REQUIRED_KEYS.items():
        data = _load(fname)
        if data is None:
            errors.append(f"LIPSĂ: {fname}")
            continue
        missing = [k for k in keys if k not in data]
        if missing:
            warnings.append(f"{fname}: câmpuri lipsă {missing}")
        else:
            files_ok += 1
    return {"files_ok": files_ok, "total": len(REQUIRED_KEYS),
            "errors": errors, "warnings": warnings}


# ── 2. Logica datelor ──────────────────────────────────────────────────────────

def check_data_logic() -> Dict[str, Any]:
    issues: List[str] = []
    now_ts = datetime.now(timezone.utc).timestamp()

    # Signals: cote lipsă, EV negativ, probabilităţi invalide
    signals_data = _load("signals.json")
    if signals_data and isinstance(signals_data.get("signals"), list):
        sigs = signals_data["signals"]
        no_odds   = sum(1 for s in sigs if not s.get("odds") or float(s.get("odds", 0) or 0) < 1.01)
        neg_ev    = sum(1 for s in sigs if isinstance(s.get("ev_pct"), (int, float)) and float(s["ev_pct"]) < 0)
        bad_prob  = sum(1 for s in sigs if isinstance(s.get("adj_prob"), (int, float))
                        and not (0 < float(s["adj_prob"]) <= 100))
        if no_odds:   issues.append(f"signals: {no_odds} intrări fără cotă validă")
        if neg_ev:    issues.append(f"signals: {neg_ev} selecţii cu EV negativ")
        if bad_prob:  issues.append(f"signals: {bad_prob} probabilităţi invalide")

    # Predictions: scor 0-0 ca fallback, meciuri viitoare cu scor
    preds_data = _load("predictions.json")
    if preds_data and isinstance(preds_data.get("predictions"), list):
        preds = preds_data["predictions"]
        fallback_00 = 0
        future_with_score = 0
        for p in preds:
            sc = str(p.get("score_prob") or p.get("predicted_score") or "").strip()
            ed = p.get("event_date", "")
            if sc in ("0-0", "0:0") and ed:
                try:
                    ev_ts = datetime.fromisoformat(ed.replace("Z", "+00:00")).timestamp()
                    if ev_ts > now_ts + 300:
                        fallback_00 += 1
                except Exception:
                    pass
            if sc not in ("", "None") and ed:
                try:
                    ev_ts = datetime.fromisoformat(ed.replace("Z", "+00:00")).timestamp()
                    if ev_ts > now_ts + 7200:
                        future_with_score += 1
                except Exception:
                    pass
        if fallback_00:       issues.append(f"predictions: {fallback_00} scoruri 0-0 fallback suspecte")
        if future_with_score: issues.append(f"predictions: {future_with_score} meciuri viitoare cu scor setat")

    # Recent results: scoruri negative sau invalide
    results_data = _load("recent_results.json")
    if results_data and isinstance(results_data.get("results"), list):
        bad_scores = 0
        for r in results_data["results"]:
            hs = r.get("home_score", r.get("home_goals"))
            as_ = r.get("away_score", r.get("away_goals"))
            for sc in (hs, as_):
                if sc is not None:
                    try:
                        if float(sc) < 0:
                            bad_scores += 1
                            break
                    except (ValueError, TypeError):
                        bad_scores += 1
                        break
        if bad_scores: issues.append(f"recent_results: {bad_scores} scoruri invalide/negative")

    # Selection journal: intrări fără timestamp
    journal_data = _load("selection_journal.json")
    if journal_data and isinstance(journal_data.get("results"), list):
        no_ts = sum(1 for r in journal_data["results"] if not r.get("published_at") and not r.get("created_at"))
        if no_ts: issues.append(f"selection_journal: {no_ts} selecţii fără timestamp de publicare")

    return {"issues": issues, "issue_count": len(issues)}


# ── 3. Calitatea modelului ─────────────────────────────────────────────────────

def check_model_quality() -> Dict[str, Any]:
    alerts: List[str] = []
    league_roi: Dict[str, float] = {}
    market_roi: Dict[str, float] = {}
    downweight_candidates: List[str] = []

    heatmap = _load("performance_heatmap.json")
    if heatmap:
        leagues = heatmap.get("leagues") or {}
        for lg_name, lg_data in leagues.items():
            roi = lg_data.get("roi_pct") or lg_data.get("roi")
            sample = lg_data.get("sample") or lg_data.get("n", 0)
            if roi is not None and sample and int(sample) >= 10:
                roi_f = float(roi)
                league_roi[lg_name] = roi_f
                if roi_f < -10.0:
                    alerts.append(f"Ligă cu ROI slab: {lg_name} → {roi_f:.1f}% (sample={sample})")
                    downweight_candidates.append(lg_name)

    perf_summary = _load("performance_summary.json")
    if perf_summary:
        by_market = perf_summary.get("by_market") or {}
        for mkt_name, mkt_data in by_market.items():
            roi = mkt_data.get("roi_pct") or mkt_data.get("roi")
            sample = mkt_data.get("sample") or mkt_data.get("n", 0)
            if roi is not None and sample and int(sample) >= 10:
                roi_f = float(roi)
                market_roi[mkt_name] = roi_f
                if roi_f < -15.0:
                    alerts.append(f"Piaţă cu ROI slab: {mkt_name} → {roi_f:.1f}% (sample={sample})")
                    downweight_candidates.append(mkt_name)

    clv = _load("clv_tracker.json")
    clv_summary = clv.get("summary", {}) if clv else {}
    clv_reliable = clv_summary.get("reliable_n", 0) or 0
    clv_beat_rate = clv_summary.get("market_beat_rate") or clv_summary.get("clv_positive_rate")

    return {
        "alerts": alerts,
        "league_roi_sample": league_roi,
        "market_roi_sample": market_roi,
        "downweight_candidates": downweight_candidates,
        "clv_reliable_n": clv_reliable,
        "clv_beat_rate": clv_beat_rate,
    }


# ── Scor global de sănătate ────────────────────────────────────────────────────

def compute_health_score(schema: Dict, logic: Dict, model: Dict) -> int:
    score = 100
    # Penalizare pentru fişiere lipsă (critice)
    score -= len(schema["errors"]) * 8
    score -= len(schema["warnings"]) * 2
    # Penalizare pentru probleme de date
    score -= min(logic["issue_count"] * 4, 30)
    # Penalizare pentru alerte model
    score -= min(len(model["alerts"]) * 3, 20)
    return max(0, min(100, score))


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    log.info("=== Platform Monitor v1 ===")

    schema  = check_schema()
    logic   = check_data_logic()
    model   = check_model_quality()
    score   = compute_health_score(schema, logic, model)

    status = "GREEN" if score >= 85 else ("YELLOW" if score >= 60 else "RED")

    result = {
        "generated_at": NOW_UTC,
        "health_score": score,
        "status": status,
        "schema_check": schema,
        "data_logic_check": logic,
        "model_quality_check": model,
        "summary": {
            "files_validated": schema["files_ok"],
            "schema_errors": len(schema["errors"]),
            "data_issues": logic["issue_count"],
            "model_alerts": len(model["alerts"]),
            "clv_reliable_n": model["clv_reliable_n"],
        },
    }

    _save("platform_monitor.json", result)
    (DEBUG / "platform_monitor_debug.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lvl = logging.INFO if status != "RED" else logging.WARNING
    log.log(lvl, "Scor sănătate: %d/100 [%s]", score, status)
    log.info("Erori schemă: %d, Probleme date: %d, Alerte model: %d",
             len(schema["errors"]), logic["issue_count"], len(model["alerts"]))
    for e in schema["errors"]:
        log.error("[SCHEMĂ] %s", e)
    for i in logic["issues"]:
        log.warning("[DATE] %s", i)
    for a in model["alerts"]:
        log.warning("[MODEL] %s", a)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
