#!/usr/bin/env python3
"""BetPredict Market / Odds Intelligence Audit v1.

Audit-only, fără API calls și fără modificare de scoruri:
- verifică value_bets.json, odds/best odds dacă există, market_intelligence.json;
- detectează duplicate, edge-uri suspecte, odds lipsă, sursă locală vs oficială;
- scrie rapoarte compacte pentru debug și QA.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DEBUG_DIR = DATA_DIR / "debug"
SOURCE = "market_odds_audit_v1"


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


def num(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except Exception:
        return default


def rows(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("results", "signals", "events", "items", "data", "value_bets"):
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []


def event_id(row: Dict[str, Any]) -> str:
    ev = row.get("event") if isinstance(row.get("event"), dict) else {}
    return str(row.get("event_id") or row.get("id") or ev.get("id") or "")


def team_label(row: Dict[str, Any]) -> str:
    ev = row.get("event") if isinstance(row.get("event"), dict) else {}
    home = row.get("home_team") or ev.get("home_team") or "—"
    away = row.get("away_team") or ev.get("away_team") or "—"
    return f"{home} vs {away}"


def market_key(row: Dict[str, Any]) -> str:
    return str(row.get("market") or row.get("market_label") or row.get("selection") or row.get("pick") or "unknown")


def probability_pct(row: Dict[str, Any]) -> float:
    p = row.get("model_probability")
    if p is None:
        p = row.get("probability") or row.get("probability_pct") or row.get("confidence")
    p = num(p, 0.0)
    if 0 < p <= 1:
        p *= 100.0
    return p


def odds_value(row: Dict[str, Any]) -> float:
    return num(row.get("market_odds") or row.get("odds") or row.get("decimal_odds") or row.get("best_odds"), 0.0)


def edge_pct(row: Dict[str, Any]) -> float:
    if row.get("edge_nv_pp") is not None:
        return num(row.get("edge_nv_pp"), 0.0)
    if row.get("edge_pp") is not None:
        return num(row.get("edge_pp"), 0.0)
    if row.get("edge") is not None:
        e = num(row.get("edge"), 0.0)
        return e * 100.0 if abs(e) <= 1 else e
    text = str(row.get("edge_pct") or "").replace("%", "").replace("+", "").strip()
    return num(text, 0.0)


def value_bet_audit(value_rows: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    seen: Dict[str, int] = {}
    warnings: List[Dict[str, Any]] = []
    odds_present = 0
    local_sources = 0
    official_sources = 0
    strong_edges = 0
    suspicious = 0

    for i, row in enumerate(value_rows):
        eid = event_id(row)
        mk = market_key(row)
        key = f"{eid}:{mk}"
        seen[key] = seen.get(key, 0) + 1

        src = str(row.get("source") or row.get("odds_source") or "").lower()
        if "local" in src:
            local_sources += 1
        if "bsd" in src or "official" in src:
            official_sources += 1

        odd = odds_value(row)
        prob = probability_pct(row)
        edge = edge_pct(row)
        if odd > 1.0:
            odds_present += 1
        if edge >= 8.0:
            strong_edges += 1

        warn: List[str] = []
        if odd and odd < 1.01:
            warn.append("invalid_odds")
        if odd and prob:
            fair = 100.0 / max(prob, 1e-9)
            if odd > fair * 1.9 and edge > 30:
                warn.append("edge_too_large_vs_fair_odd")
        if prob > 98 and odd > 1.35:
            warn.append("very_high_probability_with_high_odds")
        if edge > 35:
            warn.append("edge_above_35pp")
        if warn:
            suspicious += 1
            warnings.append({
                "event_id": eid,
                "match": team_label(row),
                "market": mk,
                "odds": odd,
                "model_probability": round(prob, 2),
                "edge_pp": round(edge, 2),
                "warnings": warn,
            })

    duplicates = [{"key": k, "count": c} for k, c in sorted(seen.items()) if c > 1]
    summary = {
        "value_bets_count": len(value_rows),
        "odds_present": odds_present,
        "local_sources": local_sources,
        "official_or_bsd_sources": official_sources,
        "strong_edges_ge_8pp": strong_edges,
        "suspicious_rows": suspicious,
        "duplicate_event_market_rows": len(duplicates),
    }
    if duplicates:
        warnings.append({"type": "duplicates", "sample": duplicates[:20]})
    return summary, warnings[:80]


def market_intel_audit(market_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    movement_counts: Dict[str, int] = {}
    events_with_1x2 = 0
    events_with_ou25 = 0
    events_with_btts = 0
    bookmakers: List[float] = []
    for row in market_rows:
        markets = row.get("markets") if isinstance(row.get("markets"), dict) else {}
        if markets.get("1x2"):
            events_with_1x2 += 1
        if markets.get("over_under_25"):
            events_with_ou25 += 1
        if markets.get("btts"):
            events_with_btts += 1
        bookmakers.append(num(row.get("bookmakers_count"), 0.0))
        for m in markets.values():
            if not isinstance(m, dict):
                continue
            outcomes = m.get("outcomes") if isinstance(m.get("outcomes"), dict) else {}
            for out in outcomes.values():
                if not isinstance(out, dict):
                    continue
                for b in out.get("bookmakers", []) if isinstance(out.get("bookmakers"), list) else []:
                    mv = str(b.get("movement") or "UNKNOWN").upper()
                    movement_counts[mv] = movement_counts.get(mv, 0) + 1
    avg_bookmakers = sum(bookmakers) / len(bookmakers) if bookmakers else 0.0
    return {
        "market_intelligence_events": len(market_rows),
        "events_with_1x2": events_with_1x2,
        "events_with_over_under_25": events_with_ou25,
        "events_with_btts": events_with_btts,
        "avg_bookmakers_count": round(avg_bookmakers, 2),
        "movement_counts": movement_counts,
    }


def file_presence() -> Dict[str, Any]:
    names = [
        "predictions.json", "signals.json", "value_bets.json", "best_odds.json",
        "market_intelligence.json", "odds_comparison.json", "api_coverage_report.json",
    ]
    return {name: (DATA_DIR / name).exists() and (DATA_DIR / name).stat().st_size > 5 for name in names}


def main() -> int:
    predictions = read_json(DATA_DIR / "predictions.json", {"results": []})
    value_payload = read_json(DATA_DIR / "value_bets.json", {"results": []})
    market_payload = read_json(DATA_DIR / "market_intelligence.json", {"results": []})
    signals_payload = read_json(DATA_DIR / "signals.json", {"signals": []})

    value_rows = rows(value_payload)
    market_rows = rows(market_payload)
    pred_rows = rows(predictions)
    sig_rows = rows(signals_payload)

    value_summary, warnings = value_bet_audit(value_rows)
    market_summary = market_intel_audit(market_rows)
    presence = file_presence()

    signal_eids = {event_id(x) for x in sig_rows if event_id(x)}
    value_eids = {event_id(x) for x in value_rows if event_id(x)}
    pred_eids = {event_id(x) for x in pred_rows if event_id(x)}

    summary = {
        "predictions_count": len(pred_rows),
        "signals_count": len(sig_rows),
        "value_bets_count": len(value_rows),
        "unique_prediction_events": len(pred_eids),
        "unique_signal_events": len(signal_eids),
        "unique_value_events": len(value_eids),
        "signals_with_value_bet_overlap": len(signal_eids & value_eids),
        **value_summary,
        **market_summary,
        "file_presence": presence,
        "score_impact": "none_safe_audit_only",
    }

    recommendations: List[str] = []
    if not presence.get("market_intelligence.json"):
        recommendations.append("market_intelligence.json lipsește sau este gol; odds movement nu poate fi auditat complet")
    if value_summary.get("suspicious_rows", 0):
        recommendations.append("verifică value_bets cu edge foarte mare sau probabilitate extremă")
    if value_summary.get("duplicate_event_market_rows", 0):
        recommendations.append("curăță duplicatele event+market din value_bets")
    if not value_rows:
        recommendations.append("value_bets.json nu are rezultate")

    payload = {
        "updated_at": now_iso(),
        "source": SOURCE,
        "summary": summary,
        "warnings": warnings,
        "recommendations": recommendations,
        "sample_value_bets": value_rows[:20],
    }
    write_json(DATA_DIR / "market_odds_audit.json", payload)
    write_json(DEBUG_DIR / "market_odds_audit_debug.json", {
        "updated_at": payload["updated_at"],
        "source": SOURCE,
        "summary": summary,
        "warnings_sample": warnings[:30],
        "recommendations": recommendations,
    })
    print(f"Market/Odds Audit: value={len(value_rows)} signals={len(sig_rows)} suspicious={value_summary.get('suspicious_rows', 0)} market_events={len(market_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
