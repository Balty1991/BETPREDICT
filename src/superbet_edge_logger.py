#!/usr/bin/env python3
"""
superbet_edge_logger.py — BetPredict v7 Superbet Edge Monitor
================================================================

Registru persistent pentru superbet_edge_engine.py: ține evidența TUTUROR
predicțiilor (picioarelor din watchlist) și biletelor sugerate afișate, ca să
se poată verifica ulterior — cu date reale, nu impresii — daca pragurile
calculate din pretul Pinnacle chiar au acoperire (win rate) in realitate.

Ciclu de viata (acelasi pattern ca sharp_clv_logger.py):
  1. OPEN   — la prima aparitie a unui picior/bilet, il inregistram (nu-l
              duplicam la rulările următoare daca setul de picioare e identic).
  2. SETTLE — cand meciul e finished (din recent_results.json), calculam
              WIN/LOSS per picior. Un bilet e WIN doar daca TOATE picioarele
              sunt WIN; e LOSS de indata ce UN picior pica.

Profitul pe bilet e un PROXY conservator: foloseste threshold_odds (pragul
minim), nu cota reala luata pe Superbet (necunoscuta sistemului) — deci ROI-ul
real e >= ROI-ul proxy daca utilizatorul a respectat regula "cota >= prag".

Output: data/superbet_edge_history.json
Ruleaza standalone (dupa superbet_edge_engine): python3 src/superbet_edge_logger.py
"""
from __future__ import annotations
import json, os, sys, tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

from sharp_clv_logger import _settle, _results_index

try:
    from analytics_core import safe_float
except Exception:
    def safe_float(v, d=0.0):
        try:
            x = float(v); return d if x != x else x
        except Exception:
            return d

LEDGER = "superbet_edge_history.json"


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


def _leg_key(eid, market, outcome) -> str:
    return f"{eid}:{market}:{outcome}"


def _ticket_key(label: str, legs: List[Dict[str, Any]]) -> str:
    sig = "|".join(sorted(_leg_key(l["event_id"], l["market"], l["outcome"]) for l in legs))
    return f"{label}::{sig}"


def _register_leg(legs_ledger: Dict[str, Any], leg: Dict[str, Any], now: str) -> None:
    k = _leg_key(leg.get("event_id"), leg.get("market"), leg.get("outcome"))
    if k in legs_ledger:
        return
    legs_ledger[k] = {
        "event_id": leg.get("event_id"), "home_team": leg.get("home_team"),
        "away_team": leg.get("away_team"), "league": leg.get("league"),
        "event_date": leg.get("event_date"), "event_time_label": leg.get("event_time_label"),
        "market": leg.get("market"), "market_label": leg.get("market_label"),
        "outcome": leg.get("outcome"), "outcome_label": leg.get("outcome_label"),
        "fair_prob_pct": leg.get("fair_prob_pct"),
        "threshold_odds": leg.get("threshold_odds"), "confidence": leg.get("confidence"),
        "steam_confirmed": leg.get("steam_confirmed"),
        "logged_at": now, "result": None, "win": None, "final_score": None, "settled_at": None,
    }


def _settle_leg(row: Dict[str, Any], res_idx: Dict[Any, Dict[str, Any]], now: str) -> None:
    if row.get("result") is not None:
        return
    r = res_idx.get(row.get("event_id"))
    if not r:
        return
    hs, as_ = r.get("home_score"), r.get("away_score")
    if hs is None or as_ is None:
        return
    w = _settle(row["market"], row["outcome"], int(hs), int(as_))
    if w is not None:
        row["win"] = bool(w)
        row["result"] = "WIN" if w else "LOSS"
        row["final_score"] = f"{int(hs)}-{int(as_)}"
        row["settled_at"] = now


