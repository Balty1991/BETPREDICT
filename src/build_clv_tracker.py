#!/usr/bin/env python3
"""
BETPREDICT CLV Tracker
----------------------
Construiește data/clv_tracker.json din selection_journal.json și ultimele cote
cunoscute din best_odds.json / odds_movement.json. Preferă closing proxy de la
Pinnacle/Bet365 când există.

Notă: fără feed istoric complet de closing line, acesta este un CLV proxy.
Câmpul clv_reliable marchează cazurile cu mișcare reală a liniei.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DEBUG = DATA / "debug"
DEBUG.mkdir(parents=True, exist_ok=True)
PREFERRED = ("pinnacle", "bet365")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def f(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
        return default if math.isnan(x) or math.isinf(x) else x
    except Exception:
        return default


def parse_dt(s: Any) -> Optional[datetime]:
    if not s:
        return None
    try:
        raw = str(s).replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def canonical_market(m: Any) -> str:
    x = str(m or "").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "1": "homewin", "home": "homewin", "homewin": "homewin", "home_win": "homewin",
        "x": "draw", "draw": "draw",
        "2": "awaywin", "away": "awaywin", "awaywin": "awaywin", "away_win": "awaywin",
        "over_1_5": "over15", "over15": "over15", "over_under_15_over": "over15",
        "under_1_5": "under15", "under15": "under15", "over_under_15_under": "under15",
        "over_2_5": "over25", "over25": "over25", "over_under_25_over": "over25",
        "under_2_5": "under25", "under25": "under25", "over_under_25_under": "under25",
        "over_3_5": "over35", "over35": "over35", "over_under_35_over": "over35",
        "under_3_5": "under35", "under35": "under35", "over_under_35_under": "under35",
        "btts": "btts", "btts_yes": "btts", "yes": "btts",
    }
    return aliases.get(x, x.replace("_", ""))


def best_market_and_outcome(market: str) -> Tuple[str, str]:
    mk = canonical_market(market)
    if mk == "homewin": return "1x2", "HOME"
    if mk == "draw": return "1x2", "DRAW"
    if mk == "awaywin": return "1x2", "AWAY"
    if mk == "over15": return "over_under_15", "over"
    if mk == "under15": return "over_under_15", "under"
    if mk == "over25": return "over_under_25", "over"
    if mk == "under25": return "over_under_25", "under"
    if mk == "over35": return "over_under_35", "over"
    if mk == "under35": return "over_under_35", "under"
    if mk == "btts": return "btts", "YES"
    return mk, ""


def choose_price(prices: Iterable[Dict[str, Any]], outcome: str) -> Optional[Dict[str, Any]]:
    candidates = []
    out = outcome.lower()
    for p in prices or []:
        po = str(p.get("outcome") or p.get("outcome_name") or "").lower()
        if out and po != out:
            continue
        odd = f(p.get("decimal_odds"), 0.0)
        if odd <= 1.01:
            continue
        bk = str(p.get("bookmaker_slug") or p.get("bookmaker") or "").lower()
        pref = 0 if bk in PREFERRED else 1
        updated = parse_dt(p.get("updated_at")) or datetime(1970, 1, 1, tzinfo=timezone.utc)
        candidates.append((pref, -updated.timestamp(), p))
    if not candidates:
        return None
    return sorted(candidates, key=lambda x: (x[0], x[1]))[0][2]


def build_best_odds_index() -> Dict[Tuple[str, str], Dict[str, Any]]:
    payload = load_json(DATA / "best_odds.json", {})
    idx: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for r in payload.get("results", []) if isinstance(payload, dict) else []:
        eid = str(r.get("event_id") or "")
        market = str(r.get("market") or r.get("_market") or "")
        if not eid or not market:
            continue
        for outcome in ("HOME", "DRAW", "AWAY", "over", "under", "YES", "NO"):
            price = choose_price(r.get("best_odds") or [], outcome)
            if price:
                idx[(eid, market, outcome.lower())] = price
    return idx


def build_movement_index() -> Dict[Tuple[str, str], Dict[str, Any]]:
    payload = load_json(DATA / "odds_movement.json", {})
    idx: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for r in payload.get("results", []) if isinstance(payload, dict) else []:
        eid = str(r.get("event_id") or "")
        m = canonical_market(r.get("market"))
        odd = f(r.get("decimal_odds"), 0.0)
        if eid and m and odd > 1.01:
            idx[(eid, m)] = r
    return idx


def closing_price(eid: str, market: str, best_idx: Dict, move_idx: Dict) -> Tuple[Optional[float], str, str]:
    bm, outcome = best_market_and_outcome(market)
    price = best_idx.get((eid, bm, outcome.lower()))
    if price:
        return f(price.get("decimal_odds"), 0.0), str(price.get("bookmaker_slug") or price.get("bookmaker_name") or "bookmaker"), "best_odds_proxy"
    mv = move_idx.get((eid, canonical_market(market)))
    if mv:
        return f(mv.get("decimal_odds"), 0.0), str(mv.get("bookmaker") or "movement"), "odds_movement_proxy"
    return None, "", "missing"


def clv_pct(picked: float, closing: float) -> Optional[float]:
    if picked <= 1.01 or closing <= 1.01:
        return None
    return round(((1.0 / closing) - (1.0 / picked)) / (1.0 / picked) * 100.0, 4)


def ev_at_pick(prob: float, odds: float) -> Optional[float]:
    p = prob / 100.0 if prob > 1.0 else prob
    if p <= 0 or odds <= 1.01:
        return None
    return round((p * odds - 1.0) * 100.0, 4)


def process(row: Dict[str, Any], best_idx: Dict, move_idx: Dict) -> Optional[Dict[str, Any]]:
    status = str(row.get("status") or "").lower()
    result = str(row.get("result") or "").upper()
    if status != "settled" and result not in {"WIN", "LOST", "LOSE"}:
        return None
    picked = f(row.get("opening_odds") or row.get("picked_odds") or row.get("odds"), 0.0)
    if picked <= 1.01:
        return None
    eid = str(row.get("event_id") or "")
    market = canonical_market(row.get("market") or row.get("market_canonical"))
    closing, bookmaker, source = closing_price(eid, market, best_idx, move_idx)
    if not closing or closing <= 1.01:
        closing = picked
        source = "no_closing_available_static_proxy"
    c = clv_pct(picked, closing)
    if c is None:
        return None
    won = result == "WIN" or f(row.get("profit_units"), -1.0) > 0
    line_move = round(((closing - picked) / picked) * 100.0, 4) if picked else 0.0
    reliable = abs(line_move) >= 0.5 and source != "no_closing_available_static_proxy"
    model_prob = f(row.get("model_probability") or row.get("adjusted_prob"), 0.0)
    ev = ev_at_pick(model_prob, picked)
    return {
        "event_id": eid,
        "date": (row.get("event_date") or row.get("settled_at") or row.get("last_seen_at") or "")[:10],
        "home": row.get("home_team") or row.get("home") or "",
        "away": row.get("away_team") or row.get("away") or "",
        "league": row.get("league") or "",
        "market": market,
        "market_label": row.get("market_label") or market,
        "picked_odds": round(picked, 4),
        "closing_odds": round(closing, 4),
        "closing_bookmaker": bookmaker,
        "closing_source": source,
        "clv_pct": c,
        "clv_positive": c > 0,
        "clv_reliable": reliable,
        "line_move_pct": line_move,
        "model_prob": round(model_prob, 4),
        "ev_at_pick_pct": ev,
        "score": f(row.get("score"), 0.0),
        "won": won,
        "status": "WIN" if won else "LOST",
        "settled_at": row.get("settled_at") or "",
    }


def roi(picks: List[Dict[str, Any]], use_closing: bool = False) -> float:
    if not picks: return 0.0
    profit = 0.0
    for p in picks:
        odds = f(p.get("closing_odds" if use_closing else "picked_odds"), 0.0)
        profit += odds - 1.0 if p.get("won") else -1.0
    return round(profit / len(picks) * 100.0, 4)


def stats(picks: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not picks:
        return {"total_picks": 0, "clv_positive_rate": 0.0, "avg_clv_pct": None, "roi_flat_pct": 0.0, "win_rate_pct": 0.0}
    vals = [f(p.get("clv_pct")) for p in picks]
    pos = [p for p in picks if f(p.get("clv_pct")) > 0]
    rel = [p for p in picks if p.get("clv_reliable")]
    wins = [p for p in picks if p.get("won")]
    return {
        "total_picks": len(picks),
        "avg_clv_pct": round(mean(vals), 4),
        "median_clv_pct": round(median(vals), 4),
        "clv_positive_n": len(pos),
        "clv_negative_n": len(picks)-len(pos),
        "clv_positive_rate": round(len(pos)/len(picks), 4),
        "win_rate_pct": round(len(wins)/len(picks)*100.0, 2),
        "roi_flat_pct": roi(picks),
        "roi_flat_closing_proxy_pct": roi(picks, use_closing=True),
        "avg_clv_wins": round(mean([f(p.get("clv_pct")) for p in wins]) if wins else 0.0, 4),
        "avg_clv_losses": round(mean([f(p.get("clv_pct")) for p in picks if not p.get("won")]) if len(wins)<len(picks) else 0.0, 4),
        "max_clv_pct": round(max(vals), 4),
        "min_clv_pct": round(min(vals), 4),
        "std_clv_pct": round(pstdev(vals), 4) if len(vals)>1 else 0.0,
        "reliable_n": len(rel),
        "reliable_pct": round(len(rel)/len(picks), 4),
        "avg_clv_reliable": round(mean([f(p.get("clv_pct")) for p in rel]), 4) if rel else None,
        "clv_positive_rate_reliable": round(sum(1 for p in rel if f(p.get("clv_pct")) > 0) / len(rel), 4) if rel else None,
        "roi_reliable_pct": roi(rel) if rel else None,
        "proxy_warning": len(rel) < max(5, len(picks)*0.25),
    }


def by_market(picks: List[Dict[str, Any]]) -> Dict[str, Any]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for p in picks: groups[str(p.get("market") or "unknown")].append(p)
    out: Dict[str, Any] = {}
    for mk, items in sorted(groups.items()):
        st = stats(items)
        out[mk] = {
            "n": len(items),
            "avg_clv_pct": st.get("avg_clv_pct"),
            "median_clv_pct": st.get("median_clv_pct"),
            "clv_positive_rate": st.get("clv_positive_rate"),
            "win_rate_pct": st.get("win_rate_pct"),
            "roi_flat_pct": st.get("roi_flat_pct"),
            "reliable_n": st.get("reliable_n"),
        }
    return out


def buckets(picks: List[Dict[str, Any]]) -> Dict[str, Any]:
    rules = {
        "clv_strong_pos": lambda c: c >= 5.0,
        "clv_mild_pos": lambda c: 0.0 < c < 5.0,
        "clv_neutral": lambda c: -1.0 <= c <= 0.0,
        "clv_mild_neg": lambda c: -5.0 < c < -1.0,
        "clv_strong_neg": lambda c: c <= -5.0,
    }
    out: Dict[str, Any] = {}
    for name, fn in rules.items():
        items = [p for p in picks if fn(f(p.get("clv_pct")))]
        out[name] = {"n": len(items), "avg_clv": round(mean([f(p.get("clv_pct")) for p in items]), 4) if items else 0.0, "win_rate": round(sum(1 for p in items if p.get("won"))/len(items)*100,2) if items else 0.0, "roi_pct": roi(items) if items else 0.0}
    return out


def rolling(picks: List[Dict[str, Any]], days: int) -> Dict[str, Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    recent = []
    for p in picks:
        dt = parse_dt(p.get("date") or p.get("settled_at"))
        if dt and dt >= cutoff:
            recent.append(p)
    st = stats(recent)
    return {"days": days, "n": len(recent), "avg_clv_pct": st.get("avg_clv_pct"), "clv_positive_rate": st.get("clv_positive_rate"), "win_rate_pct": st.get("win_rate_pct"), "roi_flat_pct": st.get("roi_flat_pct")}


def diagnosis(summary: Dict[str, Any], r30: Dict[str, Any]) -> Dict[str, Any]:
    n = int(summary.get("total_picks") or 0)
    avg = f(summary.get("avg_clv_pct"), 0.0)
    roi_v = f(summary.get("roi_flat_pct"), 0.0)
    rate = f(summary.get("clv_positive_rate"), 0.0)
    reliable_n = int(summary.get("reliable_n") or 0)
    if n < 20 or reliable_n < 20:
        return {"signal": "INSUFFICIENT_DATA", "label": "CLV proxy", "short": "closing line insuficient", "confidence": "low", "interpretation": "CLV este activ, dar nu există încă minim 20 linii cu mișcare reală closing/opening. Valorile statice nu confirmă edge-ul.", "action": "Continuă logarea pick-urilor și verifică periodic când best_odds/odds_movement oferă closing real.", "reliable_n": reliable_n}
    if avg >= 0.5 and roi_v >= 0:
        sig = "CLV_POSITIVE_ROI_POSITIVE"; lab = "edge confirmat"; conf = "high"
        txt = f"Modelul bate closing proxy: CLV mediu {avg:+.2f}%, ROI flat {roi_v:+.2f}%, CLV+ rate {rate*100:.1f}%."
        act = "Poți prioritiza piețele cu CLV+ și ROI+; menține stake disciplinat."
    elif avg >= 0.5:
        sig = "CLV_POSITIVE_ROI_NEGATIVE"; lab = "edge matematic, variance"; conf = "medium"
        txt = f"CLV este pozitiv ({avg:+.2f}%), dar ROI este {roi_v:+.2f}%. Edge-ul există, conversia încă nu."
        act = "Nu opri modelul; cere volum mai mare și filtrează piețele negative."
    elif roi_v > 0:
        sig = "CLV_NEGATIVE_ROI_POSITIVE"; lab = "ROI posibil variance"; conf = "medium"
        txt = f"ROI este pozitiv ({roi_v:+.2f}%), dar CLV mediu este {avg:+.2f}%. Piața nu confirmă încă avantajul."
        act = "Nu crește stake-ul până CLV devine pozitiv."
    else:
        sig = "CLV_NEGATIVE_ROI_NEGATIVE"; lab = "fără edge confirmat"; conf = "high"
        txt = f"CLV {avg:+.2f}% și ROI {roi_v:+.2f}%. Modelul trebuie restrâns pe filtre mai stricte."
        act = "Coboară expunerea și păstrează doar scoruri/edge premium."
    trend = "stabil"
    if r30.get("avg_clv_pct") is not None:
        trend = "în creștere" if f(r30.get("avg_clv_pct")) > avg + 1 else "în scădere" if f(r30.get("avg_clv_pct")) < avg - 1 else "stabil"
    return {"signal": sig, "label": lab, "short": lab, "confidence": conf, "rolling_trend": trend, "interpretation": txt, "action": act, "clv_positive_rate": rate}


def main() -> int:
    journal = load_json(DATA / "selection_journal.json", {})
    rows = journal.get("results", []) if isinstance(journal, dict) else []
    best_idx = build_best_odds_index()
    move_idx = build_movement_index()
    picks = [p for p in (process(r, best_idx, move_idx) for r in rows) if p]
    picks.sort(key=lambda p: (p.get("date") or "", p.get("event_id") or ""), reverse=True)
    s = stats(picks)
    r30, r90 = rolling(picks, 30), rolling(picks, 90)
    payload = {
        "updated_at": now_iso(),
        "source": "selection_journal + best_odds/odds_movement closing proxy",
        "method_note": "CLV proxy: preferă Pinnacle/Bet365 din best_odds când există; altfel folosește ultima cotă cunoscută. clv_reliable=true doar când linia s-a mișcat >=0.5%.",
        "summary": s,
        "diagnosis": diagnosis(s, r30),
        "rolling_30d": r30,
        "rolling_90d": r90,
        "by_market": by_market(picks),
        "clv_buckets": buckets(picks),
        "picks": picks[:500],
        "_pipeline_version": "clv-proxy-v1",
    }
    save_json(DATA / "clv_tracker.json", payload)
    save_json(DEBUG / "clv_tracker_debug.json", {"updated_at": payload["updated_at"], "summary": s, "sample": picks[:10], "best_idx": len(best_idx), "move_idx": len(move_idx)})
    print(f"[clv] picks={len(picks)} avg={s.get('avg_clv_pct')} rate={s.get('clv_positive_rate')} roi={s.get('roi_flat_pct')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
