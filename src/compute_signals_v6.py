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
XG_CONTEXT_JSON = DATA_DIR / "xg_context.json"
ODDS_MOVEMENT_JSON = DATA_DIR / "odds_movement.json"

OUT_SIGNALS = DATA_DIR / "signals.json"
OUT_SIGNALS_V6 = DATA_DIR / "signals_v6.json"
OUT_DEBUG = DEBUG_DIR / "compute_signals_v6_debug.json"

MODEL_VERSION = "v6.1-signals"

# Prag diferenta relevanta BSD vs calibrat (pp)
SIGNIFICANT_CAL_DIFF = 0.04   # 4pp - sub asta, consideram "unchanged"
UPGRADE_EV_THRESHOLD = 0.02   # EV calibrat > EV original + 0.02 = UPGRADED

# ------------------------------------------------------------
# GUARDRAILS CALIBRARE (aceeasi plasa de siguranta ca in v6_backtest.py)
# Previne colapsurile isotonic pe esantion mic (ex: 0.56 -> 0.19) care
# omorau picks-urile de value in LIVE cand calibratoarele nu mai sunt identity.
SHRINK_K = 40.0            # tarie shrinkage: w = n / (n + K)
MAX_CAL_DELTA = 0.10       # o calibrare nu misca prob mai mult de +/- 10pp

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


def _shrink_and_cap(prob: float, cal: float, n_train: float) -> float:
    """
    Plasa de siguranta comuna cu v6_backtest.py:
      1. Shrinkage catre prob bruta, ponderat de nr. esantioane (w = n/(n+K)).
      2. Plafon absolut MAX_CAL_DELTA: nicio calibrare nu misca prob mai mult
         de +/- 10pp (previne colapsuri gen 0.56 -> 0.19 pe date putine).
    """
    prob = _clip(prob)
    cal = _clip(cal)
    n = max(0.0, float(n_train or 0.0))
    w = n / (n + SHRINK_K)
    blended = w * cal + (1.0 - w) * prob
    delta = blended - prob
    if delta > MAX_CAL_DELTA:
        blended = prob + MAX_CAL_DELTA
    elif delta < -MAX_CAL_DELTA:
        blended = prob - MAX_CAL_DELTA
    return _clip(blended)


def apply_calibration(market: str, prob: float, cals: Dict) -> float:
    """Aplica calibratorul pentru un market si probabilitate (cu guardrails)."""
    canonical = _normalize_market(market)
    if not canonical or canonical not in cals:
        return _clip(prob)
    state = cals[canonical]
    t = state.get("type", "identity")
    p = float(prob)
    if t == "identity":
        return _clip(p)

    # nr. esantioane de antrenare (productia foloseste n_samples; fallback n_train)
    n_train = state.get("n_samples", state.get("n_train", 0))

    if t == "shift":
        raw_cal = p + float(state.get("shift", 0.0))
        return _shrink_and_cap(p, raw_cal, n_train)

    if t == "isotonic":
        iso = state.get("iso")
        if iso is None:
            return _clip(p)
        try:
            raw_cal = float(iso.predict([p])[0])
        except Exception:
            return _clip(p)
        return _shrink_and_cap(p, raw_cal, n_train)

    return _clip(p)


# ============================================================
# ADAPTIVE GATE (enforce recomandarile per-piata)
# ============================================================
# Motorul adaptive_thresholds.py CALCULEAZA deja recomandari per-piata
# (min_prob_pct, min_edge_pp, blacklisted, verdict "EVITA") in
# adaptive_thresholds.json — dar pana acum NIMENI nu le aplica. De-aia
# picks-uri structural pierzatoare (ex: under35 la prob 70-80%, ROI -28%)
# treceau nefiltrate. Aici le impunem ca poarta, NON-DISTRUCTIV: semnalul
# ramane in output, dar primeste adaptive_verdict=AVOID + motiv, iar
# scorul de afisare e penalizat ca sa cada la baza ranking-ului.

