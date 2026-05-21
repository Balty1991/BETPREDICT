#!/usr/bin/env python3
"""
src/v6_backtest.py
==================
BetPredict Pro v6.0 — Counterfactual Backtest Framework

Ce face:
- Citeste data/selection_journal.json (toate pariurile settle-uite).
- Sorteaza cronologic dupa first_seen_at.
- Aplica un time-based holdout: primele 60% pentru "fit" calibratoare,
  ultimele 40% pentru "test" out-of-sample.
- Pentru fiecare pariu test, calculeaza:
    * EV original (v5 logic): model_prob * odds - 1
    * EV calibrat (v6 logic): calibrated_prob * odds - 1
- Compara:
    * v5 = pariem daca EV > 0 (logica originala)
    * v6 = pariem daca EV calibrat > 0
- Reproduce ROI v5 (REAL, ce s-a intamplat) vs ROI v6 (CONTRAFACTUAL).
- Genereaza si un istoric COMPLET (toate 97 pariuri settle-uite) cu:
    * Predictia originala v5
    * Probabilitatea calibrata v6
    * Rezultatul real (WIN/LOSS)
    * Verdict v6 (KEEP/SKIP/UPGRADE)
    * Profit v5 (real) vs profit v6 (contrafactual)

ATENTIE METODOLOGICA:
- Modul "in_sample": foloseste TOATE pariurile pentru fit calibrator + test.
  ROI optimist (overfit). Util doar pentru "what would v6 say acum".
- Modul "out_of_sample": split time-based 60/40. ROI realist, dar mai putine
  pariuri in test set. Raportat ca metrica principala.

Output:
- data/v6_backtest_report.json
    {
      "out_of_sample": { roi_v5, roi_v6, delta_pp, n_kept_v5, n_kept_v6, ... },
      "in_sample": { same fields },
      "history": [ { full bet record with v5/v6 comparison }, ... ],
      "by_market": { market: { v5_roi, v6_roi, ... } },
      "by_strategy": { strategy: same },
    }
- data/debug/v6_backtest_debug.json
"""

from __future__ import annotations
import json
import pickle
import sys
import warnings
import traceback
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

warnings.filterwarnings("ignore")

try:
    import numpy as np
    from sklearn.isotonic import IsotonicRegression
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

# ============================================================
# CAI
# ============================================================

ROOT_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = ROOT_DIR / "data"
MODELS_DIR = ROOT_DIR / "models"
DEBUG_DIR = DATA_DIR / "debug"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

SELECTION_JOURNAL = DATA_DIR / "selection_journal.json"
CALIBRATORS_PKL = MODELS_DIR / "calibrators_v6.pkl"
OUT_REPORT = DATA_DIR / "v6_backtest_report.json"
OUT_DEBUG = DEBUG_DIR / "v6_backtest_debug.json"

# Split time-based holdout
TRAIN_FRACTION = 0.60   # primele 60% pentru fit calibratoare
MIN_TRAIN_PER_MARKET = 5  # sub asta -> identity in train

MARKET_ALIASES = {
    "1": "homeWin", "homeWin": "homeWin",
    "X": "draw", "draw": "draw",
    "2": "awayWin", "awayWin": "awayWin",
    "btts": "btts",
    "over15": "over15", "over_15": "over15",
    "over25": "over25", "over_25": "over25",
    "over35": "over35",
    "under15": "under15",
    "under25": "under25", "under_25": "under25",
    "under35": "under35", "under_35": "under35",
}

MODEL_VERSION = "v6.0-backtest"


def _log(msg: str) -> None:
    print(f"[backtest] {msg}")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(v: Any, default: float = -1.0) -> float:
    try:
        if v is None or v == "":
            return default
        x = float(v)
        return default if x != x else x
    except Exception:
        return default


def _clip(x: float, lo: float = 0.01, hi: float = 0.99) -> float:
    return max(lo, min(hi, float(x)))


