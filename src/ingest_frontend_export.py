#!/usr/bin/env python3
"""
Ingest export din Statistics (frontend, localStorage) in data/selection_journal.json.

Motivatie: selection_journal.json e populat doar de urmarirea server-side
(fetch_daily.py), care are un esantion mic (n~60). Frontend-ul salveaza
automat TOATE predictiile afisate cu cota valida (useSavedPredictions.ts),
deci acumuleaza un esantion mult mai mare din acelasi model (verdictsByEvent,
nu fallback-ul local fara AI din localAnalysis.ts). Scriptul asta ii da
calibration_engine.py mai multe date, fara sa dubleze meciuri deja urmarite.

Utilizare:
    python3 src/ingest_frontend_export.py <cale_export.json>
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
JOURNAL_PATH = DATA_DIR / "selection_journal.json"

CANONICAL_MARKETS = {
    "homeWin", "draw", "awayWin",
    "btts", "no_btts",
    "over15", "under15",
    "over25", "under25",
    "over35", "under35",
}

MARKET_ALIASES = {
    "1": "homeWin", "homeWin": "homeWin", "home_win": "homeWin", "1x2_home": "homeWin",
    "X": "draw", "draw": "draw", "1x2_draw": "draw",
    "2": "awayWin", "awayWin": "awayWin", "away_win": "awayWin", "1x2_away": "awayWin",
    "btts": "btts", "btts_yes": "btts", "BTTS": "btts",
    "no_btts": "no_btts", "btts_no": "no_btts",
    "over15": "over15", "over_15": "over15", "over_1.5": "over15",
    "under15": "under15", "under_15": "under15",
    "over25": "over25", "over_25": "over25", "over_2.5": "over25",
    "under25": "under25", "under_25": "under25",
    "over35": "over35", "over_35": "over35", "over_3.5": "over35",
    "under35": "under35", "under_35": "under35",
}


def normalize_market(name: Any) -> Optional[str]:
    if not name:
        return None
    raw = str(name).strip()
    canonical = MARKET_ALIASES.get(raw)
    if canonical:
        return canonical
    return None


def _parse_score(final_score: Optional[str]) -> Tuple[Optional[int], Optional[int]]:
    if not final_score or "-" not in final_score:
        return None, None
    try:
        home, away = final_score.split("-", 1)
        return int(home.strip()), int(away.strip())
    except Exception:
        return None, None


def _load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_json_atomic(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    tmp.replace(path)


def build_entry(pred: Dict, market_canonical: str) -> Dict:
    prob = float(pred.get("probability", 0)) / 100.0
    prob = max(0.01, min(0.99, prob))
    odds = float(pred.get("odds") or 0)
    result = "WIN" if pred.get("status") == "won" else "LOSS"
    profit_units = round(odds - 1.0, 4) if result == "WIN" else -1.0
    home_score, away_score = _parse_score(pred.get("final_score"))

    entry = {
        "event_id": pred.get("event_id"),
        "home_team": pred.get("home_team"),
        "away_team": pred.get("away_team"),
        "league": pred.get("league"),
        "event_date": pred.get("event_date"),
        "key": f"export|{pred.get('event_id')}|frontend|{market_canonical}",
        "source": "frontend_export",
        "strategy": "frontend_export",
        "strategy_label": "Export Statistici (frontend)",
        "market": market_canonical,
        "market_label": pred.get("market_label", market_canonical),
        "odds": odds,
        "model_probability": prob,
        "first_seen_at": pred.get("saved_at"),
        "last_seen_at": pred.get("saved_at"),
        "status": "settled",
        "result": result,
        "profit_units": profit_units,
        "market_canonical": market_canonical,
        "actual_score": pred.get("final_score"),
        "settled_at": pred.get("settled_at"),
        "home_score": home_score,
        "away_score": away_score,
        "score_ft": pred.get("final_score"),
    }
    return entry


def main() -> int:
    if len(sys.argv) < 2:
        print("Utilizare: python3 src/ingest_frontend_export.py <cale_export.json>")
        return 1

    export_path = Path(sys.argv[1])
    export = _load_json(export_path)
    if not export or "predictions" not in export:
        print(f"[ingest] {export_path} lipseste sau nu are 'predictions'")
        return 1

    journal = _load_json(JOURNAL_PATH, {"results": []})
    results: List[Dict] = journal.get("results", [])
    existing_keys = {
        (str(r.get("event_id")), r.get("market_canonical") or r.get("market"))
        for r in results
    }

    stats = {"added": 0, "duplicate": 0, "pending_skipped": 0, "unknown_market": 0}
    for pred in export["predictions"]:
        if pred.get("status") not in ("won", "lost"):
            stats["pending_skipped"] += 1
            continue

        market_canonical = normalize_market(pred.get("market"))
        if not market_canonical or market_canonical not in CANONICAL_MARKETS:
            stats["unknown_market"] += 1
            continue

        dedup_key = (str(pred.get("event_id")), market_canonical)
        if dedup_key in existing_keys:
            stats["duplicate"] += 1
            continue

        results.append(build_entry(pred, market_canonical))
        existing_keys.add(dedup_key)
        stats["added"] += 1

    print(f"[ingest] {stats}")

    settled = sum(1 for r in results if r.get("status") == "settled")
    pending = sum(1 for r in results if r.get("status") != "settled")
    journal["results"] = results
    journal["count"] = len(results)
    journal["settled"] = settled
    journal["pending"] = pending
    journal["voided"] = journal.get("voided", 0)
    journal["updated_at"] = datetime.now(timezone.utc).isoformat()
    journal["source"] = "selection_journal_v2_settlement+frontend_export"

    _save_json_atomic(JOURNAL_PATH, journal)
    print(f"[ingest] scris {JOURNAL_PATH} — total={len(results)} settled={settled}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
