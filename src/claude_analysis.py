#!/usr/bin/env python3
"""BETPREDICT — Claude AI Analysis Engine.

Analizează meciurile apropiate (cu date suficiente: predicții BSD, formă, cote)
folosind Claude API și produce verdicte calibrate, orientate spre acumulatoare
sigure. Scrie data/claude_predictions.json (verdict per meci) și
data/claude_accumulators.json (bilete acumulator generate automat).

Analizează toate evenimentele din fereastra de fetch (implicit 30 zile) care au
deja o predicție BSD — CLAUDE_HOURS_AHEAD/CLAUDE_MAX_EVENTS rămân reglabile din
mediu dacă trebuie redus costul per rulare (vezi .github/workflows/claude_analysis.yml).
"""
from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

MODEL = "claude-opus-4-8"
HOURS_AHEAD = int(os.environ.get("CLAUDE_HOURS_AHEAD", "720"))
MAX_EVENTS = int(os.environ.get("CLAUDE_MAX_EVENTS", "400"))
BATCH_SIZE = int(os.environ.get("CLAUDE_BATCH_SIZE", "12"))
# Buget de timp intern (secunde) — ne oprim și salvăm ce avem înainte ca
# GitHub Actions să omoare jobul la timeout, ca să nu pierdem apelurile deja plătite.
MAX_RUNTIME_SECONDS = int(os.environ.get("CLAUDE_MAX_RUNTIME_SECONDS", "1800"))

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

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "integer"},
                    "market": {"type": "string", "enum": list(MARKET_LABELS.keys())},
                    "probability": {
                        "type": "number",
                        "description": "Probabilitatea calibrată (0-100) ca piața aleasă să se realizeze.",
                    },
                    "risk_tier": {
                        "type": "string",
                        "enum": ["foarte_sigur", "sigur", "moderat", "riscant"],
                    },
                    "rationale": {
                        "type": "string",
                        "description": "1-2 propoziții în română, citând cifrele concrete din date.",
                    },
                    "accumulator_eligible": {
                        "type": "boolean",
                        "description": "true doar dacă probabilitatea e mare (>=75) și nu există semnale contradictorii.",
                    },
                },
                "required": ["event_id", "market", "probability", "risk_tier", "rationale", "accumulator_eligible"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["verdicts"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """Ești un analist cantitativ de pariuri sportive pentru un motor de acumulatoare.
Primești loturi de meciuri de fotbal cu date brute: cote reale de piață, probabilități dintr-un
model ML extern (BSD), formă recentă a echipelor, head-to-head.

Pentru fiecare meci din lot, alege piața cu cea mai bună combinație probabilitate/încredere
(nu neapărat cota cea mai mare) dintre cele din schema JSON. Preferă piețe cu variație mică
(șansă dublă, over/under, ambele echipe marchează) față de rezultate exacte greu de anticipat,
mai ales când probabilitățile sunt apropiate între ele.

Fii conservator la accumulator_eligible: marchează true doar când probabilitatea calibrată
este ridicată (>=75) ȘI datele (formă, H2H, cote) nu se contrazic. Când modelul BSD și forma
recentă sau H2H se contrazic puternic, redu probabilitatea și explică de ce în rationale.

Răspunde STRICT conform schemei JSON, în română, concis, cu numere concrete din datele primite."""


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


def build_odds_index() -> Dict[str, Dict[str, float]]:
    """event_id(str) -> {odds_home, odds_draw, odds_away, odds_over_15, ...}"""
    raw = load(DATA / "best_odds.json", {})
    rows = raw.get("results", []) if isinstance(raw, dict) else []
    idx: Dict[str, Dict[str, float]] = {}
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


def market_odds_for(bucket: Dict[str, float], market_key: str) -> Optional[float]:
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
        return no_vig_pair(bucket.get("odds_home"), bucket.get("odds_draw"))
    if market_key == "double_chance_x2":
        return no_vig_pair(bucket.get("odds_draw"), bucket.get("odds_away"))
    if market_key == "double_chance_12":
        return no_vig_pair(bucket.get("odds_home"), bucket.get("odds_away"))
    return None


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
        if not pred:
            continue  # fără predicție BSD nu avem bază numerică suficientă

        mr = (pred.get("markets") or {}).get("match_result", {})
        ou = (pred.get("markets") or {}).get("over_under", {})
        btts = (pred.get("markets") or {}).get("btts", {})
        xg = (pred.get("markets") or {}).get("expected_goals", {})
        score = (pred.get("markets") or {}).get("score", {})

        home_id = e.get("home_team_id")
        away_id = e.get("away_team_id")
        home_form = team_form.get(str(home_id)) if home_id else None
        away_form = team_form.get(str(away_id)) if away_id else None
        h2h = h2h_idx.get(eid)
        league_name = e.get("league_name") or (league_by_id.get(str(e.get("league_id"))) or {}).get("name") or "Necunoscută"
        odds_bucket = odds_idx.get(eid, {})

        candidates.append({
            "event_id": int(eid) if eid.isdigit() else eid,
            "home_team": e.get("home_team"), "away_team": e.get("away_team"),
            "home_team_id": home_id, "away_team_id": away_id,
            "league": league_name, "event_date": e.get("event_date"),
            "bsd": {
                "prob_home": mr.get("prob_home"), "prob_draw": mr.get("prob_draw"), "prob_away": mr.get("prob_away"),
                "xg_home": xg.get("home"), "xg_away": xg.get("away"),
                "over_15": ou.get("prob_over_15"), "over_25": ou.get("prob_over_25"), "over_35": ou.get("prob_over_35"),
                "btts_yes": btts.get("prob_yes"), "most_likely_score": score.get("most_likely"),
            },
            "market_odds": odds_bucket or None,
            "form_home": {
                "form": home_form.get("form_string"), "avg_scored": home_form.get("avg_goals_scored_last5"),
                "avg_conceded": home_form.get("avg_goals_conceded_last5"),
            } if home_form else None,
            "form_away": {
                "form": away_form.get("form_string"), "avg_scored": away_form.get("avg_goals_scored_last5"),
                "avg_conceded": away_form.get("avg_goals_conceded_last5"),
            } if away_form else None,
            "h2h": {
                "sample": h2h.get("sample"), "home_wins": h2h.get("home_wins"), "away_wins": h2h.get("away_wins"),
                "draws": h2h.get("draws"), "avg_goals": h2h.get("avg_goals"), "btts_pct": h2h.get("btts_pct"),
            } if h2h else None,
        })

    candidates.sort(key=lambda c: c["event_date"] or "")
    return candidates[:MAX_EVENTS]


def call_claude(client, batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    import anthropic  # local import: opțional, doar dacă rulăm efectiv

    payload = [
        {k: v for k, v in c.items() if k not in ("market_odds",)}
        for c in batch
    ]
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=8192,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            output_config={"format": {"type": "json_schema", "schema": VERDICT_SCHEMA}},
            messages=[{
                "role": "user",
                "content": "Analizează aceste meciuri și întoarce un verdict per event_id:\n"
                            + json.dumps(payload, ensure_ascii=False),
            }],
        )
    except anthropic.APIError as e:
        print(f"[ClaudeAnalysis] eroare API pe batch ({len(batch)} meciuri): {e}")
        return []

    if response.stop_reason == "refusal":
        print("[ClaudeAnalysis] batch refuzat de model, sărim peste el")
        return []

    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        return []
    try:
        return json.loads(text).get("verdicts", [])
    except Exception as e:
        print(f"[ClaudeAnalysis] răspuns JSON invalid: {e}")
        return []


def build_accumulators(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    eligible = [r for r in results if r.get("accumulator_eligible") and r.get("odds")]
    eligible.sort(key=lambda r: r.get("probability", 0), reverse=True)

    def make_ticket(label: str, min_prob: float, min_legs: int, max_legs: int) -> Optional[Dict[str, Any]]:
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
            "label": label,
            "legs": [{
                "event_id": leg["event_id"], "home_team": leg["home_team"], "away_team": leg["away_team"],
                "league": leg["league"], "market": leg["market"], "market_label": leg["market_label"],
                "odds": leg["odds"], "probability": leg["probability"], "rationale": leg["rationale"],
            } for leg in legs],
            "combined_odds": round(combined_odds, 2),
            "combined_probability_pct": round(combined_prob * 100, 1),
        }

    tickets = []
    seen_leg_sets = set()
    for label, min_prob, min_legs, max_legs in [
        ("Maxim sigur", 85.0, 2, 3),
        ("Sigur", 75.0, 4, 6),
    ]:
        t = make_ticket(label, min_prob, min_legs, max_legs)
        if not t:
            continue
        leg_key = tuple(sorted(leg["event_id"] for leg in t["legs"]))
        if leg_key in seen_leg_sets:
            continue  # evită bilete duplicate când setul eligibil e mic
        seen_leg_sets.add(leg_key)
        tickets.append(t)
    return tickets


def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        print("[ClaudeAnalysis] ANTHROPIC_API_KEY nu este setat — sar peste analiza Claude.")
        return

    try:
        import anthropic
    except ImportError:
        print("[ClaudeAnalysis] pachetul 'anthropic' nu este instalat — sar peste analiza Claude.")
        return

    candidates = build_candidates()
    print(f"[ClaudeAnalysis] {len(candidates)} meciuri candidate în următoarele {HOURS_AHEAD}h cu predicție BSD.")
    if not candidates:
        save(DATA / "claude_predictions.json", {
            "updated_at": datetime.now(timezone.utc).isoformat(), "model": MODEL, "count": 0, "results": [],
        })
        save(DATA / "claude_accumulators.json", {
            "updated_at": datetime.now(timezone.utc).isoformat(), "tickets": [],
        })
        return

    client = anthropic.Anthropic(api_key=api_key)
    by_id = {str(c["event_id"]): c for c in candidates}
    results: List[Dict[str, Any]] = []
    started_at = time.monotonic()

    for i in range(0, len(candidates), BATCH_SIZE):
        if time.monotonic() - started_at > MAX_RUNTIME_SECONDS:
            print(f"[ClaudeAnalysis] buget de timp epuizat ({MAX_RUNTIME_SECONDS}s) — "
                  f"salvez {len(results)} verdicte deja obținute și opresc rularea.")
            break
        batch = candidates[i:i + BATCH_SIZE]
        verdicts = call_claude(client, batch)
        for v in verdicts:
            eid = str(v.get("event_id"))
            c = by_id.get(eid)
            if not c:
                continue
            market_key = v.get("market")
            odds = market_odds_for(c.get("market_odds") or {}, market_key)
            prob = v.get("probability")
            fair_odds = round(100.0 / prob, 3) if prob and prob > 0 else None
            results.append({
                "event_id": c["event_id"], "home_team": c["home_team"], "away_team": c["away_team"],
                "league": c["league"], "event_date": c["event_date"],
                "market": market_key, "market_label": MARKET_LABELS.get(market_key, market_key),
                "probability": prob, "risk_tier": v.get("risk_tier"),
                "rationale": v.get("rationale"), "accumulator_eligible": bool(v.get("accumulator_eligible")),
                "odds": odds if odds is not None else fair_odds,
                "odds_is_market": odds is not None,
            })

    save(DATA / "claude_predictions.json", {
        "updated_at": datetime.now(timezone.utc).isoformat(), "model": MODEL,
        "hours_ahead": HOURS_AHEAD, "count": len(results), "results": results,
    })

    tickets = build_accumulators(results)
    save(DATA / "claude_accumulators.json", {
        "updated_at": datetime.now(timezone.utc).isoformat(), "tickets": tickets,
    })
    print(f"[ClaudeAnalysis] {len(results)} verdicte scrise, {len(tickets)} bilete acumulator generate.")


if __name__ == "__main__":
    main()
