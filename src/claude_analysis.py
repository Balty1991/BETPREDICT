#!/usr/bin/env python3
"""BETPREDICT — Local Predictions + Claude Ticket Review Engine.

Scrie data/claude_predictions.json (o predicție per meci) și
data/claude_accumulators.json (bilete acumulator generate automat).

Arhitectură (ca la VEYRA — modelul face treaba grea, gratuit; AI-ul e opțional
și minuscul, nu mai e pe calea critică):

1. Predicțiile per meci vin STRICT din modelul ML antrenat pe istoricul complet
   (vezi src/predict_historical_ensemble.py -> data/ml_predictions_historical.json,
   cu fallback pe data/signals_v6.json) — zero apeluri Claude, cost zero. Fiecare
   meci din fereastra de 30 zile cu un pick local intră direct în
   claude_predictions.json.
2. Biletele de acumulator se construiesc din aceste predicții cu reguli fixe
   (probabilitate, cotă minimă, diversificare) — vezi build_accumulators(),
   tot fără AI.
3. UN SINGUR apel Claude, opțional și ieftin (vezi call_claude_review): nu
   analizează meciuri individuale, doar citește biletele deja construite (o
   mână de tichete, nu sute de meciuri) și semnalează probleme reale sau
   evidențiază cel mai bun bilet. Cost aproape constant, indiferent de câte
   meciuri sunt în fereastră — opusul arhitecturii anterioare (verdict Claude
   per meci, cost proporțional cu numărul de meciuri analizate).
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

MODEL = "claude-sonnet-5"
HOURS_AHEAD = int(os.environ.get("CLAUDE_HOURS_AHEAD", "720"))
# Plafon de siguranță pe mărimea "pool"-ului local (gratuit) din care construim
# predicțiile — acum că predicțiile sunt gratuite (fără AI per meci), plafonul poate fi
# generos: doar o limită superioară de siguranță, nu un buton de cost ca înainte.
MAX_EVENTS = int(os.environ.get("CLAUDE_MAX_EVENTS", "1500"))
# Prag minim de semnal BSD — contează DOAR pentru meciurile fără pick din modelul
# local (fallback pe semnalul BSD brut); filtrează meciurile "monedă aruncată"
# (~50/50 peste tot), care oricum nu produc predicții utile pentru acumulator.
MIN_BSD_SIGNAL = float(os.environ.get("CLAUDE_MIN_BSD_SIGNAL", "70"))
# Cotă minimă ca o piață să fie considerată pentru acumulator — sub acest prag, riscul
# (orice contra-rezultat pică tot biletul) nu se justifică față de cât plătește piciorul.
MIN_LEG_ODDS = float(os.environ.get("CLAUDE_MIN_LEG_ODDS", "1.10"))

LOCAL_MARKET_MAP = {
    "homeWin": "home_win", "draw": "draw", "awayWin": "away_win",
    "btts": "btts_yes", "over15": "over_15", "over25": "over_25", "under35": "under_35",
}

# Invers: market local (ex. "under_35") -> cheia compacta ("under35") folosita de
# adaptive_thresholds.json. Necesar pentru poarta adaptiva la emiterea verdictelor.
COMPACT_FROM_LOCAL = {v: k for k, v in LOCAL_MARKET_MAP.items()}

MARKET_LABELS = {
    "home_win": "Gazdă câștigă",
    "draw": "Egal",
    "away_win": "Oaspete câștigă",
    "double_chance_1x": "Șansă dublă 1X",
    "double_chance_x2": "Șansă dublă X2",
    "double_chance_12": "Șansă dublă 12",
    "over_15": "Over 1.5 goluri",
    "under_15": "Under 1.5 goluri",
    "over_25": "Over 2.5 goluri",
    "under_25": "Under 2.5 goluri",
    "over_35": "Over 3.5 goluri",
    "under_35": "Under 3.5 goluri",
    "btts_yes": "Ambele echipe marchează - Da",
    "btts_no": "Ambele echipe marchează - Nu",
}

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "reviews": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "period": {"type": "string", "description": "Cheia perioadei (ex. '7', '10', '30')."},
                    "label": {"type": "string", "description": "Eticheta biletului (ex. 'Maxim sigur')."},
                    "concern": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "description": "O propoziție scurtă DOAR dacă vezi o problemă reală (picioare puternic "
                                       "corelate, contradicție evidentă între picioare, risc nejustificat pentru "
                                       "eticheta biletului). Altfel null.",
                    },
                    "highlight": {
                        "type": "boolean",
                        "description": "true pentru cel mult UN bilet din tot setul — cel mai solid per ansamblu.",
                    },
                },
                "required": ["period", "label", "concern", "highlight"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["reviews"],
    "additionalProperties": False,
}

REVIEW_SYSTEM_PROMPT = """Ești control de calitate rapid peste bilete de acumulator deja construite —
NU analist principal. Biletele primite sunt deja calculate integral local, fără AI: probabilități dintr-un
ensemble ML antrenat pe ~55.000 de meciuri istorice (CatBoost+LightGBM+LogisticRegression, calibrat izotonic,
verificat prin backtest cronologic că generalizează pe date nevăzute) + reguli fixe de combinare
(probabilitate minimă, cotă minimă, diversificare). NU recalculezi nimic și NU propui bilete noi.

Rolul tău, per bilet primit:
- Verifică dacă picioarele se contrazic sau sunt puternic corelate (ex. două piețe din ACELAȘI meci,
  sau context evident opus a ceea ce arată probabilitatea) — dacă da, scrie un "concern" scurt (1
  propoziție) care citează exact ce ai observat. Dacă nu vezi nimic îngrijorător, "concern": null.
  NU inventa probleme doar ca să pari util — marea majoritate a biletelor nu vor avea niciun concern.
