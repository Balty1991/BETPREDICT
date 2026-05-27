#!/usr/bin/env python3
"""
src/rolling_features_engine.py
===============================
BetPredict Pro v6.1 — Rolling Window Feature Engine

Implementare conform strategiei arhitecturale:
- Calculează medii mobile (rolling averages) bazate pe ultimele N=10 meciuri
- Calculează Attack Strength și Defense Strength per echipă (model Poisson)
- Calculează metrici diferențiale relative (forma față de adversarii recenți)
- Calculează tendința formei (ultimele 5 vs precedentele 5 meciuri)
- Separă statisticile home/away pentru precizie superioară

Algoritm Attack/Defense Strength (Distribuție Poisson):
  attack_strength = avg_gf_venue / league_avg_gf_venue
  defense_strength = avg_ga_venue / league_avg_ga_venue
  lambda_home = attack_home * defense_away_home * league_avg_gf_home
  lambda_away = attack_away * defense_home_away * league_avg_gf_away

Output:
  data/rolling_features.json  — features per team_id
  data/debug/rolling_features_debug.json
"""

from __future__ import annotations
import json
import traceback
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = ROOT_DIR / "data"
DEBUG_DIR = DATA_DIR / "debug"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

RECENT_RESULTS = DATA_DIR / "recent_results.json"
TEAM_FORM = DATA_DIR / "team_form.json"
OUT_ROLLING = DATA_DIR / "rolling_features.json"
OUT_DEBUG = DEBUG_DIR / "rolling_features_debug.json"

# Fereastră rolling — ultimele N meciuri per echipă
ROLLING_WINDOW = 10
# Fereastră pentru calcul tendință formă (trend)
TREND_WINDOW = 5

LOG: List[str] = []


def _log(msg: str) -> None:
    print(f"[rolling_features] {msg}")
    LOG.append(msg)


