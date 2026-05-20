#!/usr/bin/env python3
"""BetPredict Player Impact Engine v2.

v2 adaugă fallback pe data/team_squads.json, ca blocul Player Impact să nu fie
"date insuficiente" pentru aproape toate meciurile atunci când player_intelligence
are doar câțiva jucători îmbogățiți.

Design sigur:
- fără API calls;
- fără dependențe externe;
- idempotent;
- folosește player_intelligence pentru impact puternic și team_squads pentru coverage parțial;
- bonus SmartBet plafonat la +2.5 și aplicat doar când datele sunt suficient de fiabile;
- regenerează fișierele dependente după actualizarea predictions.json.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DEBUG_DIR = DATA_DIR / "debug"
VERSION = "player_impact_v2"

for p in (ROOT, ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def quality_from_score(score: float) -> str:
    s = num(score, 0)
    if s >= 92:
        return "A+"
    if s >= 82:
        return "A"
    if s >= 75:
        return "B+"
    if s >= 65:
        return "B"
    if s >= 55:
        return "C"
    if s >= 45:
        return "D"
    return "E"


def avg(values: List[float], default: Optional[float] = None) -> Optional[float]:
    vals = [v for v in values if isinstance(v, (int, float)) and math.isfinite(v)]
    return sum(vals) / len(vals) if vals else default


def player_id(row: Dict[str, Any]) -> str:
    prof = row.get("profile") if isinstance(row.get("profile"), dict) else {}
    return str(row.get("player_id") or row.get("id") or prof.get("player_id") or prof.get("id") or "")


def team_id(row: Dict[str, Any]) -> str:
    prof = row.get("profile") if isinstance(row.get("profile"), dict) else {}
    return str(row.get("current_team_id") or row.get("team_id") or row.get("_team_id") or prof.get("current_team_id") or prof.get("team_id") or "")


def player_name(row: Dict[str, Any]) -> str:
    prof = row.get("profile") if isinstance(row.get("profile"), dict) else {}
    return str(prof.get("short_name") or row.get("short_name") or row.get("name") or prof.get("name") or "—")


def availability_factor(row: Dict[str, Any]) -> float:
    prof = row.get("profile") if isinstance(row.get("profile"), dict) else {}
    raw = str(row.get("availability") or prof.get("availability") or "").lower()
    if not raw:
        return 0.92 if row.get("_source") == "team_squads" else 0.85
    if any(x in raw for x in ("injur", "suspend", "unavailable", "out", "doubt")):
        return 0.25
    if any(x in raw for x in ("bench", "question", "limited")):
        return 0.65
    return 1.0


def position_prior(pos: Any) -> float:
    p = str(pos or "").upper().strip()
    if p.startswith("F") or p in {"ST", "CF", "LW", "RW", "AM"}:
        return 50.0
    if p.startswith("M") or p in {"DM", "CM", "LM", "RM"}:
        return 45.0
    if p.startswith("D") or p in {"CB", "LB", "RB", "LWB", "RWB"}:
        return 41.0
    if p.startswith("G") or p == "GK":
        return 37.0
    return 39.0


def stats_summary(row: Dict[str, Any]) -> Dict[str, float]:
    stats = row.get("stats_preview") if isinstance(row.get("stats_preview"), list) else []
    minutes = sum(num(s.get("minutes_played"), 0) for s in stats if isinstance(s, dict))
    ratings = [num(s.get("rating"), float("nan")) for s in stats if isinstance(s, dict) and s.get("rating") is not None]
    goals = sum(num(s.get("goals"), 0) for s in stats if isinstance(s, dict))
    assists = sum(num(s.get("goal_assist", s.get("assists")), 0) for s in stats if isinstance(s, dict))
    key_passes = sum(num(s.get("key_pass"), 0) for s in stats if isinstance(s, dict))
    shots_on_target = sum(num(s.get("shots_on_target"), 0) for s in stats if isinstance(s, dict))
    tackles = sum(num(s.get("total_tackle"), 0) for s in stats if isinstance(s, dict))
    interceptions = sum(num(s.get("interception"), 0) for s in stats if isinstance(s, dict))
    return {
        "sample": float(len(stats)),
        "minutes": float(minutes),
        "rating": avg(ratings, 6.4) or 6.4,
        "goals": float(goals),
        "assists": float(assists),
        "key_passes": float(key_passes),
        "shots_on_target": float(shots_on_target),
        "def_actions": float(tackles + interceptions),
    }


def player_score(row: Dict[str, Any]) -> Dict[str, Any]:
    prof = row.get("profile") if isinstance(row.get("profile"), dict) else {}
    s = stats_summary(row)
    pos = row.get("specific_position") or row.get("position") or prof.get("specific_position") or prof.get("position")
    mv = max(0.0, num(row.get("market_value_eur") or prof.get("market_value_eur"), 0))
    avail = availability_factor(row)

    has_stats = s["sample"] > 0
    has_market = mv > 0

    if has_stats or has_market:
        rating_score = clamp((s["rating"] - 5.8) / 1.8, 0.0, 1.0)
        minutes_score = clamp(s["minutes"] / 450.0, 0.0, 1.0)
        production_score = clamp(
            (s["goals"] * 0.75 + s["assists"] * 0.60 + s["shots_on_target"] * 0.08 + s["key_passes"] * 0.055 + s["def_actions"] * 0.025) / 6.0,
            0.0,
            1.0,
        )
        market_score = clamp((math.log10(max(mv, 50000.0)) - math.log10(50000.0)) / 2.3, 0.0, 1.0)
        score = 100.0 * (rating_score * 0.40 + minutes_score * 0.25 + market_score * 0.22 + production_score * 0.13) * avail
        data_quality = clamp(0.25 + clamp(s["sample"] / 12.0, 0.0, 1.0) * 0.55 + (0.20 if has_market else 0.0), 0.0, 1.0)
    else:
        # Fallback din squad: util pentru coverage, dar cu fiabilitate mică.
        score = position_prior(pos) * avail
        data_quality = 0.14

    return {
        "player_id": row.get("player_id") or row.get("id") or prof.get("player_id") or prof.get("id"),
        "name": player_name(row),
        "position": pos,
        "team_id": team_id(row),
        "score": round(score, 2),
        "rating": round(s["rating"], 2),
        "minutes": int(s["minutes"]),
        "goals": int(s["goals"]),
        "assists": int(s["assists"]),
        "stats_sample": int(s["sample"]),
        "market_value_eur": int(mv) if mv else 0,
        "availability_factor": round(avail, 2),
        "data_quality": round(data_quality, 3),
        "source": row.get("_source") or "player_intelligence",
    }


def build_team_index(players: List[Dict[str, Any]], team_squads_payload: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Index pe echipe. player_intelligence suprascrie fallback-ul din team_squads."""
    by_team_player: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def add_row(row: Dict[str, Any], force_source: Optional[str] = None, team_hint: Any = None) -> None:
        if not isinstance(row, dict):
            return
        r = dict(row)
        if force_source:
            r["_source"] = force_source
        if team_hint is not None and not team_id(r):
            r["_team_id"] = team_hint
        tid = team_id(r)
        pid = player_id(r)
        if not tid or not pid:
            return
        scored = player_score(r)
        current = by_team_player.setdefault(tid, {}).get(pid)
        if current is None or num(scored.get("data_quality"), 0) >= num(current.get("data_quality"), 0):
            by_team_player[tid][pid] = scored

    # fallback larg: toți jucătorii din squads deja descărcați de team_intelligence
    for team in team_squads_payload.get("results", []) if isinstance(team_squads_payload, dict) else []:
        tid = team.get("team_id")
        for p in team.get("players", []) if isinstance(team, dict) else []:
            add_row(p, force_source="team_squads", team_hint=tid)

    # date îmbogățite: suprascriu fallback-ul unde există
    for row in players:
        add_row(row, force_source="player_intelligence")

    idx: Dict[str, List[Dict[str, Any]]] = {tid: list(rows.values()) for tid, rows in by_team_player.items()}
    for tid in list(idx):
        idx[tid].sort(key=lambda x: x.get("score") or 0, reverse=True)
    return idx


