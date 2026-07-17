#!/usr/bin/env python3
"""
sharp_clv_logger.py  — BetPredict v7 CLV & paper-trading ledger
================================================================

De ce exista: CLV (Closing Line Value) este SINGURUL indicator care prezice
profitul pe termen lung. Fara CLV real (nu proxy) nu poti sti niciodata daca
o strategie chiar are edge. Modulul construieste un registru persistent:

  1. OPEN  — la prima aparitie a unui semnal (sharp-value / polymarket), inregistram
             cota de pariu + probabilitatea corecta + timestamp.
  2. CLOSE — la fiecare rulare, actualizam "closing line" = cea mai recenta cota
             disponibila din best_odds.json. Cand meciul incepe, ultima cota
             inregistrata devine linia de inchidere reala.
  3. SETTLE— cand meciul e finished (din recent_results.json), calculam rezultatul
             (win/loss) si profitul la miza fixa 1u.

Output: data/sharp_paper_trades.json  (ledger + CLV agregat per strategie)

CLV% = ((1/closing) - (1/open_bet)) / (1/open_bet) * 100
  > 0  => am prins o cota mai buna decat piata la inchidere = edge dovedit.

Ruleaza standalone (dupa sharp_value_engine):  python3 src/sharp_clv_logger.py
"""
from __future__ import annotations
import json, os, sys, tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

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

LEDGER = "sharp_paper_trades.json"


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


def _parse_dt(s: Any) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


# best_odds outcome naming per market
_BO_OC = {
    "1x2": {"HOME": "HOME", "DRAW": "DRAW", "AWAY": "AWAY"},
    "btts": {"YES": "yes", "NO": "no"},
    "over_under_15": {"OVER": "over", "UNDER": "under"},
    "over_under_25": {"OVER": "over", "UNDER": "under"},
    "over_under_35": {"OVER": "over", "UNDER": "under"},
}


def _best_odds_index(best_odds: Dict[str, Any]) -> Dict[Tuple[Any, str, str], float]:
    idx = {}
    for r in (best_odds.get("results") or []):
        eid = r.get("event_id")
        market = r.get("market")
        for o in r.get("best_odds", []):
            oc = str(o.get("outcome")).lower()
            idx[(eid, market, oc)] = safe_float(o.get("decimal_odds"), 0.0)
    return idx


def _closing_odds(idx, eid, market, outcome) -> Optional[float]:
    bo_oc = _BO_OC.get(market, {}).get(outcome)
    if not bo_oc:
        return None
    v = idx.get((eid, market, bo_oc.lower()))
    return v if v and v > 1.01 else None


def _results_index(recent: Dict[str, Any]) -> Dict[Any, Dict[str, Any]]:
    res = recent.get("results", recent) if isinstance(recent, dict) else recent
    out = {}
    for r in (res or []):
        if str(r.get("status")) in ("finished", "FT") or r.get("period") == "FT":
            out[r.get("id")] = r
    return out


def _settle(market: str, outcome: str, hs: int, as_: int) -> Optional[int]:
    """Returneaza 1 (win), 0 (loss), None (nu se poate settle)."""
    tot = hs + as_
    if market == "1x2":
        if outcome == "HOME":
            return int(hs > as_)
        if outcome == "DRAW":
            return int(hs == as_)
        if outcome == "AWAY":
            return int(hs < as_)
    if market == "btts":
        btts = hs > 0 and as_ > 0
        return int(btts) if outcome == "YES" else int(not btts)
    if market.startswith("over_under_"):
        line = {"over_under_15": 1.5, "over_under_25": 2.5, "over_under_35": 3.5}[market]
        over = tot > line
        return int(over) if outcome == "OVER" else int(not over)
    return None


def _key(eid, market, outcome, strat) -> str:
    return f"{eid}:{market}:{outcome}:{strat}"