def _settle_ticket(t: Dict[str, Any], legs_ledger: Dict[str, Any], now: str) -> None:
    """Un bilet e WIN doar daca TOATE picioarele sunt WIN; LOSS de indata ce UN picior pica;
    altfel ramane in asteptare (unele picioare inca nedecontate, niciunul pierdut inca)."""
    if t.get("result") is not None:
        return
    leg_rows = [legs_ledger.get(k) for k in t.get("leg_keys", [])]
    if any(r is None for r in leg_rows):
        return
    results = [r.get("result") for r in leg_rows]
    if any(res == "LOSS" for res in results):
        t["win"] = False; t["result"] = "LOSS"
        t["profit_units_proxy"] = -1.0
        t["settled_at"] = now
    elif all(res == "WIN" for res in results):
        t["win"] = True; t["result"] = "WIN"
        t["profit_units_proxy"] = round(safe_float(t.get("combined_threshold_odds"), 1.0) - 1.0, 3)
        t["settled_at"] = now


def _aggregate_win_rate_by(rows: List[Dict[str, Any]], key: str, default: str,
                           label_key: Optional[str] = None, top_n: Optional[int] = None) -> Dict[str, Any]:
    """Win rate grupat dupa `key` (ex. 'market' sau 'league'), sortat descrescator
    dupa cate picioare decontate are fiecare grup — cele mai relevante (esantion
    mai mare) primele. `top_n` limiteaza numarul de grupuri afisate (util pt. league,
    care poate avea multe valori distincte cu 1-2 picioare fiecare)."""
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault(r.get(key) or default, []).append(r)
    items = sorted(groups.items(), key=lambda kv: len(kv[1]), reverse=True)
    if top_n is not None:
        items = items[:top_n]
    out = {}
    for k, grp in items:
        entry = {
            "n_settled": len(grp),
            "win_rate_pct": round(sum(1 for r in grp if r["win"]) / len(grp) * 100, 1) if grp else None,
        }
        if label_key:
            entry["label"] = next((r.get(label_key) for r in grp if r.get(label_key)), k)
        out[k] = entry
    return out