def _load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_atomic(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    tmp.replace(path)


def normalize_market(name: Any) -> Optional[str]:
    if not name:
        return None
    raw = str(name).strip()
    return MARKET_ALIASES.get(raw) or MARKET_ALIASES.get(
        raw.lower().replace(" ", "").replace("-", "").replace(".", "")
    )


# ============================================================
# EXTRACTIE & SORTARE CRONOLOGICA
# ============================================================

def extract_bets(journal: Dict) -> List[Dict]:
    """
    Extrage pariurile settle-uite si le sorteaza cronologic.
    Returneaza lista dict cu campurile necesare pentru backtest.
    """
    bets: List[Dict] = []
    for r in (journal or {}).get("results", []):
        if r.get("status") != "settled":
            continue
        outcome = r.get("result")
        if outcome not in ("WIN", "LOSS"):
            continue

        market = normalize_market(r.get("market"))
        if not market:
            continue

        prob = _safe_float(r.get("model_probability"))
        odds = _safe_float(r.get("odds"))
        profit = _safe_float(r.get("profit_units"), 0.0)

        if prob < 0.01 or prob > 0.99 or odds < 1.01:
            continue

        bets.append({
            "event_id": r.get("event_id"),
            "home_team": r.get("home_team", "?"),
            "away_team": r.get("away_team", "?"),
            "league": r.get("league", "?"),
            "event_date": r.get("event_date"),
            "first_seen_at": r.get("first_seen_at"),
            "settled_at": r.get("settled_at"),
            "market": market,
            "market_label": r.get("market_label", market),
            "strategy": r.get("strategy", "unknown"),
            "strategy_label": r.get("strategy_label"),
            "odds": odds,
            "prob_v5": prob,
            "ev_v5": prob * odds - 1.0,
            "result": outcome,
            "win": 1 if outcome == "WIN" else 0,
            "profit_v5": profit,
            "actual_score": r.get("actual_score"),
        })

    # Sortare cronologica (first_seen_at, fallback settled_at)
    def _sort_key(b):
        return b.get("first_seen_at") or b.get("settled_at") or ""

    bets.sort(key=_sort_key)
    return bets


# ============================================================
# CALIBRATOR (in-script, time-aware)
# ============================================================

def fit_calibrator_per_market(train_bets: List[Dict]) -> Dict[str, Any]:
    """
    Fit-eaza un calibrator per market doar pe train_bets.
    Returneaza dict: market -> state (pickle-safe).
    """
    by_market: Dict[str, List[Tuple[float, int]]] = {}
    for b in train_bets:
        by_market.setdefault(b["market"], []).append((b["prob_v5"], b["win"]))

    calibrators: Dict[str, Any] = {}
    for market, samples in by_market.items():
        n = len(samples)
        if n < MIN_TRAIN_PER_MARKET:
            calibrators[market] = {"type": "identity", "n_train": n}
            continue

        probs = np.array([p for p, _ in samples])
        outcomes = np.array([y for _, y in samples])
        avg_pred = float(probs.mean())
        avg_actual = float(outcomes.mean())

        if n >= 10:
            try:
                iso = IsotonicRegression(out_of_bounds="clip", y_min=0.01, y_max=0.99)
                iso.fit(probs, outcomes)
                calibrators[market] = {
                    "type": "isotonic",
                    "iso": iso,
                    "n_train": n,
                    "avg_pred": avg_pred,
                    "avg_actual": avg_actual,
                }
                continue
            except Exception:
                pass

        # Shift fallback
        shift = avg_actual - avg_pred
        calibrators[market] = {
            "type": "shift",
            "shift": shift,
            "n_train": n,
            "avg_pred": avg_pred,
            "avg_actual": avg_actual,
        }

    return calibrators


def apply_cal(state: Optional[Dict], prob: float) -> float:
    if not state:
        return _clip(prob)
    t = state.get("type", "identity")
    if t == "identity":
        return _clip(prob)
    if t == "shift":
        return _clip(prob + float(state.get("shift", 0.0)))
    if t == "isotonic":
        iso = state.get("iso")
        if iso is None:
            return _clip(prob)
        try:
            return _clip(float(iso.predict([prob])[0]))
        except Exception:
            return _clip(prob)
    return _clip(prob)


# ============================================================
# COUNTERFACTUAL — V5 vs V6
# ============================================================

def evaluate_bet(bet: Dict, calibrators: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compara v5 vs v6 pe un pariu settled.
    Returneaza augmentat cu prob_v6, ev_v6, verdict_v6, profit_v6.
    """
    cal_state = calibrators.get(bet["market"])
    prob_v6 = apply_cal(cal_state, bet["prob_v5"])
    ev_v6 = prob_v6 * bet["odds"] - 1.0

    # Decizii
    v5_keeps = bet["ev_v5"] > 0  # toate pariurile din journal erau cu EV>0 (filtrate)
    v6_keeps = ev_v6 > 0

    # Profit contrafactual
    # Daca v6 paste pariul -> profit_v6 = profit_v5 (acelasi outcome)
    # Daca v6 omite pariul -> profit_v6 = 0 (nu paria => 0 castig/pierdere)
    profit_v6 = bet["profit_v5"] if v6_keeps else 0.0

    # Verdict
    if v5_keeps and v6_keeps:
        verdict = "KEPT" if ev_v6 >= bet["ev_v5"] - 0.02 else "KEPT_LOWER_EV"
    elif v5_keeps and not v6_keeps:
        verdict = "SKIPPED_BY_V6"  # asta-i unde v6 salveaza/pierde
    elif not v5_keeps and v6_keeps:
        verdict = "ADDED_BY_V6"  # daca exista pariuri "marginale"
    else:
        verdict = "BOTH_SKIP"

    return {
        **bet,
        "prob_v6": round(prob_v6, 4),
        "ev_v6": round(ev_v6, 4),
        "v5_keeps": v5_keeps,
        "v6_keeps": v6_keeps,
        "verdict_v6": verdict,
        "profit_v6": round(profit_v6, 2),
        "calibrator_type": (cal_state or {}).get("type", "missing"),
    }


def compute_aggregate_stats(evaluated: List[Dict], suffix: str = "") -> Dict:
    """Statistici v5 vs v6 pe o lista evaluata."""
    n_total = len(evaluated)
    if n_total == 0:
        return {"n_total": 0}

    # V5: toti aveau v5_keeps=True (era filtrat din start)
    v5_kept = [b for b in evaluated if b["v5_keeps"]]
    v6_kept = [b for b in evaluated if b["v6_keeps"]]
    skipped = [b for b in evaluated if b["verdict_v6"] == "SKIPPED_BY_V6"]

    v5_profit = sum(b["profit_v5"] for b in v5_kept)
    v6_profit = sum(b["profit_v6"] for b in v6_kept)

    v5_wins = sum(b["win"] for b in v5_kept)
    v6_wins = sum(b["win"] for b in v6_kept)

    v5_roi = (v5_profit / len(v5_kept) * 100) if v5_kept else 0.0
    v6_roi = (v6_profit / len(v6_kept) * 100) if v6_kept else 0.0

    # Cati din SKIPPED erau LOSS-uri? = pariuri salvate
    skipped_losses = sum(1 for b in skipped if b["result"] == "LOSS")
    skipped_wins = sum(1 for b in skipped if b["result"] == "WIN")
    units_saved = sum(-b["profit_v5"] for b in skipped if b["result"] == "LOSS")
    units_lost = sum(-b["profit_v5"] for b in skipped if b["result"] == "WIN")  # b['profit_v5'] e + pentru WIN

    return {
        "n_total" + suffix: n_total,
        "n_v5_kept" + suffix: len(v5_kept),
        "n_v6_kept" + suffix: len(v6_kept),
        "n_skipped_by_v6" + suffix: len(skipped),
        "skipped_losses_avoided" + suffix: skipped_losses,
        "skipped_wins_lost" + suffix: skipped_wins,
        "units_saved_from_avoided_losses" + suffix: round(units_saved, 2),
        "units_lost_from_avoided_wins" + suffix: round(units_lost, 2),
        "net_units_impact" + suffix: round(units_saved - units_lost, 2),
        "v5_roi_pct" + suffix: round(v5_roi, 2),
        "v6_roi_pct" + suffix: round(v6_roi, 2),
        "roi_delta_pp" + suffix: round(v6_roi - v5_roi, 2),
        "v5_win_rate_pct" + suffix: round(v5_wins / len(v5_kept) * 100, 1) if v5_kept else 0,
        "v6_win_rate_pct" + suffix: round(v6_wins / len(v6_kept) * 100, 1) if v6_kept else 0,
        "v5_total_profit" + suffix: round(v5_profit, 2),
        "v6_total_profit" + suffix: round(v6_profit, 2),
    }


def aggregate_by_dimension(evaluated: List[Dict], dim: str) -> Dict[str, Dict]:
    """Agregare stats per (market sau strategie)."""
    groups: Dict[str, List[Dict]] = {}
    for b in evaluated:
        key = b.get(dim) or "unknown"
        groups.setdefault(key, []).append(b)

    out = {}
    for key, bets in groups.items():
        stats = compute_aggregate_stats(bets)
        # Adauga numele pariurilor pentru context
        stats["sample_bets"] = [
            {
                "event": f"{b['home_team']} vs {b['away_team']}",
                "market": b["market"],
                "odds": b["odds"],
                "prob_v5": round(b["prob_v5"], 3),
                "prob_v6": b["prob_v6"],
                "result": b["result"],
                "verdict_v6": b["verdict_v6"],
            }
            for b in bets[:3]  # primele 3 ca exemple
        ]
        out[key] = stats
    return out


# ============================================================
# MAIN PIPELINE
# ============================================================

def main() -> int:
    started = _now_iso()
    _log(f"=== v6 Backtest Framework — {started} ===")

    if not HAS_DEPS:
        _log("FATAL: numpy + sklearn obligatorii.")
        _save_empty("missing_deps")
        return 0

    journal = _load_json(SELECTION_JOURNAL, {})
    if not journal:
        _log("selection_journal.json lipseste")
        _save_empty("no_journal")
        return 0

    bets = extract_bets(journal)
    n_total = len(bets)
    _log(f"Extras {n_total} pariuri settle-uite (sortate cronologic)")

    if n_total < 20:
        _log("Insuficiente pariuri pentru backtest (necesar 20+)")
        _save_empty(f"only_{n_total}_bets")
        return 0

    # ============================================================
    # OUT-OF-SAMPLE BACKTEST (time-based holdout 60/40)
    # ============================================================
    split_idx = int(n_total * TRAIN_FRACTION)
    train_bets = bets[:split_idx]
    test_bets = bets[split_idx:]
    _log(f"Split: train={len(train_bets)} test={len(test_bets)}")

    train_calibrators = fit_calibrator_per_market(train_bets)
    _log(f"Calibratoare antrenate: {list(train_calibrators.keys())}")

    test_evaluated = [evaluate_bet(b, train_calibrators) for b in test_bets]
    oos_stats = compute_aggregate_stats(test_evaluated, suffix="")
    oos_by_market = aggregate_by_dimension(test_evaluated, "market")
    oos_by_strategy = aggregate_by_dimension(test_evaluated, "strategy")

    _log("Out-of-sample rezultate:")
    _log(f"  v5 ROI: {oos_stats.get('v5_roi_pct', 0):+.2f}% pe {oos_stats.get('n_v5_kept', 0)} pariuri")
    _log(f"  v6 ROI: {oos_stats.get('v6_roi_pct', 0):+.2f}% pe {oos_stats.get('n_v6_kept', 0)} pariuri")
    _log(f"  Delta:  {oos_stats.get('roi_delta_pp', 0):+.2f}pp")
    _log(f"  Loss-uri evitate: {oos_stats.get('skipped_losses_avoided', 0)} "
         f"({oos_stats.get('units_saved_from_avoided_losses', 0):+.2f}u salvate)")
    _log(f"  Wins ratate: {oos_stats.get('skipped_wins_lost', 0)} "
         f"({oos_stats.get('units_lost_from_avoided_wins', 0):.2f}u pierdute)")
    _log(f"  NET impact: {oos_stats.get('net_units_impact', 0):+.2f} unitati")

    # ============================================================
    # IN-SAMPLE BACKTEST (calibrator real fit pe TOATE) — pentru istoric
    # ============================================================
    real_calibrators = {}
    if CALIBRATORS_PKL.exists():
        try:
            with open(CALIBRATORS_PKL, "rb") as f:
                real_calibrators = pickle.load(f).get("calibrators", {})
        except Exception as e:
            _log(f"WARN incarcare calibratori reali: {e}")

    if not real_calibrators:
        # Fallback: fit pe toate
        real_calibrators = fit_calibrator_per_market(bets)

    all_evaluated = [evaluate_bet(b, real_calibrators) for b in bets]
    is_stats = compute_aggregate_stats(all_evaluated, suffix="")
    is_by_market = aggregate_by_dimension(all_evaluated, "market")
    is_by_strategy = aggregate_by_dimension(all_evaluated, "strategy")

    _log("In-sample rezultate (cu calibratori curenti):")
    _log(f"  v5 ROI: {is_stats.get('v5_roi_pct', 0):+.2f}%")
    _log(f"  v6 ROI: {is_stats.get('v6_roi_pct', 0):+.2f}%")
    _log(f"  Delta:  {is_stats.get('roi_delta_pp', 0):+.2f}pp")

    # ============================================================
    # OUTPUT
    # ============================================================
    output = {
        "updated_at": _now_iso(),
        "model_version": MODEL_VERSION,
        "source": "v6_backtest",
        "methodology": {
            "out_of_sample": (
                f"Time-based holdout {int(TRAIN_FRACTION*100)}/{int((1-TRAIN_FRACTION)*100)}. "
                f"Calibratori antrenati DOAR pe primele {split_idx} pariuri cronologic, "
                f"evaluati pe ultimele {n_total - split_idx}. "
                f"Asta simuleaza productia: invata din trecut, prezice viitor."
            ),
            "in_sample": (
                f"Calibratori reali (din models/calibrators_v6.pkl) aplicati pe TOATE "
                f"cele {n_total} pariuri. OPTIMIST — calibratorii au fost antrenati pe "
                f"aceste date. Util doar pentru istoric individual."
            ),
        },
        "out_of_sample": {
            "split": {"train_n": len(train_bets), "test_n": len(test_bets)},
            "overall": oos_stats,
            "by_market": oos_by_market,
            "by_strategy": oos_by_strategy,
        },
        "in_sample": {
            "overall": is_stats,
            "by_market": is_by_market,
            "by_strategy": is_by_strategy,
        },
        "history": all_evaluated,
        "_pipeline_version": "v6.0-backtest",
    }
    _save_atomic(OUT_REPORT, output)
    _log(f"OK: v6_backtest_report.json scris ({n_total} pariuri in istoric)")

    # Debug
    _save_atomic(OUT_DEBUG, {
        "started_at": started,
        "ended_at": _now_iso(),
        "n_total": n_total,
        "oos": oos_stats,
        "in_sample": is_stats,
    })

    return 0


def _save_empty(reason: str) -> None:
    _save_atomic(OUT_REPORT, {
        "updated_at": _now_iso(),
        "model_version": MODEL_VERSION,
        "source": "v6_backtest",
        "reason": reason,
        "out_of_sample": {},
        "in_sample": {},
        "history": [],
    })


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        _log(f"CRASH: {e}")
        traceback.print_exc()
        try:
            _save_empty(f"crash: {e}")
        except Exception:
            pass
        sys.exit(0)
