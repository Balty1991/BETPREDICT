#!/usr/bin/env python3
"""
src/adaptive_thresholds.py
==========================
BetPredict Pro v6.0 — Adaptive Strategy Thresholds

Ce face:
- Citeste data/selection_journal.json (pariuri settle-uite).
- Computeaza ROI per market, per edge bucket, per odds bucket, per strategy.
- Recomanda automat min_edge / odd_min / odd_max / min_prob per market.
- Inlocuieste valorile hardcoded din STRATEGIES (fetch_daily.py) cu praguri
  invatate din rezultate reale.

DE CE ESTE CRITIC:
Pragurile actuale din STRATEGIES sunt GHICITE, nu invatate. Datele tale arata:
- under35: +12.5% ROI / 43 pariuri  -> pastreaza praguri agresive
- over25:  +23.5% ROI / 8 pariuri   -> pastreaza praguri
- over15:  +17.2% ROI / 17 pariuri  -> pastreaza praguri
- btts:    +86% ROI / 2 pariuri     -> insuficiente date, prudent
- homeWin: -80.4% ROI / 7 pariuri   -> RIDICA dramatic pragurile
- 1 (1x2): -28.7% ROI / 8 pariuri   -> RIDICA dramatic pragurile

Strategia v5 actuala scoate prea multe pariuri pe homeWin/1X2 cu praguri mici;
v6 corecteaza automat pe baza dovezilor empirice.

Algoritm:
1. Imparte pariurile in cosuri (edge, odds, prob).
2. Calculeaza ROI per (market, bucket).
3. Gaseste pragul minim care exclude cosurile cu ROI negativ.
4. Calculeaza trust_score per market (functie de n_samples + consistenta).
5. Pentru markete cu trust ridicat -> aplica recomandarile.
6. Pentru markete cu trust scazut -> pastreaza defaults (sau prudent).
7. Markete cu ROI catastrofal si >=10 sample-uri -> blacklist sau praguri foarte stricte.

Integrare in fetch_daily.py:
    from src.adaptive_thresholds import load_thresholds, apply_to_strategies
    adaptive = load_thresholds()
    STRATEGIES = apply_to_strategies(STRATEGIES_DEFAULT, adaptive)

Output:
- data/adaptive_thresholds.json (recomandari + bucket stats pentru UI)
- data/debug/adaptive_thresholds_debug.json

Robustete:
- Daca selection_journal lipseste -> recomandari = defaults
- Erori prinse, pipeline-ul nu se sparge niciodata
"""

from __future__ import annotations
import json
import sys
import warnings
import traceback
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

# ============================================================
# CAI & CONFIGURARE
# ============================================================

ROOT_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = ROOT_DIR / "data"
DEBUG_DIR = DATA_DIR / "debug"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

SELECTION_JOURNAL = DATA_DIR / "selection_journal.json"
OUT_THRESHOLDS = DATA_DIR / "adaptive_thresholds.json"
OUT_DEBUG = DEBUG_DIR / "adaptive_thresholds_debug.json"

# Praguri minime pentru a avea incredere in date
MIN_SAMPLES_FOR_OVERRIDE = 10      # sub asta -> defaults
MIN_SAMPLES_FOR_BLACKLIST = 10     # sub asta -> NU blacklist-am
BLACKLIST_ROI_THRESHOLD = -50.0    # ROI sub asta cu n suficient -> blacklist

# Markete canonice
CANONICAL_MARKETS = [
    "homeWin", "draw", "awayWin",
    "btts", "no_btts",
    "over15", "under15",
    "over25", "under25",
    "over35", "under35",
]

# Mapare nume -> cheie canonica
MARKET_ALIASES = {
    "1": "homeWin", "homeWin": "homeWin", "home_win": "homeWin",
    "X": "draw", "draw": "draw",
    "2": "awayWin", "awayWin": "awayWin", "away_win": "awayWin",
    "btts": "btts", "btts_yes": "btts",
    "no_btts": "no_btts", "btts_no": "no_btts",
    "over15": "over15", "over_15": "over15",
    "under15": "under15", "under_15": "under15",
    "over25": "over25", "over_25": "over25",
    "under25": "under25", "under_25": "under25",
    "over35": "over35", "over_35": "over35",
    "under35": "under35", "under_35": "under35",
}

