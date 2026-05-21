#!/usr/bin/env python3
"""
src/calibration_engine.py
=========================
BetPredict Pro v6.0 — Isotonic Calibration Layer

Ce face:
- Citeste data/selection_journal.json (pariuri settle-uite).
- Pentru fiecare market, fit-eaza un IsotonicRegression care mapeaza
  "probabilitate prezisa" -> "rata reala de castig".
- Salveaza calibratoarele in models/calibrators_v6.pkl pentru uz in
  fetch_daily.py / compute_signals_from_preds.
- Genereaza data/calibration_report.json cu metrici per market (Brier,
  ECE, bias) si curbe de calibrare pentru afisare in dashboard.

DE CE ESTE CRITIC:
Datele tale arata ca v5 are bias SISTEMATIC per market:
  - under35: predict ~79% -> real 79% (CALIBRAT BINE)
  - homeWin: predict ~70% -> real 27% (BIAS +43pp!) — CATASTROFAL
  - over15:  predict ~80% -> real 82% (calibrat)
  - over25:  predict ~71% -> real 75% (mic bias)
Calibration engine corecteaza acest bias automat per market.

Strategie:
- Markete cu >=10 sample-uri settle-uite -> Isotonic Regression
- Markete cu 3-9 sample-uri -> Shift Calibration (linear bias correction)
- Markete cu <3 sample-uri -> Identity (pasaj pur, fara modificare)

Normalizare:
- selection_journal foloseste "1"/"X"/"2" si "homeWin"/"draw"/"awayWin"
  intermitent — le mapam la cheile canonice ale pipeline-ului.

Integrare:
- Dupa ce ml_ensemble.py / fetch_daily.py au probabilitati raw,
  apply_calibration() le transforma in probabilitati calibrate.

Output:
- data/calibration_report.json (metrici + curbe pentru UI)
- data/debug/calibration_debug.json
- models/calibrators_v6.pkl

Robustete:
- Daca selection_journal lipseste -> output gol cu reason
- Daca toate calibratoarele esueaza -> identity fallback
- Erori prinse, pipeline-ul daily nu se sparge niciodata
- Pickle compatibil cross-module (foloseste state dicts, fara clase custom)
"""

from __future__ import annotations
import json
import sys
import pickle
import warnings
import traceback
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

# ============================================================
# DEPENDENTE
# ============================================================

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    from sklearn.isotonic import IsotonicRegression
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

# ============================================================
# CAI & CONFIGURARE
# ============================================================

ROOT_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = ROOT_DIR / "data"
MODELS_DIR = ROOT_DIR / "models"
DEBUG_DIR = DATA_DIR / "debug"
MODELS_DIR.mkdir(parents=True, exist_ok=True)
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

SELECTION_JOURNAL = DATA_DIR / "selection_journal.json"
OUT_REPORT = DATA_DIR / "calibration_report.json"
OUT_DEBUG = DEBUG_DIR / "calibration_debug.json"
OUT_MODEL = MODELS_DIR / "calibrators_v6.pkl"

# Praguri pentru tip de calibrare
MIN_SAMPLES_ISOTONIC = 10
MIN_SAMPLES_SHIFT = 3

CANONICAL_MARKETS = [
    "homeWin", "draw", "awayWin",
    "btts", "no_btts",
    "over15", "under15",
    "over25", "under25",
    "over35", "under35",
]

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

MODEL_VERSION = "v6.0-calibration"

PIPELINE_LOG: List[str] = []


def _log(msg: str) -> None:
    print(f"[calibration] {msg}")
    PIPELINE_LOG.append(msg)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        x = float(v)
        return default if x != x else x
    except Exception:
        return default


def _clip01(x: float, lo: float = 0.01, hi: float = 0.99) -> float:
    return max(lo, min(hi, float(x)))


def _load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        _log(f"WARN citire {path.name}: {e}")
        return default


