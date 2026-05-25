"""Pattern Memory — Pilon 7 (inspirat din VEYRA).

Descoperă pattern-uri istorice câștigătoare/pierzătoare din selection_journal
și produce modificatori ±30 pe smartbet_score pentru semnalele actuale.

Filozofie: ML pur poate rata reguli simple (ex. "under 3.5G în Eliteserien la
cotă 1.20–1.30 = 90% WR"). Pattern Memory caută astfel de reguli în istoric,
le validează statistic (min support 20, p-value < 0.05 față de baseline) și
aplică boost/penalty proporțional cu mărimea efectului.

Output:
- data/pattern_memory.json   (patterns descoperite + meta)
- pattern_boost in data/signals.json (per signal: int ∈ [-30, +30])

Rulează după compute_signals_v6 și înainte de pyramid_assistant.
"""
from __future__ import annotations
import json, math, statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# ── Parametri ────────────────────────────────────────────────────────────────
MIN_SUPPORT       = 15     # min cazuri în pattern (settled) — pragul VEYRA era 20
MIN_LIFT_PP       = 8      # diferența vs baseline win rate, în puncte procentuale
MIN_PVALUE_GATE   = 0.05   # binomial test (one-sided) sub care declarăm semnificativ
ODDS_BUCKETS      = [(1.0, 1.20), (1.20, 1.40), (1.40, 1.65), (1.65, 1.95),
                     (1.95, 2.40), (2.40, 3.00), (3.00, 5.00), (5.00, 999.0)]
MAX_PATTERNS      = 80     # cap pe câte salvăm

# ── Utils ────────────────────────────────────────────────────────────────────
def _load(p: Path, default):
    try: return json.loads(p.read_text("utf-8"))
    except Exception: return default

def _save(p: Path, payload: Any):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), "utf-8")

def odds_bucket_label(o: float) -> Optional[str]:
    for lo, hi in ODDS_BUCKETS:
        if lo <= o < hi:
            return f"{lo:.2f}-{hi:.2f}"
    return None

def _as_float(v, d=None):
    try:
        if v is None or v == "": return d
        return float(v)
    except Exception:
        return d

def _binom_p_value(k: int, n: int, p: float) -> float:
    """One-sided binomial test: P(X ≥ k | n, p). Implementare simplă fără scipy."""
    if n <= 0: return 1.0
    if k > n: return 0.0
    if p <= 0: return 0.0
    if p >= 1: return 1.0
    # Folosim aproximarea normală pentru n*p*(1-p) >= 10, altfel suma exactă (small n).
    if n * p * (1 - p) >= 10:
        mu = n * p
        sd = math.sqrt(n * p * (1 - p))
        z = (k - 0.5 - mu) / sd  # continuity correction
        # P(Z ≥ z) ≈ 0.5 * erfc(z/√2)
        return 0.5 * math.erfc(z / math.sqrt(2))
    # Exact (factorial)
    from math import comb
    return sum(comb(n, i) * (p ** i) * ((1 - p) ** (n - i)) for i in range(k, n + 1))

