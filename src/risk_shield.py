"""RiskShield & Bankroll Manager — Pilon 4.

Adaugă layer-ul de protecție pe care platforma nu îl avea: stake calculator
Kelly fracționat cu cap, max-expunere zilnică, stop-loss pe streak, circuit
breaker pe drawdown, blocaj per-piață când scade calitatea.

Output: data/risk_state.json — consumat de Dashboard UI.

Rulează după compute_signals_v6.py (când signals_v6.json e proaspăt) și
folosește selection_journal.json pentru istoric/drawdown.
"""
from __future__ import annotations
import json, math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# --- Reguli centrale ----------------------------------------------------------
# Toate procentele sunt aplicate la `bankroll_unit` (default 100 unități).
RULES: Dict[str, Any] = {
    "bankroll_unit":            100.0,
    "max_daily_exposure_pct":   5.0,   # max stake total/zi (procent din bankroll)
    "max_per_signal_pct":       1.5,   # max stake/semnal
    "kelly_fraction":           0.25,  # quarter-Kelly (conservator)
    "kelly_cap":                0.03,  # max 3% per stake după Kelly
    "min_grade_for_live":       "B",   # blochează semnalele sub Grade B
    "max_correlated_per_league":3,     # max 3 semnale per ligă/zi
    "stop_loss_streak":         5,     # 5 LOST consecutive → reducere 50%
    "drawdown_circuit_breaker_pct": -15,  # -15% în 7d → pauză 24h
    "circuit_breaker_pause_h":  24,
    "blocked_markets_window_days": 7,  # market blocat 7 zile dacă CLV+ rate < 40%
    "clv_min_positive_rate":    0.40,
    "clv_lookback_days":        30,
}

# --- Utils --------------------------------------------------------------------
def _load(path: Path, default):
    try: return json.loads(path.read_text("utf-8"))
    except Exception: return default

def _save(path: Path, payload: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), "utf-8")

def _grade_rank(g: str) -> int:
    return {"A+": 6, "A": 5, "B": 4, "C": 3, "D": 2, "N/A": 0}.get(str(g or "N/A").strip(), 0)

def _kelly(prob: float, odds: float) -> float:
    """Kelly clasic: f = (bp - q) / b, unde b = odds-1, q = 1-p."""
    if not (prob and odds and odds > 1): return 0.0
    b = odds - 1.0
    q = 1.0 - prob
    f = (b * prob - q) / b
    return max(0.0, f)

def _iso_to_dt(s: str):
    if not s: return None
    try: return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception: return None

def _today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()

def _signal_dates(signals):
    """Determine 'today' based on the freshest signals (not wall clock) to handle
    cases where the workflow ran the previous day and signals point to tomorrow."""
    dates = sorted({(s.get("event_date") or "")[:10] for s in signals if s.get("event_date")})
    return dates

# --- Core ---------------------------------------------------------------------
def compute_drawdown(journal_rows: List[Dict[str, Any]], days: int) -> Dict[str, float]:
    """Drawdown rolling: profit cumulat în ferestră, peak vs current."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = []
    for r in journal_rows:
        dt = _iso_to_dt(r.get("settled_at") or r.get("event_date"))
        if not dt or dt < cutoff: continue
        try: rows.append((dt, float(r.get("profit_units") or 0.0)))
        except Exception: continue
    rows.sort(key=lambda x: x[0])
    if not rows:
        return {"rolling_pct": 0.0, "peak": 0.0, "current": 0.0, "n": 0}
    cum, peak, dd_peak = 0.0, 0.0, 0.0
    for _, p in rows:
        cum += p
        if cum > peak: peak = cum
        dd_peak = min(dd_peak, cum - peak)  # cel mai jos drawdown
    rolling_pct = round((cum / RULES["bankroll_unit"]) * 100, 2)
    return {"rolling_pct": rolling_pct, "peak": round(peak, 2), "current": round(cum, 2),
            "drawdown_peak_units": round(dd_peak, 2), "n": len(rows)}

def compute_streak(journal_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Câte LOST consecutive la urmă (cele mai recente decontate)."""
    settled = [r for r in journal_rows if str(r.get("status", "")).lower() == "settled" and r.get("result")]
    settled.sort(key=lambda r: _iso_to_dt(r.get("settled_at") or r.get("event_date")) or datetime.min.replace(tzinfo=timezone.utc),
                 reverse=True)
    streak, last_result = 0, None
    for r in settled:
        res = str(r.get("result", "")).upper()
        if res == "LOSS" or res == "LOST":
            if last_result is None or last_result == "LOST":
                streak += 1; last_result = "LOST"
            else: break
        else:
            break
    return {"consecutive_losses": streak,
            "stop_loss_triggered": streak >= RULES["stop_loss_streak"]}

