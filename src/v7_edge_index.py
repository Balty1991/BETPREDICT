#!/usr/bin/env python3
"""
v7_edge_index.py — index compact de edge per-eveniment pentru UI
================================================================

Produce `data/v7_edge_index.json` cu un verdict de VALOARE per meci, pe care
frontend-ul il afiseaza direct pe:
  - cardurile meciurilor (EventListCard)
  - predictiile oferite (PredictionsPage)
  - analiza evenimentelor (detaliu meci)

Pentru fiecare eveniment alege CEL MAI BUN semnal (grad + edge) din signals_v6
si il combina cu confirmarea Sharp (value vs Pinnacle). Probabilitatea afisata
e ANCORATA PE PIATA (nu pe modelul umflat) — la fel ca smart_accumulator.

Output schema:
{
  "by_event": { "<event_id>": {
     "pick", "market", "market_label", "grade", "honest_prob_pct",
     "edge_pp", "ev_pct", "odds", "sharp_confirmed", "consensus_tier",
     "clv_state", "is_value", "verdict"
  }},
  "summary": {...}
}
Ruleaza:  python3 src/v7_edge_index.py
"""
from __future__ import annotations
import json, os, sys, tempfile
from datetime import datetime, timezone
from typing import Any, Dict, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, ROOT)

try:
    from analytics_core import safe_float
except Exception:
    def safe_float(v, d=0.0):
        try:
            x = float(v); return d if x != x else x
        except Exception:
            return d

GRADE_RANK = {"A+": 3, "A": 2, "B": 1, "C": 0, "D": -1, "E": -2}
_V6_TO_SHARP = {
    "homeWin": ("1x2", "HOME"), "draw": ("1x2", "DRAW"), "awayWin": ("1x2", "AWAY"),
    "btts": ("btts", "YES"), "no_btts": ("btts", "NO"),
    "over15": ("over_under_15", "OVER"), "under15": ("over_under_15", "UNDER"),
    "over25": ("over_under_25", "OVER"), "under25": ("over_under_25", "UNDER"),
    "over35": ("over_under_35", "OVER"), "under35": ("over_under_35", "UNDER"),
}


def _load(name: str, default: Any = None) -> Any:
    try:
        with open(os.path.join(DATA, name), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _atomic_write(name: str, obj: Any) -> None:
    p = os.path.join(DATA, name)
    fd, tmp = tempfile.mkstemp(dir=DATA, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _sharp_set() -> set:
    sv = _load("sharp_value_signals.json", {}) or {}
    out = set()
    for s in sv.get("value_signals", []):
        out.add((s.get("event_id"), s.get("market"), s.get("outcome")))
    for s in sv.get("steam_signals", []):
        out.add((s.get("event_id"), s.get("market"), s.get("outcome")))
    return out


def _honest_prob(model_prob: Optional[float], odds: float) -> float:
    """70% ancora de piata (de-vig) + 30% model."""
    implied = 1.0 / odds if odds > 1.01 else 0.5
    market_anchor = min(0.985, implied * 0.96)
    mp = model_prob if (model_prob and 0 < model_prob <= 1) else market_anchor
    return max(0.01, min(0.99, 0.70 * market_anchor + 0.30 * mp))


def main() -> int:
    sigs = _load("signals_v6.json", {}) or {}
    rows = sigs.get("signals") or (sigs if isinstance(sigs, list) else [])
    sharp = _sharp_set()

    best_by_event: Dict[Any, Dict[str, Any]] = {}
    for s in rows:
        eid = s.get("event_id")
        odds = safe_float(s.get("odds"), 0.0)
        if eid is None or odds <= 1.01:
            continue
        grade = s.get("quality_grade_v6") or s.get("quality_grade") or "C"
        grade_rank = GRADE_RANK.get(grade, 0)

        model_prob = None
        for k in ("calibrated_prob", "blend_prob", "adj_prob"):
            v = s.get(k)
            if v is not None and 0 < safe_float(v) <= 1:
                model_prob = safe_float(v); break
        prob = _honest_prob(model_prob, odds)
        implied = 1.0 / odds
        edge_pp = round((prob - implied) * 100, 1)
        ev_pct = round((prob * odds - 1.0) * 100, 1)

        market = s.get("market")
        sm, so = _V6_TO_SHARP.get(market, (None, None))
        sharp_confirmed = (eid, sm, so) in sharp if sm else False

        is_value = ev_pct >= 1.0 and grade_rank >= 1  # EV>=1% si grad >=B
        # scor pentru a alege cel mai bun semnal pe meci
        rank_score = grade_rank * 20 + prob * 40 + max(0.0, edge_pp) * 1.5 + (15 if sharp_confirmed else 0)

        entry = {
            "pick": s.get("market_label") or market,
            "market": market, "market_label": s.get("market_label") or market,
            "grade": grade, "honest_prob_pct": round(prob * 100, 1),
            "edge_pp": edge_pp, "ev_pct": ev_pct, "odds": round(odds, 2),
            "sharp_confirmed": sharp_confirmed,
            "consensus_tier": s.get("consensus_tier"),
            "clv_state": s.get("clv_state"),
            "is_value": is_value,
            "verdict": ("VALUE" if is_value else "NEUTRU"),
            "_rank": rank_score,
        }
        prev = best_by_event.get(eid)
        if prev is None or rank_score > prev["_rank"]:
            best_by_event[eid] = entry

    by_event = {}
    for eid, e in best_by_event.items():
        e.pop("_rank", None)
        by_event[str(eid)] = e

    n_value = sum(1 for e in by_event.values() if e["is_value"])
    n_sharp = sum(1 for e in by_event.values() if e["sharp_confirmed"])
    n_aplus = sum(1 for e in by_event.values() if e["grade"] == "A+")

    out = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "v7_edge_index",
        "note": "Verdict de valoare per meci: probabilitate ancorata pe piata, edge onest, "
                "confirmare sharp. Alimenteaza cardurile, predictiile si analiza din UI.",
        "summary": {"n_events": len(by_event), "n_value": n_value,
                    "n_sharp_confirmed": n_sharp, "n_aplus": n_aplus},
        "by_event": by_event,
    }
    _atomic_write("v7_edge_index.json", out)
    print(f"[v7_edge_index] {len(by_event)} meciuri | {n_value} value | "
          f"{n_sharp} sharp-confirmate | {n_aplus} A+")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
