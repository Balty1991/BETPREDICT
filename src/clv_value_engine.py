#!/usr/bin/env python3
"""
BETPREDICT 2.0 — CLV Value Engine
=================================
Tracks the exact odds shown when a prediction is published and compares them
against the closest available closing line snapshot from odds_movement/best_odds.

Outputs:
  data/clv_snapshots.json   persistent pick-level CLV log
  data/clv_tracker.json     summary + by market/league/event indexes
  data/signals.json         augmented with clv_beat_pct/clv_state/clv_badge

Important:
  A CLV row is marked reliable only when the closing source is usable and the
  event is close to start/settled. Without a true historical bookmaker closing
  feed, this engine is strict and labels the line as PROXY/OBSERVED.
"""
from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

TOP_BOOKS = {"pinnacle", "bet365", "betfair", "sbo", "sbobet"}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return now_utc().isoformat()


def load_json(path: Path, default: Any) -> Any:
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)
        fh.write("\n")
    tmp.replace(path)


def fnum(v: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if isinstance(v, str):
            v = v.replace("%", "").replace(",", ".").strip()
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    except Exception:
        return default


def parse_dt(v: Any) -> Optional[datetime]:
    if not v:
        return None
    try:
        s = str(v).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def norm_market(m: Any) -> str:
    s = str(m or "").lower().strip().replace(" ", "_").replace("-", "_")
    aliases = {
        "over15": "over_under_15", "over_15": "over_under_15", "over_1_5": "over_under_15", "over1_5": "over_under_15",
        "over25": "over_under_25", "over_25": "over_under_25", "over_2_5": "over_under_25", "over2_5": "over_under_25",
        "under35": "over_under_35", "under_35": "over_under_35", "under_3_5": "over_under_35", "under3_5": "over_under_35",
        "btts": "btts", "gg": "btts",
        "homewin": "1x2", "home": "1x2", "1": "1x2",
        "draw": "1x2", "x": "1x2",
        "awaywin": "1x2", "away": "1x2", "2": "1x2",
    }
    return aliases.get(s, s)


def canonical_market(m: Any) -> str:
    s = str(m or "").lower().replace(" ", "").replace("_", "")
    if "over15" in s or "over1.5" in s:
        return "over15"
    if "over25" in s or "over2.5" in s:
        return "over25"
    if "under35" in s or "under3.5" in s:
        return "under35"
    if "btts" in s or s == "gg":
        return "btts"
    if s in {"home", "homewin", "1"}:
        return "homeWin"
    if s in {"draw", "x"}:
        return "draw"
    if s in {"away", "awaywin", "2"}:
        return "awayWin"
    return s or "unknown"


def outcome_for_market(market: Any, sig: Dict[str, Any]) -> str:
    c = canonical_market(market)
    if c == "over15": return "OVER 1.50"
    if c == "over25": return "OVER 2.50"
    if c == "under35": return "UNDER 3.50"
    if c == "btts": return "YES"
    if c == "homeWin": return "HOME"
    if c == "draw": return "DRAW"
    if c == "awayWin": return "AWAY"
    return str(sig.get("outcome") or sig.get("selection") or "").upper()


def signal_key(sig: Dict[str, Any]) -> str:
    eid = str(sig.get("event_id") or sig.get("id") or "")
    cm = canonical_market(sig.get("market"))
    out = outcome_for_market(sig.get("market"), sig)
    return f"{eid}|{cm}|{out}"


def source_rank(book: Any) -> int:
    b = str(book or "").lower().replace(" ", "")
    return 0 if b in TOP_BOOKS else 1


def build_best_odds_index(best_odds: Dict[str, Any]) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    idx: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for row in best_odds.get("results", []) if isinstance(best_odds, dict) else []:
        eid = str(row.get("event_id") or row.get("event", {}).get("id") or "")
        market = norm_market(row.get("market") or row.get("_market"))
        rows = row.get("best_odds") or []
        if not eid or not rows:
            continue
        for odd in rows:
            outcome = str(odd.get("outcome") or odd.get("outcome_name") or "").upper()
            price = fnum(odd.get("decimal_odds"))
            if not price or price <= 1:
                continue
            book = odd.get("bookmaker_slug") or odd.get("bookmaker_name")
            rec = {
                "event_id": eid,
                "market": market,
                "outcome": outcome,
                "odds": round(price, 4),
                "bookmaker": book,
                "updated_at": odd.get("updated_at") or row.get("updated_at"),
                "source": "best_odds",
                "top_book": source_rank(book) == 0,
            }
            k = (eid, market, outcome)
            prev = idx.get(k)
            if prev is None or (source_rank(book), -price) < (source_rank(prev.get("bookmaker")), -float(prev.get("odds") or 0)):
                idx[k] = rec
    return idx


def build_movement_index(movement: Dict[str, Any]) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    idx: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for row in movement.get("results", []) if isinstance(movement, dict) else []:
        eid = str(row.get("event_id") or "")
        market = norm_market(row.get("market"))
        outcome = str(row.get("outcome") or "").upper()
        price = fnum(row.get("decimal_odds"))
        if not eid or not outcome or not price or price <= 1:
            continue
        book = row.get("bookmaker") or row.get("bookmaker_slug")
        rec = {
            "event_id": eid,
            "market": market,
            "outcome": outcome,
            "odds": round(price, 4),
            "bookmaker": book,
            "updated_at": row.get("updated_at"),
            "source": "odds_movement",
            "previous_odds": fnum(row.get("previous_odds")),
            "delta": fnum(row.get("delta")),
            "movement": row.get("movement"),
            "top_book": source_rank(book) == 0,
        }
        k = (eid, market, outcome)
        prev = idx.get(k)
        if prev is None or (source_rank(book), abs(fnum(row.get("delta"), 0) or 0)) < (source_rank(prev.get("bookmaker")), abs(float(prev.get("delta") or 0))):
            idx[k] = rec
    return idx


def current_line(sig: Dict[str, Any], best_idx: Dict, move_idx: Dict) -> Dict[str, Any]:
    eid = str(sig.get("event_id") or "")
    market = norm_market(sig.get("odds_market") or sig.get("market"))
    outcome = outcome_for_market(sig.get("market"), sig).upper()
    candidates = []
    for idx in (move_idx, best_idx):
        rec = idx.get((eid, market, outcome))
        if rec:
            candidates.append(rec)
    # fallback for 1x2 aliases in best odds
    if not candidates and market != norm_market(sig.get("market")):
        market2 = norm_market(sig.get("market"))
        for idx in (move_idx, best_idx):
            rec = idx.get((eid, market2, outcome))
            if rec:
                candidates.append(rec)
    # fallback to displayed signal odds
    if not candidates:
        odds = fnum(sig.get("odds"))
        return {"odds": odds, "bookmaker": sig.get("bookmaker") or "signal", "source": "signal", "top_book": False, "movement": None}
    candidates.sort(key=lambda r: (0 if r.get("top_book") else 1, 0 if r.get("source") == "odds_movement" else 1))
    return candidates[0]


def clv_pct(entry_odds: Optional[float], close_odds: Optional[float]) -> Optional[float]:
    if not entry_odds or not close_odds or entry_odds <= 1 or close_odds <= 1:
        return None
    return round((entry_odds / close_odds - 1.0) * 100.0, 3)


def status_for_event(sig: Dict[str, Any], journal_idx: Dict[str, Dict[str, Any]]) -> Tuple[str, bool]:
    key = signal_key(sig)
    jr = journal_idx.get(key)
    if jr and str(jr.get("status") or "").lower() == "settled":
        return "closed", True
    start = parse_dt(sig.get("event_date"))
    if start and now_utc() >= start - timedelta(minutes=10):
        return "closing_window", True
    return "tracking", False


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    reliable = [r for r in rows if r.get("clv_reliable") and fnum(r.get("clv_pct")) is not None]
    all_clv = [fnum(r.get("clv_pct")) for r in rows if fnum(r.get("clv_pct")) is not None]
    rel_clv = [float(r["clv_pct"]) for r in reliable]
    pos = [x for x in rel_clv if x > 0]
    return {
        "total_picks": len(rows),
        "tracked_open": sum(1 for r in rows if r.get("entry_odds")),
        "reliable_n": len(reliable),
        "avg_clv_pct": round(statistics.mean(rel_clv), 3) if rel_clv else None,
        "avg_observed_clv_pct": round(statistics.mean([x for x in all_clv if x is not None]), 3) if all_clv else None,
        "market_beat_rate": round(len(pos) / len(rel_clv) * 100, 1) if rel_clv else None,
        "clv_positive_rate": round(len(pos) / len(rel_clv), 4) if rel_clv else None,
        "proxy_warning": len(reliable) < 20,
    }


def group(rows: List[Dict[str, Any]], key: str) -> Dict[str, Any]:
    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        buckets[str(r.get(key) or "unknown")].append(r)
    out = {}
    for k, vals in buckets.items():
        s = summarize(vals)
        s["sample"] = len(vals)
        out[k] = s
    return dict(sorted(out.items(), key=lambda kv: ((kv[1].get("market_beat_rate") or -1), kv[1].get("reliable_n") or 0), reverse=True))


def main() -> None:
    signals_payload = load_json(DATA / "signals.json", {"signals": []})
    signals = signals_payload.get("signals", []) if isinstance(signals_payload, dict) else []
    best_idx = build_best_odds_index(load_json(DATA / "best_odds.json", {}))
    move_idx = build_movement_index(load_json(DATA / "odds_movement.json", {}))
    previous = load_json(DATA / "clv_snapshots.json", {"items": []})
    prev_by_key = {r.get("key"): r for r in previous.get("items", []) if isinstance(r, dict) and r.get("key")}
    journal = load_json(DATA / "selection_journal.json", {})
    journal_idx = {str(r.get("key")): r for r in journal.get("results", []) if isinstance(r, dict) and r.get("key")}

    items: List[Dict[str, Any]] = []
    by_sig_key: Dict[str, Dict[str, Any]] = {}
    for sig in signals:
        key = signal_key(sig)
        prev = prev_by_key.get(key, {})
        entry = fnum(prev.get("entry_odds"), fnum(sig.get("odds")))
        first_seen = prev.get("first_seen_at") or sig.get("first_seen_at") or iso_now()
        cur = current_line(sig, best_idx, move_idx)
        current_odds = fnum(cur.get("odds"), entry)
        state, eligible = status_for_event(sig, journal_idx)
        existing_close = fnum(prev.get("closing_odds"))
        closing = existing_close if existing_close and prev.get("clv_reliable") else (current_odds if eligible else None)
        clv = clv_pct(entry, closing if closing else current_odds)
        reliable = bool(eligible and closing and cur.get("source") != "signal")
        if reliable and not cur.get("top_book"):
            # still usable, but not elite; keep reliable only if movement has a real previous/current delta
            reliable = cur.get("source") == "odds_movement" and fnum(cur.get("delta")) is not None
        rec = {
            "key": key,
            "event_id": sig.get("event_id"),
            "home_team": sig.get("home_team"),
            "away_team": sig.get("away_team"),
            "league": sig.get("league"),
            "league_id": sig.get("league_id"),
            "event_date": sig.get("event_date"),
            "market": canonical_market(sig.get("market")),
            "market_label": sig.get("market_label") or sig.get("market"),
            "outcome": outcome_for_market(sig.get("market"), sig),
            "entry_odds": round(entry, 4) if entry else None,
            "first_seen_at": first_seen,
            "last_seen_at": iso_now(),
            "current_odds": round(current_odds, 4) if current_odds else None,
            "current_bookmaker": cur.get("bookmaker"),
            "current_source": cur.get("source"),
            "closing_odds": round(closing, 4) if closing else None,
            "closing_source": cur.get("source") if closing else None,
            "closing_bookmaker": cur.get("bookmaker") if closing else None,
            "clv_pct": clv,
            "clv_positive": bool(clv is not None and clv > 0),
            "clv_reliable": reliable,
            "state": state,
            "top_bookmaker_line": bool(cur.get("top_book")),
            "movement": cur.get("movement"),
        }
        items.append(rec)
        by_sig_key[key] = rec

    # Preserve old records that are no longer in today's signals; they remain part of CLV history.
    seen = {r["key"] for r in items}
    for key, rec in prev_by_key.items():
        if key not in seen:
            items.append(rec)

    # Augment today's signals.
    for sig in signals:
        rec = by_sig_key.get(signal_key(sig), {})
        clv = fnum(rec.get("clv_pct"))
        reliable = bool(rec.get("clv_reliable"))
        sig["clv_observed_pct"] = clv
        sig["clv_beat_pct"] = clv if reliable else None
        sig["clv_state"] = rec.get("state") or "tracking"
        sig["clv_reliable"] = reliable
        sig["clv_badge"] = "CLV Beat" if reliable and clv is not None and clv > 0 else ("CLV Risk" if reliable and clv is not None and clv < 0 else "CLV Tracking")

    summary = summarize(items)
    rolling = [r for r in items if parse_dt(r.get("last_seen_at")) and parse_dt(r.get("last_seen_at")) >= now_utc() - timedelta(days=30)]
    payload = {
        "updated_at": iso_now(),
        "source": "betpredict_20_clv_value_engine",
        "method": "CLV% = entry_odds / closing_odds - 1. Positive value means BETPREDICT captured a better price than the closing market.",
        "summary": summary,
        "rolling_30d": summarize(rolling),
        "by_market": group(items, "market"),
        "by_league": group(items, "league"),
        "by_event_market": {r["key"]: r for r in items if r.get("event_id")},
        "diagnosis": {
            "label": "CLV reliable" if not summary.get("proxy_warning") else "CLV în acumulare",
            "short": "minimum 20 linii reliable" if summary.get("proxy_warning") else "sample suficient pentru market beat rate",
            "interpretation": "Nu crește miza doar pe ROI; urmărește Market Beat Rate/CLV+ pe minimum 20 de linii.",
        },
    }
    save_json(DATA / "clv_snapshots.json", {"updated_at": iso_now(), "count": len(items), "items": items})
    save_json(DATA / "clv_tracker.json", payload)
    if isinstance(signals_payload, dict):
        signals_payload["signals"] = signals
        signals_payload["count"] = len(signals)
        signals_payload["_clv_value_engine"] = {"updated_at": iso_now(), "tracked": len(signals), "reliable_n": summary.get("reliable_n")}
        save_json(DATA / "signals.json", signals_payload)
    print(f"[clv] tracked={len(signals)} total_history={len(items)} reliable={summary.get('reliable_n')}")


if __name__ == "__main__":
    main()
