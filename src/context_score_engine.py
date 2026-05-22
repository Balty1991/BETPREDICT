#!/usr/bin/env python3
"""
BETPREDICT Context Score Engine
--------------------------------
Sintetizează datele BSD contextuale (meteo, teren, lineups, player impact,
match intelligence) într-un scor simplu 0-100 și îl atașează semnalelor.

Output:
  data/context_scores.json
  data/signals.json       (adaugă context_score, context_adjustment_pp, context_summary)
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DEBUG = DATA / "debug"
DEBUG.mkdir(parents=True, exist_ok=True)


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


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def index_results(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for r in payload.get("results", []) if isinstance(payload, dict) else []:
        eid = r.get("event_id") or r.get("id")
        if eid is not None:
            out[str(eid)] = r
    return out


def lineup_confidence(ctx: Dict[str, Any], lineup_intel: Dict[str, Any]) -> Tuple[float, List[str]]:
    notes: List[str] = []
    score = 0.0
    status = (ctx.get("lineup_status") or lineup_intel.get("lineup_status") or "").lower()
    reliability = f(lineup_intel.get("reliability"), -1.0)

    if status == "confirmed":
        score += 10.0
        notes.append("echipe confirmate")
    elif status == "predicted":
        score += 4.0
        notes.append("lineup probabil")
    elif status:
        score += 1.0
        notes.append(f"lineup {status}")

    if reliability >= 0:
        score += clamp(reliability * 8.0, 0.0, 8.0)
        notes.append(f"reliability {round(reliability * 100)}%")

    # Dacă lineup-urile sunt foarte dezechilibrate, contextul devine mai riscant.
    delta = abs(f(lineup_intel.get("delta_score"), 0.0))
    if delta > 18:
        score -= 4.0
        notes.append("diferență mare în XI")
    elif delta > 10:
        score -= 2.0
        notes.append("diferență moderată în XI")

    return score, notes


def weather_adjustment(ctx: Dict[str, Any], market: str) -> Tuple[float, float, List[str]]:
    wc = ctx.get("weather_context") or {}
    detail = ctx.get("detail") or {}
    dw = detail.get("weather") or {}
    wind = f(wc.get("wind_speed", dw.get("wind_speed")), -1.0)
    temp = f(wc.get("temperature_c", dw.get("temperature_c")), -999.0)
    pitch = wc.get("pitch_condition", detail.get("pitch_condition"))
    label = str(wc.get("label") or dw.get("description") or "").lower()
    m = str(market or "").lower()
    score_delta = 0.0
    prob_adj = 0.0
    notes: List[str] = []

    if wind >= 34:
        score_delta -= 9.0
        if "over" in m:
            prob_adj -= 5.0
        if "under" in m:
            prob_adj += 2.0
        notes.append("vânt puternic")
    elif wind >= 24:
        score_delta -= 5.0
        if "over" in m:
            prob_adj -= 2.5
        notes.append("vânt moderat")

    if temp != -999.0:
        if temp <= 0 or temp >= 34:
            score_delta -= 3.0
            notes.append("temperatură extremă")

    bad_pitch = False
    if isinstance(pitch, str):
        bad_pitch = pitch.lower() in {"poor", "bad", "heavy", "wet"}
    elif isinstance(pitch, (int, float)):
        bad_pitch = f(pitch) >= 3.0
    if bad_pitch or any(x in label for x in ["heavy", "rain", "storm", "snow", "wet"]):
        score_delta -= 6.0
        if "over" in m:
            prob_adj -= 3.0
        if "under" in m:
            prob_adj += 2.0
        notes.append("teren/meteo dificil")

    if not notes:
        notes.append("meteo fără risc major")
    return score_delta, prob_adj, notes


def player_adjustment(player: Dict[str, Any], market: str) -> Tuple[float, float, List[str]]:
    if not player:
        return 0.0, 0.0, ["player impact neindexat"]
    notes: List[str] = []
    reliability = f(player.get("reliability"), 0.0)
    delta = f(player.get("delta_score"), 0.0)
    score_delta = clamp(reliability * 6.0, 0.0, 6.0)
    prob_adj = 0.0
    if abs(delta) > 12:
        score_delta -= 2.5
        notes.append("impact jucători dezechilibrat")
    elif reliability > 0:
        notes.append("player impact inclus")
    else:
        notes.append("player impact slab")
    return score_delta, prob_adj, notes


def match_intel_adjustment(mi: Dict[str, Any], market: str) -> Tuple[float, float, List[str]]:
    if not mi:
        return 0.0, 0.0, ["match intelligence lipsă"]
    rel = f(mi.get("reliability"), -1.0)
    score_delta = clamp(rel * 5.0, 0.0, 5.0) if rel >= 0 else 0.0
    prob_adj = 0.0
    market_key = str(market or "")
    goals_adj = mi.get("goals_market_adj") or {}
    if market_key in goals_adj:
        prob_adj += f(goals_adj.get(market_key), 0.0)
    align = mi.get("alignment") or ""
    return score_delta, prob_adj, [str(align).replace("_", " ")[:40] or "match intelligence neutru"]


def compute_for_signal(sig: Dict[str, Any], ctx_idx: Dict[str, Dict], lineup_idx: Dict[str, Dict], player_idx: Dict[str, Dict], match_idx: Dict[str, Dict]) -> Dict[str, Any]:
    eid = str(sig.get("event_id") or "")
    market = str(sig.get("market") or "")
    ctx = ctx_idx.get(eid, {})
    lineup = lineup_idx.get(eid, {})
    player = player_idx.get(eid, {})
    mi = match_idx.get(eid, {})

    base = 58.0
    notes: List[str] = []
    prob_adj = 0.0

    coverage = f(ctx.get("coverage_score"), 0.0)
    base += clamp(coverage * 3.0, 0.0, 14.0)
    if coverage:
        notes.append(f"coverage {round(coverage)}/5")

    ds, ln = lineup_confidence(ctx, lineup)
    base += ds; notes.extend(ln[:2])

    ds, pp, wn = weather_adjustment(ctx, market)
    base += ds; prob_adj += pp; notes.extend(wn[:1])

    ds, pp, pn = player_adjustment(player, market)
    base += ds; prob_adj += pp; notes.extend(pn[:1])

    ds, pp, mn = match_intel_adjustment(mi, market)
    base += ds; prob_adj += pp
    if mn and mn[0] not in {"no event match data", "match intelligence lipsă"}:
        notes.extend(mn[:1])

    # Calibrare simplă după market. Over-urile sunt mai sensibile la vreme/teren.
    if market in {"over25", "over15", "btts"} and prob_adj < 0:
        base += prob_adj * 0.75
    elif market.startswith("under") and prob_adj > 0:
        base += prob_adj * 0.5

    score = round(clamp(base, 1.0, 100.0), 1)
    adj = round(clamp(prob_adj, -12.0, 8.0), 2)
    label = "CONTEXT_OK" if score >= 75 else "CONTEXT_NEUTRU" if score >= 60 else "CONTEXT_RISC"

    # Scurtă sinteză, exact ce trebuie pe card.
    if adj <= -4:
        lead = f"Context scade piața cu {abs(adj):.1f}pp"
    elif adj >= 3:
        lead = f"Context susține piața cu +{adj:.1f}pp"
    else:
        lead = "Context fără abatere majoră"
    summary = lead + " · " + " · ".join(dict.fromkeys(notes[:3]))

    return {
        "event_id": eid,
        "home_team": sig.get("home_team"),
        "away_team": sig.get("away_team"),
        "market": market,
        "context_score": score,
        "context_adjustment_pp": adj,
        "context_label": label,
        "summary": summary,
        "drivers": list(dict.fromkeys(notes))[:8],
    }


def add_display_score(sig: Dict[str, Any], context_row: Dict[str, Any]) -> None:
    # Signal score pentru piața afișată, nu smartbet_score vechi 1X2.
    direct = f(sig.get("market_signal_score"), -1.0)
    if direct > 0:
        score = direct
    else:
        v6 = f(sig.get("smartbet_score_v6"), -1.0)
        if v6 > 0:
            score = v6
        else:
            p = f(sig.get("adj_prob"), 0.0)
            edge = f(sig.get("edge_pp"), 0.0)
            ev_txt = str(sig.get("ev_pct") or "0").replace("%", "")
            ev = f(ev_txt, 0.0)
            score = p * 0.68 + max(edge, 0.0) * 2.1 + max(ev, 0.0) * 0.75
            if sig.get("odds_real"):
                score += 4.0
            if str(sig.get("consensus_tier") or "").upper().startswith("TOTAL"):
                score += 4.0
    ctx_score = f(context_row.get("context_score"), 60.0)
    # context slab limitează puțin scorul final; context bun îl confirmă.
    score += (ctx_score - 65.0) * 0.08
    score = round(clamp(score, 1.0, 100.0), 1)
    sig["market_signal_score"] = score
    sig["display_score"] = score
    sig["display_grade"] = "A+" if score >= 90 else "A" if score >= 82 else "B" if score >= 74 else "C" if score >= 66 else "D" if score >= 55 else "E"


def main() -> int:
    signals_path = DATA / "signals.json"
    signals_data = load_json(signals_path, {})
    signals: List[Dict[str, Any]] = signals_data.get("signals", []) if isinstance(signals_data, dict) else []

    ctx_idx = index_results(load_json(DATA / "match_context.json", {}))
    lineup_idx = index_results(load_json(DATA / "lineup_intelligence.json", {}))
    player_idx = index_results(load_json(DATA / "player_impact.json", {}))
    match_idx = index_results(load_json(DATA / "event_match_intelligence.json", {}))

    rows: List[Dict[str, Any]] = []
    by_event: Dict[str, Dict[str, Any]] = {}
    enriched: List[Dict[str, Any]] = []
    for sig in signals:
        row = compute_for_signal(sig, ctx_idx, lineup_idx, player_idx, match_idx)
        rows.append(row)
        eid = row["event_id"]
        # păstrează cea mai bună sinteză per eveniment pentru UI
        current = by_event.get(eid)
        if current is None or f(row.get("context_score")) > f(current.get("context_score")):
            by_event[eid] = row
        ns = dict(sig)
        ns["context_score"] = row["context_score"]
        ns["context_adjustment_pp"] = row["context_adjustment_pp"]
        ns["context_label"] = row["context_label"]
        ns["context_summary"] = row["summary"]
        add_display_score(ns, row)
        enriched.append(ns)

    # re-sortează după scorul real de piață; nu după smartbet_score vechi care poate fi 0
    enriched.sort(key=lambda s: (f(s.get("display_score")), f(s.get("edge_pp"))), reverse=True)
    signals_data["signals"] = enriched
    signals_data["count"] = len(enriched)
    by_strategy: Dict[str, List[Dict[str, Any]]] = {}
    for sig in enriched:
        by_strategy.setdefault(sig.get("strategy") or "unknown", []).append(sig)
    signals_data["by_strategy"] = by_strategy
    for k, items in by_strategy.items():
        avg = sum(f(x.get("display_score")) for x in items) / max(len(items), 1)
        signals_data.setdefault("strategy_stats", {}).setdefault(k, {})["avg_score"] = round(avg, 1)
        signals_data["strategy_stats"][k]["count"] = len(items)
    signals_data["_context_score_enhanced"] = True
    signals_data["_context_score_updated_at"] = now_iso()
    save_json(signals_path, signals_data)

    summary = {
        "count": len(rows),
        "avg_context_score": round(sum(f(r.get("context_score")) for r in rows) / max(len(rows), 1), 2),
        "context_ok": sum(1 for r in rows if f(r.get("context_score")) >= 75),
        "context_risk": sum(1 for r in rows if f(r.get("context_score")) < 60),
    }
    payload = {
        "updated_at": now_iso(),
        "source": "match_context + lineup_intelligence + player_impact + event_match_intelligence",
        "summary": summary,
        "count": len(rows),
        "results": rows,
        "by_event": by_event,
        "_pipeline_version": "context-score-v1",
    }
    save_json(DATA / "context_scores.json", payload)
    save_json(DEBUG / "context_score_debug.json", {"updated_at": payload["updated_at"], "summary": summary, "sample": rows[:10]})
    print(f"[context-score] enhanced={len(enriched)} avg={summary['avg_context_score']} ok={summary['context_ok']} risk={summary['context_risk']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