def _sf(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        x = float(v)
        return default if x != x else x
    except Exception:
        return default


def _parse_date(s: Any) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def _load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        _log(f"WARN citire {path.name}: {e}")
        return default


def _save_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    tmp.replace(path)


# ============================================================
# CONSTRUIRE INDICE DE MECIURI PER ECHIPĂ
# ============================================================

def build_team_match_index(recent_results: List[Dict]) -> Dict[int, List[Dict]]:
    """
    Construiește un indice {team_id: [lista meciuri finalizate, sortate cronologic]}.
    Fiecare intrare conține: event_date, gf, ga, venue (home/away), league_id.
    """
    index: Dict[int, List[Dict]] = defaultdict(list)

    for ev in (recent_results or []):
        if ev.get("status") != "finished":
            continue
        hs = ev.get("home_score")
        as_ = ev.get("away_score")
        if hs is None or as_ is None:
            continue
        try:
            hs_i = int(hs)
            as_i = int(as_)
        except (TypeError, ValueError):
            continue

        hid = ev.get("home_team_id")
        aid = ev.get("away_team_id")
        edate = ev.get("event_date")
        lid = ev.get("league_id", 0)

        if hid is not None:
            try:
                index[int(hid)].append({
                    "event_date": edate,
                    "gf": hs_i, "ga": as_i,
                    "venue": "home",
                    "league_id": lid,
                    "result": "W" if hs_i > as_i else ("D" if hs_i == as_i else "L"),
                })
            except (TypeError, ValueError):
                pass

        if aid is not None:
            try:
                index[int(aid)].append({
                    "event_date": edate,
                    "gf": as_i, "ga": hs_i,
                    "venue": "away",
                    "league_id": lid,
                    "result": "W" if as_i > hs_i else ("D" if as_i == hs_i else "L"),
                })
            except (TypeError, ValueError):
                pass

    # Sortare cronologică per echipă
    for tid in index:
        index[tid].sort(key=lambda x: str(x.get("event_date") or ""))

    return dict(index)


# ============================================================
# STATISTICI LIGĂ — medii globale pentru normalizare Poisson
# ============================================================

def compute_league_averages(recent_results: List[Dict]) -> Dict[int, Dict[str, float]]:
    """
    Calculează medii de goluri per ligă (home/away) pentru normalizarea
    Attack Strength și Defense Strength.

    Returns: {league_id: {avg_gf_home, avg_ga_home, avg_gf_away, avg_ga_away}}
    """
    league_data: Dict[int, Dict[str, List[float]]] = defaultdict(
        lambda: {"gf_home": [], "ga_home": [], "gf_away": [], "ga_away": []}
    )

    for ev in (recent_results or []):
        if ev.get("status") != "finished":
            continue
        hs = ev.get("home_score")
        as_ = ev.get("away_score")
        lid = ev.get("league_id")
        if hs is None or as_ is None or lid is None:
            continue
        try:
            hs_i = int(hs)
            as_i = int(as_)
            lid_i = int(lid)
        except (TypeError, ValueError):
            continue

        league_data[lid_i]["gf_home"].append(hs_i)
        league_data[lid_i]["ga_home"].append(as_i)
        league_data[lid_i]["gf_away"].append(as_i)
        league_data[lid_i]["ga_away"].append(hs_i)

    averages: Dict[int, Dict[str, float]] = {}
    global_gf_home = global_gf_away = []

    # Medii globale fallback
    all_gf_h = [v for d in league_data.values() for v in d["gf_home"]]
    all_gf_a = [v for d in league_data.values() for v in d["gf_away"]]
    global_avg_home = sum(all_gf_h) / max(1, len(all_gf_h))
    global_avg_away = sum(all_gf_a) / max(1, len(all_gf_a))

    for lid_i, d in league_data.items():
        n_h = max(1, len(d["gf_home"]))
        n_a = max(1, len(d["gf_away"]))
        averages[lid_i] = {
            "avg_gf_home": sum(d["gf_home"]) / n_h,
            "avg_ga_home": sum(d["ga_home"]) / n_h,
            "avg_gf_away": sum(d["gf_away"]) / n_a,
            "avg_ga_away": sum(d["ga_away"]) / n_a,
            "n_matches": len(d["gf_home"]),
        }

    # Stocare medii globale pentru fallback
    averages[0] = {
        "avg_gf_home": global_avg_home,
        "avg_ga_home": global_avg_away,
        "avg_gf_away": global_avg_away,
        "avg_ga_away": global_avg_home,
        "n_matches": len(all_gf_h),
    }

    return averages


# ============================================================
# CALCULUL FEATURELOR ROLLING PER ECHIPĂ
# ============================================================

def compute_team_rolling_features(
    team_id: int,
    matches: List[Dict],
    league_averages: Dict[int, Dict[str, float]],
    window: int = ROLLING_WINDOW,
    trend_w: int = TREND_WINDOW,
) -> Dict[str, float]:
    """
    Calculează toate featuri rolling pentru o echipă.

    Returns dict cu:
    - avg_gf_10, avg_ga_10           — goluri medii (overall) last 10
    - avg_gf_home_10, avg_ga_home_10 — goluri medii HOME last 10 home matches
    - avg_gf_away_10, avg_ga_away_10 — goluri medii AWAY last 10 away matches
    - form_pts_10                    — puncte per joc last 10
    - form_trend                     — (pts/game last 5) - (pts/game prev 5)
    - attack_str_home                — putere atac home vs ligă (Poisson)
    - attack_str_away                — putere atac away vs ligă (Poisson)
    - defense_str_home               — putere apărare home vs ligă (Poisson)
    - defense_str_away               — putere apărare away vs ligă (Poisson)
    - n_matches_total                — nr total meciuri disponibile
    - n_home, n_away                 — nr meciuri home/away disponibile
    """

    # Ultimele `window` meciuri
    recent = matches[-window:] if len(matches) >= window else matches

    home_matches = [m for m in recent if m["venue"] == "home"]
    away_matches = [m for m in recent if m["venue"] == "away"]

    def _avg(vals: List[float], default: float = 0.0) -> float:
        return sum(vals) / len(vals) if vals else default

    def _pts(result: str) -> float:
        return 3.0 if result == "W" else (1.0 if result == "D" else 0.0)

    # Overall rolling stats
    all_gf = [m["gf"] for m in recent]
    all_ga = [m["ga"] for m in recent]
    all_pts = [_pts(m["result"]) for m in recent]

    avg_gf_10 = _avg(all_gf, 1.20)
    avg_ga_10 = _avg(all_ga, 1.20)
    form_pts_10 = _avg(all_pts, 1.20)

    # Form trend: ultimele 5 vs precedentele 5
    trend_recent = matches[-trend_w:] if len(matches) >= trend_w else matches
    trend_prev = matches[-(2 * trend_w):-trend_w] if len(matches) >= 2 * trend_w else []
    pts_recent = _avg([_pts(m["result"]) for m in trend_recent], 1.20)
    pts_prev = _avg([_pts(m["result"]) for m in trend_prev], 1.20) if trend_prev else pts_recent
    form_trend = round(pts_recent - pts_prev, 4)

    # Home/Away rolling stats
    avg_gf_home = _avg([m["gf"] for m in home_matches], avg_gf_10)
    avg_ga_home = _avg([m["ga"] for m in home_matches], avg_ga_10)
    avg_gf_away = _avg([m["gf"] for m in away_matches], avg_gf_10)
    avg_ga_away = _avg([m["ga"] for m in away_matches], avg_ga_10)

    # Liga predominantă (cea mai frecventă în meciurile recente)
    if recent:
        league_counts: Dict[int, int] = defaultdict(int)
        for m in recent:
            league_counts[int(m.get("league_id", 0))] += 1
        dominant_league = max(league_counts, key=lambda k: league_counts[k])
    else:
        dominant_league = 0

    league_avg = league_averages.get(dominant_league) or league_averages.get(0, {
        "avg_gf_home": 1.40, "avg_ga_home": 1.10,
        "avg_gf_away": 1.10, "avg_ga_away": 1.40,
    })

    l_avg_gf_h = max(0.5, _sf(league_avg.get("avg_gf_home"), 1.40))
    l_avg_ga_h = max(0.5, _sf(league_avg.get("avg_ga_home"), 1.10))
    l_avg_gf_a = max(0.5, _sf(league_avg.get("avg_gf_away"), 1.10))
    l_avg_ga_a = max(0.5, _sf(league_avg.get("avg_ga_away"), 1.40))

    # Attack Strength (Putere Atac): avg_gf / league_avg_gf
    attack_str_home = round(max(0.1, avg_gf_home) / l_avg_gf_h, 4)
    attack_str_away = round(max(0.1, avg_gf_away) / l_avg_gf_a, 4)

    # Defense Strength (Putere Apărare): avg_ga / league_avg_ga
    # Valoare mică = apărare bună (marchează puțin la adversari)
    defense_str_home = round(max(0.1, avg_ga_home) / l_avg_ga_h, 4)
    defense_str_away = round(max(0.1, avg_ga_away) / l_avg_ga_a, 4)

    return {
        "avg_gf_10": round(avg_gf_10, 4),
        "avg_ga_10": round(avg_ga_10, 4),
        "avg_gf_home_10": round(avg_gf_home, 4),
        "avg_ga_home_10": round(avg_ga_home, 4),
        "avg_gf_away_10": round(avg_gf_away, 4),
        "avg_ga_away_10": round(avg_ga_away, 4),
        "form_pts_10": round(form_pts_10, 4),
        "form_trend": form_trend,
        "attack_str_home": attack_str_home,
        "attack_str_away": attack_str_away,
        "defense_str_home": defense_str_home,
        "defense_str_away": defense_str_away,
        "n_matches_total": len(matches),
        "n_home": len(home_matches),
        "n_away": len(away_matches),
        "dominant_league_id": dominant_league,
    }


# ============================================================
# CALCUL LAMBDA POISSON PENTRU MECIURI PROGRAMATE
# ============================================================

def compute_match_lambdas(
    home_feats: Dict[str, float],
    away_feats: Dict[str, float],
    league_avg: Dict[str, float],
) -> Dict[str, float]:
    """
    Calculează lambda-urile Poisson pentru un meci dat.

    λ_home = attack_home * defense_away_home * league_avg_gf_home
    λ_away = attack_away * defense_home_away * league_avg_gf_away
    """
    l_avg_gf_h = max(0.5, _sf(league_avg.get("avg_gf_home"), 1.40))
    l_avg_gf_a = max(0.5, _sf(league_avg.get("avg_gf_away"), 1.10))

    lam_home = (
        home_feats.get("attack_str_home", 1.0) *
        away_feats.get("defense_str_away", 1.0) *
        l_avg_gf_h
    )
    lam_away = (
        away_feats.get("attack_str_away", 1.0) *
        home_feats.get("defense_str_home", 1.0) *
        l_avg_gf_a
    )

    return {
        "lambda_home": round(max(0.1, min(5.0, lam_home)), 4),
        "lambda_away": round(max(0.1, min(5.0, lam_away)), 4),
    }


# ============================================================
# ENTRY POINT PRINCIPAL
# ============================================================

def main() -> None:
    _log("=== Rolling Features Engine v6.1 ===")

    recent_raw = _load_json(RECENT_RESULTS, {})
    recent_list = recent_raw.get("results", recent_raw) if isinstance(recent_raw, dict) else recent_raw
    if not isinstance(recent_list, list):
        recent_list = []
    finished = [r for r in recent_list if r.get("status") == "finished"]
    _log(f"Meciuri finalizate disponibile: {len(finished)}")

    if len(finished) < 20:
        _log("WARN: Sub 20 meciuri finalizate — features vor folosi valori implicite")

    # Construiește indicele de meciuri per echipă
    team_index = build_team_match_index(finished)
    _log(f"Echipe indexate: {len(team_index)}")

    # Calculează mediile ligii pentru normalizare Poisson
    league_averages = compute_league_averages(finished)
    _log(f"Ligi indexate: {len(league_averages)} (incl. global fallback)")

    # Calculează featuri rolling per echipă
    team_features: Dict[str, Dict] = {}
    stats = {"min_matches": 999, "max_matches": 0, "total_teams": 0}

    for tid, matches in team_index.items():
        feats = compute_team_rolling_features(tid, matches, league_averages)
        team_features[str(tid)] = feats
        n = feats["n_matches_total"]
        stats["min_matches"] = min(stats["min_matches"], n)
        stats["max_matches"] = max(stats["max_matches"], n)
        stats["total_teams"] += 1

    if stats["min_matches"] == 999:
        stats["min_matches"] = 0

    _log(f"Features calculate: {stats['total_teams']} echipe, "
         f"min={stats['min_matches']} / max={stats['max_matches']} meciuri per echipă")

    # Output final
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": "v6.1-rolling",
        "config": {
            "rolling_window": ROLLING_WINDOW,
            "trend_window": TREND_WINDOW,
        },
        "stats": stats,
        "league_averages": {str(k): v for k, v in league_averages.items()},
        "team_features": team_features,
    }

    _save_json(OUT_ROLLING, out)
    _log(f"Salvat: {OUT_ROLLING}")

    # Debug output
    debug = {
        "log": LOG,
        "stats": stats,
        "sample_teams": dict(list(team_features.items())[:5]),
        "league_averages_sample": dict(list({str(k): v for k, v in league_averages.items()}.items())[:5]),
    }
    _save_json(OUT_DEBUG, debug)

    _log("=== Rolling Features Engine completat ===")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(f"[rolling_features] FATAL:\n{traceback.format_exc()}")
        raise
