#!/usr/bin/env python3
"""
referee_ou_edge.py  — BetPredict v7 edge specific: Arbitru + Forma pe Over/Under
================================================================================

Ipoteza de edge: book-urile SOFT preteaza pietele Over/Under aproape exclusiv
pe statisticile echipelor + media ligii. SUB-pondereaza tendinta ARBITRULUI.
Un arbitru cu medie mare de goluri (permisiv, lasa jocul sa curga) sau mica
(fluiera des, rupe ritmul) e un factor real pe care piata il ignora partial.

Cand: (arbitru cu tendinta clara de goluri) + (forma ambelor echipe confirma
aceeasi directie) => estimam λ (goluri asteptate) via Poisson, comparam cu
cota implicita a pietei, si emitem semnal DOAR daca exista EV pozitiv.

Surse: matches_today.json (referee_id), referee_stats.json (avg_goals),
       team_form.json (avg_gf/avg_ga), best_odds.json (cote O/U),
       lineup_intelligence.json (gate de incredere pe lineup confirmat).

Output: data/referee_ou_edge.json
Ruleaza standalone:  python3 src/referee_ou_edge.py
"""
from __future__ import annotations
import json, os, sys, tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, ROOT)

try:
    from analytics_core import poisson_market_probabilities, safe_float, kelly_fraction
except Exception:
    def safe_float(v, d=0.0):
        try:
            x = float(v); return d if x != x else x
        except Exception:
            return d

# ---- Config ----------------------------------------------------------------
MIN_REF_MATCHES = 20      # arbitru cu minim atatea meciuri = tendinta fiabila
LEAGUE_AVG_GOALS = 2.65   # baseline global goluri/meci
MIN_EV = 0.03             # 3% EV minim vs piata
MAX_EV = 0.20
REF_WEIGHT = 0.35         # cat de mult ajustam λ dupa arbitru (0..1)
KELLY_FRACTION = 0.25
KELLY_CAP = 0.05


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


def _referee_index() -> Dict[str, Dict[str, Any]]:
    """Unifica referee_stats.json + referee_profiles.json (acoperire mai larga).
    Normalizeaza campurile: avg_goals, matches, is_high_goals, is_low_goals."""
    idx: Dict[str, Dict[str, Any]] = {}

    def add(rid, name, matches, avg_goals):
        if rid is None or avg_goals in (None, 0):
            return
        key = str(rid)
        if key in idx and safe_float(idx[key].get("matches")) >= safe_float(matches):
            return  # pastreaza sursa cu mai multe meciuri
        ag = safe_float(avg_goals)
        idx[key] = {"name": name, "matches": matches, "avg_goals": ag,
                    "is_high_goals": ag >= 2.9, "is_low_goals": ag <= 2.35}

    stats = (_load("referee_stats.json", {}) or {}).get("referees", {})
    if isinstance(stats, dict):
        for rid, r in stats.items():
            if isinstance(r, dict):
                add(rid, r.get("name"), r.get("matches"), r.get("avg_goals"))
    for r in ((_load("referee_profiles.json", {}) or {}).get("results") or []):
        add(r.get("id"), r.get("name"), r.get("matches"), r.get("avg_goals_per_match"))
    return idx


def _team_form_index(tf: Dict[str, Any]) -> Dict[Any, Dict[str, Any]]:
    rows = tf.get("results") or tf.get("teams") or []
    if isinstance(tf, list):
        rows = tf
    if isinstance(rows, dict):
        rows = list(rows.values())
    return {r.get("team_id"): r for r in rows if isinstance(r, dict)}


def _best_ou_index(best_odds: Dict[str, Any]) -> Dict[tuple, float]:
    idx = {}
    for r in (best_odds.get("results") or []):
        m = r.get("market")
        if not str(m).startswith("over_under_"):
            continue
        for o in r.get("best_odds", []):
            idx[(r.get("event_id"), m, str(o.get("outcome")).lower())] = \
                safe_float(o.get("decimal_odds"), 0.0)
    return idx


def _lineup_index(li: Dict[str, Any]) -> Dict[Any, Dict[str, Any]]:
    rows = li.get("results") or li.get("events") or []
    if isinstance(li, dict) and not rows:
        rows = [v for v in li.values() if isinstance(v, dict)]
    return {r.get("event_id"): r for r in rows if isinstance(r, dict)}