def team_strength(team_players: List[Dict[str, Any]]) -> Dict[str, Any]:
    top = team_players[:6]
    if not top:
        return {"available": False, "partial": False, "score": 0.0, "reliability": 0.0, "players_indexed": 0, "avg_rating": None, "top_players": []}

    weights = [1.00, 0.92, 0.84, 0.76, 0.68, 0.60]
    total_w = sum(weights[: len(top)])
    weighted = sum((p.get("score") or 0) * weights[i] for i, p in enumerate(top)) / max(total_w, 1e-9)
    avg_rating = avg([num(p.get("rating"), float("nan")) for p in top], None)
    avg_sample = avg([num(p.get("stats_sample"), 0) for p in top], 0.0) or 0.0
    avg_quality = avg([num(p.get("data_quality"), 0) for p in top], 0.0) or 0.0
    enriched_count = sum(1 for p in top if p.get("source") == "player_intelligence")
    player_cov = clamp(len(top) / 6.0, 0.0, 1.0)
    reliability = clamp(player_cov * 0.20 + avg_quality * 0.70 + clamp(enriched_count / 4.0, 0, 1) * 0.10, 0.0, 1.0)
    partial = reliability < 0.45

    return {
        "available": True,
        "partial": partial,
        "score": round(weighted, 2),
        "reliability": round(reliability, 3),
        "players_indexed": len(team_players),
        "top_used": len(top),
        "enriched_top_players": enriched_count,
        "avg_rating": round(avg_rating, 2) if avg_rating is not None else None,
        "avg_stats_sample": round(avg_sample, 2),
        "avg_data_quality": round(avg_quality, 3),
        "top_players": top[:5],
    }


