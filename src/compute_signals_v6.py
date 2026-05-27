#!/usr/bin/env python3
"""
src/compute_signals_v6.py
=========================
BetPredict Pro v6.0 — Enhanced Signal Engine

Ce face:
- Citeste data/signals.json (semnalele generate de fetch_daily.py v5).
- Augmenteaza fiecare semnal cu date v6: ML prob, probabilitate calibrata,
  consensus score, smartbet_score_v6, quality_grade_v6, EV calibrat.
- Rescrie data/signals.json cu schema COMPATIBILA (campuri noi adaugate,
  zero campuri existente sterse sau redenumite).
- Rescrie data/signals_v6.json cu date complete v6 pentru UI dashboard.
- Re-sorteaza semnalele dupa smartbet_score_v6 (cel mai bun prim).
- Marcheaza semnale downgraded (calibrare reduce EV la negativ) si
  upgraded (ML + calibrare cresc EV vs v5).

Schema NOUA (campuri adaugate la fiecare semnal):
  ml_prob            - probabilitate ML ensemble pentru market
  blend_prob         - media BSD+ML (calibrata)
  consensus_score    - acord 0-1 intre surse
  consensus_tier     - TOTAL/PARTIAL/DIVERGENT/CONTRADICTORIU
  calibrated_prob    - probabilitate dupa isotonic calibration
  ev_calibrated      - EV recalculat cu probabilitate calibrata
  ev_calibrated_pct  - EV calibrat ca procent
  smartbet_score_v6  - scor v6 cu ML + consens + calibrare
  quality_grade_v6   - A+/A/B/C/D/E
  _v6_status         - UPGRADED/DOWNGRADED/UNCHANGED/NEW_ML
  _v6_enhanced       - true (marker vizibil in debug)

Comportament:
- Semnale DOWNGRADED: EV calibrat < 0 → raman in output, marcate
  (UI poate colora diferit sau ascunde; nu le stergem fara ok)
- Semnale UPGRADED: EV calibrat > EV original + 0.02 → marcate cu
  evidentierea ML value
- Nu se sterg semnale din signals.json (siguranta pipeline)

Rulat DUPA: ml_ensemble.py, calibration_engine.py, consensus_engine.py
Output:
  data/signals.json      (actualizat cu campuri v6, backward-compat)
  data/signals_v6.json   (copie completa pentru UI dashboard v6)
  data/debug/compute_signals_v6_debug.json
"""

from __future__ import annotations
import json
import pickle
import sys
import traceback
import warnings
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

warnings.filterwarnings("ignore")

# ============================================================
# CALE & CONFIGURARE
# ============================================================

ROOT_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = ROOT_DIR / "data"
MODELS_DIR = ROOT_DIR / "models"
DEBUG_DIR = DATA_DIR / "debug"
SRC_DIR = ROOT_DIR / "src"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

SIGNALS_JSON = DATA_DIR / "signals.json"
ML_PREDICTIONS = DATA_DIR / "ml_predictions.json"
CONSENSUS_JSON = DATA_DIR / "consensus.json"
CALIBRATORS_PKL = MODELS_DIR / "calibrators_v6.pkl"
ADAPTIVE_JSON = DATA_DIR / "adaptive_thresholds.json"
PREDICTIONS_JSON = DATA_DIR / "predictions.json"
ROLLING_FEATURES = DATA_DIR / "rolling_features.json"

OUT_SIGNALS = DATA_DIR / "signals.json"
OUT_SIGNALS_V6 = DATA_DIR / "signals_v6.json"
OUT_DEBUG = DEBUG_DIR / "compute_signals_v6_debug.json"

MODEL_VERSION = "v6.1-signals"

# Prag diferenta relevanta BSD vs calibrat (pp)
SIGNIFICANT_CAL_DIFF = 0.04   # 4pp - sub asta, consideram "unchanged"
UPGRADE_EV_THRESHOLD = 0.02   # EV calibrat > EV original + 0.02 = UPGRADED

MARKET_ALIASES = {
    "1": "homeWin", "homeWin": "homeWin",
    "X": "draw", "draw": "draw",
    "2": "awayWin", "awayWin": "awayWin",
    "btts": "btts", "btts_yes": "btts",
    "over15": "over15", "over_15": "over15",
    "under15": "under15",
    "over25": "over25", "over_25": "over25",
    "under25": "under25", "under_25": "under25",
    "over35": "over35",
    "under35": "under35", "under_35": "under35",
}