def main() -> int:
    signals = _load("sharp_value_signals.json", {})
    best_odds = _load("best_odds.json", {})
    recent = _load("recent_results.json", {})
    ledger = _load(LEDGER, {}) or {}
    trades: Dict[str, Any] = ledger.get("trades", {})

    now = datetime.now(timezone.utc)
    bo_idx = _best_odds_index(best_odds)
    res_idx = _results_index(recent)

    # 1) OPEN — inregistreaza semnale noi
    def register(sig: Dict[str, Any], strat: str, bet_odds_key: str, prob_key: str):
        eid = sig.get("event_id"); market = sig.get("market"); oc = sig.get("outcome")
        if eid is None or not market or not oc:
            return
        k = _key(eid, market, oc, strat)
        if k in trades:
            return
        trades[k] = {
            "event_id": eid, "home_team": sig.get("home_team"),
            "away_team": sig.get("away_team"), "league": sig.get("league"),
            "event_date": sig.get("event_date"), "market": market, "outcome": oc,
            "strategy": strat,
            "open_odds": safe_float(sig.get(bet_odds_key)),
            "open_book": sig.get("bet_book"),
            "fair_prob_pct": sig.get(prob_key),
            "opened_at": now.isoformat(),
            "closing_odds": None, "clv_pct": None,
            "result": None, "win": None, "profit_units": None, "settled_at": None,
        }

    for s in signals.get("value_signals", []):
        register(s, "sharp_value", "bet_odds", "fair_prob_pct")
    for s in signals.get("polymarket_divergence", []):
        register(s, "polymarket", "bet_odds", "poly_prob_pct")

    # 2) CLOSE + 3) SETTLE — actualizeaza toate trade-urile deschise
    for k, t in trades.items():
        eid = t["event_id"]; market = t["market"]; oc = t["outcome"]
        started = False
        dt = _parse_dt(t.get("event_date"))
        if dt and now >= dt:
            started = True
        # inainte de start: reimprospatam closing candidate cu cea mai recenta cota
        cur = _closing_odds(bo_idx, eid, market, oc)
        if t.get("result") is None:
            if not started and cur:
                t["closing_odds"] = cur
            elif started and t.get("closing_odds") is None and cur:
                t["closing_odds"] = cur
        # CLV
        if t.get("closing_odds") and t["open_odds"] > 1.01 and t["closing_odds"] > 1.01:
            io, ic = 1.0 / t["open_odds"], 1.0 / t["closing_odds"]
            t["clv_pct"] = round((ic - io) / io * 100.0, 3)
        # SETTLE
        if t.get("result") is None and eid in res_idx:
            r = res_idx[eid]
            hs, as_ = r.get("home_score"), r.get("away_score")
            if hs is not None and as_ is not None:
                w = _settle(market, oc, int(hs), int(as_))
                if w is not None:
                    t["win"] = w
                    t["result"] = "WIN" if w else "LOSS"
                    t["profit_units"] = round(t["open_odds"] - 1.0, 4) if w else -1.0
                    t["settled_at"] = now.isoformat()

    # 4) AGREGARE per strategie
    def agg(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        clvs = [r["clv_pct"] for r in rows if r.get("clv_pct") is not None]
        settled = [r for r in rows if r.get("result") in ("WIN", "LOSS")]
        wins = sum(1 for r in settled if r["win"])
        profit = sum(safe_float(r.get("profit_units")) for r in settled)
        return {
            "n_trades": len(rows), "n_with_clv": len(clvs), "n_settled": len(settled),
            "avg_clv_pct": round(sum(clvs) / len(clvs), 3) if clvs else None,
            "clv_positive_rate": round(sum(1 for c in clvs if c > 0) / len(clvs), 3) if clvs else None,
            "win_rate_pct": round(wins / len(settled) * 100, 1) if settled else None,
            "roi_pct": round(profit / len(settled) * 100, 1) if settled else None,
            "profit_units": round(profit, 2),
        }

    all_rows = list(trades.values())
    by_strategy = {}
    for strat in sorted({r["strategy"] for r in all_rows}):
        by_strategy[strat] = agg([r for r in all_rows if r["strategy"] == strat])

    out = {
        "updated_at": now.isoformat(),
        "source": "sharp_clv_logger_v7",
        "note": "CLV real din snapshot open + closing best_odds. >=100 trade-uri settle-uite "
                "cu CLV pozitiv = strategie validata. Sub atat = orientativ.",
        "overall": agg(all_rows),
        "by_strategy": by_strategy,
        "trades": trades,
    }
    _atomic_write(LEDGER, out)

    o = out["overall"]
    print(f"[sharp_clv] trades={o['n_trades']} | cu CLV={o['n_with_clv']} "
          f"(avg {o['avg_clv_pct']}%) | settled={o['n_settled']} "
          f"| ROI={o['roi_pct']}%")
    for strat, a in by_strategy.items():
        print(f"  {strat}: {a['n_trades']} trades | CLV {a['avg_clv_pct']}% "
              f"| win {a['win_rate_pct']}% | ROI {a['roi_pct']}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
