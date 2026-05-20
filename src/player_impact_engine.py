#!/usr/bin/env python3
"""BetPredict Player Impact Engine v3.

Scop v3:
- folosește simultan data/player_intelligence.json + data/team_squads.json;
- diferențiază mai bine echipele cu date parțiale, nu le mai lasă generic 46.0 vs 46.0;
- păstrează protecția: datele parțiale au impact mic și bonus SmartBet plafonat;
- idempotent: nu aplică bonusul de mai multe ori;
- regenerează fișierele dependente după predictions.json.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DEBUG_DIR = DATA_DIR / "debug"
VERSION = "player_impact_v3"

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


def as_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except Exception:
        return None


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


def extract_rows(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("results", "players", "items", "data"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [x for x in rows if isinstance(x, dict)]
    return []


def clean_pos(value: Any) -> str:
    p = str(value or "").strip().upper()
    if not p:
        return "?"
    if p.startswith("G") or p in ("GK", "GOALKEEPER"):
        return "G"
    if p.startswith("D") or p in ("CB", "LB", "RB", "LWB", "RWB", "DEFENDER"):
        return "D"
    if p.startswith("M") or p in ("CM", "DM", "AM", "LM", "RM", "MIDFIELDER"):
        return "M"
    if p.startswith("F") or p.startswith("A") or p in ("ST", "CF", "LW", "RW", "FW", "FORWARD", "ATTACKER"):
        return "F"
    return p[:1]


def age_from_dob(dob: Any) -> Optional[int]:
    if not dob:
        return None
    try:
        year = int(str(dob)[:4])
        if year < 1950 or year > 2026:
            return None
        return max(0, datetime.now(timezone.utc).year - year)
    except Exception:
        return None


def safe_profile(row: Dict[str, Any]) -> Dict[str, Any]:
    return row.get("profile") if isinstance(row.get("profile"), dict) else {}


def player_id(row: Dict[str, Any]) -> str:
    prof = safe_profile(row)
    return str(row.get("player_id") or row.get("id") or prof.get("player_id") or prof.get("id") or "")


def team_id(row: Dict[str, Any]) -> str:
    prof = safe_profile(row)
    return str(row.get("current_team_id") or row.get("team_id") or prof.get("current_team_id") or prof.get("team_id") or "")


def player_name(row: Dict[str, Any]) -> str:
    prof = safe_profile(row)
    return str(prof.get("short_name") or row.get("short_name") or row.get("name") or prof.get("name") or "—")


def current_position(row: Dict[str, Any]) -> str:
    prof = safe_profile(row)
    return clean_pos(row.get("specific_position") or row.get("position") or prof.get("specific_position") or prof.get("position"))


def jersey_no(row: Dict[str, Any]) -> Optional[int]:
    prof = safe_profile(row)
    return as_int(row.get("jersey_number") or prof.get("jersey_number"))


def availability_factor(row: Dict[str, Any]) -> float:
    prof = safe_profile(row)
    raw = str(row.get("availability") or prof.get("availability") or "").lower()
    if not raw:
        return 0.92
    if any(x in raw for x in ("injur", "suspend", "unavailable", "out", "doubt")):
        return 0.25
    if any(x in raw for x in ("bench", "question", "limited")):
        return 0.65
    return 1.0


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


def basic_squad_player_score(row: Dict[str, Any]) -> float:
    pos = current_position(row)
    pos_base = {"G": 38.0, "D": 42.0, "M": 44.5, "F": 46.0}.get(pos, 40.0)
    shirt = jersey_no(row)
    shirt_bonus = 0.0
    if shirt is not None:
        if 1 <= shirt <= 11:
            shirt_bonus = 4.0
        elif 12 <= shirt <= 23:
            shirt_bonus = 2.2
        elif 24 <= shirt <= 30:
            shirt_bonus = 0.8
        elif shirt >= 40:
            shirt_bonus = -1.0
    dob = row.get("date_of_birth") or safe_profile(row).get("date_of_birth")
    age = age_from_dob(dob)
    age_bonus = 0.0
    if age is not None:
        if 23 <= age <= 29:
            age_bonus = 3.0
        elif 20 <= age <= 22 or 30 <= age <= 32:
            age_bonus = 1.3
        elif age <= 18 or age >= 35:
            age_bonus = -1.2
    role_bonus = 1.0 if pos in ("M", "F") and shirt is not None and 1 <= shirt <= 11 else 0.0
    return clamp((pos_base + shirt_bonus + age_bonus + role_bonus) * availability_factor(row), 28.0, 58.0)


def detailed_player_score(row: Dict[str, Any]) -> float:
    s = stats_summary(row)
    rating_score = clamp((s["rating"] - 5.8) / 1.8, 0.0, 1.0)
    minutes_score = clamp(s["minutes"] / 450.0, 0.0, 1.0)
    production_score = clamp(
        (s["goals"] * 0.75 + s["assists"] * 0.60 + s["shots_on_target"] * 0.08 + s["key_passes"] * 0.055 + s["def_actions"] * 0.025) / 6.0,
        0.0,
        1.0,
    )
    prof = safe_profile(row)
    mv = max(0.0, num(row.get("market_value_eur") or prof.get("market_value_eur"), 0))
    market_score = clamp((math.log10(max(mv, 50000.0)) - math.log10(50000.0)) / 2.3, 0.0, 1.0)
    score = 100.0 * (rating_score * 0.40 + minutes_score * 0.25 + market_score * 0.22 + production_score * 0.13) * availability_factor(row)
    return clamp(score, 20.0, 92.0)


def player_score(row: Dict[str, Any]) -> Dict[str, Any]:
    s = stats_summary(row)
    detailed = bool(row.get("_detailed")) or s["sample"] > 0 or bool(row.get("stats_count"))
    score = detailed_player_score(row) if detailed else basic_squad_player_score(row)
    prof = safe_profile(row)
    mv = max(0.0, num(row.get("market_value_eur") or prof.get("market_value_eur"), 0))
    return {
        "player_id": row.get("player_id") or row.get("id") or prof.get("player_id") or prof.get("id"),
        "name": player_name(row),
        "position": current_position(row),
        "team_id": team_id(row),
        "score": round(score, 2),
        "rating": round(s["rating"], 2) if detailed else None,
        "minutes": int(s["minutes"]),
        "goals": int(s["goals"]),
        "assists": int(s["assists"]),
        "stats_sample": int(s["sample"]),
        "market_value_eur": int(mv) if mv else 0,
        "availability_factor": round(availability_factor(row), 2),
        "detail_level": "detailed" if detailed else "squad_basic",
    }


def build_squad_rows(team_squads_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for team in extract_rows(team_squads_payload):
        tid = team.get("team_id")
        tname = team.get("name")
        players = team.get("players") if isinstance(team.get("players"), list) else []
        for p in players:
            if not isinstance(p, dict):
                continue
            r = dict(p)
            r.setdefault("current_team_id", tid)
            r.setdefault("team_id", tid)
            r.setdefault("team_name", tname)
            r["_detailed"] = False
            r["_source"] = "team_squads"
            rows.append(r)
    return rows


def build_team_index(players_payload: Dict[str, Any], team_squads_payload: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for row in build_squad_rows(team_squads_payload):
        pid = player_id(row)
        tid = team_id(row)
        if not pid or not tid:
            continue
        merged[f"{tid}:{pid}"] = row
    for row in extract_rows(players_payload):
        pid = player_id(row)
        tid = team_id(row)
        if not pid or not tid:
            continue
        key = f"{tid}:{pid}"
        base = merged.get(key, {})
        combined = dict(base)
        combined.update(row)
        combined["_detailed"] = True
        combined["_source"] = "player_intelligence"
        merged[key] = combined
    idx: Dict[str, List[Dict[str, Any]]] = {}
    for row in merged.values():
        tid = team_id(row)
        pid = player_id(row)
        if tid and pid:
            idx.setdefault(tid, []).append(player_score(row))
    for tid in list(idx):
        idx[tid].sort(key=lambda x: x.get("score") or 0, reverse=True)
    return idx


def positional_balance(players: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts = {"G": 0, "D": 0, "M": 0, "F": 0, "?": 0}
    for p in players:
        pos = str(p.get("position") or "?").upper()
        if pos not in counts:
            pos = "?"
        counts[pos] += 1
    req = {"G": 2, "D": 7, "M": 7, "F": 3}
    cov = sum(clamp(counts[k] / req[k], 0.0, 1.0) for k in req) / 4.0
    depth = clamp(len(players) / 28.0, 0.0, 1.0)
    attack_options = clamp((counts["M"] + counts["F"]) / max(len(players), 1), 0.0, 1.0)
    return {"counts": counts, "coverage": round(cov, 3), "depth": round(depth, 3), "attack_ratio": round(attack_options, 3)}


def team_strength(team_players: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not team_players:
        return {"available": False, "partial": False, "score": 0.0, "reliability": 0.0, "players_indexed": 0, "detailed_players": 0, "squad_basic_players": 0, "strength_source": "none", "avg_rating": None, "positional_balance": {}, "top_players": []}
    top = team_players[:8]
    detailed = [p for p in team_players if p.get("detail_level") == "detailed"]
    basic = [p for p in team_players if p.get("detail_level") != "detailed"]
    posbal = positional_balance(team_players)
    weights = [1.00, 0.94, 0.88, 0.80, 0.72, 0.64, 0.56, 0.50]
    total_w = sum(weights[: len(top)])
    top_score = sum((p.get("score") or 0) * weights[i] for i, p in enumerate(top)) / max(total_w, 1e-9)
    depth_score = 38.0 + posbal["depth"] * 6.0 + posbal["coverage"] * 7.0 + posbal["attack_ratio"] * 3.0
    if len(detailed) >= 4:
        score = top_score * 0.78 + depth_score * 0.22
        stats_samples = [num(p.get("stats_sample"), 0) for p in detailed[:8]]
        stats_cov = clamp((avg(stats_samples, 0.0) or 0.0) / 12.0, 0.0, 1.0)
        reliability = clamp(0.38 + min(len(detailed), 8) / 8.0 * 0.28 + stats_cov * 0.22 + posbal["coverage"] * 0.12, 0.0, 0.86)
        source = "detailed"
        partial = False
    elif len(detailed) > 0:
        score = top_score * 0.58 + depth_score * 0.42
        reliability = clamp(0.24 + min(len(detailed), 4) / 4.0 * 0.18 + posbal["coverage"] * 0.12, 0.0, 0.56)
        source = "mixed_partial"
        partial = True
    else:
        score = top_score * 0.45 + depth_score * 0.55
        reliability = clamp(0.16 + posbal["coverage"] * 0.12 + posbal["depth"] * 0.08, 0.0, 0.38)
        source = "squad_partial"
        partial = True
    avg_rating = avg([num(p.get("rating"), float("nan")) for p in detailed[:8]], None)
    return {"available": True, "partial": partial, "score": round(score, 2), "reliability": round(reliability, 3), "players_indexed": len(team_players), "detailed_players": len(detailed), "squad_basic_players": len(basic), "top_used": len(top), "strength_source": source, "avg_rating": round(avg_rating, 2) if avg_rating is not None else None, "positional_balance": posbal, "top_players": top[:5]}


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
    partial = bool(h.get("partial") or a.get("partial")) if available else False
    reliability = min(num(h.get("reliability"), 0), num(a.get("reliability"), 0)) if available else 0.0
    raw_delta = num(h.get("score"), 0) - num(a.get("score"), 0)
    if not available:
        cap_pp, denom = 0.0, 20.0
    elif partial:
        cap_pp, denom = 0.55, 18.0
    else:
        cap_pp, denom = 1.65, 22.0
    normalized_delta = clamp(raw_delta / denom, -1.0, 1.0)
    home_pp = clamp(normalized_delta * reliability * (1.60 if not partial else 1.18), -cap_pp, cap_pp)
    away_pp = -home_pp
    draw_pp = -abs(home_pp) * 0.20
    best = best_1x2(pred)
    aligned = (best == "home" and home_pp > 0.08) or (best == "away" and away_pp > 0.08)
    contradiction = (best == "home" and home_pp < -0.20) or (best == "away" and away_pp < -0.20)
    smartbet_bonus = 0.0
    if available and aligned and reliability >= 0.20:
        raw_bonus = abs(home_pp) * (0.72 if partial else 1.05)
        smartbet_bonus = clamp(raw_bonus, 0.0, 0.45 if partial else 1.25)
    if not available:
        label = "insufficient_player_data"
    elif partial and contradiction:
        label = "partial_contradicts_main_side"
    elif partial and aligned:
        label = "partial_supports_main_side"
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
        "home_players_indexed": h.get("players_indexed", 0),
        "away_players_indexed": a.get("players_indexed", 0),
        "delta_score": round(raw_delta, 2),
        "normalized_delta": round(normalized_delta, 3),
        "reliability": round(reliability, 3),
        "cap_pp": round(cap_pp, 2),
        "best_1x2": best,
        "alignment": label,
        "adjustment_pp": {"home": round(home_pp, 3), "draw": round(draw_pp, 3), "away": round(away_pp, 3)},
        "smartbet_bonus": round(smartbet_bonus, 2),
    }


def regenerate_dependents() -> Dict[str, Any]:
    report = {"signals": False, "value_bets": False, "selection_journal": False, "performance_summary": False, "qa_report": False, "errors": []}
    try:
        import fetch_daily as fd
    except Exception as exc:
        report["errors"].append(f"fetch_daily import failed: {exc}")
        return report
    steps = [("signals", getattr(fd, "compute_signals", None)), ("value_bets", getattr(fd, "_compute_value_bets_local", None)), ("selection_journal", getattr(fd, "update_selection_journal", None)), ("performance_summary", getattr(fd, "compute_performance_summary", None)), ("qa_report", getattr(fd, "fetch_production_qa_report", None))]
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
    squads_payload = read_json(DATA_DIR / "team_squads.json", {})
    preds = preds_payload.get("results") if isinstance(preds_payload, dict) else None
    if not isinstance(preds, list):
        write_json(DEBUG_DIR / "player_impact_debug.json", {"updated_at": now_iso(), "source": VERSION, "error": "missing_predictions"})
        print("Player Impact v3: predictions.json missing/invalid; skip")
        return 0
    team_idx = build_team_index(players_payload if isinstance(players_payload, dict) else {}, squads_payload if isinstance(squads_payload, dict) else {})
    if not team_idx:
        write_json(DEBUG_DIR / "player_impact_debug.json", {"updated_at": now_iso(), "source": VERSION, "error": "missing_player_and_squad_data", "total_predictions": len(preds)})
        print("Player Impact v3: player/squad data missing; skip")
        return 0
    rows: List[Dict[str, Any]] = []
    enriched: List[Dict[str, Any]] = []
    boosted = available = partial = contradicted = 0
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
        if "contradicts" in str(impact.get("alignment", "")):
            contradicted += 1
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
            "home_players_indexed": impact.get("home_players_indexed"),
            "away_players_indexed": impact.get("away_players_indexed"),
            "home_source": impact.get("home", {}).get("strength_source"),
            "away_source": impact.get("away", {}).get("strength_source"),
            "delta_score": impact.get("delta_score"),
            "reliability": impact.get("reliability"),
            "cap_pp": impact.get("cap_pp"),
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
    player_rows = len(extract_rows(players_payload))
    squad_teams = len(extract_rows(squads_payload))
    impact_payload = {"updated_at": now_iso(), "source": VERSION, "count": len(rows), "summary": {"total_predictions": len(enriched), "player_rows": player_rows, "squad_teams": squad_teams, "teams_indexed": len(team_idx), "available_predictions": available, "partial_predictions": partial, "contradicted_predictions": contradicted, "boosted_predictions": boosted, "max_smartbet_bonus": round(max_bonus, 2), "avg_reliability": round(sum(num(r.get("reliability"), 0) for r in rows) / max(len(rows), 1), 4), "avg_abs_delta_score": round(sum(abs(num(r.get("delta_score"), 0)) for r in rows if r.get("available")) / max(available, 1), 3)}, "results": rows}
    write_json(DATA_DIR / "player_impact.json", impact_payload)
    regen = regenerate_dependents()
    debug = {"updated_at": now_iso(), "source": VERSION, "summary": impact_payload["summary"], "sample": rows[:30], "regenerated": regen}
    write_json(DEBUG_DIR / "player_impact_debug.json", debug)
    print("Player Impact v3: " f"available={available}/{len(enriched)} partial={partial} boosted={boosted} max_bonus={round(max_bonus, 2)} avg_abs_delta={impact_payload['summary']['avg_abs_delta_score']} regen_errors={len(regen.get('errors') or [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