# Defaults (corespund cu STRATEGIES din fetch_daily.py)
DEFAULT_MARKET_THRESHOLDS = {
    "min_edge_pp": 5.0,
    "min_prob_pct": 66.0,
    "odd_min": 1.20,
    "odd_max": 2.00,
}

# Cosuri pentru bucket analysis
EDGE_BUCKETS = [(-100, 0), (0, 2), (2, 5), (5, 10), (10, 15), (15, 25), (25, 100)]
ODDS_BUCKETS = [(1.0, 1.2), (1.2, 1.4), (1.4, 1.6), (1.6, 2.0), (2.0, 3.0), (3.0, 100.0)]
PROB_BUCKETS = [(0, 50), (50, 60), (60, 70), (70, 80), (80, 90), (90, 100)]

MODEL_VERSION = "v6.0-adaptive"

PIPELINE_LOG: List[str] = []


def _log(msg: str) -> None:
    print(f"[adaptive] {msg}")
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
# EXTRACTIE PARIURI
# ============================================================

def extract_settled_bets(journal: Dict) -> List[Dict]:
    """
    Extrage pariurile settle-uite cu metricile necesare.
    Returneaza lista de dict: {market, strategy, prob, odds, edge_pp, ev, profit, result}
    """
    bets: List[Dict] = []
    skipped = {"not_settled": 0, "unknown_market": 0, "no_data": 0, "push_void": 0}

    for r in (journal or {}).get("results", []):
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
        odds = _safe_float(r.get("odds"), -1.0)

        if prob < 0.01 or prob > 0.99 or odds < 1.01:
            skipped["no_data"] += 1
            continue

        edge_pp = (prob - 1.0 / odds) * 100
        ev = prob * odds - 1.0
        profit = _safe_float(r.get("profit_units"), 0.0)
        strategy = r.get("strategy") or "unknown"

        bets.append({
            "market": market,
            "strategy": strategy,
            "prob_pct": prob * 100,
            "odds": odds,
            "edge_pp": edge_pp,
            "ev": ev,
            "profit_units": profit,
            "win": 1 if outcome == "WIN" else 0,
        })

    _log(f"Extrase {len(bets)} pariuri valide. Skipped: {skipped}")
    return bets


# ============================================================
# AGREGARE PE COSURI
# ============================================================

def bucketize(value: float, buckets: List[Tuple[float, float]]) -> int:
    for i, (lo, hi) in enumerate(buckets):
        if lo <= value < hi:
            return i
    return len(buckets) - 1


def aggregate_by_bucket(
    bets: List[Dict],
    dim: str,
    buckets: List[Tuple[float, float]],
) -> List[Dict]:
    """Agregare ROI / win_rate per cos pentru o dimensiune."""
    out = []
    for i, (lo, hi) in enumerate(buckets):
        bucket_bets = [b for b in bets if lo <= b[dim] < hi]
        n = len(bucket_bets)
        if n == 0:
            out.append({
                "range_lo": lo, "range_hi": hi, "n": 0,
                "wins": 0, "losses": 0,
                "win_rate_pct": None, "roi_pct": None, "avg_odds": None,
            })
            continue
        wins = sum(b["win"] for b in bucket_bets)
        losses = n - wins
        profit = sum(b["profit_units"] for b in bucket_bets)
        avg_odds = sum(b["odds"] for b in bucket_bets) / n
        out.append({
            "range_lo": lo, "range_hi": hi, "n": n,
            "wins": wins, "losses": losses,
            "win_rate_pct": round(wins / n * 100, 1),
            "roi_pct": round(profit / n * 100, 1),
            "avg_odds": round(avg_odds, 2),
        })
    return out


# ============================================================
# COMPUTE RECOMMENDATIONS PER MARKET
# ============================================================