def load_adaptive_gates() -> Dict[str, Dict[str, Any]]:
    """Incarca recomandarile per-piata din adaptive_thresholds.json."""
    data = _load_json(ADAPTIVE_JSON, {})
    if not isinstance(data, dict):
        return {}
    by_market = data.get("by_market", {}) or {}
    gates: Dict[str, Dict[str, Any]] = {}
    for market, entry in by_market.items():
        rec = (entry or {}).get("recommended", {}) or {}
        gates[market] = {
            "min_prob_pct": _safe_float(rec.get("min_prob_pct"), 0.0),
            "min_edge_pp": _safe_float(rec.get("min_edge_pp"), -999.0),
            "blacklisted": bool(rec.get("blacklisted", False)),
            "use_defaults": bool(rec.get("use_defaults", True)),
            "verdict": rec.get("verdict", ""),
        }
    return gates


def load_performance_guards() -> Dict[str, Dict[str, Any]]:
    """Încarcă deciziile bazate pe ROI real, separat de calibrarea probabilității."""
    try:
        if str(SRC_DIR) not in sys.path:
            sys.path.insert(0, str(SRC_DIR))
        from market_performance_guard import market_guard
        return market_guard()
    except Exception as exc:
        _log(f"WARN market performance guard indisponibil: {exc}")
        return {}


def adaptive_verdict(market: str, prob_pct: float, edge_pp: float,
                     gates: Dict[str, Dict[str, Any]]) -> Tuple[str, str]:
    """
    Returneaza (verdict, motiv). verdict: PASS / AVOID / BLACKLIST.
    Aplica recomandarea per-piata doar cand use_defaults=false (adica motorul
    a strans destule date ca sa aiba incredere in recomandare).
    """
    g = gates.get(market)
    if not g or g.get("use_defaults", True):
        return ("PASS", "")
    if g.get("blacklisted"):
        return ("BLACKLIST", f"{market} blacklisted de motorul adaptiv")
    min_prob = g.get("min_prob_pct", 0.0)
    min_edge = g.get("min_edge_pp", -999.0)
    if prob_pct >= 0 and min_prob > 0 and prob_pct < min_prob:
        return ("AVOID", f"prob {prob_pct:.0f}% < prag {min_prob:.0f}% pentru {market}")
    if edge_pp is not None and edge_pp > -900 and min_edge > -900 and edge_pp < min_edge:
        return ("AVOID", f"edge {edge_pp:.1f}pp < prag {min_edge:.1f}pp pentru {market}")
    return ("PASS", "")


# Penalizare scor pentru semnalele AVOID (le trimite la baza ranking-ului
# fara a le sterge — masurarea ramane intacta).
ADAPTIVE_AVOID_PENALTY = 1000.0


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


def build_ml_hist_index(hist_data: Dict) -> Dict[Tuple[int, str], float]:
    """Index (event_id, market_canonical) -> prob din modelul ISTORIC (antrenat
    saptamanal pe ~44k meciuri din warehouse, AUC homeWin/awayWin ~0.69 vs ~0.58-0.62
    la modelul zilnic antrenat pe <1000 meciuri recente). Probabilitatile vin in
    procente (62.9) — normalizate aici la 0-1."""
    idx: Dict[Tuple[int, str], float] = {}
    rows = (hist_data or {}).get("predictions") or (hist_data or {}).get("results") or []
    for r in rows:
        eid_raw = r.get("event_id")
        if eid_raw is None:
            continue
        try:
            eid = int(eid_raw)
        except (TypeError, ValueError):
            continue
        for mk, val in (r.get("markets") or {}).items():
            p = _safe_float(val)
            if p < 0:
                continue
            if p > 1.0:
                p = p / 100.0
            canonical = _normalize_market(mk)
            if canonical and 0.0 <= p <= 1.0:
                idx[(eid, canonical)] = p
    return idx


def combine_ml_indexes(daily_idx: Dict[Tuple[int, str], float],
                       hist_idx: Dict[Tuple[int, str], float],
                       daily_metrics: Dict, hist_metrics: Dict) -> Dict[Tuple[int, str], float]:
    """Combina modelul zilnic cu cel istoric, ponderat per piata cu skill-ul MASURAT
    (AUC - 0.5, din propriile lor metrici CV). Unde doar unul are predictie, il
    foloseste pe acela. Efect: homeWin/awayWin sunt dominate de modelul istoric
    (AUC 0.69-0.70), pietele unde ambele sunt slabe raman aproape neschimbate."""
    out: Dict[Tuple[int, str], float] = {}
    for k in set(daily_idx) | set(hist_idx):
        mk = k[1]
        pd_ = daily_idx.get(k)
        ph = hist_idx.get(k)
        if pd_ is not None and ph is not None:
            wd = max(_safe_float((daily_metrics.get(mk) or {}).get("auc"), 0.5) - 0.5, 0.02)
            wh = max(_safe_float((hist_metrics.get(mk) or {}).get("auc"), 0.5) - 0.5, 0.02)
            out[k] = (pd_ * wd + ph * wh) / (wd + wh)
        elif ph is not None:
            out[k] = ph
        else:
            out[k] = pd_
    return out


