#!/usr/bin/env python3
"""
predict_historical_ensemble.py — folosește ensemble-ul antrenat pe istoricul complet
(models/ml_ensemble_v6_historical.pkl, vezi train_historical_ensemble.py) ca să producă
predicții pentru meciurile VIITOARE (nejucate încă) din data/events_window.json.

De ce un script separat, nu doar predict_upcoming() din ml_ensemble.py:
- ml_ensemble.py construiește features în alt format (50 coloane, din team_form.json/
  h2h_context.json "curente") — incompatibil cu ensemble-ul antrenat pe cele 455 de
  coloane din feature_engineering.py (calculate cronologic, punct-în-timp corect).
- Acest script adaptează meciurile viitoare la EXACT ACELAȘI proces ca cele din istoric
  (feature_engineering.py), doar că sunt adăugate la finalul listei cronologice — astfel
  văd tot istoricul real de dinaintea lor (formă, H2H, ELO, baseline pe ligă), fără să
  strice nimic în urma lor (vezi _is_played() în feature_engineering.py).

Output: data/ml_predictions_historical.json — probabilități calibrate per piață per
meci viitor. Consumat de src/claude_analysis.py (build_local_signal_index) ca sursă de
local_pick, alături/în completarea lui data/signals_v6.json.

Rulare:
  python3 src/predict_historical_ensemble.py
"""
from __future__ import annotations

import json
import pickle
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
MODELS_DIR = ROOT / "models"
MODEL_PATH = MODELS_DIR / "ml_ensemble_v6_historical.pkl"
OUT_PATH = DATA_DIR / "ml_predictions_historical.json"

HOURS_AHEAD = 720  # aceeași fereastră ca src/claude_analysis.py

sys.path.insert(0, str(ROOT / "src"))
import feature_engineering as fe  # noqa: E402 — reutilizează exact logica de antrenare


def _log(msg: str) -> None:
    print(f"[predict_historical] {msg}")


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def build_odds_index() -> Dict[str, Dict[str, Any]]:
    """Copie a build_odds_index() din claude_analysis.py — format compatibil cu
    odds_features() din feature_engineering.py (odds_home/odds_draw/... etc.)."""
    raw = load_json(DATA_DIR / "best_odds.json", {})
    rows = raw.get("results", []) if isinstance(raw, dict) else []
    idx: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        eid = str(row.get("event_id") or "")
        if not eid:
            continue
        bucket = idx.setdefault(eid, {})
        market = row.get("market")
        if market == "1x2":
            if row.get("home_odds"):
                bucket["odds_home"] = row["home_odds"]
            if row.get("draw_odds"):
                bucket["odds_draw"] = row["draw_odds"]
            if row.get("away_odds"):
                bucket["odds_away"] = row["away_odds"]
        elif market in ("over_under_15", "over_under_25", "over_under_35"):
            suffix = market.replace("over_under_", "")
            if row.get("over_odds"):
                bucket[f"odds_over_{suffix}"] = row["over_odds"]
            if row.get("under_odds"):
                bucket[f"odds_under_{suffix}"] = row["under_odds"]
        elif market == "btts":
            if row.get("over_odds") or row.get("yes_odds"):
                bucket["odds_btts_yes"] = row.get("over_odds") or row.get("yes_odds")
            if row.get("under_odds") or row.get("no_odds"):
                bucket["odds_btts_no"] = row.get("under_odds") or row.get("no_odds")
    return idx


def build_bsd_index() -> Dict[str, Dict[str, Any]]:
    """event_id(str) -> api_prob_* — probabilitățile BSD externe, ca feature suplimentar
    (același rol ca în ml_ensemble.py: 'BSD ca input', nu ca sursă principală)."""
    raw = load_json(DATA_DIR / "predictions.json", {})
    rows = raw.get("results", []) if isinstance(raw, dict) else []
    idx: Dict[str, Dict[str, Any]] = {}
    for p in rows:
        eid = str((p.get("event") or {}).get("id") or p.get("event_id") or "")
        if not eid:
            continue
        mr = (p.get("markets") or {}).get("match_result", {})
        btts = (p.get("markets") or {}).get("btts", {})
        idx[eid] = {
            "api_prob_home_win": mr.get("prob_home"),
            "api_prob_draw": mr.get("prob_draw"),
            "api_prob_away_win": mr.get("prob_away"),
            "api_prob_btts_yes": btts.get("prob_yes"),
        }
    return idx


def build_upcoming_rows() -> List[Dict[str, Any]]:
    """Adaptează meciurile viitoare din events_window.json la exact schema de rând
    folosită de feature_engineering.py pentru meciurile din warehouse — dar fără scor
    (home_score/away_score/home_win/etc. = None, marcând explicit 'nejucat încă')."""
    events_raw = load_json(DATA_DIR / "events_window.json", {})
    events = events_raw.get("results", []) if isinstance(events_raw, dict) else []
    odds_idx = build_odds_index()
    bsd_idx = build_bsd_index()

    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=HOURS_AHEAD)

    rows = []
    for e in events:
        if e.get("status") != "notstarted":
            continue
        date_str = e.get("event_date")
        if not date_str:
            continue
        try:
            dt = datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
        except Exception:
            continue
        if dt < now or dt > cutoff:
            continue
        eid = str(e.get("event_id") or e.get("id") or "")
        if not eid:
            continue
        odds = odds_idx.get(eid, {})
        bsd = bsd_idx.get(eid, {})
        rows.append({
            "event_id": int(eid) if eid.isdigit() else eid,
            "date": date_str,
            "season_year": dt.year,
            "league": e.get("league_name") or str(e.get("league_id") or "Unknown"),
            "league_id": e.get("league_id"),
            "home_team_id": e.get("home_team_id"), "away_team_id": e.get("away_team_id"),
            "home_team": e.get("home_team", ""), "away_team": e.get("away_team", ""),
            # scor absent => _is_played() == False în feature_engineering.py
            "home_score": None, "away_score": None, "total_goals": None,
            "home_win": None, "draw": None, "away_win": None,
            "btts_yes": None, "over_15": None, "over_25": None, "over_35": None, "under_35": None,
            "result_1x2": "",
            "xg_home": None, "xg_away": None,  # xG real nu există înainte de meci
            **odds, **bsd,
        })
    return rows


