#!/usr/bin/env python3
"""
pyramid_staking.py — Staircase / Pyramid stake plan (2 → 5 → 10)
===============================================================
Complement to pyramid_assistant.py (which selects high-prob odds-per-step picks).

This module builds a STAKE REINVESTMENT staircase:
  Step 1: stake `units[0]` (default 2) on a green high-confidence pick
  Win  → reinvest into Step 2 stake `units[1]` (default 5)
  Win  → reinvest into Step 3 stake `units[2]` (default 10)
  Loss → stop-loss: reset to step 1 (or abort series if bankroll_cap hit)

Honest math:
  - Combined survival P(n) ≈ product of calibrated probs (independence assumption —
    real correlation makes it worse).
  - Expected value of the series is often NEGATIVE even with good singles;
    staircase amplifies variance, not edge.
  - Default status is PAPER_ONLY until pyramid tracker shows positive flat ROI.

Outputs: data/pyramid_plans.json
Standalone: python3 src/pyramid_staking.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

try:
    from analytics_core import safe_float
except Exception:
    def safe_float(v, d=0.0):
        try:
            x = float(v)
            return d if x != x else x
        except Exception:
            return d

DEFAULT_UNITS = (2.0, 5.0, 10.0)
DEFAULT_BANKROLL_UNITS = 100.0
MAX_STAKE_PCT_BANKROLL = 0.12  # never stake >12% bankroll on one step
STOP_LOSS_UNITS = 10.0         # abort series after cumulative loss ≥ this


def _load(name: str, default: Any = None) -> Any:
    try:
        with open(os.path.join(DATA, name), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _atomic_write(name: str, obj: Any) -> None:
    os.makedirs(DATA, exist_ok=True)
    path = os.path.join(DATA, name)
    fd, tmp = tempfile.mkstemp(dir=DATA, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2, default=str)
            f.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _cal_prob(sig: Dict[str, Any]) -> float:
    for k in ("calibrated_prob", "blend_prob"):
        v = safe_float(sig.get(k), -1.0)
        if 0 < v <= 1:
            return v
    adj = safe_float(sig.get("adj_prob"), -1.0)
    if adj > 1:
        return min(0.99, adj / 100.0)
    if 0 < adj <= 1:
        return adj
    return 0.0


GRADE_RANK = {"A+": 3, "A": 2, "B": 1, "C": 0}


def select_step_candidates(
    signals: List[Dict[str, Any]],
    n: int = 8,
    min_grade: str = "A",
    min_cal: float = 0.62,
    min_consensus: float = 0.75,
) -> List[Dict[str, Any]]:
    """Strict picks for staircase legs — prefer green A+/A TOTAL consensus."""
    min_rank = GRADE_RANK.get(min_grade, 2)
    rows: List[Dict[str, Any]] = []
    for s in signals:
        if not isinstance(s, dict):
            continue
        if s.get("publication_eligible") is False:
            continue
        if str(s.get("adaptive_verdict") or "").upper() in ("AVOID", "BLACKLIST"):
            continue
        grade = s.get("quality_grade_v6") or s.get("quality_grade") or "C"
        if GRADE_RANK.get(grade, 0) < min_rank:
            continue
        cal = _cal_prob(s)
        if cal < min_cal:
            continue
        tier = str(s.get("consensus_tier") or "").upper()
        cscore = safe_float(s.get("consensus_score"), 0.0)
        if tier not in ("TOTAL", "PARTIAL") or (tier == "PARTIAL" and cscore < min_consensus):
            if grade != "A+" or cal < 0.70:
                continue
        odds = safe_float(s.get("odds"), 0.0)
        if odds < 1.20 or odds > 2.10:
            continue  # staircase wants controlled odds so bankroll path is predictable
        ev = safe_float(s.get("ev_calibrated"), 0.0)
        if ev < -0.01:
            continue
        score = (
            GRADE_RANK.get(grade, 0) * 25
            + cal * 100 * 0.4
            + (12 if tier == "TOTAL" else 4)
            + max(0.0, ev) * 80
            - abs(odds - 1.40) * 8
        )
        rows.append({
            "event_id": s.get("event_id"),
            "home_team": s.get("home_team"),
            "away_team": s.get("away_team"),
            "league": s.get("league"),
            "event_date": s.get("event_date"),
            "market": s.get("market"),
            "market_label": s.get("market_label") or s.get("market"),
            "odds": round(odds, 2),
            "calibrated_prob": round(cal, 4),
            "ev_calibrated": round(ev, 4),
            "quality_grade_v6": grade,
            "consensus_tier": tier,
            "consensus_score": s.get("consensus_score"),
            "green_badge": grade in ("A+", "A") and tier in ("TOTAL", "PARTIAL"),
            "pyramid_ready_score": round(score, 1),
            "bookmaker": s.get("bookmaker") or "best_odds",
        })
    rows.sort(key=lambda r: r["pyramid_ready_score"], reverse=True)
    # unique events
    seen = set()
    out = []
    for r in rows:
        eid = r.get("event_id")
        if eid in seen:
            continue
        seen.add(eid)
        out.append(r)
        if len(out) >= n:
            break
    return out


def build_staircase_plan(
    candidates: List[Dict[str, Any]],
    units: tuple = DEFAULT_UNITS,
    bankroll_units: float = DEFAULT_BANKROLL_UNITS,
    unit_value_lei: float = 10.0,
) -> Dict[str, Any]:
    """Build 2→5→10 style plan with reinvestment projection."""
    steps: List[Dict[str, Any]] = []
    survival = 1.0
    bankroll = float(bankroll_units)
    cumulative_risk = 0.0

    for i, stake_u in enumerate(units):
        step_no = i + 1
        # Cap stake vs bankroll
        max_u = bankroll * MAX_STAKE_PCT_BANKROLL
        stake = min(float(stake_u), max_u) if max_u > 0 else float(stake_u)
        if stake < 0.5:
            stake = float(stake_u)  # still show intended stake even if bankroll thin

        pick = candidates[i] if i < len(candidates) else (candidates[0] if candidates else None)
        if pick is None:
            steps.append({
                "step": step_no,
                "stake_units": stake_u,
                "stake_lei": round(stake_u * unit_value_lei, 2),
                "status": "NO_CANDIDATE",
                "note": "Nu există pick verde suficient de strict pentru acest pas.",
            })
            continue

        odds = safe_float(pick.get("odds"), 1.3)
        cal = safe_float(pick.get("calibrated_prob"), 0.6)
        survival *= cal
        win_bankroll = bankroll - stake + stake * odds
        # Reinvestment: next stake comes from winnings path
        projected_profit_units = stake * (odds - 1.0)
        cumulative_risk += stake

        steps.append({
            "step": step_no,
            "stake_units": round(stake, 2),
            "stake_intended_units": stake_u,
            "stake_lei": round(stake * unit_value_lei, 2),
            "stake_pct_bankroll": round((stake / bankroll_units) * 100, 2) if bankroll_units else None,
            "candidate": pick,
            "if_win_bankroll_units": round(win_bankroll, 2),
            "if_win_profit_units": round(projected_profit_units, 2),
            "if_loss_action": "RESET_TO_STEP_1" if step_no == 1 else "ABORT_SERIES",
            "survival_probability_to_here": round(survival, 6),
            "one_in": round(1 / survival) if survival > 0 else None,
            "green_badge": bool(pick.get("green_badge")),
        })
        # Assume win for projection of next bankroll (planning path only)
        bankroll = win_bankroll

    final_survival = steps[-1]["survival_probability_to_here"] if steps and "survival_probability_to_here" in steps[-1] else None
    return {
        "name": f"Staircase {' → '.join(str(int(u)) if u == int(u) else str(u) for u in units)}",
        "units": list(units),
        "unit_value_lei": unit_value_lei,
        "bankroll_units_start": bankroll_units,
        "bankroll_lei_start": round(bankroll_units * unit_value_lei, 2),
        "max_stake_pct_bankroll": MAX_STAKE_PCT_BANKROLL,
        "stop_loss_units": STOP_LOSS_UNITS,
        "steps": steps,
        "series_survival_probability": final_survival,
        "series_one_in": round(1 / final_survival) if final_survival else None,
        "projected_bankroll_if_all_win_units": round(bankroll, 2) if candidates else None,
        "cumulative_stake_at_risk_units": round(min(STOP_LOSS_UNITS, sum(u for u in units)), 2),
        "execution_status": "PAPER_ONLY",
        "disclaimer": (
            "Scara 2→5→10 REINVESTEȘTE câștigurile — amplifică variance-ul, nu edge-ul. "
            "O singură pierdere pe treaptă resetează seria. Nu există profit garantat. "
            "Folosește doar pe pick-uri verzi (A+/A + consens) și mize în unități, nu 'all-in'."
        ),
    }


def load_signals() -> List[Dict[str, Any]]:
    sv6 = _load("signals_v6.json", {}) or {}
    rows = sv6.get("signals") or []
    if rows:
        return rows
    sigs = _load("signals.json", {}) or {}
    return sigs.get("signals") or []


def build_plans(
    units: tuple = DEFAULT_UNITS,
    bankroll_units: float = DEFAULT_BANKROLL_UNITS,
    unit_value_lei: float = 10.0,
) -> Dict[str, Any]:
    signals = load_signals()
    candidates = select_step_candidates(signals)
    # Also pull pyramid_assistant top picks if available (already Superbet-matched)
    pa = _load("pyramid_assistant.json", {}) or {}
    pa_pool = (pa.get("current_step_pool") or {}).get("1") or []
    merged = list(candidates)
    seen = {(c.get("event_id"), c.get("market")) for c in merged}
    for r in pa_pool:
        k = (r.get("event_id"), r.get("market"))
        if k in seen:
            continue
        cal = _cal_prob(r)
        if cal < 0.60:
            continue
        merged.append({
            "event_id": r.get("event_id"),
            "home_team": r.get("home_team"),
            "away_team": r.get("away_team"),
            "league": r.get("league"),
            "event_date": r.get("event_date"),
            "market": r.get("market"),
            "market_label": r.get("market_label") or r.get("market"),
            "odds": round(safe_float(r.get("odds"), 0), 2),
            "calibrated_prob": round(cal, 4),
            "ev_calibrated": round(safe_float(r.get("ev_calibrated"), 0), 4),
            "quality_grade_v6": r.get("quality_grade_v6") or r.get("quality_grade") or "A",
            "consensus_tier": r.get("consensus_tier") or "PARTIAL",
            "green_badge": True,
            "pyramid_ready_score": safe_float(r.get("pyramid_ready_score"), 70),
            "bookmaker": r.get("bookmaker") or "Superbet",
            "source": "pyramid_assistant",
        })
        seen.add(k)
    merged.sort(key=lambda r: safe_float(r.get("pyramid_ready_score"), 0), reverse=True)

    plan_2510 = build_staircase_plan(merged, units=units, bankroll_units=bankroll_units,
                                     unit_value_lei=unit_value_lei)
    # Alternate shorter staircase 1→2→4 (half risk)
    plan_half = build_staircase_plan(
        merged, units=(1.0, 2.0, 4.0), bankroll_units=bankroll_units, unit_value_lei=unit_value_lei
    )
    plan_half["name"] = "Staircase conservatoare 1 → 2 → 4"

    track = ((_load("pyramid_state.json", {}) or {}).get("tracks") or {}).get("safe") or {}
    hist = (_load("pyramid_assistant.json", {}) or {}).get("historical_track_record") or {}

    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "pyramid_staking_v8",
        "objective": "Plan de mize tip scară (reinvestment) pe pick-uri v6 verzi — nu creștere magică a edge-ului.",
        "how_to_use": [
            "1. Pornește cu unitatea 2 pe pick-ul pasului 1 (badge verde).",
            "2. Doar dacă câștigi, urcă la unitatea 5 pe un alt meci/zi (nu același event).",
            "3. Doar dacă câștigi din nou, urcă la unitatea 10.",
            "4. La orice pierdere: STOP seria → revii la pasul 1; nu 'recupera' cu miză mai mare.",
            "5. Plafon: max 12% din bancă pe un pas; stop-loss serie = 10 unități.",
        ],
        "risk_warning": (
            "Pariurile sportive implică risc de pierdere a întregii mize. "
            "Scara crește variance-ul. Nu există strategie cu profit garantat."
        ),
        "historical_leg_win_rate_pct": hist.get("leg_win_rate_pct"),
        "paper_tracker_step": track.get("step"),
        "candidates_available": len(merged),
        "plans": [plan_2510, plan_half],
        "top_green_candidates": merged[:10],
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Pyramid staircase staking 2-5-10")
    parser.add_argument("--units", default="2,5,10", help="Comma-separated stake units")
    parser.add_argument("--bankroll-units", type=float, default=DEFAULT_BANKROLL_UNITS)
    parser.add_argument("--unit-lei", type=float, default=10.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        units = tuple(float(x.strip()) for x in args.units.split(",") if x.strip())
        if len(units) < 2:
            units = DEFAULT_UNITS
        out = build_plans(units=units, bankroll_units=args.bankroll_units,
                          unit_value_lei=args.unit_lei)
    except Exception as exc:
        print(f"[pyramid_staking] WARN: {exc}")
        out = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "source": "pyramid_staking_v8",
            "error": str(exc),
            "plans": [],
            "top_green_candidates": [],
        }

    _atomic_write("pyramid_plans.json", out)
    print(f"[pyramid_staking] candidates={out.get('candidates_available')} "
          f"plans={len(out.get('plans') or [])}")
    for p in out.get("plans") or []:
        surv = p.get("series_survival_probability")
        print(f"  • {p.get('name')}: steps={len(p.get('steps') or [])} "
              f"survival={surv} one_in={p.get('series_one_in')}")
    if args.dry_run:
        print("[pyramid_staking] dry-run complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
