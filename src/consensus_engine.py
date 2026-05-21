#!/usr/bin/env python3
"""
src/consensus_engine.py
=======================
BetPredict Pro v6.0 — 3-Way Consensus Engine

Ce face:
- Compara predictiile din 3 surse diferite per meci per market:
    1. BSD API (predictions.json: blended_home/draw/away + poisson_*)
    2. ML Ensemble (ml_predictions.json: ml_probabilities)
    3. Re-calcul Poisson standalone (din xg_context.json)
- Calculeaza un "consensus score" per market:
    agreement = max(0, 1 - 2 * std([p1, p2, p3]))
    Cand toate 3 sunt de acord -> agreement aproape 1.0
    Cand diverge mult -> agreement < 0.5
- Clasifica in tiers: TOTAL / PARTIAL / DIVERGENT / CONTRADICTORIU
- Genereaza un "consens_prob" (media probabilitatilor) care e mai robust
  decat oricare sursa individuala (ensemble effect).

PUTERE DIFERENTIATOARE vs VEYRA:
VEYRA are un singur model. Consensul 3-way este semnalul CEL MAI FIABIL:
- Daca BSD spune 75% si ML spune 74% si Poisson spune 73% -> BET.
- Daca BSD spune 85% si ML spune 45% -> WARNING. Nu paria pe overconfidence.

Output:
- data/consensus.json
- data/debug/consensus_debug.json
"""

from __future__ import annotations
import json
import math
import sys
import warnings
import traceback
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

warnings.filterwarnings("ignore")

# ============================================================
# CAI & CONFIGURARE
# ============================================================

ROOT_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = ROOT_DIR / "data"
DEBUG_DIR = DATA_DIR / "debug"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

PREDICTIONS_JSON = DATA_DIR / "predictions.json"
ML_PREDICTIONS = DATA_DIR / "ml_predictions.json"
XG_CONTEXT = DATA_DIR / "xg_context.json"
OUT_CONSENSUS = DATA_DIR / "consensus.json"
OUT_DEBUG = DEBUG_DIR / "consensus_debug.json"

# Tiers de consens
TIER_TOTAL = "TOTAL"          # agreement >= 0.85  (verzi)
TIER_PARTIAL = "PARTIAL"      # agreement >= 0.60  (albastru)
TIER_DIVERGENT = "DIVERGENT"  # agreement >= 0.35  (portocaliu)
TIER_CONTRA = "CONTRADICTORIU"  # < 0.35            (rosu)

TIER_THRESHOLDS = [
    (0.85, TIER_TOTAL),
    (0.60, TIER_PARTIAL),
    (0.35, TIER_DIVERGENT),
    (0.0, TIER_CONTRA),
]

# Markete pentru care calculam consensul
MARKETS = ["homeWin", "draw", "awayWin", "btts", "over15", "over25", "under35"]

MODEL_VERSION = "v6.0-consensus"

PIPELINE_LOG: List[str] = []


def _log(msg: str) -> None:
    print(f"[consensus] {msg}")
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


# ============================================================
# POISSON STANDALONE (sursa 3)
# ============================================================

def _poisson_pmf(lam: float, k: int) -> float:
    if lam <= 0:
        return 0.0
    try:
        return math.exp(-lam) * (lam ** k) / math.factorial(k)
    except (OverflowError, ValueError):
        return 0.0