def compute_market_stats(bets: List[Dict], market: str) -> Dict:
    """Statistici generale pentru un market."""
    market_bets = [b for b in bets if b["market"] == market]
    n = len(market_bets)
    if n == 0:
        return {"n": 0, "roi_pct": None, "win_rate_pct": None, "avg_odds": None}

    wins = sum(b["win"] for b in market_bets)
    profit = sum(b["profit_units"] for b in market_bets)
    avg_odds = sum(b["odds"] for b in market_bets) / n
    avg_prob = sum(b["prob_pct"] for b in market_bets) / n
    avg_edge = sum(b["edge_pp"] for b in market_bets) / n

    return {
        "n": n,
        "wins": wins,
        "losses": n - wins,
        "roi_pct": round(profit / n * 100, 1),
        "win_rate_pct": round(wins / n * 100, 1),
        "avg_odds": round(avg_odds, 2),
        "avg_prob_pct": round(avg_prob, 1),
        "avg_edge_pp": round(avg_edge, 1),
        "total_profit_units": round(profit, 2),
    }


def compute_trust_score(stats: Dict) -> float:
    """
    Trust score 0-1 pe baza nr de sample-uri si consistenta.
    n>=30 -> trust 0.85-1.0
    n=20-30 -> trust 0.6-0.85
    n=10-20 -> trust 0.4-0.6
    n<10 -> trust <0.4 (use defaults)
    """
    n = stats.get("n", 0)
    if n < 5:
        return 0.0
    if n >= 30:
        base = 0.85
    elif n >= 20:
        base = 0.60
    elif n >= 10:
        base = 0.40
    else:
        base = 0.20

    # Penalty pentru ROI extrem (poate fi noise)
    roi = stats.get("roi_pct", 0) or 0
    if abs(roi) > 50 and n < 20:
        base *= 0.7  # Reducem incredere in ROI extrem cu n mic

    # Bonus pentru sample-uri foarte multe
    if n >= 50:
        base = min(1.0, base + 0.10)

    return round(base, 2)