PIPELINE_LOG: List[str] = []


def _log(msg: str) -> None:
    print(f"[signals_v6] {msg}")
    PIPELINE_LOG.append(msg)


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
    except Exception as e:
        _log(f"WARN citire {path.name}: {e}")
        return default


def _save_json_atomic(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    tmp.replace(path)


def _normalize_market(name: Any) -> Optional[str]:
    if not name:
        return None
    raw = str(name).strip()
    return MARKET_ALIASES.get(raw)


# ============================================================
# INCARCARE CALIBRATOARE
# ============================================================

def load_calibrators() -> Dict[str, Any]:
    if not CALIBRATORS_PKL.exists():
        _log("WARN: calibrators_v6.pkl lipseste — rulati calibration_engine.py mai intai")
        return {}
    try:
        with open(CALIBRATORS_PKL, "rb") as f:
            data = pickle.load(f)
        cals = data.get("calibrators", {})
        _log(f"Calibratoare incarcate: {list(cals.keys())}")
        return cals
    except Exception as e:
        _log(f"WARN incarcare calibratoare: {e}")
        return {}


def apply_calibration(market: str, prob: float, cals: Dict) -> float:
    """Aplica calibratorul pentru un market si probabilitate."""
    canonical = _normalize_market(market)
    if not canonical or canonical not in cals:
        return _clip(prob)
    state = cals[canonical]
    t = state.get("type", "identity")
    p = float(prob)
    if t == "identity":
        return _clip(p)
    if t == "shift":
        return _clip(p + float(state.get("shift", 0.0)))
    if t == "isotonic":
        iso = state.get("iso")
        if iso is None:
            return _clip(p)
        try:
            return _clip(float(iso.predict([p])[0]))
        except Exception:
            return _clip(p)
    return _clip(p)


# ============================================================
# INDECSI RAPIZI
# ============================================================

def build_ml_index(ml_data: Dict) -> Dict[Tuple[int, str], float]:
    """Index (event_id, market_canonical) -> prob ML."""
    idx: Dict[Tuple[int, str], float] = {}
    for r in (ml_data or {}).get("results", []):
        eid_raw = r.get("event_id")
        if eid_raw is None:
            continue
        try:
            eid = int(eid_raw)
        except (TypeError, ValueError):
            continue
        probs = r.get("ml_probabilities") or {}
        for mk, val in probs.items():
            p = _safe_float(val)
            if p >= 0:
                canonical = _normalize_market(mk)
                if canonical:
                    idx[(eid, canonical)] = p
    return idx


def build_consensus_index(cons_data: Dict) -> Dict[Tuple[int, str], Dict]:
    """Index (event_id, market_canonical) -> consensus info."""
    idx: Dict[Tuple[int, str], Dict] = {}
    for r in (cons_data or {}).get("results", []):
        eid_raw = r.get("event_id")
        if eid_raw is None:
            continue
        try:
            eid = int(eid_raw)
        except (TypeError, ValueError):
            continue
        for mk, mdata in (r.get("markets") or {}).items():
            canonical = _normalize_market(mk)
            if canonical:
                idx[(eid, canonical)] = mdata
    return idx


# ============================================================
# BLEND 3-WAY (inline, fara import)
# ============================================================

def _blend_3way(bsd: float, ml: float, w_bsd: float = 0.50,
                w_ml: float = 0.50) -> float:
    """Media ponderata BSD+ML. Daca una lipseste, cealalta primeste tot."""
    sources = {}
    if 0.0 <= bsd <= 1.0:
        sources["bsd"] = (bsd, max(0.0, w_bsd))
    if 0.0 <= ml <= 1.0:
        sources["ml"] = (ml, max(0.0, w_ml))
    if not sources:
        return 0.5
    total_w = sum(w for _, w in sources.values())
    if total_w <= 1e-12:
        return sum(p for p, _ in sources.values()) / len(sources)
    blended = sum(p * w for p, w in sources.values()) / total_w
    return _clip(blended)


def _consensus_agreement(p1: float, p2: float,
                         p3: float = -1.0) -> float:
    """Masura de acord 0-1. Valori negative ignorate."""
    valid = [p for p in (p1, p2, p3) if 0.0 <= p <= 1.0]
    n = len(valid)
    if n < 2:
        return 1.0
    mean = sum(valid) / n
    from math import sqrt
    variance = sum((p - mean) ** 2 for p in valid) / n
    return round(max(0.0, 1.0 - 2.0 * sqrt(variance)), 4)


def _tier_from_ag(ag: float) -> str:
    if ag >= 0.85:
        return "TOTAL"
    if ag >= 0.60:
        return "PARTIAL"
    if ag >= 0.35:
        return "DIVERGENT"
    return "CONTRADICTORIU"


def _smartbet_v6(calibrated_prob: float, consensus_ag: float,
                 ls_delta: float = 0.0) -> float:
    """SmartBet Score v6: prob calibrata + consens + league strength."""
    prob_score = max(0.0, min(100.0, (calibrated_prob - 0.50) / 0.35 * 100))
    consensus_bonus = _clip(consensus_ag, 0.0, 1.0) * 15.0
    ls_delta_abs = abs(_safe_float(ls_delta, 0.0))
    ls_bonus = max(0.0, min(8.0, (ls_delta_abs - 8.0) / 35.0 * 8.0))
    raw = prob_score * 0.85 + consensus_bonus + ls_bonus
    return round(max(0.0, min(100.0, raw)), 1)


def _grade_v6(score: float, ag: float) -> str:
    if score >= 88 and ag >= 0.80:
        return "A+"
    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    if score >= 35:
        return "D"
    return "E"


def _parse_pct(value: Any, default: Optional[float] = None) -> Optional[float]:
    """Extrage un numar din valori de forma 7.1, '7.1%' sau '7,1%'."""
    if value is None or value == "":
        return default
    try:
        if isinstance(value, str):
            value = value.replace("%", "").replace(",", ".").strip()
        x = float(value)
        return default if x != x else x
    except Exception:
        return default


def _market_signal_score(sig: Dict[str, Any]) -> float:
    """
    Scor pentru piata recomandata pe card, nu pentru piata 1X2.

    smartbet_score vechi poate ramane 0 pentru selectii Over/BTTS, deoarece era
    derivat din probabilitatile home/draw/away. Acest scor foloseste campurile
    semnalului afisat: adj_prob, edge_pp, EV si cota.
    """
    prob = _parse_pct(sig.get("adj_prob"), None)
    edge = max(0.0, _parse_pct(sig.get("edge_pp"), 0.0) or 0.0)
    ev = _parse_pct(sig.get("ev_calibrated_pct"), None)
    if ev is None:
        ev = _parse_pct(sig.get("ev_pct"), None)
    if ev is None:
        ev_raw = _parse_pct(sig.get("ev_calibrated"), None)
        if ev_raw is None:
            ev_raw = _parse_pct(sig.get("ev"), 0.0)
        ev = (ev_raw or 0.0) * 100.0 if abs(ev_raw or 0.0) <= 1.0 else (ev_raw or 0.0)

    odds = _safe_float(sig.get("odds") or sig.get("market_odds") or sig.get("best_odds"), 0.0)

    if prob is None or prob <= 0:
        fallback = _safe_float(sig.get("smartbet_score_v6"), -1.0)
        if fallback < 0:
            fallback = _safe_float(sig.get("smartbet_score"), 0.0)
        return round(max(0.0, min(100.0, fallback)), 1)

    prob_score = max(0.0, min(100.0, (prob - 60.0) / 30.0 * 100.0))
    edge_score = max(0.0, min(100.0, edge / 8.0 * 100.0))
    ev_score = max(0.0, min(100.0, max(0.0, ev or 0.0) / 12.0 * 100.0))

    if 1.15 <= odds <= 1.65:
        odds_score = 100.0
    elif 1.05 <= odds <= 2.00:
        odds_score = 70.0
    else:
        odds_score = 40.0

    score = prob_score * 0.50 + edge_score * 0.25 + ev_score * 0.20 + odds_score * 0.05
    return round(max(0.0, min(100.0, score)), 1)


def _market_signal_grade(score: float) -> str:
    if score >= 88:
        return "A+"
    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    if score >= 35:
        return "D"
    return "E"


# ============================================================
# AUGMENTARE SEMNAL
# ============================================================

# ============================================================
# POISSON INLINE (fara import extern — robustete CI/CD)
# ============================================================

def _poisson_pmf(lam: float, k: int) -> float:
    from math import exp, factorial as _fac
    lam = max(0.01, min(10.0, float(lam)))
    k = max(0, int(k))
    return exp(-lam) * (lam ** k) / _fac(k)


def _poisson_most_likely_score(lam_h: float, lam_a: float, max_g: int = 7) -> str:
    best_p, best_s = -1.0, "1-1"
    for h in range(max_g + 1):
        for a in range(max_g + 1):
            p = _poisson_pmf(lam_h, h) * _poisson_pmf(lam_a, a)
            if p > best_p:
                best_p = p
                best_s = f"{h}-{a}"
    return best_s


def build_rolling_index(rolling_data: Optional[Dict]) -> Tuple[Dict[int, Dict], Dict[int, Dict]]:
    """
    Returns (team_features_idx, league_averages_idx).
    team_features_idx: {team_id_int: {attack_str_home, defense_str_home, ...}}
    league_averages_idx: {league_id_int: {avg_gf_home, avg_gf_away, ...}}
    """
    tf: Dict[int, Dict] = {}
    la: Dict[int, Dict] = {}
    if not rolling_data:
        return tf, la
    for tid_str, feats in rolling_data.get("team_features", {}).items():
        try:
            tf[int(tid_str)] = feats
        except (TypeError, ValueError):
            pass
    for lid_str, avgs in rolling_data.get("league_averages", {}).items():
        try:
            la[int(lid_str)] = avgs
        except (TypeError, ValueError):
            pass
    return tf, la


def _enrich_with_poisson(
    sig: Dict,
    rolling_tf: Dict[int, Dict],
    rolling_la: Dict[int, Dict],
) -> None:
    """
    Calculeaza si injecteaza campurile Poisson in semnal (in-place).
    Foloseste Attack/Defense Strength din rolling_features_engine.py.

    Formule:
      λ_home = attack_str_home * defense_str_away * league_avg_gf_home
      λ_away = attack_str_away * defense_str_home * league_avg_gf_away
    """
    try:
        hid_raw = sig.get("home_team_id")
        aid_raw = sig.get("away_team_id")
        lid_raw = sig.get("league_id")
        if hid_raw is None or aid_raw is None:
            return

        hid = int(hid_raw)
        aid = int(aid_raw)
        lid = int(lid_raw) if lid_raw is not None else 0

        hf = rolling_tf.get(hid, {})
        af = rolling_tf.get(aid, {})

        # Liga dominantă: încearcă liga meciului, altfel fallback global (0)
        lav = rolling_la.get(lid) or rolling_la.get(0, {})
        l_avg_gf_h = max(0.5, float(lav.get("avg_gf_home", 1.40)))
        l_avg_gf_a = max(0.5, float(lav.get("avg_gf_away", 1.10)))

        atk_h = float(hf.get("attack_str_home", 1.0))
        def_h = float(hf.get("defense_str_home", 1.0))
        atk_a = float(af.get("attack_str_away", 1.0))
        def_a = float(af.get("defense_str_away", 1.0))

        lam_h = max(0.1, min(5.0, atk_h * def_a * l_avg_gf_h))
        lam_a = max(0.1, min(5.0, atk_a * def_h * l_avg_gf_a))

        sig["lambda_home"] = round(lam_h, 2)
        sig["lambda_away"] = round(lam_a, 2)
        sig["poisson_score"] = _poisson_most_likely_score(lam_h, lam_a)
        sig["h_attack_str"] = round(atk_h, 2)
        sig["a_attack_str"] = round(atk_a, 2)
        sig["h_defense_str"] = round(def_h, 2)
        sig["a_defense_str"] = round(def_a, 2)
        sig["h_form_trend"] = round(float(hf.get("form_trend", 0.0)), 2)
        sig["a_form_trend"] = round(float(af.get("form_trend", 0.0)), 2)
        sig["h_form_pts_10"] = round(float(hf.get("form_pts_10", 1.4)), 2)
        sig["a_form_pts_10"] = round(float(af.get("form_pts_10", 1.4)), 2)
        sig["_has_poisson_data"] = True
    except Exception:
        pass  # Nu blocăm pipeline-ul pentru erori de enrichment


def augment_signal(
    sig: Dict,
    ml_idx: Dict,
    cons_idx: Dict,
    cals: Dict,
    rolling_tf: Optional[Dict] = None,
    rolling_la: Optional[Dict] = None,
) -> Dict:
    """
    Adauga campuri v6 la un semnal existent.
    NU modifica campurile existente — adauga doar campuri noi.
    """
    sig = dict(sig)  # copie, nu modifica originalul

    eid = sig.get("event_id")
    market = sig.get("market", "")
    canonical = _normalize_market(market) or market

    # Probabilitate BSD raw (adj_prob e in %, convertim la 0-1)
    adj_pct = _safe_float(sig.get("adj_prob"), -1.0)
    bsd_prob = adj_pct / 100.0 if adj_pct > 1.0 else adj_pct
    if bsd_prob < 0:
        bsd_prob = -1.0

    # ML prob
    ml_prob = -1.0
    if eid is not None:
        try:
            ml_prob = ml_idx.get((int(eid), canonical), -1.0)
        except (TypeError, ValueError):
            pass

    # Consensus data
    cons_data: Dict = {}
    if eid is not None:
        try:
            cons_data = cons_idx.get((int(eid), canonical), {})
        except (TypeError, ValueError):
            pass

    consensus_score = _safe_float(cons_data.get("agreement"), -1.0)
    if consensus_score < 0:
        # Calculeaza din sursele disponibile
        p_poi = _safe_float(cons_data.get("p_poisson"), -1.0)
        consensus_score = _consensus_agreement(
            bsd_prob if bsd_prob >= 0 else -1,
            ml_prob if ml_prob >= 0 else -1,
            p_poi,
        )
    consensus_tier = cons_data.get("tier") or _tier_from_ag(consensus_score)

    # Blend BSD + ML
    blend_prob = -1.0
    if bsd_prob >= 0 and ml_prob >= 0:
        blend_prob = _blend_3way(bsd_prob, ml_prob)
    elif bsd_prob >= 0:
        blend_prob = bsd_prob
    elif ml_prob >= 0:
        blend_prob = ml_prob

    # Calibrare
    calibrated_prob = -1.0
    if blend_prob >= 0:
        calibrated_prob = apply_calibration(canonical, blend_prob, cals)
    elif bsd_prob >= 0:
        calibrated_prob = apply_calibration(canonical, bsd_prob, cals)

    # EV calibrat
    odds = _safe_float(sig.get("odds"), -1.0)
    ev_calibrated = None
    ev_calibrated_pct = None
    if calibrated_prob > 0 and odds > 1.01:
        ev_cal = calibrated_prob * (odds - 1.0) - (1.0 - calibrated_prob)
        ev_calibrated = round(ev_cal, 4)
        ev_calibrated_pct = f"{ev_cal * 100:.1f}%"

    # SmartBet v6
    ls_delta = _safe_float(sig.get("league_strength_delta"), 0.0)
    ag_for_score = max(0.0, consensus_score)
    prob_for_score = calibrated_prob if calibrated_prob > 0 else (bsd_prob if bsd_prob > 0 else 0.5)
    sb_v6 = _smartbet_v6(prob_for_score, ag_for_score, ls_delta)
    grade_v6 = _grade_v6(sb_v6, ag_for_score)

    # Status v6
    ev_original = _safe_float(sig.get("ev"), -99.0)
    if ev_calibrated is not None:
        if ev_calibrated <= 0 and ev_original > 0:
            status = "DOWNGRADED"
        elif ev_calibrated is not None and ev_original > -99 and ev_calibrated > ev_original + UPGRADE_EV_THRESHOLD:
            status = "UPGRADED"
        else:
            diff = abs((calibrated_prob - (bsd_prob if bsd_prob >= 0 else 0.5)))
            status = "UNCHANGED" if diff < SIGNIFICANT_CAL_DIFF else "ADJUSTED"
    else:
        status = "UNCHANGED"

    # Adauga campuri v6 (fara a modifica cele existente)
    sig["ml_prob"] = round(ml_prob, 4) if ml_prob >= 0 else None
    sig["blend_prob"] = round(blend_prob, 4) if blend_prob >= 0 else None
    sig["calibrated_prob"] = round(calibrated_prob, 4) if calibrated_prob > 0 else None
    sig["consensus_score"] = round(consensus_score, 3) if consensus_score >= 0 else None
    sig["consensus_tier"] = consensus_tier
    sig["ev_calibrated"] = ev_calibrated
    sig["ev_calibrated_pct"] = ev_calibrated_pct
    sig["smartbet_score_v6"] = sb_v6
    sig["quality_grade_v6"] = grade_v6

    market_score = _market_signal_score(sig)
    sig["market_signal_score"] = market_score
    sig["market_signal_grade"] = _market_signal_grade(market_score)
    sig["display_score"] = market_score
    sig["display_grade"] = sig["market_signal_grade"]
    sig["display_score_source"] = "market_signal_score"

    sig["_v6_status"] = status
    sig["_v6_enhanced"] = True

    # v6.1: enrichment Poisson cu rolling Attack/Defense Strength
    if rolling_tf is not None:
        _enrich_with_poisson(sig, rolling_tf, rolling_la or {})

    return sig


# ============================================================
# MAIN
# ============================================================

def main() -> int:
    started = _now_iso()
    _log(f"=== Compute Signals v6.0 — {started} ===")

    # Incarcare date
    signals_data = _load_json(SIGNALS_JSON, {})
    ml_data = _load_json(ML_PREDICTIONS, {})
    cons_data = _load_json(CONSENSUS_JSON, {})
    cals = load_calibrators()
    rolling_data = _load_json(ROLLING_FEATURES, None)  # v6.1

    signals = (signals_data or {}).get("signals", [])
    _log(f"Semnale v5 originale: {len(signals)}")
    _log(f"ML predictions: {len((ml_data or {}).get('results', []))}")
    _log(f"Consensus entries: {len((cons_data or {}).get('results', []))}")
    _log(f"Calibratoare: {list(cals.keys())}")

    # Indice rolling features pentru enrichment Poisson
    rolling_tf, rolling_la = build_rolling_index(rolling_data)
    has_rolling = bool(rolling_tf)
    _log(f"Rolling features: {'DA' if has_rolling else 'NU'} "
         f"({len(rolling_tf)} echipe, {len(rolling_la)} ligi)")

    if not signals:
        _log("Nu exista semnale de augmentat")
        _save_empty(signals_data)
        return 0

    # Indecsi
    ml_idx = build_ml_index(ml_data)
    cons_idx = build_consensus_index(cons_data)
    _log(f"ML index: {len(ml_idx)} (event,market) perechi")
    _log(f"Consensus index: {len(cons_idx)} (event,market) perechi")

    # Augmentare
    enhanced: List[Dict] = []
    stats = {"upgraded": 0, "downgraded": 0, "adjusted": 0, "unchanged": 0}

    for sig in signals:
        try:
            aug = augment_signal(
                sig, ml_idx, cons_idx, cals,
                rolling_tf=rolling_tf if has_rolling else None,
                rolling_la=rolling_la if has_rolling else None,
            )
            enhanced.append(aug)
            st = aug.get("_v6_status", "UNCHANGED").lower()
            if st in stats:
                stats[st] += 1
            elif st == "adjusted":
                stats["adjusted"] += 1
        except Exception as e:
            _log(f"  WARN augment {sig.get('event_id')} {sig.get('market')}: {e}")
            enhanced.append(dict(sig))  # pastreaza originalul

    # Sortare dupa scorul pietei recomandate pe card, cu fallback pe v6/legacy.
    enhanced.sort(
        key=lambda s: (
            s.get("market_signal_score") or s.get("display_score") or s.get("smartbet_score_v6") or s.get("smartbet_score") or 0,
            s.get("edge_pp") or 0,
        ),
        reverse=True,
    )

    _log(f"Augmentate: {len(enhanced)} semnale")
    _log(f"Stats: upgraded={stats['upgraded']} downgraded={stats['downgraded']} "
         f"adjusted={stats['adjusted']} unchanged={stats['unchanged']}")

    # Statistici calitate v6
    n_aplus = sum(1 for s in enhanced if s.get("quality_grade_v6") == "A+")
    n_a = sum(1 for s in enhanced if s.get("quality_grade_v6") == "A")
    n_downgraded = sum(1 for s in enhanced if s.get("_v6_status") == "DOWNGRADED")
    _log(f"Calitate v6: A+={n_aplus} A={n_a} downgraded={n_downgraded}")

    # by_strategy (pastraza structura existenta)
    by_strategy: Dict[str, List[Dict]] = {}
    for sig in enhanced:
        strat = sig.get("strategy") or "unknown"
        by_strategy.setdefault(strat, []).append(sig)

    strategy_stats: Dict[str, Any] = {}
    for strat, sigs in by_strategy.items():
        strategy_stats[strat] = {
            "count": len(sigs),
            "avg_score": round(
                sum(s.get("market_signal_score") or s.get("display_score") or s.get("smartbet_score_v6") or s.get("smartbet_score") or 0
                    for s in sigs) / len(sigs), 1
            ) if sigs else 0,
            "avg_ev_calibrated": round(
                sum(s.get("ev_calibrated") or s.get("ev") or 0 for s in sigs) / len(sigs), 4
            ) if sigs else 0,
        }

    # Output signals.json (backward-compat + v6 fields)
    now = _now_iso()
    out_signals = {
        **(signals_data or {}),
        "updated_at": now,
        "count": len(enhanced),
        "signals": enhanced,
        "by_strategy": by_strategy,
        "strategy_stats": strategy_stats,
        "_v6_enhanced": True,
        "_v6_stats": {
            "upgraded": stats["upgraded"],
            "downgraded": stats["downgraded"],
            "n_aplus": n_aplus,
            "n_a": n_a,
        },
        "_pipeline_version": MODEL_VERSION,
    }
    _save_json_atomic(OUT_SIGNALS, out_signals)
    _log(f"OK: signals.json actualizat ({len(enhanced)} semnale)")

    # Output signals_v6.json (copie completa cu date suplimentare)
    _save_json_atomic(OUT_SIGNALS_V6, {
        "updated_at": now,
        "model_version": MODEL_VERSION,
        "source": "compute_signals_v6",
        "count": len(enhanced),
        "summary": {
            "total": len(enhanced),
            "upgraded": stats["upgraded"],
            "downgraded": stats["downgraded"],
            "adjusted": stats["adjusted"],
            "unchanged": stats["unchanged"],
            "quality_aplus": n_aplus,
            "quality_a": n_a,
            "calibrators_applied": list(cals.keys()),
        },
        "signals": enhanced,
        "by_strategy": by_strategy,
        "_pipeline_version": MODEL_VERSION,
    })
    _log(f"OK: signals_v6.json scris")

    # Debug
    _save_json_atomic(OUT_DEBUG, {
        "status": "ok",
        "started_at": started,
        "ended_at": _now_iso(),
        "n_input": len(signals),
        "n_output": len(enhanced),
        "stats": stats,
        "quality": {"aplus": n_aplus, "a": n_a, "downgraded": n_downgraded},
        "sample_upgraded": [
            {k: v for k, v in s.items()
             if k in ("home_team", "away_team", "market", "adj_prob",
                      "calibrated_prob", "ev", "ev_calibrated", "smartbet_score_v6",
                      "market_signal_score", "display_score", "quality_grade_v6",
                      "display_grade", "_v6_status")}
            for s in enhanced if s.get("_v6_status") == "UPGRADED"
        ][:5],
        "sample_downgraded": [
            {k: v for k, v in s.items()
             if k in ("home_team", "away_team", "market", "adj_prob",
                      "calibrated_prob", "ev", "ev_calibrated", "_v6_status")}
            for s in enhanced if s.get("_v6_status") == "DOWNGRADED"
        ][:5],
        "log": PIPELINE_LOG[-50:],
    })

    return 0


def _save_empty(original: Optional[Dict]) -> None:
    if original:
        _save_json_atomic(OUT_SIGNALS, {**original, "_v6_enhanced": False})
    _save_json_atomic(OUT_SIGNALS_V6, {
        "updated_at": _now_iso(),
        "model_version": MODEL_VERSION,
        "count": 0,
        "signals": [],
        "reason": "no_signals_to_enhance",
    })


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"[signals_v6] CRASH: {e}")
        traceback.print_exc()
        sys.exit(0)