def poisson_probs(xg_home: float, xg_away: float, max_g: int = 7) -> Dict[str, float]:
    """Calcul Poisson + Dixon-Coles (rho=-0.08) pentru un set de xG."""
    lh = max(0.1, min(6.0, float(xg_home)))
    la = max(0.1, min(6.0, float(xg_away)))
    rho = -0.08

    matrix: List[List[float]] = []
    total = 0.0
    for h in range(max_g + 1):
        row = []
        for a in range(max_g + 1):
            p = _poisson_pmf(lh, h) * _poisson_pmf(la, a)
            # Dixon-Coles correction
            if h == 0 and a == 0:
                p *= max(0.01, 1 - lh * la * rho)
            elif h == 0 and a == 1:
                p *= max(0.01, 1 + lh * rho)
            elif h == 1 and a == 0:
                p *= max(0.01, 1 + la * rho)
            elif h == 1 and a == 1:
                p *= max(0.01, 1 - rho)
            row.append(p)
            total += p
        matrix.append(row)

    if total <= 0:
        return {m: 0.5 for m in MARKETS}

    matrix = [[p / total for p in row] for row in matrix]

    home = draw = away = btts = o15 = o25 = u35 = 0.0
    for h, row in enumerate(matrix):
        for a, p in enumerate(row):
            if h > a:
                home += p
            elif h == a:
                draw += p
            else:
                away += p
            if h > 0 and a > 0:
                btts += p
            if h + a > 1.5:
                o15 += p
            if h + a > 2.5:
                o25 += p
            if h + a < 3.5:
                u35 += p

    return {
        "homeWin": home,
        "draw": draw,
        "awayWin": away,
        "btts": btts,
        "over15": o15,
        "over25": o25,
        "under35": u35,
    }


# ============================================================
# INDEX-URI
# ============================================================

def build_bsd_index(predictions: Dict) -> Dict[int, Dict[str, float]]:
    """
    Extrage probabilitatile BSD+Poisson blended din predictions.json.
    Cheie: event_id
    """
    idx: Dict[int, Dict[str, float]] = {}
    for p in (predictions or {}).get("results", []):
        ev = p.get("event") or {}
        eid_raw = ev.get("id")
        if eid_raw is None:
            continue
        try:
            eid = int(eid_raw)
        except (TypeError, ValueError):
            continue

        # Prioritate: blended > BSD raw > markets
        markets_obj = p.get("markets") or {}
        mr = markets_obj.get("match_result") or {}
        s = 100 if (mr.get("prob_home", 0) or 0) > 1 else 1

        ph = _safe_float(p.get("blended_home") or p.get("home_win_probability") or mr.get("prob_home") and (mr["prob_home"] / s))
        pd = _safe_float(p.get("blended_draw") or p.get("draw_probability") or mr.get("prob_draw") and (mr.get("prob_draw") / s))
        pa = _safe_float(p.get("blended_away") or p.get("away_win_probability") or mr.get("prob_away") and (mr.get("prob_away") / s))

        ou = markets_obj.get("over_under") or {}
        ou_s = 100 if (ou.get("prob_over_25", 0) or 0) > 1 else 1

        o15 = _safe_float(p.get("poisson_over15") or p.get("over_15_probability") or ou.get("prob_over_15") and (ou["prob_over_15"] / ou_s))
        o25 = _safe_float(p.get("poisson_over25") or p.get("over_25_probability") or ou.get("prob_over_25") and (ou.get("prob_over_25") / ou_s))
        btts_v = _safe_float(p.get("poisson_btts") or p.get("btts_probability"))
        u35_raw = _safe_float(p.get("poisson_under35") or p.get("under_35_probability"))

        # Fallback u35 din over35
        if u35_raw < 0 and o25 >= 0:
            o35_raw = _safe_float(p.get("poisson_over35") or p.get("over_35_probability"))
            if o35_raw >= 0:
                u35_raw = 1.0 - o35_raw

        idx[eid] = {
            "homeWin": ph if ph >= 0 else -1,
            "draw": pd if pd >= 0 else -1,
            "awayWin": pa if pa >= 0 else -1,
            "btts": btts_v,
            "over15": o15,
            "over25": o25,
            "under35": u35_raw,
        }
    return idx


def build_ml_index(ml_data: Dict) -> Dict[int, Dict[str, float]]:
    """
    Extrage probabilitatile ML din ml_predictions.json.
    Cheie: event_id
    """
    idx: Dict[int, Dict[str, float]] = {}
    for r in (ml_data or {}).get("results", []):
        eid_raw = r.get("event_id")
        if eid_raw is None:
            continue
        try:
            eid = int(eid_raw)
        except (TypeError, ValueError):
            continue
        probs = r.get("ml_probabilities") or {}
        idx[eid] = {m: _safe_float(probs.get(m)) for m in MARKETS}
    return idx