- Marchează "highlight": true pentru CEL MULT UN bilet din tot setul primit — cel mai solid per
  ansamblu (echilibru bun între probabilitate combinată și cotă, nu neapărat cel mai "sigur" sau cel
  mai plătit). Pentru restul, "highlight": false.

Răspunde STRICT conform schemei JSON, în română, concis. Un obiect de review per bilet primit,
identificat prin "period" + "label" exact cum le-ai primit."""


def load(path: Path, default: Any) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    tmp.replace(path)


def parse_dt(s: Optional[str]):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def no_vig_pair(o1: Optional[float], o2: Optional[float]) -> Optional[float]:
    """Cotă combinată (no-vig aprox.) pentru unirea a două rezultate dintr-un market 1x2/OU."""
    try:
        o1f, o2f = float(o1), float(o2)
        if o1f < 1.01 or o2f < 1.01:
            return None
        implied = 1.0 / o1f + 1.0 / o2f
        return round(1.0 / implied, 3) if implied > 0 else None
    except Exception:
        return None


def build_odds_index() -> Dict[str, Dict[str, Any]]:
    """event_id(str) -> {odds_home, odds_draw, odds_away, odds_over_15, ..., bk_home, bk_draw, ...}.
    bk_* reține numele casei de pariuri care oferă cota respectivă (pentru afișaj, ca la VEYRA)."""
    raw = load(DATA / "best_odds.json", {})
    rows = raw.get("results", []) if isinstance(raw, dict) else []
    idx: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        eid = str(row.get("event_id") or "")
        if not eid:
            continue
        bucket = idx.setdefault(eid, {})
        market = row.get("market")
        best_list = row.get("best_odds") or []

        def bk_for(outcome: str) -> Optional[str]:
            for item in best_list:
                if str(item.get("outcome") or "").lower() == outcome:
                    return item.get("bookmaker_name")
            return None

        if market == "1x2":
            if row.get("home_odds"):
                bucket["odds_home"] = row["home_odds"]
                bucket["bk_home"] = row.get("home_bookmaker") or bk_for("home")
            if row.get("draw_odds"):
                bucket["odds_draw"] = row["draw_odds"]
                bucket["bk_draw"] = row.get("draw_bookmaker") or bk_for("draw")
            if row.get("away_odds"):
                bucket["odds_away"] = row["away_odds"]
                bucket["bk_away"] = row.get("away_bookmaker") or bk_for("away")
        elif market in ("over_under_15", "over_under_25", "over_under_35"):
            suffix = market.replace("over_under_", "")
            if row.get("over_odds"):
                bucket[f"odds_over_{suffix}"] = row["over_odds"]
                bucket[f"bk_over_{suffix}"] = bk_for("over")
            if row.get("under_odds"):
                bucket[f"odds_under_{suffix}"] = row["under_odds"]
                bucket[f"bk_under_{suffix}"] = bk_for("under")
        elif market == "btts":
            if row.get("over_odds") or row.get("yes_odds"):
                bucket["odds_btts_yes"] = row.get("over_odds") or row.get("yes_odds")
                bucket["bk_btts_yes"] = bk_for("yes") or bk_for("over")
            if row.get("under_odds") or row.get("no_odds"):
                bucket["odds_btts_no"] = row.get("under_odds") or row.get("no_odds")
                bucket["bk_btts_no"] = bk_for("no") or bk_for("under")
        elif market == "double_chance":
            if row.get("dc_1x_odds"):
                bucket["odds_double_chance_1x"] = row["dc_1x_odds"]
                bucket["bk_double_chance_1x"] = row.get("dc_1x_bookmaker") or bk_for("1x")
            if row.get("dc_x2_odds"):
                bucket["odds_double_chance_x2"] = row["dc_x2_odds"]
                bucket["bk_double_chance_x2"] = row.get("dc_x2_bookmaker") or bk_for("x2")
            if row.get("dc_12_odds"):
                bucket["odds_double_chance_12"] = row["dc_12_odds"]
                bucket["bk_double_chance_12"] = row.get("dc_12_bookmaker") or bk_for("12")
    return idx


def market_odds_for(bucket: Dict[str, Any], market_key: str) -> Optional[float]:
    direct = {
        "home_win": "odds_home", "draw": "odds_draw", "away_win": "odds_away",
        "over_15": "odds_over_15", "under_15": "odds_under_15",
        "over_25": "odds_over_25", "under_25": "odds_under_25",
        "over_35": "odds_over_35", "under_35": "odds_under_35",
        "btts_yes": "odds_btts_yes", "btts_no": "odds_btts_no",
    }
    if market_key in direct:
        v = bucket.get(direct[market_key])
        return float(v) if v else None
    if market_key == "double_chance_1x":
        v = bucket.get("odds_double_chance_1x")
        return float(v) if v else no_vig_pair(bucket.get("odds_home"), bucket.get("odds_draw"))
    if market_key == "double_chance_x2":
        v = bucket.get("odds_double_chance_x2")
        return float(v) if v else no_vig_pair(bucket.get("odds_draw"), bucket.get("odds_away"))
    if market_key == "double_chance_12":
        v = bucket.get("odds_double_chance_12")
        return float(v) if v else no_vig_pair(bucket.get("odds_home"), bucket.get("odds_away"))
    return None


def market_bookmaker_for(bucket: Dict[str, Any], market_key: str) -> Optional[str]:
    """Casa de pariuri care oferă cota folosită. Pentru șansă dublă întoarce casa reală
    doar dacă avem cotă reală de la piața 'double_chance'; dacă am căzut pe fallback-ul
    no-vig sintetic (combinație din cotele 1x2), nu există o casă unică de atribuit."""
    direct = {
        "home_win": "bk_home", "draw": "bk_draw", "away_win": "bk_away",
        "over_15": "bk_over_15", "under_15": "bk_under_15",
        "over_25": "bk_over_25", "under_25": "bk_under_25",
        "over_35": "bk_over_35", "under_35": "bk_under_35",
        "btts_yes": "bk_btts_yes", "btts_no": "bk_btts_no",
        "double_chance_1x": "bk_double_chance_1x",
        "double_chance_x2": "bk_double_chance_x2",
        "double_chance_12": "bk_double_chance_12",
    }
    return bucket.get(direct.get(market_key, "")) if market_key in direct else None


def best_bsd_signal(bsd: Dict[str, Any]) -> float:
    """Cea mai mare probabilitate de succes dintre piețele BSD ale meciului cu adevărat
    discriminante: 1x2, over/under 2.5 și btts. Over 1.5 și under 3.5 sunt excluse
    intenționat — la marea majoritate a meciurilor sunt aproape mereu adevărate
    (>1.5 goluri / <3.5 goluri), deci nu spun nimic despre cât de "sigur" e meciul;
    incluse, ar lăsa să treacă mai departe orice meci, chiar și cele complet
    echilibrate pe toate celelalte piețe. Over 2.5 e singura linie de goluri
    aproximativ echilibrată la nivel de ligă, deci e cea care chiar discriminează."""
    vals: List[float] = []
    for key in ("prob_home", "prob_draw", "prob_away"):
        v = bsd.get(key)
        if v is not None:
            vals.append(float(v))
    for key in ("over_25", "btts_yes"):
        v = bsd.get(key)
        if v is not None:
            v = float(v)
            vals.append(max(v, 100.0 - v))
    return max(vals) if vals else 0.0


def build_lineup_index() -> Dict[str, Dict[str, Any]]:
    """event_id(str) -> {status, home: {formation, confidence, key_players}, away: {...}}.
    Acoperire parțială — event_lineups.json conține doar subsetul de meciuri deja
    prioritizate de restul pipeline-ului, nu toate cele din fereastra de 30 zile."""
    raw = load(DATA / "event_lineups.json", {})
    rows = raw.get("results", []) if isinstance(raw, dict) else []
    idx: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        eid = str(row.get("event_id") or "")
        if not eid:
            continue
        lineups = ((row.get("raw") or {}).get("lineups")) or {}
        if not lineups:
            continue

        def side_summary(side: str) -> Dict[str, Any]:
            team = lineups.get(side) or {}
            players = sorted(team.get("players") or [], key=lambda p: p.get("ai_score") or 0, reverse=True)
            return {
                "formation": team.get("formation"),
                "key_players": [p.get("short_name") or p.get("name") for p in players[:6] if p.get("short_name") or p.get("name")],
            }

        idx[eid] = {
            "status": (row.get("raw") or {}).get("lineup_status"),
            "home": side_summary("home"),
            "away": side_summary("away"),
        }
    return idx


def build_player_impact_index() -> Dict[str, Dict[str, Any]]:
    """event_id(str) -> {home_score, away_score, delta_score, reliability, adjustment_pp}.
    Scor de echipă recalculat din compoziția reală a lotului disponibil (nu doar formă
    generică) — deja calculat de pipeline-ul local, deci gratuit de folosit aici."""
    raw = load(DATA / "player_impact.json", {})
    rows = raw.get("results", []) if isinstance(raw, dict) else []
    idx: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not row.get("available"):
            continue
        eid = str(row.get("event_id") or "")
        if not eid:
            continue
        idx[eid] = {
            "home_score": row.get("home_score"), "away_score": row.get("away_score"),
            "delta_score": row.get("delta_score"), "reliability": row.get("reliability"),
            "adjustment_pp": row.get("adjustment_pp"),
        }
    return idx


def build_standings_index() -> Dict[str, Dict[str, Any]]:
    """team_id(str) -> {position, played, pts, gd, xgd, form, total_teams}."""
    raw = load(DATA / "standings.json", {})
    leagues = raw.get("leagues", {}) if isinstance(raw, dict) else {}
    idx: Dict[str, Dict[str, Any]] = {}
    for league in leagues.values():
        rows = league.get("standings") or []
        total = len(rows)
        for row in rows:
            tid = row.get("team_id")
            if tid is None:
                continue
            idx[str(tid)] = {
                "position": row.get("position"), "played": row.get("played"), "pts": row.get("pts"),
                "gd": row.get("gd"), "xgd": row.get("xgd"), "form": row.get("form"), "total_teams": total,
            }
    return idx


def load_historical_market_auc() -> Dict[str, float]:
    """market_key local (ex. 'over15') -> AUC pe holdout cronologic (meciuri nevăzute la
    antrenare), din data/historical_ensemble_backtest.json — vezi train_historical_ensemble.py
    --holdout-frac. Folosit ca proxy de încredere per piață pentru modelul istoric, în
    lipsa unui quality_grade per-pick ca la signals_v6.json."""
    raw = load(DATA / "historical_ensemble_backtest.json", {})
    results = raw.get("results") or {}
    return {k: v.get("holdout_auc") for k, v in results.items()
            if isinstance(v, dict) and v.get("holdout_auc") is not None}


def derive_risk_tier_historical(probability: float, holdout_auc: Optional[float]) -> str:
    """risk_tier pentru pick-urile modelului istoric: combină puterea probabilității cu
    cât de bine discriminează piața respectivă pe holdout (nevăzut la antrenare) — o piață
    slab discriminantă (AUC~0.55, ex. draw) nu ajunge niciodată 'foarte_sigur', oricât de
    mare ar fi probabilitatea brută calibrată."""
    if holdout_auc is None or holdout_auc < 0.55:
        return "riscant"
    if probability >= 78 and holdout_auc >= 0.65:
        return "foarte_sigur"
    if probability >= 65 and holdout_auc >= 0.58:
        return "sigur"
    if probability >= 55:
        return "moderat"
    return "riscant"


def build_historical_signal_index() -> Dict[str, Dict[str, Any]]:
    """event_id(str) -> pick-ul modelului antrenat pe istoricul complet (vezi
    train_historical_ensemble.py + predict_historical_ensemble.py), pentru meciuri
    viitoare — sursă preferată față de signals_v6.json (verificat prin backtest
    cronologic că generalizează pe date nevăzute, nu doar teoretic)."""
    raw = load(DATA / "ml_predictions_historical.json", {})
    rows = raw.get("results") or []
    auc_idx = load_historical_market_auc()
    idx: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        eid = str(row.get("event_id") or "")
        local_market = row.get("best_market")
        market = LOCAL_MARKET_MAP.get(local_market)
        prob = row.get("best_probability")
        if not eid or not market or prob is None:
            continue
        idx[eid] = {
            "market": market, "market_label": MARKET_LABELS.get(market, market),
            "probability": round(float(prob), 1),
            "risk_tier": derive_risk_tier_historical(float(prob), auc_idx.get(local_market)),
            "odds": None, "edge_pp": None,
        }
    return idx


def build_local_signal_index(calib_idx: Dict[str, str],
                              adaptive_idx: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """event_id(str) -> pick-ul deja calculat de pipeline-ul local — gratuit, calibrat pe
    rezultate reale. Claude primește acest pick ca 'local_pick' (inclusiv risk_tier deja
    derivat) și îl validează sau îl suprascrie, în loc să deriveze o predicție de la zero
    din date brute. Preferă modelul antrenat pe istoricul complet (mai multe date, verificat
    prin backtest cronologic) — vezi build_historical_signal_index() — și cade pe
    signals_v6.json (ml_ensemble.py, antrenat doar pe meciuri recente) pentru meciurile pe
    care modelul istoric nu le acoperă încă."""
    idx = build_historical_signal_index()

    raw = load(DATA / "signals_v6.json", {})
    rows = raw.get("signals") or []
    for row in rows:
        eid = str(row.get("event_id") or "")
        if not eid or eid in idx:
            continue  # modelul istoric are deja un pick pentru acest meci — îl păstrăm
        local_market = row.get("market")  # ex. "over15" — cheia din signals_v6/calibration/adaptive
        market = LOCAL_MARKET_MAP.get(local_market)
        prob = row.get("calibrated_prob")
        if not market or prob is None:
            continue
        prob_pct = float(prob) * 100 if float(prob) <= 1 else float(prob)
        adaptive = adaptive_idx.get(local_market) or {}
        idx[eid] = {
            "market": market, "market_label": MARKET_LABELS.get(market, market),
            "probability": round(prob_pct, 1),
            "risk_tier": derive_risk_tier(
                row.get("quality_grade"), calib_idx.get(local_market),
                adaptive.get("verdict"), bool(adaptive.get("blacklisted")),
            ),
            "odds": row.get("odds"), "edge_pp": row.get("edge_pp"),
        }
    return idx


def build_calibration_health_index() -> Dict[str, str]:
    """market_key local (ex. 'over15') -> status HEALTHY/DRIFT/CRITICAL/NO_DATA."""
    raw = load(DATA / "calibration_health.json", {})
    per_market = raw.get("per_market") or {}
    return {k: (v.get("status") or "NO_DATA") for k, v in per_market.items()}


def build_adaptive_thresholds_index() -> Dict[str, Dict[str, Any]]:
    """market_key local -> {verdict, blacklisted} din data/adaptive_thresholds.json —
    ce spune istoricul de ROI/win-rate despre cât de mult să ai încredere în piața asta."""
    raw = load(DATA / "adaptive_thresholds.json", {})
    by_market = raw.get("by_market") or {}
    idx: Dict[str, Dict[str, Any]] = {}
    for k, v in by_market.items():
        rec = v.get("recommended") or {}
        idx[k] = {
            "verdict": rec.get("verdict"),
            "blacklisted": bool(rec.get("blacklisted")),
            "min_prob_pct": rec.get("min_prob_pct"),
            "min_edge_pp": rec.get("min_edge_pp"),
            "use_defaults": bool(rec.get("use_defaults", True)),
        }
    return idx


def derive_risk_tier(quality_grade: Optional[str], calib_status: Optional[str],
                      adaptive_verdict: Optional[str], blacklisted: bool) -> str:
    """Combină semnale deja calculate local (grad de calitate al pick-ului, sănătatea
    calibrării pe piața respectivă, verdictul de prag adaptiv bazat pe ROI real) într-un
    risk_tier determinist — în loc să-l lase complet la latitudinea lui Claude, care nu
    are cum să știe istoricul de performanță reală al pieței."""
    if blacklisted or calib_status == "CRITICAL":
        return "riscant"
    if adaptive_verdict and "BLACKLIST" in adaptive_verdict:
        return "riscant"
    grade = (quality_grade or "").upper()
    if grade in ("A+", "A"):
        return "foarte_sigur"
    if grade in ("B+", "B"):
        return "sigur"
    if grade in ("C+", "C"):
        return "moderat"
    return "riscant"


def summarize_key_signals(candidate: Dict[str, Any]) -> List[str]:
    """Rezumat scurt (câteva fraze) al contextului deja calculat — trimis lui Claude
    în loc de blob-urile complete (h2h/lineups/weather/standings), ca payload-ul să
    rămână mic chiar și când avem un local_pick de validat."""
    out: List[str] = []
    fh, fa = candidate.get("form_home"), candidate.get("form_away")
    if fh and fh.get("form"):
        out.append(f"Formă gazdă: {fh['form']} ({fh.get('avg_scored')}-{fh.get('avg_conceded')} goluri/meci)")
    if fa and fa.get("form"):
        out.append(f"Formă oaspete: {fa['form']} ({fa.get('avg_scored')}-{fa.get('avg_conceded')} goluri/meci)")
    h2h = candidate.get("h2h")
    if h2h and h2h.get("sample"):
        out.append(f"H2H ({h2h['sample']} meciuri): {h2h.get('home_wins')}-{h2h.get('draws')}-{h2h.get('away_wins')}, "
                    f"medie {h2h.get('avg_goals')} goluri")
    pi = candidate.get("player_impact")
    if pi and (pi.get("reliability") or 0) >= 0.3:
        # adjustment_pp e un dict {home, draw, away} (puncte procentuale per rezultat) —
        # raportăm cel mai mare în modul, pe partea (gazdă/oaspete) căreia îi aparține.
        adj = pi.get("adjustment_pp")
        home_adj = (adj or {}).get("home") or 0 if isinstance(adj, dict) else (adj or 0)
        away_adj = (adj or {}).get("away") or 0 if isinstance(adj, dict) else 0
        biggest, side = (home_adj, "gazdă") if abs(home_adj) >= abs(away_adj) else (away_adj, "oaspete")
        if abs(biggest) >= 3:
            out.append(f"Impact lot ({side}): ajustare {biggest:+.1f}pp (delta_score {pi.get('delta_score')})")
    lu = candidate.get("lineups")
    if lu and lu.get("status"):
        out.append(f"Aliniere: {lu['status']}")
    if candidate.get("is_local_derby"):
        out.append("Derby local — variație crescută.")
    weather = candidate.get("weather")
    if weather and weather.get("label") not in (None, "unknown", "necunoscut / acoperit"):
        out.append(f"Vreme: {weather['label']}")
    return out


def build_candidates() -> List[Dict[str, Any]]:
    events_raw = load(DATA / "events_window.json", {})
    events = events_raw.get("results", []) if isinstance(events_raw, dict) else []

    preds_raw = load(DATA / "predictions.json", {})
    preds = preds_raw.get("results", []) if isinstance(preds_raw, dict) else []
    pred_idx: Dict[str, Dict[str, Any]] = {}
    for p in preds:
        eid = str((p.get("event") or {}).get("id") or p.get("event_id") or "")
        if eid:
            pred_idx[eid] = p

    league_raw = load(DATA / "league_lookup.json", {})
    league_by_id = {str(k): v for k, v in (league_raw.get("by_id") or {}).items()}

    form_raw = load(DATA / "team_form_cache.json", {})
    team_form = form_raw.get("teams") or {}

    h2h_raw = load(DATA / "h2h_context.json", {})
    h2h_list = h2h_raw.get("results", []) if isinstance(h2h_raw, dict) else []
    h2h_idx = {str(h.get("event_id")): h for h in h2h_list if h.get("event_id")}

    odds_idx = build_odds_index()
    lineup_idx = build_lineup_index()
    player_impact_idx = build_player_impact_index()
    standings_idx = build_standings_index()
    calib_health_idx = build_calibration_health_index()
    adaptive_idx = build_adaptive_thresholds_index()
    local_signal_idx = build_local_signal_index(calib_health_idx, adaptive_idx)

    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=HOURS_AHEAD)

    candidates = []
    for e in events:
        if e.get("status") != "notstarted":
            continue
        dt = parse_dt(e.get("event_date"))
        if not dt or dt < now or dt > cutoff:
            continue
        eid = str(e.get("event_id") or e.get("id") or "")
        pred = pred_idx.get(eid)
        local_pick = local_signal_idx.get(eid)
        if not pred and not local_pick:
            continue  # nici predicție BSD, nici pick din modelul local — nimic de arătat

        mr = ((pred or {}).get("markets") or {}).get("match_result", {})
        ou = ((pred or {}).get("markets") or {}).get("over_under", {})
        btts = ((pred or {}).get("markets") or {}).get("btts", {})
        xg = ((pred or {}).get("markets") or {}).get("expected_goals", {})
        score = ((pred or {}).get("markets") or {}).get("score", {})

        bsd = {
            "prob_home": mr.get("prob_home"), "prob_draw": mr.get("prob_draw"), "prob_away": mr.get("prob_away"),
            "xg_home": xg.get("home"), "xg_away": xg.get("away"),
            "over_15": ou.get("prob_over_15"), "over_25": ou.get("prob_over_25"), "over_35": ou.get("prob_over_35"),
            "btts_yes": btts.get("prob_yes"), "most_likely_score": score.get("most_likely"),
        }
        # Pragul de semnal BSD contează doar cât timp nu avem un pick local (modelul
        # antrenat pe istoric) — acela e deja mai de încredere decât un semnal BSD brut slab.
        if not local_pick and best_bsd_signal(bsd) < MIN_BSD_SIGNAL:
            continue  # niciun market nu are un semnal real — nu merită arătat

        home_id = e.get("home_team_id")
        away_id = e.get("away_team_id")
        home_form = team_form.get(str(home_id)) if home_id else None
        away_form = team_form.get(str(away_id)) if away_id else None
        h2h = h2h_idx.get(eid)
        league_name = e.get("league_name") or (league_by_id.get(str(e.get("league_id"))) or {}).get("name") or "Necunoscută"
        odds_bucket = odds_idx.get(eid, {})

        weather = e.get("weather_context") or {}

        candidates.append({
            "event_id": int(eid) if eid.isdigit() else eid,
            "home_team": e.get("home_team"), "away_team": e.get("away_team"),
            "home_team_id": home_id, "away_team_id": away_id,
            "league": league_name, "event_date": e.get("event_date"),
            "is_local_derby": bool(e.get("is_local_derby")),
            "weather": {
                "label": weather.get("label"), "temperature_c": weather.get("temperature_c"),
                "wind_speed": weather.get("wind_speed"),
            } if weather else None,
            "bsd": bsd,
            "market_odds": odds_bucket or None,
            "form_home": {
                "form": home_form.get("form_string"), "avg_scored": home_form.get("avg_goals_scored_last5"),
                "avg_conceded": home_form.get("avg_goals_conceded_last5"),
                "over25_pct": home_form.get("over25_pct"), "btts_pct": home_form.get("btts_last5"),
            } if home_form else None,
            "form_away": {
                "form": away_form.get("form_string"), "avg_scored": away_form.get("avg_goals_scored_last5"),
                "avg_conceded": away_form.get("avg_goals_conceded_last5"),
                "over25_pct": away_form.get("over25_pct"), "btts_pct": away_form.get("btts_last5"),
            } if away_form else None,
            "h2h": {
                "sample": h2h.get("sample"), "home_wins": h2h.get("home_wins"), "away_wins": h2h.get("away_wins"),
                "draws": h2h.get("draws"), "avg_goals": h2h.get("avg_goals"), "btts_pct": h2h.get("btts_pct"),
                "last_matches": [
                    {"date": str(m.get("event_date"))[:10], "home": m.get("home_team"), "away": m.get("away_team"), "score": m.get("score")}
                    for m in (h2h.get("matches") or [])[:3]
                ] or None,
            } if h2h else None,
            "lineups": lineup_idx.get(eid),
            "player_impact": player_impact_idx.get(eid),
            "standings_home": standings_idx.get(str(home_id)) if home_id else None,
            "standings_away": standings_idx.get(str(away_id)) if away_id else None,
            "local_pick": local_pick,
        })
        candidates[-1]["key_signals"] = summarize_key_signals(candidates[-1])

    # Clasăm după puterea semnalului — local_pick (când există) contează mai mult decât
    # BSD brut, modelul local fiind calibrat pe rezultate reale ale aplicației. Ordinea nu
    # mai limitează ce ajunge în claude_predictions.json (main() ia tot pool-ul), doar
    # ordinea de afișare/prioritate.
    def _rank(c: Dict[str, Any]) -> float:
        lp = c.get("local_pick")
        if lp:
            return 100.0 + lp["probability"]  # local_pick trece mereu înaintea fallback-ului BSD
        return best_bsd_signal(c["bsd"])

    candidates.sort(key=_rank, reverse=True)
    return candidates[:MAX_EVENTS]


def call_claude_review(client, tickets_by_period: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """UN SINGUR apel Claude, ieftin și opțional: revizuiește biletele deja construite local
    (nu meciuri individuale) — semnalează probleme reale sau evidențiază cel mai bun bilet.
    Cost aproape constant, indiferent de câte meciuri au intrat în calculul local din
    build_accumulators(). Payload condensat — doar echipe/ligă/piață/probabilitate per picior,
    nu blob-urile complete de context."""
    import anthropic  # local import: opțional, doar dacă rulăm efectiv

    payload = []
    for period, tickets in tickets_by_period.items():
        for t in tickets:
            payload.append({
                "period": period, "label": t["label"], "risk_level": t["risk_level"],
                "combined_odds": t["combined_odds"], "combined_probability_pct": t["combined_probability_pct"],
                "legs": [
                    {"teams": f"{leg['home_team']} vs {leg['away_team']}", "league": leg["league"],
                     "market": leg["market_label"], "probability": leg["probability"]}
                    for leg in t["legs"]
                ],
            })
    if not payload:
        return []

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=[{"type": "text", "text": REVIEW_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            output_config={
                "format": {"type": "json_schema", "schema": REVIEW_SCHEMA},
                "effort": "low",
            },
            messages=[{
                "role": "user",
                "content": "Revizuiește aceste bilete deja construite (nu recalcula nimic):\n"
                            + json.dumps(payload, ensure_ascii=False),
            }],
        )
    except anthropic.APIError as e:
        print(f"[ClaudeAnalysis] eroare API la revizuirea biletelor: {e}")
        return []

    u = response.usage
    print(f"[ClaudeAnalysis] review usage: input={u.input_tokens} "
          f"cache_write={u.cache_creation_input_tokens} cache_read={u.cache_read_input_tokens} "
          f"output={u.output_tokens}")

    if response.stop_reason == "refusal":
        print("[ClaudeAnalysis] revizuire refuzată de model, sărim peste ea")
        return []

    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        return []
    try:
        return json.loads(text).get("reviews", [])
    except Exception as e:
        print(f"[ClaudeAnalysis] răspuns JSON invalid la review: {e}")
        return []


def _serialize_legs(legs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{
        "event_id": leg["event_id"], "home_team": leg["home_team"], "away_team": leg["away_team"],
        "league": leg["league"], "event_date": leg.get("event_date"),
        "market": leg["market"], "market_label": leg["market_label"],
        "odds": leg["odds"], "probability": leg["probability"], "rationale": leg["rationale"],
        "bookmaker": leg.get("bookmaker"),
    } for leg in legs]


def build_accumulators(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    eligible = [r for r in results if r.get("accumulator_eligible") and r.get("odds")]
    eligible.sort(key=lambda r: r.get("probability", 0), reverse=True)

    # Toate verdictele cu o cotă utilă (indiferent de risk_tier) — sortate tot după probabilitate,
    # ca biletele "long shot" să înceapă cu cele mai sigure picioare disponibile, chiar dacă
    # tot biletul, cu 15-30 selecții, e statistic foarte improbabil să pice întreg. Cotele sub
    # MIN_LEG_ODDS sunt excluse și aici — nu adaugă payout, doar încă un risc de eșec.
    broad_pool = [r for r in results if r.get("odds") and r["odds"] >= MIN_LEG_ODDS]
    broad_pool.sort(key=lambda r: r.get("probability", 0), reverse=True)

    def make_ticket(label: str, risk_level: str, min_prob: float, min_legs: int, max_legs: int) -> Optional[Dict[str, Any]]:
        legs = []
        for r in eligible:
            if r.get("probability", 0) < min_prob:
                continue
            if len(legs) >= max_legs:
                break
            legs.append(r)
        if len(legs) < min_legs:
            return None
        combined_odds = 1.0
        combined_prob = 1.0
        for leg in legs:
            combined_odds *= float(leg["odds"])
            combined_prob *= float(leg["probability"]) / 100.0
        return {
            "label": label, "risk_level": risk_level,
            "legs": _serialize_legs(legs),
            "combined_odds": round(combined_odds, 2),
            "combined_probability_pct": round(combined_prob * 100, 4),
        }

    def make_longshot_ticket(label: str, min_total_odds: float, min_legs: int, max_legs: int) -> Optional[Dict[str, Any]]:
        """Bilet 'de amuzament' — multe selecții (până la max_legs), umplut greedy cu cele mai
        probabile picioare disponibile (indiferent de risk_tier) până se atinge cota țintă.
        Nu e un pick recomandat ca 'sigur' — statistic, șansa reală ca tot biletul să pice e mică,
        exact genul de bilet 'poate se agață' cerut explicit, nu o strategie de bază."""
        legs = []
        combined_odds = 1.0
        for r in broad_pool:
            if len(legs) >= max_legs:
                break
            legs.append(r)
            combined_odds *= float(r["odds"])
            if len(legs) >= min_legs and combined_odds >= min_total_odds:
                break
        if len(legs) < min_legs or combined_odds < min_total_odds:
            return None  # pool-ul curent nu are destule verdicte pentru cota țintă
        combined_prob = 1.0
        for leg in legs:
            combined_prob *= float(leg["probability"]) / 100.0
        return {
            "label": label, "risk_level": "longshot",
            "legs": _serialize_legs(legs),
            "combined_odds": round(combined_odds, 2),
            "combined_probability_pct": round(combined_prob * 100, 4),
        }

    tickets = []
    seen_leg_sets = set()

    def add_ticket(t: Optional[Dict[str, Any]]) -> None:
        if not t:
            return
        leg_key = tuple(sorted(leg["event_id"] for leg in t["legs"]))
        if leg_key in seen_leg_sets:
            return  # evită bilete duplicate când setul eligibil e mic
        seen_leg_sets.add(leg_key)
        tickets.append(t)

    for label, min_prob, min_legs, max_legs in [
        ("Maxim sigur", 85.0, 2, 3),
        ("Sigur", 78.0, 4, 6),
    ]:
        add_ticket(make_ticket(label, "safe", min_prob, min_legs, max_legs))

    for label, min_total_odds, min_legs, max_legs in [
        ("Long shot x100", 100.0, 15, 30),
        ("Long shot x500", 500.0, 20, 35),
    ]:
        add_ticket(make_longshot_ticket(label, min_total_odds, min_legs, max_legs))

    return tickets


ACCUMULATOR_PERIODS = [("7", 7), ("10", 10), ("30", 30)]


def build_accumulators_by_period(results: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Bilete acumulator pre-calculate pentru fiecare fereastră de generare (7/10/30 zile),
    ca frontend-ul să aleagă direct setul potrivit, fără nicio recalculare în browser.

    v7: delegă către smart_accumulator (edge-based, control de corelație, ancoră de
    piață). Fallback la logica clasică dacă modulul/semnalele lipsesc."""
    try:
        from smart_accumulator import build_tickets_by_period
        smart = build_tickets_by_period()
        if any(smart.values()):
            print("[ClaudeAnalysis] Acumulatoare v7 (smart_accumulator) folosite.")
            return smart
        print("[ClaudeAnalysis] smart_accumulator gol — fallback la logica clasică.")
    except Exception as e:
        print(f"[ClaudeAnalysis] smart_accumulator indisponibil ({e}) — fallback clasic.")

    now = datetime.now(timezone.utc)
    by_period: Dict[str, List[Dict[str, Any]]] = {}
    for key, days in ACCUMULATOR_PERIODS:
        cutoff = now + timedelta(days=days)
        window = [r for r in results if (dt := parse_dt(r.get("event_date"))) and dt <= cutoff]
        by_period[key] = build_accumulators(window)
    return by_period