def recommend_thresholds(
    market: str,
    stats: Dict,
    edge_buckets: List[Dict],
    odds_buckets: List[Dict],
    prob_buckets: List[Dict],
    trust: float,
) -> Dict[str, Any]:
    """
    Recomanda praguri per market.

    Logica:
    - Trust scazut (<0.4) -> defaults
    - Trust mediu -> ajustari mici
    - Trust ridicat -> recomandari complete pe baza datelor
    - ROI catastrofal (<-50% cu n>=10) -> blacklist sau praguri foarte stricte
    """
    if trust < 0.4 or stats["n"] < MIN_SAMPLES_FOR_OVERRIDE:
        return {
            **DEFAULT_MARKET_THRESHOLDS,
            "verdict": "DEFAULT — date insuficiente",
            "use_defaults": True,
            "blacklisted": False,
        }

    roi = stats["roi_pct"] or 0
    n = stats["n"]

    # Verdict pe baza ROI
    if roi < BLACKLIST_ROI_THRESHOLD and n >= MIN_SAMPLES_FOR_BLACKLIST:
        verdict = "BLACKLIST — pierderi sistemice grave"
        blacklisted = True
    elif roi < -15:
        verdict = "EVITA — doar consensuri foarte tari"
        blacklisted = False
    elif roi < 0:
        verdict = "PRUDENT — pragul minim ridicat"
        blacklisted = False
    elif roi < 5:
        verdict = "NEUTRU — praguri standard"
        blacklisted = False
    elif roi < 15:
        verdict = "FAVORIT — pragul minim redus"
        blacklisted = False
    else:
        verdict = "STAR — pragul minim agresiv"
        blacklisted = False

    # Calcul min_edge: cel mai mic bucket cu ROI > 0
    min_edge_pp = DEFAULT_MARKET_THRESHOLDS["min_edge_pp"]
    profitable_edge_buckets = [
        b for b in edge_buckets
        if b["roi_pct"] is not None and b["roi_pct"] > 0 and b["n"] >= 3
    ]
    if profitable_edge_buckets:
        min_edge_pp = min(b["range_lo"] for b in profitable_edge_buckets)
        # Pentru markete cu ROI negativ global, ridicam pragul
        if roi < 0:
            # Doar cosuri cu ROI > 10% si n>=3
            strict_buckets = [
                b for b in profitable_edge_buckets
                if b["roi_pct"] > 10 and b["n"] >= 3
            ]
            if strict_buckets:
                min_edge_pp = min(b["range_lo"] for b in strict_buckets)
            else:
                # Pune un prag foarte mare daca nu gasim nimic profitabil
                min_edge_pp = max(min_edge_pp, 20.0)

    # Calcul odds range: bucket-urile cu ROI > 0
    profitable_odds_buckets = [
        b for b in odds_buckets
        if b["roi_pct"] is not None and b["roi_pct"] > 0 and b["n"] >= 3
    ]
    if profitable_odds_buckets:
        odd_min = min(b["range_lo"] for b in profitable_odds_buckets)
        odd_max = max(b["range_hi"] for b in profitable_odds_buckets)
        odd_max = min(odd_max, 5.0)  # cap rezonabil
    else:
        odd_min = DEFAULT_MARKET_THRESHOLDS["odd_min"]
        odd_max = DEFAULT_MARKET_THRESHOLDS["odd_max"]

    # Calcul min_prob: cel mai mic bucket cu ROI > 0
    min_prob_pct = DEFAULT_MARKET_THRESHOLDS["min_prob_pct"]
    profitable_prob_buckets = [
        b for b in prob_buckets
        if b["roi_pct"] is not None and b["roi_pct"] > 0 and b["n"] >= 3
    ]
    if profitable_prob_buckets:
        min_prob_pct = min(b["range_lo"] for b in profitable_prob_buckets)
        if roi < 0:
            # Ridica pragul pentru markete cu pierderi
            strict = [b for b in profitable_prob_buckets
                      if b["roi_pct"] > 10 and b["n"] >= 3]
            if strict:
                min_prob_pct = min(b["range_lo"] for b in strict)
            else:
                min_prob_pct = max(min_prob_pct, 80.0)

    return {
        "min_edge_pp": round(min_edge_pp, 1),
        "min_prob_pct": round(min_prob_pct, 1),
        "odd_min": round(odd_min, 2),
        "odd_max": round(odd_max, 2),
        "verdict": verdict,
        "use_defaults": False,
        "blacklisted": blacklisted,
        "rationale": (
            f"ROI={roi:+.1f}% pe {n} pariuri; trust={trust:.2f}. "
            f"Cosuri edge profitabile: {len(profitable_edge_buckets)}; "
            f"cosuri odds profitabile: {len(profitable_odds_buckets)}."
        ),
    }


# ============================================================
# API PUBLIC (importabil din fetch_daily.py)
# ============================================================

def load_thresholds() -> Dict[str, Any]:
    """Incarca thresholds salvate. Returneaza dict gol daca lipseste."""
    return _load_json(OUT_THRESHOLDS, {}) or {}


def get_market_threshold(market: str, key: str,
                         default: Optional[float] = None,
                         thresholds: Optional[Dict] = None) -> Optional[float]:
    """
    Returneaza un threshold specific (min_edge_pp, min_prob_pct, odd_min, odd_max).
    Foloseste default daca nu exista.
    """
    if thresholds is None:
        thresholds = load_thresholds()
    market_canonical = normalize_market(market)
    if not market_canonical:
        return default
    market_data = (thresholds.get("by_market") or {}).get(market_canonical)
    if not market_data:
        return default
    rec = market_data.get("recommended", {})
    return rec.get(key, default)


def is_market_blacklisted(market: str, thresholds: Optional[Dict] = None) -> bool:
    """Verifica daca un market e blacklist-at de adaptive engine."""
    if thresholds is None:
        thresholds = load_thresholds()
    market_canonical = normalize_market(market)
    if not market_canonical:
        return False
    market_data = (thresholds.get("by_market") or {}).get(market_canonical)
    if not market_data:
        return False
    return bool(market_data.get("recommended", {}).get("blacklisted", False))


