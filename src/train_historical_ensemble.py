#!/usr/bin/env python3
"""
train_historical_ensemble.py — antrenează ensemble-ul ML pe TOT istoricul din
data/warehouse/ (ani de meciuri, nu doar fereastra recentă din recent_results.json
folosită de src/ml_ensemble.py în retrain-ul săptămânal).

De ce un script separat, nu modific ml_ensemble.py:
- ml_ensemble.py rămâne neschimbat și tot retrain-ul săptămânal de producție
  (ml_train.yml) merge exact ca înainte — zero risc pentru pipeline-ul curent.
- Reutilizează clasa MarketEnsemble din ml_ensemble.py (stacking CatBoost +
  LightGBM + GradientBoosting + LogisticRegression, meta-learner, TimeSeriesSplit,
  calibrare izotonică) — nu reinventează arhitectura de antrenare.
- Sursa de features e feature_engineering.py, care citește data/warehouse/ și
  construiește deja snapshot-uri cronologice fără leakage (ELO, formă pe
  ferestre 3/5/8/10 meciuri, H2H, baseline per ligă) — exact ce trebuie pentru
  ani de istoric, spre deosebire de make_feature_vector() din ml_ensemble.py,
  care se bazează pe team_form.json/h2h_context.json "curente" (corecte doar
  pentru meciurile de azi, nu pentru unele din 2005).

Precondiție: data/warehouse/ trebuie populat (rulează întâi
.github/workflows/fetch_history_full.yml). Cu doar ~85 din ~849 sezoane
disponibile (cât e local acum), rezultatul e informativ, nu un model de
producție — scriptul afișează explicit câte meciuri eligibile a folosit.

Output (separat de modelele de producție, ca să compari înainte de a înlocui):
- models/ml_ensemble_v6_historical.pkl
- data/historical_ensemble_metrics.json

Rulare:
  python3 src/train_historical_ensemble.py
  python3 src/train_historical_ensemble.py --min-eligible min3   # ferestre mai scurte, mai multe rânduri
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
MODELS_DIR = ROOT / "models"

FEATURES_PATH = DATA_DIR / "features_v2.json"
OUT_MODEL = MODELS_DIR / "ml_ensemble_v6_historical.pkl"
OUT_METRICS = DATA_DIR / "historical_ensemble_metrics.json"

# Mapare targets din feature_engineering.py -> chei de market folosite de
# ml_ensemble.py/signals_v6.json (MARKETS = homeWin/draw/awayWin/btts/over15/over25/under35).
TARGET_TO_MARKET = {
    "target_home_win": "homeWin",
    "target_draw": "draw",
    "target_away_win": "awayWin",
    "target_btts_yes": "btts",
    "target_over_15": "over15",
    "target_over_25": "over25",
    "target_under_35": "under35",
}


def _log(msg: str) -> None:
    print(f"[train_historical] {msg}")


def ensure_features_built() -> None:
    if FEATURES_PATH.exists():
        _log(f"{FEATURES_PATH.name} există deja — folosesc ce e pe disc. "
             f"Rulează manual src/feature_engineering.py întâi dacă vrei să-l regenerezi.")
        return
    warehouse = DATA_DIR / "warehouse"
    if not warehouse.exists() or not any(warehouse.glob("events_season_*.json")):
        _log("FATAL: data/warehouse/ e gol — rulează întâi "
             ".github/workflows/fetch_history_full.yml (fetch_history_batch.py --mode full).")
        sys.exit(1)
    _log("Rulez src/feature_engineering.py ca să construiesc features_v2.json din warehouse...")
    subprocess.run([sys.executable, str(ROOT / "src" / "feature_engineering.py")],
                    cwd=str(ROOT), check=True)


def load_rows(min_eligible: str) -> List[Dict[str, Any]]:
    rows = json.loads(FEATURES_PATH.read_text(encoding="utf-8"))
    key = "eligible_min5" if min_eligible == "min5" else "eligible_min3"
    eligible = [r for r in rows if r.get(key)]
    _log(f"{len(rows)} rânduri totale, {len(eligible)} eligibile ({key}=1)")
    return eligible


def build_matrix(rows: List[Dict[str, Any]]) -> Tuple[Any, Dict[str, Any], List[str]]:
    import numpy as np

    prefixes = ("home_", "away_", "form_", "h2h_", "goals_", "btts_", "over2", "under",
                "xg_", "poisson", "nv_", "odds_", "api_", "league_", "rest_", "month",
                "day_", "hour_", "season_year", "close_", "heavy_", "venue_", "elo_",
                "data_quality", "ref_", "shotmap_", "player_", "keeper_")
    targets = set(TARGET_TO_MARKET.keys())
    # home_team/away_team (nume echipe) și home_streak_type/away_streak_type (cod
    # W/D/L/N) au prefixe care se potrivesc, dar sunt text, nu features numerice.
    non_numeric = {"home_team", "away_team", "home_streak_type", "away_streak_type"}
    candidate_cols = sorted({
        k for k in rows[0]
        if k.startswith(prefixes) and k not in targets and k not in non_numeric
    })
    # Plasă de siguranță: confirmă pe un eșantion că nicio coloană rămasă nu ține
    # valori text (dacă feature_engineering.py mai adaugă vreun câmp categoric pe
    # viitor, îl excludem automat în loc să pice antrenarea).
    sample = rows[:200] + rows[-200:]
    feat_cols = [
        c for c in candidate_cols
        if not any(isinstance(r.get(c), str) for r in sample)
    ]
    dropped = set(candidate_cols) - set(feat_cols)
    if dropped:
        _log(f"  Excluse (valori text detectate): {sorted(dropped)}")
    _log(f"{len(feat_cols)} coloane de features folosite pentru antrenare.")

    def _num(v: Any) -> float:
        try:
            return float(v) if v is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    X = np.array([[_num(r.get(c)) for c in feat_cols] for r in rows], dtype=float)
    y_dict = {
        target: np.array([int(r.get(target) or 0) for r in rows], dtype=int)
        for target in TARGET_TO_MARKET
        if target in rows[0]
    }
    return X, y_dict, feat_cols


def run_holdout_backtest(X: Any, y_dict: Dict[str, Any], holdout_frac: float) -> Dict[str, Any]:
    """Test real de generalizare: antrenează DOAR pe primii (1-holdout_frac) din meciuri
    (cronologic — features_v2.json e deja sortat cronologic de feature_engineering.py) și
    evaluează pe ultima felie, nevăzută la antrenare — exact scenariul de producție
    (antrenezi pe trecut, prezici viitor), nu doar OOF intern ca în MarketEnsemble.fit().
    Nu salvează niciun model — doar raportează metrici pe holdout."""
    from sklearn.metrics import log_loss, brier_score_loss, roc_auc_score

    os.environ["SKIP_SKLEARN_GBM"] = "1"
    from ml_ensemble import MarketEnsemble

    n = len(X)
    split = int(n * (1.0 - holdout_frac))
    _log(f"Holdout cronologic: antrenare pe primele {split} meciuri, test pe ultimele {n - split} "
         f"(nevăzute la antrenare).")

    results: Dict[str, Any] = {}
    for target, market_key in TARGET_TO_MARKET.items():
        y = y_dict.get(target)
        if y is None:
            continue
        y_train, y_test = y[:split], y[split:]
        X_train, X_test = X[:split], X[split:]
        if len(set(y_train.tolist())) < 2 or len(set(y_test.tolist())) < 2:
            _log(f"  {market_key}: o singură clasă în train/test — skip.")
            continue
        _log(f"  {market_key}: antrenare pe {len(y_train)}, test pe {len(y_test)}...")
        try:
            ens = MarketEnsemble(market_key).fit(X_train, y_train)
            preds = ens.predict_proba(X_test)
            results[market_key] = {
                "n_train": int(len(y_train)), "n_test": int(len(y_test)),
                "holdout_auc": float(roc_auc_score(y_test, preds)),
                "holdout_brier": float(brier_score_loss(y_test, preds)),
                "holdout_log_loss": float(log_loss(y_test, preds)),
                "train_oof_auc": ens.metrics.get("auc"),
                "train_oof_brier": ens.metrics.get("brier"),
            }
            _log(f"    holdout AUC={results[market_key]['holdout_auc']:.3f}, "
                 f"brier={results[market_key]['holdout_brier']:.3f} "
                 f"(vs. OOF pe train: AUC={ens.metrics.get('auc')}, brier={ens.metrics.get('brier')})")
        except Exception as e:
            _log(f"    EȘUAT: {e}")
            results[market_key] = {"error": str(e)}
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-eligible", choices=["min3", "min5"], default="min5",
                         help="min5 (implicit) = necesită 5+ meciuri anterioare per echipă; "
                              "min3 = mai puțin strict, mai multe rânduri disponibile.")
    parser.add_argument("--holdout-frac", type=float, default=None,
                         help="Dacă e setat (ex. 0.2), rulează DOAR un backtest de generalizare: "
                              "antrenează pe primii (1-frac) din meciuri, testează pe ultima felie "
                              "cronologică nevăzută. Nu salvează niciun model — scrie "
                              "data/historical_ensemble_backtest.json și iese.")
    args = parser.parse_args()

    ensure_features_built()
    rows = load_rows(args.min_eligible)
    if len(rows) < 80:
        _log(f"FATAL: doar {len(rows)} rânduri eligibile (<80) — insuficient pentru antrenare "
             f"de încredere. Rulează fetch_history_full.yml ca să extinzi data/warehouse/.")
        return 1

    X, y_dict, feat_cols = build_matrix(rows)

    if args.holdout_frac is not None:
        backtest = run_holdout_backtest(X, y_dict, args.holdout_frac)
        out_path = DATA_DIR / "historical_ensemble_backtest.json"
        out_path.write_text(json.dumps({
            "holdout_frac": args.holdout_frac, "n_total": len(rows),
            "min_eligible": args.min_eligible, "results": backtest,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        _log(f"Backtest salvat: {out_path}")
        return 0

    # GradientBoostingClassifier (sklearn) e mult mai lent decât CatBoost/LightGBM pe
    # seturi mari (55k rânduri) și nu aduce suficient peste ele ca să merite timpul —
    # îl scoatem doar aici, nu afectează retrain-ul săptămânal de producție.
    os.environ["SKIP_SKLEARN_GBM"] = "1"
    from ml_ensemble import MarketEnsemble  # reutilizează arhitectura de stacking existentă

    ensembles: Dict[str, Any] = {}
    metrics: Dict[str, Any] = {}
    for target, market_key in TARGET_TO_MARKET.items():
        y = y_dict.get(target)
        if y is None:
            _log(f"  {market_key}: target '{target}' lipsește din features_v2.json — skip.")
            continue
        _log(f"  Antrenare {market_key} pe {len(y)} meciuri...")
        try:
            ens = MarketEnsemble(market_key).fit(X, y)
            ensembles[market_key] = ens
            metrics[market_key] = {k: v for k, v in ens.metrics.items() if k != "base_weights"}
            _log(f"    OK — AUC={metrics[market_key].get('auc')}, "
                 f"brier={metrics[market_key].get('brier')}")
        except Exception as e:
            _log(f"    EȘUAT: {e}")
            metrics[market_key] = {"error": str(e)}

    if not ensembles:
        _log("Niciun market antrenat cu succes.")
        return 1

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_MODEL, "wb") as f:
        pickle.dump({
            "version": "v6.1-ml-ensemble-historical",
            "ensembles": ensembles,
            "feature_names": feat_cols,
            "n_training_rows": len(rows),
            "min_eligible": args.min_eligible,
        }, f)
    _log(f"Model salvat: {OUT_MODEL}")

    OUT_METRICS.write_text(json.dumps({
        "n_training_rows": len(rows),
        "min_eligible": args.min_eligible,
        "n_features": len(feat_cols),
        "metrics": metrics,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    _log(f"Metrici salvate: {OUT_METRICS}")
    _log("Compară AUC/brier de aici cu data/ml_predictions.json (modelul de producție, "
         "antrenat pe recent_results.json) înainte să înlocuiești modelul curent — "
         "vezi Faza 2 din planul de reducere de cost.")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "src"))
    raise SystemExit(main())