def build_xg_index(xg_data: Dict) -> Dict[int, Tuple[float, float]]:
    """
    Extrage xG home/away pentru re-calcul Poisson standalone.
    Cheie: event_id
    """
    idx: Dict[int, Tuple[float, float]] = {}
    for r in (xg_data or {}).get("results", []):
        eid_raw = r.get("event_id")
        if eid_raw is None:
            continue
        try:
            eid = int(eid_raw)
        except (TypeError, ValueError):
            continue
        xgh = _safe_float(r.get("xg_home"), -1)
        xga = _safe_float(r.get("xg_away"), -1)
        if xgh > 0 and xga > 0:
            idx[eid] = (xgh, xga)
    return idx


# ============================================================
# CALCUL CONSENS PER MECI
# ============================================================

def agreement_score(probs: List[float]) -> float:
    """
    Masura de acord intre estimatii multiple.
    agreement = max(0, 1 - 2 * std(probs))
    1.0 = consens perfect, 0.0 = divergenta maxima.
    """
    n = len(probs)
    if n < 2:
        return 1.0
    mean = sum(probs) / n
    variance = sum((p - mean) ** 2 for p in probs) / n
    std = math.sqrt(variance)
    return max(0.0, 1.0 - 2.0 * std)


def tier_from_agreement(ag: float) -> str:
    for threshold, tier in TIER_THRESHOLDS:
        if ag >= threshold:
            return tier
    return TIER_CONTRA


def consensus_for_match(
    eid: int,
    bsd_idx: Dict,
    ml_idx: Dict,
    xg_idx: Dict,
) -> Dict[str, Any]:
    """Calculeaza consensul per market pentru un meci."""
    bsd = bsd_idx.get(eid, {})
    ml = ml_idx.get(eid, {})
    xg = xg_idx.get(eid)

    # Poisson standalone daca avem xG
    poisson = {}
    if xg:
        try:
            poisson = poisson_probs(xg[0], xg[1])
        except Exception:
            pass

    markets_out: Dict[str, Any] = {}
    market_agreements: List[float] = []

    for market in MARKETS:
        sources: Dict[str, float] = {}

        p_bsd = bsd.get(market, -1.0)
        if p_bsd >= 0.01:
            sources["bsd"] = _clip(p_bsd)

        p_ml = ml.get(market, -1.0)
        if p_ml >= 0.01:
            sources["ml"] = _clip(p_ml)

        p_poi = poisson.get(market, -1.0)
        if p_poi >= 0.01:
            sources["poisson"] = _clip(p_poi)

        valid_probs = list(sources.values())
        if not valid_probs:
            continue

        mean_prob = sum(valid_probs) / len(valid_probs)
        ag = agreement_score(valid_probs) if len(valid_probs) >= 2 else 1.0
        tier = tier_from_agreement(ag)

        market_agreements.append(ag)

        markets_out[market] = {
            **{f"p_{k}": round(v, 4) for k, v in sources.items()},
            "consensus_prob": round(mean_prob, 4),
            "n_sources": len(valid_probs),
            "agreement": round(ag, 3),
            "tier": tier,
        }

    # Best consensus market (mai mare agreement + prob > 50%)
    best_market = None
    best_ag = -1.0
    for m, d in markets_out.items():
        if d["agreement"] > best_ag and d["consensus_prob"] > 0.55:
            best_ag = d["agreement"]
            best_market = m

    # Overall consensus score pentru meci
    overall_ag = (
        sum(market_agreements) / len(market_agreements)
        if market_agreements else 0.0
    )

    return {
        "markets": markets_out,
        "best_consensus_market": best_market,
        "best_consensus_agreement": round(best_ag, 3),
        "overall_match_consensus": round(overall_ag, 3),
        "n_markets_computed": len(markets_out),
        "has_poisson": bool(poisson),
        "has_ml": bool(ml),
        "has_bsd": bool(bsd),
    }


# ============================================================
# MAIN
# ============================================================