def apply_to_strategies(
    default_strategies: Dict[str, Dict],
    thresholds: Optional[Dict] = None,
) -> Dict[str, Dict]:
    """
    Aplica recomandarile adaptive pe configurarea STRATEGIES din fetch_daily.py.

    Logica:
    - Pentru fiecare market intr-o strategie, foloseste pragurile recomandate
      (filtrate prin maximum cu pragurile strategiei pentru a nu permite
      strategii "conservative" sa devina mai laxe decat trebuie).
    - Markete blacklisted sunt eliminate din lista de markets a strategiei.

    Returneaza un nou dict, nu modifica intrarea.
    """
    if thresholds is None:
        thresholds = load_thresholds()

    by_market = thresholds.get("by_market") or {}
    if not by_market:
        return default_strategies  # Nimic de aplicat

    out: Dict[str, Dict] = {}
    for strat_name, strat_config in default_strategies.items():
        new_config = dict(strat_config)

        # Filtreaza markets blacklisted
        original_markets = strat_config.get("markets", [])
        new_markets = []
        for m in original_markets:
            m_canonical = normalize_market(m) or m
            market_data = by_market.get(m_canonical, {})
            rec = market_data.get("recommended", {})
            if rec.get("blacklisted"):
                continue
            new_markets.append(m)
        new_config["markets"] = new_markets

        # Calculeaza pragurile cele mai stricte din markete + defaults strategiei
        per_market_thresholds = []
        for m in new_markets:
            m_canonical = normalize_market(m) or m
            market_data = by_market.get(m_canonical, {})
            rec = market_data.get("recommended", {})
            if rec and not rec.get("use_defaults"):
                per_market_thresholds.append(rec)

        if per_market_thresholds:
            # Pentru o strategie, folosim MAX(default, MIN_recomandat_per_market)
            # ca sa nu lasam o strategie conservatoare sa devina lax
            min_edge_recommended = min(
                t["min_edge_pp"] for t in per_market_thresholds
            )
            min_prob_recommended = min(
                t["min_prob_pct"] for t in per_market_thresholds
            )
            # Folosim max pentru a pastra rigorile strategiei
            new_config["min_edge"] = max(
                new_config.get("min_edge", 5.0),
                min_edge_recommended
            )
            new_config["min_adj"] = max(
                new_config.get("min_adj", 66.0),
                min_prob_recommended
            )

        new_config["_adaptive_applied"] = True
        out[strat_name] = new_config

    return out


# ============================================================
# MAIN PIPELINE
# ============================================================