def main() -> None:
    pool = build_candidates()
    adaptive_gate_idx = build_adaptive_thresholds_index()
    gate_skipped = 0
    print(f"[ClaudeAnalysis] {len(pool)} meciuri cu predicție disponibilă (model local istoric "
          f"și/sau BSD brut) în următoarele {HOURS_AHEAD}h.")

    # Predicțiile per meci vin STRICT din modelul local — zero apeluri Claude, cost zero
    # (vezi build_local_signal_index() din build_candidates()). Meciurile fără niciun pick
    # local (modelul nu le acoperă încă) rămân în afara claude_predictions.json — frontend-ul
    # are propria analiză rapidă locală pentru ele.
    results: List[Dict[str, Any]] = []
    for c in pool:
        lp = c.get("local_pick")
        if not lp:
            continue
        market_key = lp["market"]
        prob = lp["probability"]
        risk_tier = lp["risk_tier"]

        # ---- POARTA ADAPTIVA: nu emite verdicte pe piete pe care istoricul le-a
        # marcat ca structural pierzatoare sub un anumit prag (ex: under35 <80% prob,
        # ROI -28%). Frontend-ul cade automat pe analiza rapida locala (care exclude
        # under_35). Se aplica doar cand motorul are destule date (use_defaults=false).
        compact_mkt = COMPACT_FROM_LOCAL.get(market_key)
        rec = adaptive_gate_idx.get(compact_mkt) if compact_mkt else None
        if rec and not rec.get("use_defaults", True):
            min_prob = rec.get("min_prob_pct")
            if rec.get("blacklisted"):
                gate_skipped += 1
                continue
            if min_prob is not None and prob is not None and prob < float(min_prob):
                gate_skipped += 1
                continue
        odds_bucket = c.get("market_odds") or {}
        odds = market_odds_for(odds_bucket, market_key)
        bookmaker = market_bookmaker_for(odds_bucket, market_key) if odds is not None else None
        fair_odds = round(100.0 / prob, 3) if prob and prob > 0 else None
        edge_pp = None
        value_pct = None
        if odds is not None and prob is not None:
            implied_pct = 100.0 / odds
            edge_pp = round(prob - implied_pct, 1)
            value_pct = round((prob / 100.0) * odds * 100 - 100, 1)
        final_odds = odds if odds is not None else fair_odds
        accumulator_eligible = (
            prob is not None and prob >= 78
            and risk_tier in ("foarte_sigur", "sigur")
            and final_odds is not None and final_odds >= MIN_LEG_ODDS
        )
        market_label = MARKET_LABELS.get(market_key, market_key)
        results.append({
            "event_id": c["event_id"], "home_team": c["home_team"], "away_team": c["away_team"],
            "league": c["league"], "event_date": c["event_date"],
            "market": market_key, "market_label": market_label,
            "probability": prob, "risk_tier": risk_tier,
            "rationale": f"Model local antrenat pe istoric (fără AI): {prob}% pentru {market_label}.",
            "accumulator_eligible": accumulator_eligible,
            "odds": final_odds,
            "odds_is_market": odds is not None,
            "bookmaker": bookmaker,
            "fair_odds": fair_odds,
            "edge_pp": edge_pp,
            "value_pct": value_pct,
            "is_local_derby": c.get("is_local_derby"),
            "weather": c.get("weather"),
            "form_home": c.get("form_home"),
            "form_away": c.get("form_away"),
            "h2h": c.get("h2h"),
            "source": "local_model",
        })

    save(DATA / "claude_predictions.json", {
        "updated_at": datetime.now(timezone.utc).isoformat(), "model": "local-ensemble-historical",
        "hours_ahead": HOURS_AHEAD, "pool_size": len(pool), "analyzed": len(results),
        "count": len(results), "results": results,
    })

    tickets_by_period = build_accumulators_by_period(results)
    print(f"[ClaudeAnalysis] Poarta adaptiva: {gate_skipped} verdicte locale filtrate "
          f"(piete sub prag, ex: under35 <80%).")
    total_tickets = sum(len(v) for v in tickets_by_period.values())
    print(f"[ClaudeAnalysis] {len(results)} predicții din modelul local, {total_tickets} bilete acumulator "
          f"({', '.join(f'{k}={len(v)}' for k, v in tickets_by_period.items())}).")

    # Revizuire Claude, opțională și ieftină: UN SINGUR apel care citește DOAR biletele deja
    # construite mai sus (nu meciurile individuale) — vezi call_claude_review(). Dacă lipsește
    # cheia API sau pachetul anthropic, biletele rămân neschimbate (funcționează 100% și fără AI).
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            reviews = call_claude_review(client, tickets_by_period)
            review_idx = {(r.get("period"), r.get("label")): r for r in reviews}
            for period, tickets in tickets_by_period.items():
                for t in tickets:
                    r = review_idx.get((period, t["label"]))
                    t["claude_concern"] = r.get("concern") if r else None
                    t["claude_highlight"] = bool(r.get("highlight")) if r else False
            print(f"[ClaudeAnalysis] {len(reviews)} bilete revizuite de Claude.")
        except ImportError:
            print("[ClaudeAnalysis] pachetul 'anthropic' nu este instalat — sar peste revizuirea Claude "
                  "(biletele locale rămân neschimbate).")
    else:
        print("[ClaudeAnalysis] ANTHROPIC_API_KEY nu este setat — sar peste revizuirea Claude "
              "(biletele locale rămân neschimbate).")

    save(DATA / "claude_accumulators.json", {
        "updated_at": datetime.now(timezone.utc).isoformat(), "tickets_by_period": tickets_by_period,
    })


if __name__ == "__main__":
    main()