def best_1x2(pred: Dict[str, Any]) -> str:
    vals = {
        "home": num(pred.get("ctx_home_win", pred.get("blended_home", pred.get("home_win_probability"))), 0),
        "draw": num(pred.get("ctx_draw", pred.get("blended_draw", pred.get("draw_probability"))), 0),
        "away": num(pred.get("ctx_away_win", pred.get("blended_away", pred.get("away_win_probability"))), 0),
    }
    return max(vals.items(), key=lambda kv: kv[1])[0]


def current_base_score(pred: Dict[str, Any]) -> float:
    current = num(pred.get("smartbet_score"), 0)
    previous_base = pred.get("smartbet_score_before_player_impact")
    previous_bonus = num(pred.get("player_impact_bonus"), 0)
    if previous_base is not None:
        before = num(previous_base, current)
        if abs(current - (before + previous_bonus)) <= 0.08:
            return before
    return current


def compute_match_impact(pred: Dict[str, Any], team_idx: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    ev = pred.get("event") if isinstance(pred.get("event"), dict) else {}
    hid = str(ev.get("home_team_id") or "")
    aid = str(ev.get("away_team_id") or "")
    h = team_strength(team_idx.get(hid, []))
    a = team_strength(team_idx.get(aid, []))
    available = bool(h.get("available") and a.get("available"))
    reliability = min(num(h.get("reliability"), 0), num(a.get("reliability"), 0)) if available else 0.0
    partial = bool(available and (h.get("partial") or a.get("partial") or reliability < 0.45))

    raw_delta = num(h.get("score"), 0) - num(a.get("score"), 0)
    normalized_delta = clamp(raw_delta / 25.0, -1.0, 1.0)
    home_pp = clamp(normalized_delta * reliability * 2.0, -2.0, 2.0)
    away_pp = -home_pp
    draw_pp = -abs(home_pp) * 0.20

    best = best_1x2(pred)
    aligned = (best == "home" and home_pp > 0.15) or (best == "away" and away_pp > 0.15)
    contradiction = (best == "home" and home_pp < -0.35) or (best == "away" and away_pp < -0.35)

    # Bonus doar când avem date reale, nu doar fallback squad.
    smartbet_bonus = clamp(abs(home_pp) * 1.15, 0.0, 2.5) if available and aligned and reliability >= 0.45 else 0.0

    if not available:
        label = "insufficient_player_data"
    elif partial:
        label = "partial_squad_data"
    elif contradiction:
        label = "contradicts_main_side"
    elif aligned:
        label = "supports_main_side"
    else:
        label = "neutral"

    return {
        "available": available,
        "partial": partial,
        "source": VERSION,
        "home_team_id": ev.get("home_team_id"),
        "away_team_id": ev.get("away_team_id"),
        "home_team": ev.get("home_team"),
        "away_team": ev.get("away_team"),
        "home": h,
        "away": a,
        "delta_score": round(raw_delta, 2),
        "normalized_delta": round(normalized_delta, 3),
        "reliability": round(reliability, 3),
        "best_1x2": best,
        "alignment": label,
        "adjustment_pp": {"home": round(home_pp, 3), "draw": round(draw_pp, 3), "away": round(away_pp, 3)},
        "smartbet_bonus": round(smartbet_bonus, 2),
    }


def regenerate_dependents() -> Dict[str, Any]:
    report = {"signals": False, "value_bets": False, "selection_journal": False, "performance_summary": False, "qa_report": False, "errors": []}
    try:
        import fetch_daily as fd  # noqa: WPS433
    except Exception as exc:
        report["errors"].append(f"fetch_daily import failed: {exc}")
        return report
    steps = [
        ("signals", getattr(fd, "compute_signals", None)),
        ("value_bets", getattr(fd, "_compute_value_bets_local", None)),
        ("selection_journal", getattr(fd, "update_selection_journal", None)),
        ("performance_summary", getattr(fd, "compute_performance_summary", None)),
        ("qa_report", getattr(fd, "fetch_production_qa_report", None)),
    ]
    for name, fn in steps:
        if not callable(fn):
            report["errors"].append(f"{name}: function missing")
            continue
        try:
            fn()
            report[name] = True
        except Exception as exc:
            report["errors"].append(f"{name}: {exc}")
            print(f"  ⚠ player_impact regenerate {name} failed: {exc}")
    return report


def main() -> int:
    pred_path = DATA_DIR / "predictions.json"
    preds_payload = read_json(pred_path, {})
    players_payload = read_json(DATA_DIR / "player_intelligence.json", {})
    team_squads_payload = read_json(DATA_DIR / "team_squads.json", {})
    preds = preds_payload.get("results") if isinstance(preds_payload, dict) else None
    players = players_payload.get("results") if isinstance(players_payload, dict) else []

    if not isinstance(preds, list):
        write_json(DEBUG_DIR / "player_impact_debug.json", {"updated_at": now_iso(), "source": VERSION, "error": "missing_predictions"})
        print("Player Impact: predictions.json missing/invalid; skip")
        return 0
    if not isinstance(players, list):
        players = []

    team_idx = build_team_index(players, team_squads_payload)
    rows: List[Dict[str, Any]] = []
    enriched: List[Dict[str, Any]] = []
    boosted = 0
    available = 0
    partial = 0
    max_bonus = 0.0

    for pred in preds:
        if not isinstance(pred, dict):
            enriched.append(pred)
            continue
        impact = compute_match_impact(pred, team_idx)
        base = current_base_score(pred)
        bonus = num(impact.get("smartbet_bonus"), 0)
        new_score = clamp(base + bonus, 0.0, 100.0)
        pred["player_impact"] = impact
        pred["smartbet_score_before_player_impact"] = round(base, 2)
        pred["player_impact_bonus"] = round(bonus, 2)
        pred["smartbet_score"] = round(new_score, 2)
        pred["quality_grade"] = quality_from_score(new_score)
        pred["_player_impact_engine"] = VERSION
        if impact.get("available"):
            available += 1
        if impact.get("partial"):
            partial += 1
        if bonus > 0:
            boosted += 1
            max_bonus = max(max_bonus, bonus)
        ev = pred.get("event") if isinstance(pred.get("event"), dict) else {}
        rows.append({
            "event_id": ev.get("id"),
            "match": f"{ev.get('home_team', '—')} vs {ev.get('away_team', '—')}",
            "available": impact.get("available"),
            "partial": impact.get("partial"),
            "home_score": impact.get("home", {}).get("score"),
            "away_score": impact.get("away", {}).get("score"),
            "home_players_indexed": impact.get("home", {}).get("players_indexed"),
            "away_players_indexed": impact.get("away", {}).get("players_indexed"),
            "delta_score": impact.get("delta_score"),
            "reliability": impact.get("reliability"),
            "alignment": impact.get("alignment"),
            "adjustment_pp": impact.get("adjustment_pp"),
            "smartbet_before": round(base, 2),
            "smartbet_bonus": round(bonus, 2),
            "smartbet_after": round(new_score, 2),
        })
        enriched.append(pred)

    preds_payload["results"] = enriched
    preds_payload["count"] = len(enriched)
    preds_payload["updated_at"] = now_iso()
    preds_payload["_player_impact_engine"] = VERSION
    write_json(pred_path, preds_payload)

    impact_payload = {
        "updated_at": now_iso(),
        "source": VERSION,
        "count": len(rows),
        "summary": {
            "total_predictions": len(enriched),
            "player_rows": len(players),
            "squad_teams": len(team_squads_payload.get("results", [])) if isinstance(team_squads_payload, dict) else 0,
            "teams_indexed": len(team_idx),
            "available_predictions": available,
            "partial_predictions": partial,
            "boosted_predictions": boosted,
            "max_smartbet_bonus": round(max_bonus, 2),
            "avg_reliability": round(sum(num(r.get("reliability"), 0) for r in rows) / max(len(rows), 1), 4),
        },
        "results": rows,
    }
    write_json(DATA_DIR / "player_impact.json", impact_payload)
    regen = regenerate_dependents()
    debug = {"updated_at": now_iso(), "source": VERSION, "summary": impact_payload["summary"], "sample": rows[:25], "regenerated": regen}
    write_json(DEBUG_DIR / "player_impact_debug.json", debug)
    print(f"Player Impact v2: available={available}/{len(enriched)} partial={partial} boosted={boosted} max_bonus={round(max_bonus, 2)} regen_errors={len(regen.get('errors') or [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