def main() -> int:
    started = _now_iso()
    _log(f"=== Adaptive Thresholds Engine v6.0 — {started} ===")

    journal = _load_json(SELECTION_JOURNAL, {})
    if not journal:
        _log("selection_journal.json lipseste -> output gol cu defaults")
        _save_empty("no_journal")
        return 0

    bets = extract_settled_bets(journal)
    if not bets:
        _log("Niciun pariu settle-uit valid -> defaults")
        _save_empty("no_valid_bets")
        return 0

    # Statistici per market
    by_market: Dict[str, Any] = {}
    markets_seen = set(b["market"] for b in bets)

    for market in markets_seen:
        market_bets = [b for b in bets if b["market"] == market]
        stats = compute_market_stats(bets, market)
        trust = compute_trust_score(stats)

        edge_buckets = aggregate_by_bucket(market_bets, "edge_pp", EDGE_BUCKETS)
        odds_buckets = aggregate_by_bucket(market_bets, "odds", ODDS_BUCKETS)
        prob_buckets = aggregate_by_bucket(market_bets, "prob_pct", PROB_BUCKETS)

        recommended = recommend_thresholds(
            market, stats, edge_buckets, odds_buckets, prob_buckets, trust
        )

        by_market[market] = {
            "stats": stats,
            "trust_score": trust,
            "recommended": recommended,
            "edge_buckets": edge_buckets,
            "odds_buckets": odds_buckets,
            "prob_buckets": prob_buckets,
        }

        roi = stats["roi_pct"] or 0
        ble = "BL" if recommended["blacklisted"] else ""
        _log(f"  {market:10s} | n={stats['n']:3d} ROI={roi:+6.1f}% trust={trust:.2f} "
             f"-> min_edge={recommended['min_edge_pp']:5.1f}pp min_prob="
             f"{recommended['min_prob_pct']:5.1f}% odds={recommended['odd_min']:.2f}-"
             f"{recommended['odd_max']:.2f} {ble}")

    # Stats per strategie (din journal)
    by_strategy: Dict[str, Any] = {}
    strategies_seen = set(b["strategy"] for b in bets if b["strategy"] != "unknown")
    for strat in strategies_seen:
        strat_bets = [b for b in bets if b["strategy"] == strat]
        n = len(strat_bets)
        if n == 0:
            continue
        wins = sum(b["win"] for b in strat_bets)
        profit = sum(b["profit_units"] for b in strat_bets)
        by_strategy[strat] = {
            "n": n,
            "wins": wins,
            "losses": n - wins,
            "win_rate_pct": round(wins / n * 100, 1),
            "roi_pct": round(profit / n * 100, 1),
            "total_profit_units": round(profit, 2),
        }

    # Overall
    n_total = len(bets)
    overall_profit = sum(b["profit_units"] for b in bets)
    overall_wins = sum(b["win"] for b in bets)
    sorted_markets = sorted(by_market.items(), key=lambda kv: kv[1]["stats"]["roi_pct"] or 0)
    blacklisted = [m for m, d in by_market.items() if d["recommended"]["blacklisted"]]

    overall = {
        "n_total_settled": n_total,
        "overall_roi_pct": round(overall_profit / n_total * 100, 1),
        "overall_win_rate_pct": round(overall_wins / n_total * 100, 1),
        "total_profit_units": round(overall_profit, 2),
        "best_market": sorted_markets[-1][0] if sorted_markets else None,
        "best_market_roi": sorted_markets[-1][1]["stats"]["roi_pct"] if sorted_markets else None,
        "worst_market": sorted_markets[0][0] if sorted_markets else None,
        "worst_market_roi": sorted_markets[0][1]["stats"]["roi_pct"] if sorted_markets else None,
        "blacklisted_markets": blacklisted,
        "markets_with_overrides": sum(
            1 for d in by_market.values() if not d["recommended"]["use_defaults"]
        ),
    }

    # Save
    output = {
        "updated_at": _now_iso(),
        "model_version": MODEL_VERSION,
        "source": "adaptive_thresholds_v6",
        "overall": overall,
        "by_market": by_market,
        "by_strategy": by_strategy,
        "default_market_thresholds": DEFAULT_MARKET_THRESHOLDS,
        "_pipeline_version": "v6.0-adaptive",
    }
    _save_json_atomic(OUT_THRESHOLDS, output)
    _log("OK: adaptive_thresholds.json scris")
    _log(f"Overall ROI: {overall['overall_roi_pct']:+.1f}% pe {n_total} pariuri")
    if blacklisted:
        _log(f"Blacklist: {blacklisted}")

    _save_json_atomic(OUT_DEBUG, {
        "status": "ok",
        "started_at": started,
        "ended_at": _now_iso(),
        "overall": overall,
        "log": PIPELINE_LOG[-50:],
    })

    return 0


def _save_empty(reason: str) -> None:
    _save_json_atomic(OUT_THRESHOLDS, {
        "updated_at": _now_iso(),
        "model_version": MODEL_VERSION,
        "source": "adaptive_thresholds_v6",
        "overall": {},
        "by_market": {},
        "by_strategy": {},
        "default_market_thresholds": DEFAULT_MARKET_THRESHOLDS,
        "reason": reason,
        "_pipeline_version": "v6.0-adaptive",
    })


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"[adaptive] CRASH: {e}")
        traceback.print_exc()
        try:
            _save_empty(f"crash: {e}")
        except Exception:
            pass
        sys.exit(0)
