#!/usr/bin/env python3
"""Apply BetPredict Context Engine after daily pipeline data exists.

This runner keeps fetch_daily.py safe: it enriches data/predictions.json atomically and
then regenerates dependent local files that use smartbet_score.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DEBUG_DIR = DATA_DIR / "debug"
for p in (ROOT, ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from context_engine import enrich_with_context, reset_engine  # noqa: E402


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


def summarize(preds: List[Dict[str, Any]]) -> Dict[str, Any]:
    processed = [p for p in preds if isinstance(p, dict) and p.get("_context_engine")]
    confs = [float(p.get("context_confidence") or 0) for p in processed]
    boosts = [float(p.get("smartbet_context_boost") or 0) for p in processed]
    verdicts: Dict[str, int] = {}
    for p in processed:
        best = p.get("ctx_best_verdict") or "none"
        verdicts[str(best)] = verdicts.get(str(best), 0) + 1
    sample = []
    for p in processed[:20]:
        ev = p.get("event") if isinstance(p.get("event"), dict) else {}
        sample.append({
            "event_id": ev.get("id"),
            "match": f"{ev.get('home_team', '—')} vs {ev.get('away_team', '—')}",
            "context_confidence": p.get("context_confidence"),
            "smartbet_score_base": p.get("smartbet_score_base"),
            "smartbet_score": p.get("smartbet_score"),
            "smartbet_context_boost": p.get("smartbet_context_boost"),
            "ctx_best_verdict": p.get("ctx_best_verdict"),
            "ctx_verdicts": p.get("ctx_verdicts"),
        })
    return {
        "updated_at": now_iso(),
        "source": "context_engine_runner_v1",
        "total_predictions": len(preds),
        "processed_predictions": len(processed),
        "with_context_confidence": sum(1 for x in confs if x > 0),
        "avg_context_confidence": round(sum(confs) / len(confs), 4) if confs else 0.0,
        "max_context_confidence": round(max(confs), 4) if confs else 0.0,
        "avg_context_boost": round(sum(boosts) / len(boosts), 4) if boosts else 0.0,
        "max_context_boost": round(max(boosts), 4) if boosts else 0.0,
        "best_verdict_counts": verdicts,
        "sample": sample,
    }


def regenerate_dependents() -> Dict[str, Any]:
    report = {
        "signals": False,
        "value_bets": False,
        "selection_journal": False,
        "performance_summary": False,
        "qa_report": False,
        "errors": [],
    }
    try:
        import fetch_daily as fd  # noqa: WPS433
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
            print(f"  ⚠ context_engine regenerate {name} failed: {exc}")
    return report


def main() -> int:
    pred_path = DATA_DIR / "predictions.json"
    payload = read_json(pred_path, {})
    preds = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(preds, list):
        write_json(DEBUG_DIR / "context_engine_debug.json", {
            "updated_at": now_iso(),
            "error": "missing_or_invalid_predictions_json",
            "total_predictions": 0,
        })
        print("Context Engine: predictions.json invalid or missing")
        return 1

    reset_engine()
    enriched: List[Dict[str, Any]] = []
    errors: List[str] = []
    for idx, pred in enumerate(preds):
        if not isinstance(pred, dict):
            enriched.append(pred)
            continue
        try:
            enriched.append(enrich_with_context(pred, DATA_DIR))
        except Exception as exc:
            errors.append(f"prediction[{idx}]: {exc}")
            enriched.append(pred)

    payload["results"] = enriched
    payload["count"] = len(enriched)
    payload["updated_at"] = now_iso()
    payload["_context_engine"] = "v1.0"
    write_json(pred_path, payload)

    debug = summarize(enriched)
    debug["errors"] = errors[:100]
    debug["error_count"] = len(errors)
    write_json(DEBUG_DIR / "context_engine_debug.json", debug)

    regen = regenerate_dependents()
    debug["regenerated"] = regen
    write_json(DEBUG_DIR / "context_engine_debug.json", debug)

    print(
        "Context Engine: "
        f"processed={debug['processed_predictions']}/{debug['total_predictions']} "
        f"with_ctx={debug['with_context_confidence']} "
        f"avg_conf={debug['avg_context_confidence']} "
        f"max_boost={debug['max_context_boost']}"
    )
    return 2 if errors or regen.get("errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