# Pondere ML per piata in blend-ul BSD+ML, setata in main() dupa AUC-ul combinat:
# baza 15% (ML = tiebreaker); piete unde vreun model dovedeste AUC >= 0.65 primesc
# 25% — mai mult semnal acolo unde skill-ul e demonstrat, zgomotul ramane plafonat.
_ML_MARKET_WEIGHT: Dict[str, float] = {}


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

def _blend_3way(bsd: float, ml: float, w_bsd: float = 0.85,
                w_ml: float = 0.15) -> float:
    """Media ponderata BSD+ML. Daca una lipseste, cealalta primeste tot.

    v7: ML repozitionat ca tiebreaker (15%), nu sursa co-egala. Motiv: AUC 0.583
    (aproape random) — ML-ul cu 50% pondere adauga zgomot, nu semnal. BSD (pretul
    real din piata) e ancora dominanta; ML doar inclina usor la marginile stranse.
    """
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
        # O singura sursa disponibila — nu putem verifica consensul; folosim 0.70
        # (certitudine partiala, nu maxima) pentru a evita supraestimarea increderii
        return 0.70
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

    Foloseste adj_prob (BSD raw) pentru ranking-ul vizual — quality_grade_v6
    filtreaza deja semnalele slabe prin calibrated_prob+consensus. Daca adj_prob
    lipseste, fallback la calibrated_prob (convertit la %).
    """
    prob = _parse_pct(sig.get("adj_prob"), None)
    # Fallback: calibrated_prob (0-1) → convertit la procente
    if prob is None or prob <= 0:
        cal_raw = _safe_float(sig.get("calibrated_prob"), -1.0)
        if 0.0 < cal_raw <= 1.0:
            prob = cal_raw * 100.0
        elif cal_raw > 1.0:
            prob = min(cal_raw, 100.0)

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
# INDECSI AUXILIARI: xG + odds movement
# ============================================================

def build_xg_index(xg_data: Optional[Dict]) -> Dict[int, Dict]:
    """Index event_id -> {xg_home, xg_away, xg_total} din xg_context.json."""
    idx: Dict[int, Dict] = {}
    if not xg_data:
        return idx
    for entry in (xg_data or {}).get("results", []):
        eid = entry.get("event_id")
        if eid is None:
            continue
        try:
            idx[int(eid)] = {
                "xg_home": float(entry.get("xg_home") or 1.3),
                "xg_away": float(entry.get("xg_away") or 1.0),
                "xg_total": float(entry.get("xg_total") or 2.3),
            }
        except (TypeError, ValueError):
            pass
    return idx


def build_odds_movement_index(mov_data: Optional[Any]) -> Dict[Tuple[int, str], str]:
    """Index (event_id, market) -> 'SHORTENING'|'DRIFTING'|'STABLE'."""
    idx: Dict[Tuple[int, str], str] = {}
    results = []
    if isinstance(mov_data, dict):
        results = mov_data.get("results", mov_data.get("data", []))
    elif isinstance(mov_data, list):
        results = mov_data
    for entry in results:
        eid = entry.get("event_id")
        market = entry.get("market")
        movement = entry.get("movement", "STABLE")
        if eid is None or not market:
            continue
        try:
            key = (int(eid), str(market))
            # SHORTENING = smart money; sobrescrie STABLE cu ceva mai informativ
            if key not in idx or movement in ("SHORTENING", "DRIFTING"):
                idx[key] = str(movement)
        except (TypeError, ValueError):
            pass
    return idx


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
    xg_idx: Optional[Dict] = None,
) -> None:
    """
    Calculeaza si injecteaza campurile Poisson in semnal (in-place).

    Prioritate λ:
      1. xG real din xg_context.json (predictiv — ce TREBUIA sa se intample)
      2. Attack/Defense Strength * avg_gf din rolling (reactiv — ce S-A intamplat)
    """
    try:
        hid_raw = sig.get("home_team_id")
        aid_raw = sig.get("away_team_id")
        lid_raw = sig.get("league_id")
        eid_raw = sig.get("event_id")
        if hid_raw is None or aid_raw is None:
            return

        hid = int(hid_raw)
        aid = int(aid_raw)
        lid = int(lid_raw) if lid_raw is not None else 0
        eid = int(eid_raw) if eid_raw is not None else -1

        hf = rolling_tf.get(hid, {})
        af = rolling_tf.get(aid, {})

        # Prioritatea 1: xG real (mai predictiv decat goluri istorice)
        xg_entry = (xg_idx or {}).get(eid)
        if xg_entry and xg_entry.get("xg_home") and xg_entry.get("xg_away"):
            lam_h = max(0.1, min(5.0, float(xg_entry["xg_home"])))
            lam_a = max(0.1, min(5.0, float(xg_entry["xg_away"])))
            sig["poisson_source"] = "xG"
        else:
            # Prioritatea 2: Attack/Defense Strength * avg_gf (fallback)
            lav = rolling_la.get(lid) or rolling_la.get(0, {})
            l_avg_gf_h = max(0.5, float(lav.get("avg_gf_home", 1.40)))
            l_avg_gf_a = max(0.5, float(lav.get("avg_gf_away", 1.10)))
            atk_h = float(hf.get("attack_str_home", 1.0))
            def_h = float(hf.get("defense_str_home", 1.0))
            atk_a = float(af.get("attack_str_away", 1.0))
            def_a = float(af.get("defense_str_away", 1.0))
            lam_h = max(0.1, min(5.0, atk_h * def_a * l_avg_gf_h))
            lam_a = max(0.1, min(5.0, atk_a * def_h * l_avg_gf_a))
            sig["poisson_source"] = "rolling_strength"

        sig["lambda_home"] = round(lam_h, 2)
        sig["lambda_away"] = round(lam_a, 2)
        sig["poisson_score"] = _poisson_most_likely_score(lam_h, lam_a)
        sig["h_attack_str"] = round(float(hf.get("attack_str_home", 1.0)), 2)
        sig["a_attack_str"] = round(float(af.get("attack_str_away", 1.0)), 2)
        sig["h_defense_str"] = round(float(hf.get("defense_str_home", 1.0)), 2)
        sig["a_defense_str"] = round(float(af.get("defense_str_away", 1.0)), 2)
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
    xg_idx: Optional[Dict] = None,
    movement_idx: Optional[Dict] = None,
    gates: Optional[Dict] = None,
    performance_guards: Optional[Dict] = None,
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
        # Calculeaza din sursele disponibile (BSD + ML + Poisson daca e disponibil)
        p_poi = _safe_float(cons_data.get("p_poisson"), -1.0)
        consensus_score = _consensus_agreement(
            bsd_prob if bsd_prob >= 0 else -1,
            ml_prob if ml_prob >= 0 else -1,
            p_poi,
        )
    consensus_tier = cons_data.get("tier") or _tier_from_ag(consensus_score)

    # Blend BSD + ML (pondere ML per piata, dupa AUC-ul masurat al modelelor)
    blend_prob = -1.0
    if bsd_prob >= 0 and ml_prob >= 0:
        w_ml = _ML_MARKET_WEIGHT.get(canonical, 0.15)
        blend_prob = _blend_3way(bsd_prob, ml_prob, w_bsd=1.0 - w_ml, w_ml=w_ml)
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

    # Diagnostic: gap intre probabilitatea modelului si cea implicita din cota
    # Useful pentru detectia supraestimarii — nu afecteaza scorul
    raw_odds = _safe_float(sig.get("odds"), -1.0)
    if raw_odds > 1.01 and calibrated_prob > 0:
        implied_p = (1.0 / raw_odds) / 1.05  # de-vig ~5%
        sig["model_vs_market_gap_pp"] = round((calibrated_prob - implied_p) * 100, 1)
    else:
        sig["model_vs_market_gap_pp"] = None

    sig["_v6_status"] = status
    sig["_v6_enhanced"] = True

    # ---- ADAPTIVE GATE: impune recomandarile per-piata (non-distructiv) ----
    if gates:
        prob_pct_gate = -1.0
        if calibrated_prob > 0:
            prob_pct_gate = calibrated_prob * 100.0
        elif bsd_prob > 0:
            prob_pct_gate = bsd_prob * 100.0
        edge_pp_gate = _safe_float(sig.get("edge_pp"), -999.0)
        verdict, reason = adaptive_verdict(canonical, prob_pct_gate, edge_pp_gate, gates)
        sig["adaptive_verdict"] = verdict
        sig["adaptive_reason"] = reason
        if verdict in ("AVOID", "BLACKLIST"):
            # Penalizeaza scorurile de ranking ca semnalul sa cada la baza listei,
            # fara sa-l stergem (ramane pentru masurare/invatare).
            for score_key in ("market_signal_score", "display_score", "smartbet_score_v6"):
                base = _safe_float(sig.get(score_key), 0.0)
                sig[score_key] = base - ADAPTIVE_AVOID_PENALTY
    else:
        sig["adaptive_verdict"] = "PASS"
        sig["adaptive_reason"] = ""

    # Poarta pe randament este independentă de calibrare: o piață poate fi bine
    # calibrată, dar totuși neprofitabilă după cote. Nu ștergem datele de audit,
    # însă marcăm fără echivoc semnalul drept neeligibil pentru publicare.
    perf = (performance_guards or {}).get(canonical, {})
    sig["performance_guard"] = perf
    if perf.get("blocked"):
        sig["publication_eligible"] = False
        sig["publication_reason"] = perf.get("reason") or "piață blocată de performanță"
        sig["performance_verdict"] = "BLOCKED"
        for score_key in ("market_signal_score", "display_score", "smartbet_score_v6"):
            sig[score_key] = _safe_float(sig.get(score_key), 0.0) - ADAPTIVE_AVOID_PENALTY
    elif perf:
        sig["publication_eligible"] = sig.get("adaptive_verdict") == "PASS"
        sig["publication_reason"] = perf.get("reason", "")
        sig["performance_verdict"] = "PENALIZED"
        for score_key in ("market_signal_score", "display_score", "smartbet_score_v6"):
            sig[score_key] = round(_safe_float(sig.get(score_key), 0.0) * float(perf.get("mult") or 1.0), 3)
    else:
        sig["publication_eligible"] = sig.get("adaptive_verdict") == "PASS"
        sig["publication_reason"] = sig.get("adaptive_reason", "")
        sig["performance_verdict"] = "PASS"

    # v6.1: enrichment Poisson — xG prioritar, rolling ca fallback
    if rolling_tf is not None:
        _enrich_with_poisson(sig, rolling_tf, rolling_la or {}, xg_idx=xg_idx)

    # v6.2: Market Momentum din odds_movement.json
    if movement_idx is not None:
        eid_int = None
        try:
            eid_int = int(sig.get("event_id", -1))
        except (TypeError, ValueError):
            pass
        market_raw = sig.get("market", "")
        if eid_int is not None and eid_int >= 0:
            movement = movement_idx.get((eid_int, market_raw), "STABLE")
            sig["market_momentum"] = movement
            # Bonus de confidenta daca smart money confirma directia noastra (EV+)
            sig["smart_money_confirm"] = (
                movement == "SHORTENING" and sig.get("ev_calibrated", 0) > 0
            )

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
    gates = load_adaptive_gates()                          # adaptive gate per-piata
    performance_guards = load_performance_guards()          # ROI real decontat per-piata
    active_gates = [m for m, g in gates.items() if not g.get("use_defaults", True)]
    _log(f"Adaptive gates active (non-default): {active_gates or 'niciuna'}")
    _log(f"Performance guard: blocate={[m for m, g in performance_guards.items() if g.get('blocked')] or 'niciuna'}")
    rolling_data = _load_json(ROLLING_FEATURES, None)      # v6.1
    xg_data = _load_json(XG_CONTEXT_JSON, None)            # v6.2 xG
    mov_data = _load_json(ODDS_MOVEMENT_JSON, None)        # v6.2 market momentum

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

    # Indice xG (v6.2) — pentru Poisson predictiv
    xg_idx = build_xg_index(xg_data)
    _log(f"xG context: {len(xg_idx)} meciuri cu date xG disponibile")

    # Indice odds movement (v6.2) — Market Momentum / Smart Money
    movement_idx = build_odds_movement_index(mov_data)
    _log(f"Odds movement: {len(movement_idx)} (event,market) perechi")

    if not signals:
        _log("Nu exista semnale de augmentat")
        _save_empty(signals_data)
        return 0

    # Indecsi — modelul zilnic (n<1000 recente) combinat cu cel ISTORIC
    # (antrenat saptamanal pe ~44k meciuri, AUC homeWin/awayWin ~0.69),
    # ponderat per piata cu skill-ul masurat al fiecaruia (AUC-0.5).
    ml_daily_idx = build_ml_index(ml_data)
    ml_hist_data = _load_json(DATA_DIR / "ml_predictions_historical.json", {})
    ml_hist_idx = build_ml_hist_index(ml_hist_data)
    daily_metrics = (ml_data or {}).get("metrics") or {}
    hist_metrics = (_load_json(DATA_DIR / "historical_ensemble_metrics.json", {}) or {}).get("metrics") or {}
    ml_idx = combine_ml_indexes(ml_daily_idx, ml_hist_idx, daily_metrics, hist_metrics)
    global _ML_MARKET_WEIGHT
    _ML_MARKET_WEIGHT = {}
    for mk in set(daily_metrics) | set(hist_metrics):
        best_auc = max(_safe_float((daily_metrics.get(mk) or {}).get("auc"), 0.5),
                       _safe_float((hist_metrics.get(mk) or {}).get("auc"), 0.5))
        _ML_MARKET_WEIGHT[mk] = 0.25 if best_auc >= 0.65 else 0.15
    cons_idx = build_consensus_index(cons_data)
    _log(f"ML index: {len(ml_idx)} (event,market) perechi "
         f"(zilnic={len(ml_daily_idx)}, istoric={len(ml_hist_idx)})")
    _log(f"Ponderi ML per piata: {_ML_MARKET_WEIGHT}")
    _log(f"Consensus index: {len(cons_idx)} (event,market) perechi")

    # Augmentare
    enhanced: List[Dict] = []
    stats = {"upgraded": 0, "downgraded": 0, "adjusted": 0, "unchanged": 0}
    gate_stats = {"avoid": 0, "blacklist": 0, "pass": 0}

    for sig in signals:
        try:
            aug = augment_signal(
                sig, ml_idx, cons_idx, cals,
                rolling_tf=rolling_tf if has_rolling else None,
                rolling_la=rolling_la if has_rolling else None,
                xg_idx=xg_idx if xg_idx else None,
                movement_idx=movement_idx if movement_idx else None,
                gates=gates if gates else None,
                performance_guards=performance_guards,
            )
            enhanced.append(aug)
            v = aug.get("adaptive_verdict", "PASS").lower()
            if v in gate_stats:
                gate_stats[v] += 1
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
    _log(f"Adaptive gate: AVOID={gate_stats['avoid']} BLACKLIST={gate_stats['blacklist']} "
         f"PASS={gate_stats['pass']}")

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
            "publication_eligible": sum(1 for s in enhanced if s.get("publication_eligible")),
            "performance_blocked": sum(1 for s in enhanced if s.get("performance_verdict") == "BLOCKED"),
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
            "adaptive_gate": {
                "avoid": gate_stats["avoid"],
                "blacklist": gate_stats["blacklist"],
                "pass": gate_stats["pass"],
                "active_markets": active_gates,
            },
            "performance_guard": {
                "blocked": [m for m, g in performance_guards.items() if g.get("blocked")],
                "eligible": sum(1 for s in enhanced if s.get("publication_eligible")),
            },
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
        _save_json_atomic(OUT_SIGNALS, {
            **original,
            "updated_at": _now_iso(),
            "count": 0,
            "signals": [],
            "_v6_enhanced": True,
            "_v6_stats": {
                "upgraded": 0,
                "downgraded": 0,
                "n_aplus": 0,
                "n_a": 0,
                "publication_eligible": 0,
                "performance_blocked": 0,
            },
        })
    _save_json_atomic(OUT_SIGNALS_V6, {
        "updated_at": _now_iso(),
        "model_version": MODEL_VERSION,
        "source": "compute_signals_v6",
        "count": 0,
        "summary": {
            "total": 0,
            "upgraded": 0,
            "downgraded": 0,
            "adjusted": 0,
            "unchanged": 0,
            "quality_aplus": 0,
            "quality_a": 0,
            "publication_eligible": 0,
            "performance_guard": {"blocked": [], "eligible": 0},
        },
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