def main() -> int:
    started = _now_iso()
    _log(f"=== Consensus Engine v6.0 — {started} ===")

    predictions = _load_json(PREDICTIONS_JSON, {})
    ml_data = _load_json(ML_PREDICTIONS, {})
    xg_data = _load_json(XG_CONTEXT, {})

    preds_list = (predictions or {}).get("results", [])
    _log(f"BSD predictions: {len(preds_list)}")
    _log(f"ML predictions: {len((ml_data or {}).get('results', []))}")
    _log(f"xG entries: {len((xg_data or {}).get('results', []))}")

    if not preds_list:
        _log("Nu exista predictions.json cu date -> output gol")
        _save_empty("no_predictions")
        return 0

    bsd_idx = build_bsd_index(predictions)
    ml_idx = build_ml_index(ml_data)
    xg_idx = build_xg_index(xg_data)
    _log(f"Indecsi: bsd={len(bsd_idx)} ml={len(ml_idx)} xg={len(xg_idx)}")

    results: List[Dict] = []
    stats = {
        TIER_TOTAL: 0, TIER_PARTIAL: 0, TIER_DIVERGENT: 0, TIER_CONTRA: 0
    }

    for p in preds_list:
        ev = p.get("event") or {}
        eid_raw = ev.get("id")
        if eid_raw is None:
            continue
        try:
            eid = int(eid_raw)
        except (TypeError, ValueError):
            continue

        cons = consensus_for_match(eid, bsd_idx, ml_idx, xg_idx)

        # Conteaza cel mai bun market
        best_tier = tier_from_agreement(cons["best_consensus_agreement"])
        stats[best_tier] = stats.get(best_tier, 0) + 1

        results.append({
            "event_id": eid,
            "home_team": ev.get("home_team", "?"),
            "away_team": ev.get("away_team", "?"),
            "league": p.get("_league_name") or ev.get("league_name", "?"),
            "event_date": ev.get("event_date"),
            **cons,
        })

    # Sortare: overall_match_consensus descrescator
    results.sort(key=lambda r: r["overall_match_consensus"], reverse=True)

    # Sample stats
    tier_distribution = {
        "total": stats.get(TIER_TOTAL, 0),
        "partial": stats.get(TIER_PARTIAL, 0),
        "divergent": stats.get(TIER_DIVERGENT, 0),
        "contradictoriu": stats.get(TIER_CONTRA, 0),
    }
    total_matches = len(results)
    avg_consensus = (
        sum(r["overall_match_consensus"] for r in results) / total_matches
        if total_matches else 0
    )

    # Meciuri cu consens total per market
    total_consensus_by_market: Dict[str, int] = {m: 0 for m in MARKETS}
    for r in results:
        for m, d in r.get("markets", {}).items():
            if d.get("tier") == TIER_TOTAL:
                total_consensus_by_market[m] = total_consensus_by_market.get(m, 0) + 1

    output = {
        "updated_at": _now_iso(),
        "model_version": MODEL_VERSION,
        "source": "consensus_engine_v6",
        "n_matches": total_matches,
        "summary": {
            "avg_consensus_score": round(avg_consensus, 3),
            "tier_distribution": tier_distribution,
            "total_consensus_per_market": total_consensus_by_market,
        },
        "results": results,
        "_pipeline_version": "v6.0-consensus",
    }
    _save_json_atomic(OUT_CONSENSUS, output)
    _log(f"OK: consensus.json scris ({total_matches} meciuri)")
    _log(f"Tier distribution: {tier_distribution}")
    _log(f"Avg consensus score: {avg_consensus:.3f}")

    _save_json_atomic(OUT_DEBUG, {
        "status": "ok",
        "started_at": started,
        "ended_at": _now_iso(),
        "n_matches": total_matches,
        "summary": output["summary"],
        "log": PIPELINE_LOG[-30:],
    })

    return 0


def _save_empty(reason: str) -> None:
    _save_json_atomic(OUT_CONSENSUS, {
        "updated_at": _now_iso(),
        "model_version": MODEL_VERSION,
        "source": "consensus_engine_v6",
        "n_matches": 0,
        "summary": {},
        "results": [],
        "reason": reason,
        "_pipeline_version": "v6.0-consensus",
    })


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"[consensus] CRASH: {e}")
        traceback.print_exc()
        try:
            _save_empty(f"crash: {e}")
        except Exception:
            pass
        sys.exit(0)