def main() -> int:
    signals = _load("superbet_edge_signals.json", {}) or {}
    recent = _load("recent_results.json", {}) or {}
    ledger = _load(LEDGER, {}) or {}
    legs_ledger: Dict[str, Any] = ledger.get("legs", {})
    tickets_ledger: Dict[str, Any] = ledger.get("tickets", {})

    now = datetime.now(timezone.utc).isoformat()
    res_idx = _results_index(recent)

    # 1) OPEN — inregistreaza toate picioarele din watchlist (monitorizarea predictiilor)
    # + backfill etichete (market_label/outcome_label/event_time_label) pe intrari vechi din
    # jurnal care nu le aveau inca (adaugate ulterior primei rulari a acestui script).
    for leg in signals.get("watchlist", []):
        k = _leg_key(leg.get("event_id"), leg.get("market"), leg.get("outcome"))
        existing = legs_ledger.get(k)
        if existing is not None and not existing.get("market_label"):
            existing["market_label"] = leg.get("market_label")
            existing["outcome_label"] = leg.get("outcome_label")
            existing["event_time_label"] = leg.get("event_time_label")
        _register_leg(legs_ledger, leg, now)

    # 2) OPEN — inregistreaza biletele sugerate curente (monitorizarea biletelor)
    for t in signals.get("suggested_tickets", []):
        legs = t.get("legs") or []
        if not legs:
            continue
        for leg in legs:
            _register_leg(legs_ledger, leg, now)
        tk = _ticket_key(t.get("label", "?"), legs)
        if tk not in tickets_ledger:
            tickets_ledger[tk] = {
                "label": t.get("label"),
                "leg_keys": [_leg_key(l["event_id"], l["market"], l["outcome"]) for l in legs],
                "legs_summary": [f"{l.get('home_team')} - {l.get('away_team')} ({l.get('event_time_label') or '?'}) · "
                                 f"{l.get('market_label')} ({l.get('outcome_label')})" for l in legs],
                "combined_threshold_odds": t.get("combined_threshold_odds"),
                "combined_probability_pct": t.get("combined_probability_pct"),
                "stake_pct_of_bankroll": t.get("stake_pct_of_bankroll"),
                "logged_at": now, "result": None, "win": None,
                "profit_units_proxy": None, "settled_at": None,
            }

    # 3) SETTLE picioare (+ backfill scor final pe picioare deja decontate inainte ca
    # acest camp sa existe — la fel ca backfill-ul de etichete de mai sus)
    for row in legs_ledger.values():
        if row.get("result") is not None and not row.get("final_score"):
            r = res_idx.get(row.get("event_id"))
            if r and r.get("home_score") is not None and r.get("away_score") is not None:
                row["final_score"] = f"{int(r['home_score'])}-{int(r['away_score'])}"
        _settle_leg(row, res_idx, now)

    # 4) SETTLE bilete — WIN doar daca toate picioarele WIN; LOSS daca vreunul pica
    for t in tickets_ledger.values():
        _settle_ticket(t, legs_ledger, now)

    # 5) Agregare
    all_legs = list(legs_ledger.values())
    settled_legs = [r for r in all_legs if r.get("result") in ("WIN", "LOSS")]
    legs_summary = {
        "n_logged": len(all_legs), "n_settled": len(settled_legs),
        "win_rate_pct": round(sum(1 for r in settled_legs if r["win"]) / len(settled_legs) * 100, 1) if settled_legs else None,
    }
    by_confidence: Dict[str, Any] = {}
    for conf in ("ridicat", "mediu"):
        rows = [r for r in settled_legs if r.get("confidence") == conf]
        by_confidence[conf] = {
            "n_settled": len(rows),
            "win_rate_pct": round(sum(1 for r in rows if r["win"]) / len(rows) * 100, 1) if rows else None,
        }

    # Win rate pe tip de piata (1x2/btts/over_under_*) — care piete chiar merg, nu doar
    # agregatul general. Win rate pe liga — utile ca sa vezi daca anumite campionate au
    # fost sistematic mai slabe (calitate date, volatilitate) fara sa rasfoiesti jurnalul.
    legs_by_market = _aggregate_win_rate_by(settled_legs, "market", "necunoscut", label_key="market_label")
    legs_by_league = _aggregate_win_rate_by(settled_legs, "league", "necunoscuta", top_n=15)

    all_tickets = list(tickets_ledger.values())
    settled_tickets = [t for t in all_tickets if t.get("result") in ("WIN", "LOSS")]
    profit = sum(safe_float(t.get("profit_units_proxy")) for t in settled_tickets)
    tickets_summary = {
        "n_logged": len(all_tickets), "n_settled": len(settled_tickets),
        "win_rate_pct": round(sum(1 for t in settled_tickets if t["win"]) / len(settled_tickets) * 100, 1) if settled_tickets else None,
        "roi_pct_proxy": round(profit / len(settled_tickets) * 100, 1) if settled_tickets else None,
        "note": "ROI proxy calculat cu pragul minim de cota (threshold_odds), nu cota reala Superbet — ROI real >= acesta daca ai respectat regula cota >= prag.",
    }

    out = {
        "updated_at": now,
        "source": "superbet_edge_logger_v1",
        "legs_summary": legs_summary,
        "legs_by_confidence": by_confidence,
        "legs_by_market": legs_by_market,
        "legs_by_league": legs_by_league,
        "tickets_summary": tickets_summary,
        "legs": legs_ledger,
        "tickets": tickets_ledger,
    }
    _atomic_write(LEDGER, out)

    print(f"[superbet_log] legs={legs_summary['n_logged']} settled={legs_summary['n_settled']} "
          f"win_rate={legs_summary['win_rate_pct']} | tickets={tickets_summary['n_logged']} "
          f"settled={tickets_summary['n_settled']} win_rate={tickets_summary['win_rate_pct']} "
          f"roi_proxy={tickets_summary['roi_pct_proxy']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