def _save_json_atomic(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    tmp.replace(path)


def normalize_market(name: Any) -> Optional[str]:
    if not name:
        return None
    raw = str(name).strip()
    canonical = MARKET_ALIASES.get(raw)
    if canonical:
        return canonical
    cleaned = raw.lower().replace(" ", "").replace("-", "").replace(".", "")
    return MARKET_ALIASES.get(cleaned)


# ============================================================
# COLECTARE DATE
# ============================================================

def collect_settled_bets(journal: Dict) -> Dict[str, List[Tuple[float, int]]]:
    """
    Returneaza dict {market_canonical: [(predicted_prob, actual_outcome), ...]}
    actual_outcome: 1 daca WIN, 0 daca LOSS
    Ignora PUSH/VOID/null.
    """
    by_market: Dict[str, List[Tuple[float, int]]] = {}
    skipped = {"unknown_market": 0, "no_prob": 0, "not_settled": 0, "push_void": 0}

    results = (journal or {}).get("results", [])
    for r in results:
        if r.get("status") != "settled":
            skipped["not_settled"] += 1
            continue

        outcome = r.get("result")
        if outcome not in ("WIN", "LOSS"):
            skipped["push_void"] += 1
            continue

        market = normalize_market(r.get("market"))
        if not market:
            skipped["unknown_market"] += 1
            continue

        prob = _safe_float(r.get("model_probability"), -1.0)
        if prob < 0.01 or prob > 0.99:
            skipped["no_prob"] += 1
            continue

        y = 1 if outcome == "WIN" else 0
        by_market.setdefault(market, []).append((prob, y))

    _log("Sample-uri pe market: " +
         ", ".join(f"{m}={len(v)}" for m, v in sorted(by_market.items())))
    if any(skipped.values()):
        _log(f"Skipped: {skipped}")

    return by_market


# ============================================================
# CALIBRATOR STATE — PLAIN DICTS (pickle-safe cross-module)
# ============================================================
#
# Decizie de design:
# Nu folosim clase custom (IdentityCalibrator/ShiftCalibrator) pentru ca
# pickle salveaza referinta __main__.ClassName si la unpickle din alt
# modul (ex: fetch_daily.py imports calibration_engine), referinta nu
# se mai poate rezolva.
#
# In loc, stocam STATE ca dict simplu:
#   {"type": "identity"}
#   {"type": "shift", "shift": 0.05}
#   {"type": "isotonic", "iso": <IsotonicRegression>}
# IsotonicRegression e clasa nativa sklearn, pickle-safe.

def fit_calibrator_state(samples: List[Tuple[float, int]]) -> Dict[str, Any]:
    n = len(samples)
    base = {"n_samples": n}

    if n == 0:
        return {"type": "identity", **base, "reason": "no_samples"}

    probs = [p for p, _ in samples]
    outcomes = [y for _, y in samples]
    avg_pred = sum(probs) / n
    avg_actual = sum(outcomes) / n
    bias = avg_pred - avg_actual

    base.update({
        "avg_predicted": float(avg_pred),
        "avg_actual": float(avg_actual),
        "bias": float(bias),
    })

    if n >= MIN_SAMPLES_ISOTONIC and HAS_SKLEARN and HAS_NUMPY:
        try:
            iso = IsotonicRegression(out_of_bounds="clip", y_min=0.01, y_max=0.99)
            iso.fit(np.array(probs), np.array(outcomes))
            return {"type": "isotonic", "iso": iso, **base}
        except Exception as e:
            _log(f"  Isotonic fit fail: {e} -> fallback la shift")

    if n >= MIN_SAMPLES_SHIFT:
        shift = avg_actual - avg_pred
        return {"type": "shift", "shift": float(shift), **base}

    return {"type": "identity", **base, "reason": f"only_{n}_samples"}


def apply_state(state: Dict[str, Any], prob: float) -> float:
    """Aplica un state de calibrator pe o probabilitate."""
    t = state.get("type", "identity")
    p = float(prob)

    if t == "identity":
        return _clip01(p)

    if t == "shift":
        return _clip01(p + float(state.get("shift", 0.0)))

    if t == "isotonic":
        iso = state.get("iso")
        if iso is None:
            return _clip01(p)
        try:
            out = iso.predict([p])
            return _clip01(float(out[0]))
        except Exception:
            return _clip01(p)

    return _clip01(p)


# ============================================================
# METRICI & CURBE
# ============================================================

def compute_brier(samples: List[Tuple[float, int]]) -> float:
    if not samples:
        return 0.0
    return float(sum((p - y) ** 2 for p, y in samples) / len(samples))


def compute_ece(samples: List[Tuple[float, int]], n_bins: int = 10) -> Dict:
    if not samples:
        return {"ece": 0.0, "curve": []}

    bins: Dict[int, List[Tuple[float, int]]] = {i: [] for i in range(n_bins)}
    for p, y in samples:
        idx = min(n_bins - 1, max(0, int(p * n_bins)))
        bins[idx].append((p, y))

    total = len(samples)
    ece = 0.0
    curve = []
    for i in range(n_bins):
        bucket = bins[i]
        if not bucket:
            curve.append({
                "bin": i + 1,
                "range_lo": round(i / n_bins, 2),
                "range_hi": round((i + 1) / n_bins, 2),
                "n": 0, "predicted_avg": None, "actual_avg": None, "gap": None,
            })
            continue
        avg_p = sum(p for p, _ in bucket) / len(bucket)
        avg_y = sum(y for _, y in bucket) / len(bucket)
        gap = avg_p - avg_y
        ece += abs(gap) * len(bucket) / total
        curve.append({
            "bin": i + 1,
            "range_lo": round(i / n_bins, 2),
            "range_hi": round((i + 1) / n_bins, 2),
            "n": len(bucket),
            "predicted_avg": round(avg_p, 4),
            "actual_avg": round(avg_y, 4),
            "gap": round(gap, 4),
        })

    return {"ece": round(ece, 4), "curve": curve}


def evaluate_state(
    state: Dict[str, Any],
    samples: List[Tuple[float, int]],
) -> Dict[str, Any]:
    pre_brier = compute_brier(samples)
    pre_ece = compute_ece(samples)

    post_samples = [(apply_state(state, p), y) for p, y in samples]
    post_brier = compute_brier(post_samples)
    post_ece = compute_ece(post_samples)

    improvement = pre_brier - post_brier

    return {
        "pre": {
            "brier": round(pre_brier, 4),
            "ece": pre_ece["ece"],
            "avg_predicted": round(state.get("avg_predicted", 0), 4),
            "avg_actual": round(state.get("avg_actual", 0), 4),
            "bias": round(state.get("bias", 0), 4),
        },
        "post": {
            "brier": round(post_brier, 4),
            "ece": post_ece["ece"],
        },
        "improvement": {
            "brier_delta": round(improvement, 4),
            "improved": improvement > 0,
        },
        "calibration_curve": pre_ece["curve"],
    }


# ============================================================
# API PUBLIC (importabil din fetch_daily.py etc.)
# ============================================================

def apply_calibration(
    market: str,
    prob: float,
    calibrators: Optional[Dict[str, Any]] = None,
) -> float:
    """
    Aplica calibratorul pe o probabilitate raw.
    Folosibila din fetch_daily.py:
        from src.calibration_engine import load_calibrators, apply_calibration
        cals = load_calibrators()
        new_prob = apply_calibration("under35", 0.85, cals)
    """
    if calibrators is None:
        calibrators = load_calibrators()

    market_canonical = normalize_market(market)
    if not market_canonical or market_canonical not in calibrators:
        return _clip01(prob)

    return apply_state(calibrators[market_canonical], prob)


def load_calibrators() -> Dict[str, Any]:
    """Incarca calibratoarele salvate. Returneaza dict gol daca nu exista."""
    if not OUT_MODEL.exists():
        return {}
    try:
        with open(OUT_MODEL, "rb") as f:
            data = pickle.load(f)
        return data.get("calibrators", {})
    except Exception as e:
        print(f"[calibration] WARN incarcare model: {e}")
        return {}


def get_market_bias(market: str, calibrators: Optional[Dict] = None) -> Optional[float]:
    """Returneaza bias-ul istoric pentru un market (avg_pred - avg_actual)."""
    if calibrators is None:
        calibrators = load_calibrators()
    market_canonical = normalize_market(market)
    if not market_canonical or market_canonical not in calibrators:
        return None
    return calibrators[market_canonical].get("bias")


# ============================================================
# MAIN PIPELINE
# ============================================================

def main() -> int:
    started = _now_iso()
    _log(f"=== Calibration Engine v6.0 — {started} ===")
    _log(f"Dependinte: numpy={HAS_NUMPY} sklearn={HAS_SKLEARN}")

    if not HAS_SKLEARN:
        _log("FATAL: sklearn obligatoriu. Adauga-l in requirements.txt.")
        _save_empty_report("missing_sklearn")
        return 0

    journal = _load_json(SELECTION_JOURNAL, {})
    if not journal:
        _log("selection_journal.json lipseste sau e gol")
        _save_empty_report("no_journal")
        return 0

    by_market = collect_settled_bets(journal)
    total_settled = sum(len(v) for v in by_market.values())
    _log(f"Total pariuri settle-uite extrase: {total_settled}")

    if total_settled == 0:
        _log("Niciun pariu settle-uit gasit")
        _save_empty_report("no_settled_bets")
        return 0

    calibrators: Dict[str, Any] = {}
    market_reports: Dict[str, Any] = {}

    for market, samples in by_market.items():
        state = fit_calibrator_state(samples)
        calibrators[market] = state
        evaluation = evaluate_state(state, samples)

        market_reports[market] = {
            "type": state["type"],
            "n_samples": state["n_samples"],
            **evaluation,
            **({"shift_applied": round(state["shift"], 4)}
               if "shift" in state else {}),
            **({"reason": state["reason"]}
               if "reason" in state else {}),
        }

        bias_pct = evaluation["pre"]["bias"] * 100
        improved = "MAI BUN" if evaluation["improvement"]["improved"] else "neutru"
        _log(f"  {market:10s} | tip={state['type']:8s} n={state['n_samples']:3d} "
             f"bias={bias_pct:+6.1f}pp Brier {evaluation['pre']['brier']:.4f}->"
             f"{evaluation['post']['brier']:.4f} ({improved})")

    try:
        with open(OUT_MODEL, "wb") as f:
            pickle.dump({
                "version": MODEL_VERSION,
                "calibrators": calibrators,
                "trained_at": _now_iso(),
                "n_total_settled": total_settled,
            }, f)
        _log(f"Calibratoare salvate: {OUT_MODEL}")
    except Exception as e:
        _log(f"WARN salvare pickle: {e}")

    if market_reports:
        overall = {
            "n_markets_calibrated": sum(1 for r in market_reports.values()
                                        if r["type"] in ("isotonic", "shift")),
            "n_markets_identity": sum(1 for r in market_reports.values()
                                      if r["type"] == "identity"),
            "avg_brier_pre": round(sum(r["pre"]["brier"] for r in market_reports.values())
                                   / len(market_reports), 4),
            "avg_brier_post": round(sum(r["post"]["brier"] for r in market_reports.values())
                                    / len(market_reports), 4),
            "biggest_bias_market": max(
                market_reports.items(),
                key=lambda kv: abs(kv[1]["pre"]["bias"]),
            )[0],
            "biggest_bias_value_pp": round(max(
                market_reports.values(),
                key=lambda r: abs(r["pre"]["bias"]),
            )["pre"]["bias"] * 100, 1),
        }
    else:
        overall = {}

    report = {
        "updated_at": _now_iso(),
        "model_version": MODEL_VERSION,
        "source": "calibration_engine_v6",
        "n_total_settled": total_settled,
        "overall": overall,
        "markets": market_reports,
        "_pipeline_version": "v6.0-calibration",
    }
    _save_json_atomic(OUT_REPORT, report)
    _log("OK: calibration_report.json scris")

    _save_json_atomic(OUT_DEBUG, {
        "status": "ok",
        "started_at": started,
        "ended_at": _now_iso(),
        "samples_per_market": {m: len(v) for m, v in by_market.items()},
        "calibrators_summary": {
            m: {"type": c["type"], "n_samples": c["n_samples"]}
            for m, c in calibrators.items()
        },
        "overall": overall,
        "log": PIPELINE_LOG[-50:],
        "_meta": {"has_numpy": HAS_NUMPY, "has_sklearn": HAS_SKLEARN},
    })

    return 0


def _save_empty_report(reason: str) -> None:
    _save_json_atomic(OUT_REPORT, {
        "updated_at": _now_iso(),
        "model_version": MODEL_VERSION,
        "source": "calibration_engine_v6",
        "n_total_settled": 0,
        "overall": {},
        "markets": {},
        "reason": reason,
        "_pipeline_version": "v6.0-calibration",
    })


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"[calibration] CRASH: {e}")
        traceback.print_exc()
        try:
            _save_empty_report(f"crash: {e}")
        except Exception:
            pass
        sys.exit(0)