def main() -> int:
    if not MODEL_PATH.exists():
        _log(f"FATAL: {MODEL_PATH} nu există — rulează întâi train_historical_ensemble.py.")
        return 1

    with open(MODEL_PATH, "rb") as f:
        model_blob = pickle.load(f)
    ensembles = model_blob["ensembles"]
    feat_cols: List[str] = model_blob["feature_names"]
    _log(f"Model încărcat: {len(ensembles)} piețe, {len(feat_cols)} coloane de features.")

    historical_rows = fe.load_warehouse()
    upcoming_rows = build_upcoming_rows()
    _log(f"{len(historical_rows)} meciuri istorice + {len(upcoming_rows)} meciuri viitoare de prezis.")
    if not upcoming_rows:
        _log("Niciun meci viitor eligibil — nimic de prezis.")
        OUT_PATH.write_text(json.dumps({
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "model_version": model_blob.get("version"),
            "results": [],
        }, ensure_ascii=False), encoding="utf-8")
        return 0

    combined = sorted(historical_rows + upcoming_rows, key=lambda r: r.get("date", ""))
    upcoming_ids = {r["event_id"] for r in upcoming_rows}

    _log("Construiesc snapshot-uri cronologice (ELO, formă, H2H, baseline pe ligă)...")
    league_baselines = fe.build_league_baselines(historical_rows)
    league_baseline_snaps = fe.build_league_baseline_snapshots(combined)
    elo_snaps = fe.build_elo_snapshots(combined)
    team_snaps = fe.build_team_histories(combined)
    h2h_snaps = fe.build_h2h_tracker(combined)

    stats_cache = load_json(DATA_DIR / "stats_cache.json", {})
    incidents_cache = load_json(DATA_DIR / "incidents_cache.json", {})
    shotmap_cache = load_json(DATA_DIR / "shotmap_cache.json", {})
    player_stats_cache = load_json(DATA_DIR / "player_stats_cache.json", {})

    feature_rows = []
    for row in combined:
        if row["event_id"] not in upcoming_ids:
            continue
        eid = row["event_id"]
        snap = team_snaps.get(eid, {})
        h2h = h2h_snaps.get(eid, {})
        lb = league_baseline_snaps.get(eid) or league_baselines.get(row.get("league", ""))
        feat_row = fe.build_feature_row(
            row, h_snap=snap.get("home_hist", []), a_snap=snap.get("away_hist", []),
            h2h_snap=h2h, league_baseline=lb,
            stats_cache=stats_cache, incidents_cache=incidents_cache,
            shotmap_cache=shotmap_cache, player_stats_cache=player_stats_cache,
            elo_snapshot=elo_snaps.get(eid, {}),
        )
        feature_rows.append((row, feat_row))
    _log(f"{len(feature_rows)} rânduri de features construite pentru meciuri viitoare.")

    import os as _os
    if _os.environ.get("DEBUG_DUMP_FEATURES"):
        dbg_path = DATA_DIR / "debug" / "predict_historical_features_debug.json"
        dbg_path.parent.mkdir(parents=True, exist_ok=True)
        dbg_path.write_text(json.dumps(
            [{"event_id": r["event_id"], "home_team": r["home_team"], "away_team": r["away_team"],
              "league": r.get("league"), **fr} for r, fr in feature_rows],
            ensure_ascii=False, default=str), encoding="utf-8")
        _log(f"DEBUG: features brute salvate în {dbg_path}")

    def _num(v: Any) -> float:
        try:
            return float(v) if v is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    import numpy as np
    X = np.array([[_num(fr.get(c)) for c in feat_cols] for _, fr in feature_rows], dtype=float)

    market_label = {
        "homeWin": "Victorie gazdă", "draw": "Egal", "awayWin": "Victorie oaspete",
        "btts": "Ambele echipe marchează", "over15": "Over 1.5 goluri",
        "over25": "Over 2.5 goluri", "under35": "Under 3.5 goluri",
    }
    probs_per_market: Dict[str, Any] = {}
    for market, ens in ensembles.items():
        try:
            probs_per_market[market] = ens.predict_proba(X)
        except Exception as e:
            _log(f"  {market}: predict_proba eșuat: {e}")

    results = []
    for i, (row, _) in enumerate(feature_rows):
        markets = {m: round(float(p[i]) * 100, 1) for m, p in probs_per_market.items()}
        if not markets:
            continue
        best_market = max(markets, key=markets.get)
        results.append({
            "event_id": row["event_id"], "home_team": row["home_team"], "away_team": row["away_team"],
            "league": row.get("league"), "event_date": row.get("date"),
            "markets": markets,
            "best_market": best_market, "best_market_label": market_label.get(best_market, best_market),
            "best_probability": markets[best_market],
        })

    OUT_PATH.write_text(json.dumps({
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "model_version": model_blob.get("version"),
        "n_matches": len(results),
        "results": results,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    _log(f"Scris: {OUT_PATH} ({len(results)} meciuri).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