def main() -> int:
    matches = _load("matches_today.json", {})
    mrows = matches.get("results") or matches.get("matches") or (matches if isinstance(matches, list) else [])
    refs = _referee_index()
    tf_idx = _team_form_index(_load("team_form.json", {}) or {})
    ou_idx = _best_ou_index(_load("best_odds.json", {}) or {})
    li_idx = _lineup_index(_load("lineup_intelligence.json", {}) or {})

    signals = []
    n_with_ref_id = n_ref_covered = 0
    for m in mrows:
        rid = m.get("referee_id")
        eid = m.get("id") or m.get("event_id")
        if rid is None or eid is None:
            continue
        n_with_ref_id += 1
        ref = refs.get(str(rid)) or refs.get(rid)
        if not isinstance(ref, dict):
            continue
        n_ref_covered += 1
        if safe_float(ref.get("matches")) < MIN_REF_MATCHES:
            continue
        high = bool(ref.get("is_high_goals"))
        low = bool(ref.get("is_low_goals"))
        if not (high or low):
            continue  # doar arbitri cu tendinta CLARA

        hf = tf_idx.get(m.get("home_team_id"))
        af = tf_idx.get(m.get("away_team_id"))
        if not hf or not af:
            continue

        # λ estimat din forma (recent avg) — model simplu de intalnire
        lam_home = (safe_float(hf.get("avg_gf"), 1.3) + safe_float(af.get("avg_ga"), 1.3)) / 2.0
        lam_away = (safe_float(af.get("avg_gf"), 1.1) + safe_float(hf.get("avg_ga"), 1.3)) / 2.0
        total = lam_home + lam_away
        # confirmare directie: forma echipelor trebuie sa concorde cu arbitrul
        form_high = (safe_float(hf.get("over25_pct")) + safe_float(af.get("over25_pct"))) / 2.0 >= 55
        form_low = (safe_float(hf.get("over25_pct")) + safe_float(af.get("over25_pct"))) / 2.0 <= 45
        if high and not form_high:
            continue
        if low and not form_low:
            continue

        # ajustare arbitru pe λ
        ref_factor = safe_float(ref.get("avg_goals"), LEAGUE_AVG_GOALS) / LEAGUE_AVG_GOALS
        adj = 1.0 + REF_WEIGHT * (ref_factor - 1.0)
        lam_home *= adj
        lam_away *= adj

        try:
            pm = poisson_market_probabilities(lam_home, lam_away)
        except Exception:
            continue

        # directia si piata tinta
        if high:
            market, outcome, model_p = "over_under_25", "over", safe_float(pm.get("over25"))
        else:
            market, outcome, model_p = "over_under_25", "under", safe_float(pm.get("under25"))
        if model_p <= 0:
            continue

        odds = ou_idx.get((eid, market, outcome))
        if not odds or odds <= 1.01:
            continue
        ev = model_p * (odds - 1.0) - (1.0 - model_p)
        if not (MIN_EV <= ev <= MAX_EV):
            continue

        lu = li_idx.get(eid, {})
        lineup_ok = bool(lu.get("available")) and str(lu.get("lineup_status", "")).lower() in ("confirmed", "official", "")
        k = 0.0
        try:
            k = kelly_fraction(model_p, odds, KELLY_FRACTION, KELLY_CAP)
        except Exception:
            pass

        signals.append({
            "event_id": eid, "home_team": m.get("home_team"), "away_team": m.get("away_team"),
            "referee": ref.get("name"), "referee_matches": ref.get("matches"),
            "referee_avg_goals": ref.get("avg_goals"),
            "referee_tendency": "HIGH_GOALS" if high else "LOW_GOALS",
            "market": market, "outcome": outcome,
            "model_lambda_total": round(lam_home + lam_away, 2),
            "model_prob_pct": round(model_p * 100, 1),
            "bet_odds": odds, "book_implied_pct": round(1.0 / odds * 100, 1),
            "ev_pct": round(ev * 100, 2), "kelly_pct": round(k * 100, 2),
            "lineup_confirmed": lineup_ok,
            "form_home_over25_pct": hf.get("over25_pct"),
            "form_away_over25_pct": af.get("over25_pct"),
        })

    signals.sort(key=lambda s: (s["lineup_confirmed"], s["ev_pct"]), reverse=True)
    out = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "referee_ou_edge_v7",
        "methodology": "Arbitru cu tendinta clara de goluri + forma echipelor confirma directia "
                       "=> Poisson λ ajustat pe arbitru vs cota pietei. Edge pe factorul pe care "
                       "book-urile soft il sub-pondereaza.",
        "config": {"min_referee_matches": MIN_REF_MATCHES, "ref_weight": REF_WEIGHT,
                   "min_ev_pct": MIN_EV * 100},
        "summary": {"n_matches_scanned": len(mrows), "n_signals": len(signals),
                    "n_with_referee_id": n_with_ref_id, "n_referee_covered": n_ref_covered,
                    "referee_db_size": len(refs),
                    "coverage_note": ("Arbitrii pentru meciurile de azi nu sunt in baza de date "
                                      "(desemnati aproape de start / neacoperiti de fetch_referee_stats). "
                                      "Semnalele apar cand acoperirea creste.")
                                     if n_ref_covered == 0 else "ok",
                    "avg_ev_pct": round(sum(s["ev_pct"] for s in signals) / len(signals), 2)
                                   if signals else 0.0},
        "signals": signals,
    }
    _atomic_write("referee_ou_edge.json", out)
    print(f"[referee_ou] scanate {len(mrows)} meciuri | {len(signals)} semnale "
          f"(EV mediu {out['summary']['avg_ev_pct']}%)")
    for s in signals[:8]:
        print(f"  {s['home_team']} v {s['away_team']} | {s['outcome'].upper()} 2.5 "
              f"| ref {s['referee']} ({s['referee_avg_goals']}g, {s['referee_tendency']}) "
              f"| λ={s['model_lambda_total']} model {s['model_prob_pct']}% vs book {s['book_implied_pct']}% "
              f"| EV +{s['ev_pct']}%{' | LINEUP' if s['lineup_confirmed'] else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