# ── Core ─────────────────────────────────────────────────────────────────────
def _enrich(r: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extrage trăsăturile relevante dintr-un rând journal."""
    result = str(r.get("result", "")).upper()
    if result not in ("WIN", "LOSS", "LOST"): return None
    league = str(r.get("league") or r.get("league_name") or "").strip()
    market = str(r.get("market_canonical") or r.get("market") or "").strip()
    if not (league and market): return None
    odds = _as_float(r.get("odds")) or _as_float(r.get("odds_taken"))
    if odds is None: return None
    bucket = odds_bucket_label(odds)
    if bucket is None: return None
    ed = r.get("event_date") or ""
    try:
        dt = datetime.fromisoformat(str(ed).replace("Z", "+00:00")) if ed else None
        dow = dt.strftime("%a") if dt else None  # Mon, Tue, ...
    except Exception:
        dow = None
    return {
        "win":    1 if result == "WIN" else 0,
        "league": league,
        "market": market,
        "bucket": bucket,
        "dow":    dow,
    }

def _discover(rows: List[Dict[str, Any]], baseline: float) -> List[Dict[str, Any]]:
    """Generare candidați la pattern-uri prin grupare pe combinații de chei."""
    if not rows: return []
    keysets = [
        ("league", "market"),
        ("league", "market", "bucket"),
        ("market", "bucket"),
        ("league", "bucket"),
        ("market", "dow"),
    ]
    patterns: Dict[Tuple, Dict[str, Any]] = {}
    for keys in keysets:
        bucket_map: Dict[Tuple, List[int]] = {}
        for r in rows:
            key = tuple(r.get(k) or "_" for k in keys)
            if any(v == "_" for v in key): continue
            bucket_map.setdefault(key, []).append(r["win"])
        for key, wins in bucket_map.items():
            n = len(wins)
            if n < MIN_SUPPORT: continue
            wr = sum(wins) / n
            lift_pp = (wr - baseline) * 100
            if abs(lift_pp) < MIN_LIFT_PP: continue
            # binomial test în direcția corectă
            k = sum(wins) if wr > baseline else (n - sum(wins))
            p_alt = baseline if wr > baseline else (1 - baseline)
            pval = _binom_p_value(k, n, p_alt)
            if pval > MIN_PVALUE_GATE: continue
            # Modificator pe smartbet_score: linear pe lift, cap ±30.
            modifier = int(round(max(-30, min(30, lift_pp * 1.2))))
            pattern_id = "|".join(f"{k}={v}" for k, v in zip(keys, key))
            patterns[(keys, key)] = {
                "id": pattern_id,
                "keys": list(keys),
                "values": list(key),
                "support": n,
                "win_rate": round(wr * 100, 1),
                "baseline_wr": round(baseline * 100, 1),
                "lift_pp": round(lift_pp, 1),
                "p_value": round(pval, 4),
                "modifier": modifier,
                "direction": "boost" if modifier > 0 else "block",
            }
    # Sortează după mărimea efectului absolut · √support (efect + încredere)
    return sorted(patterns.values(), key=lambda p: abs(p["lift_pp"]) * math.sqrt(p["support"]),
                  reverse=True)[:MAX_PATTERNS]

def _match_signal(sig: Dict[str, Any], patterns: List[Dict[str, Any]]) -> Tuple[int, List[str]]:
    """Caută toate pattern-urile care match-uiesc semnalul. Returnează (modifier_sum_capat, motive)."""
    league = str(sig.get("league") or "")
    market = str(sig.get("market") or "")
    odds = _as_float(sig.get("odds"))
    bucket = odds_bucket_label(odds) if odds is not None else None
    ed = sig.get("event_date") or ""
    try:
        dt = datetime.fromisoformat(str(ed).replace("Z", "+00:00")) if ed else None
        dow = dt.strftime("%a") if dt else None
    except Exception:
        dow = None
    feat = {"league": league, "market": market, "bucket": bucket, "dow": dow}

    total_mod = 0
    reasons: List[str] = []
    for p in patterns:
        ok = True
        for k, v in zip(p["keys"], p["values"]):
            if feat.get(k) != v: ok = False; break
        if not ok: continue
        total_mod += p["modifier"]
        sign = "+" if p["modifier"] > 0 else ""
        reasons.append(f"{p['id']} → {sign}{p['modifier']} (WR {p['win_rate']}% vs {p['baseline_wr']}%, n={p['support']})")
    total_mod = max(-30, min(30, total_mod))  # cap final
    return total_mod, reasons

def main():
    print("[pattern_memory] start")
    journal = _load(DATA / "selection_journal.json", {}).get("results", [])
    rows = [x for x in (_enrich(r) for r in journal) if x]
    n = len(rows)
    if n < MIN_SUPPORT:
        print(f"[pattern_memory] sample insuficient ({n} < {MIN_SUPPORT}), skip")
        _save(DATA / "pattern_memory.json",
              {"updated_at": datetime.now(timezone.utc).isoformat(),
               "source": "pattern_memory.py", "n_journal": n,
               "baseline_wr": None, "patterns": [], "note": "sample insuficient"})
        return
    baseline = sum(r["win"] for r in rows) / n
    patterns = _discover(rows, baseline)

    # Aplică boost pe signals.json (in-place)
    sp = _load(DATA / "signals.json", {"signals": []})
    sigs = sp.get("signals", [])
    applied = 0
    for s in sigs:
        if not isinstance(s, dict): continue
        mod, reasons = _match_signal(s, patterns)
        if mod != 0:
            s["pattern_boost"] = mod
            s["pattern_reasons"] = reasons
            # propagăm în display_score (cap [0, 100])
            base = _as_float(s.get("display_score")) or _as_float(s.get("smartbet_score_v6")) or 0
            new_score = max(0, min(100, base + mod))
            s["display_score"] = round(new_score, 1)
            applied += 1

    _save(DATA / "signals.json", sp)
    _save(DATA / "pattern_memory.json", {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "pattern_memory.py",
        "n_journal": n,
        "baseline_wr": round(baseline * 100, 2),
        "params": {
            "min_support": MIN_SUPPORT, "min_lift_pp": MIN_LIFT_PP,
            "min_pvalue": MIN_PVALUE_GATE, "odds_buckets": ODDS_BUCKETS,
        },
        "summary": {
            "n_patterns": len(patterns),
            "n_boosts":   sum(1 for p in patterns if p["modifier"] > 0),
            "n_blocks":   sum(1 for p in patterns if p["modifier"] < 0),
            "n_signals_affected": applied,
        },
        "patterns": patterns,
    })
    print(f"[pattern_memory] baseline_wr={baseline*100:.1f}% patterns={len(patterns)} "
          f"applied_to={applied}/{len(sigs)} signals")

if __name__ == "__main__":
    main()