def compute_market_blocks(journal_rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Blochează piețele cu CLV+ rate < 40% în 30 zile rolling."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=RULES["clv_lookback_days"])
    by_market: Dict[str, List[bool]] = {}
    for r in journal_rows:
        dt = _iso_to_dt(r.get("settled_at") or r.get("event_date"))
        if not dt or dt < cutoff: continue
        mk = str(r.get("market_canonical") or r.get("market") or "")
        if not mk: continue
        # clv_positive: True dacă CLV pct > 0 sau result WIN cu odds_taken >= closing_odds
        clv = r.get("clv_beat_pct"); pos = None
        if clv is not None:
            try: pos = float(clv) > 0
            except Exception: pos = None
        if pos is None: continue
        by_market.setdefault(mk, []).append(pos)
    blocks = {}
    for mk, lst in by_market.items():
        n = len(lst)
        if n < 10: continue  # nu blocăm pe sample mic
        pos_rate = sum(lst) / n
        if pos_rate < RULES["clv_min_positive_rate"]:
            blocks[mk] = {
                "blocked": True, "clv_positive_rate": round(pos_rate, 3), "n": n,
                "reason": f"CLV+ rate {pos_rate:.1%} < {RULES['clv_min_positive_rate']:.0%} pe {RULES['clv_lookback_days']}d",
                "expires_at": (datetime.now(timezone.utc) + timedelta(days=RULES["blocked_markets_window_days"])).isoformat(),
            }
    return blocks

def compute_circuit_breaker(drawdown_7d: Dict[str, float]) -> Dict[str, Any]:
    trigger = RULES["drawdown_circuit_breaker_pct"]
    active = drawdown_7d["rolling_pct"] <= trigger
    if not active:
        return {"active": False, "trigger_pct": trigger, "rolling_pct": drawdown_7d["rolling_pct"]}
    return {"active": True, "trigger_pct": trigger, "rolling_pct": drawdown_7d["rolling_pct"],
            "reason": f"Drawdown {drawdown_7d['rolling_pct']:.1f}% ≤ {trigger}% prag",
            "pause_h": RULES["circuit_breaker_pause_h"]}

def gate_signal(s: Dict[str, Any], streak: Dict[str, Any], breaker: Dict[str, Any],
                market_blocks: Dict[str, Dict[str, Any]], per_league_count: Dict[str, int]) -> Dict[str, Any]:
    """Întoarce decizia per signal: stake recomandat + motive blocaj."""
    out = {"event_id": s.get("event_id"), "market": s.get("market"), "league": s.get("league"),
           "stake_pct": 0.0, "stake_amount": 0.0, "kelly_raw": 0.0,
           "blocked": False, "reasons": []}

    if breaker.get("active"):
        out["blocked"] = True; out["reasons"].append("circuit_breaker"); return out

    grade = ""
    for k in ("display_grade", "quality_grade_v6", "market_signal_grade", "quality_grade",
              "grade", "smartbet_grade"):
        v = s.get(k)
        if v:
            grade = str(v).strip()
            break
    if _grade_rank(grade) < _grade_rank(RULES["min_grade_for_live"]):
        out["blocked"] = True; out["reasons"].append(f"grade<{RULES['min_grade_for_live']}({grade or 'n/a'})"); return out

    mk = str(s.get("market_canonical") or s.get("market") or "")
    if mk in market_blocks:
        out["blocked"] = True; out["reasons"].append("market_blocked_clv"); return out

    lg = str(s.get("league") or "unknown")
    if per_league_count.get(lg, 0) >= RULES["max_correlated_per_league"]:
        out["blocked"] = True; out["reasons"].append("correlated_cap"); return out

    # Kelly recomandare
    prob = None
    for k in ("calibrated_prob", "adj_prob", "model_probability", "probability"):
        v = s.get(k)
        if v is not None:
            try: prob = float(v); break
            except Exception: pass
    if prob is not None and prob > 1.5: prob /= 100.0  # uneori vine ca %
    odds = None
    for k in ("odds", "fair_odds", "market_odds", "best_odds"):
        v = s.get(k)
        if v is not None:
            try: odds = float(v); break
            except Exception: pass

    kelly_raw = _kelly(prob or 0.0, odds or 0.0)
    kelly_frac = kelly_raw * RULES["kelly_fraction"]
    stake_pct = min(kelly_frac, RULES["kelly_cap"], RULES["max_per_signal_pct"] / 100.0) * 100
    if streak.get("stop_loss_triggered"):
        stake_pct *= 0.5
        out["reasons"].append("stop_loss_halved")

    out.update({"stake_pct": round(stake_pct, 3),
                "stake_amount": round(stake_pct / 100 * RULES["bankroll_unit"], 2),
                "kelly_raw": round(kelly_raw, 4)})
    return out

def main():
    print("[risk_shield] start")
    signals_doc = _load(DATA / "signals_v6.json", {})
    signals = signals_doc.get("signals") if isinstance(signals_doc, dict) else (signals_doc or [])
    journal = _load(DATA / "selection_journal.json", {}).get("results", [])

    today_wall = _today_iso()
    # "Today" pentru expunere = ziua calendaristică curentă SAU prima zi cu semnale dacă
    # azi nu are semnale (poate workflow-ul a rulat noaptea pentru meciurile de mâine).
    sig_dates = _signal_dates([s for s in signals if isinstance(s, dict)])
    today = today_wall if today_wall in sig_dates else (sig_dates[0] if sig_dates else today_wall)
    # Drawdown
    dd_7  = compute_drawdown(journal, 7)
    dd_30 = compute_drawdown(journal, 30)
    streak = compute_streak(journal)
    market_blocks = compute_market_blocks(journal)
    breaker = compute_circuit_breaker(dd_7)

    # Gating per semnal — first pass collects league counters
    per_league_count: Dict[str, int] = {}
    per_signal: Dict[str, Dict[str, Any]] = {}
    # Sort signals by quality (smartbet_score desc) so top picks claim league slots first
    def score_of(s):
        for k in ("smartbet_score_v6", "smartbet_score", "display_score", "market_signal_score"):
            v = s.get(k)
            if v is not None:
                try: return float(v)
                except Exception: pass
        return 0.0
    signals_sorted = sorted([s for s in signals if isinstance(s, dict)], key=score_of, reverse=True)

    today_exposure_pct = 0.0
    n_active = 0
    for s in signals_sorted:
        # Filtru: doar semnale pentru evenimente din azi (sau viitor apropiat)
        eid = str(s.get("event_id") or "")
        mk  = str(s.get("market") or "")
        key = f"{eid}|{mk}"
        decision = gate_signal(s, streak, breaker, market_blocks, per_league_count)
        per_signal[key] = decision
        if not decision["blocked"]:
            lg = str(s.get("league") or "unknown")
            per_league_count[lg] = per_league_count.get(lg, 0) + 1
            # Acumulează expunere doar pentru semnalele "today"
            ed = s.get("event_date") or ""
            if ed.startswith(today):
                today_exposure_pct += decision["stake_pct"]
                n_active += 1

    # Cap pe expunere zilnică totală: scalează în jos toate stake-urile dacă depășește
    max_exp = RULES["max_daily_exposure_pct"]
    scale_applied = 1.0
    if today_exposure_pct > max_exp and today_exposure_pct > 0:
        scale_applied = max_exp / today_exposure_pct
        for key, dec in per_signal.items():
            eid = key.split("|", 1)[0]
            sig = next((s for s in signals_sorted if str(s.get("event_id")) == eid), None)
            if sig and (sig.get("event_date") or "").startswith(today) and not dec["blocked"]:
                dec["stake_pct"]    = round(dec["stake_pct"] * scale_applied, 3)
                dec["stake_amount"] = round(dec["stake_amount"] * scale_applied, 2)
                dec["reasons"].append("daily_cap_scaled")
        today_exposure_pct *= scale_applied

    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "rules": RULES,
        "today": {
            "exposure_pct":    round(today_exposure_pct, 2),
            "exposure_amount": round(today_exposure_pct / 100 * RULES["bankroll_unit"], 2),
            "n_active":        n_active,
            "n_blocked":       sum(1 for d in per_signal.values() if d["blocked"]),
            "scale_applied":   round(scale_applied, 3),
            "max_pct":         max_exp,
        },
        "drawdown": {"rolling_7d_pct": dd_7["rolling_pct"], "rolling_30d_pct": dd_30["rolling_pct"],
                     "peak_units": dd_7["peak"], "current_units": dd_7["current"], "n_30d": dd_30["n"]},
        "streak": streak,
        "circuit_breaker": breaker,
        "blocked_markets": market_blocks,
        "per_signal": per_signal,
    }
    _save(DATA / "risk_state.json", payload)
    print(f"[risk_shield] active={n_active} blocked={payload['today']['n_blocked']} "
          f"exposure={payload['today']['exposure_pct']:.2f}% "
          f"dd7={dd_7['rolling_pct']:.1f}% breaker={'ON' if breaker.get('active') else 'OFF'} "
          f"blocked_markets={list(market_blocks.keys())}")

if __name__ == "__main__":
    main()
