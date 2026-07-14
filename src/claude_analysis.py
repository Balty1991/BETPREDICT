#!/usr/bin/env python3
"""BETPREDICT — Claude AI Analysis Engine.

Analizează meciurile apropiate (cu date suficiente: predicții BSD, formă, cote)
folosind Claude API și produce verdicte calibrate, orientate spre acumulatoare
sigure. Scrie data/claude_predictions.json (verdict per meci) și
data/claude_accumulators.json (bilete acumulator generate automat).

Arhitectură pe două niveluri, ca să țină costul mic dar analiza profundă:

1. Nivel local (gratuit) — din toate meciurile din fereastra de 30 zile cu
   predicție BSD, filtrează cele fără niciun semnal real (~50/50 peste tot,
   vezi MIN_BSD_SIGNAL) și le clasează după cât de puternic e semnalul.
2. Nivel Claude (Sonnet 5, cu thinking) — analizează în profunzime DOAR primele
   TOP_N_DEEP meciuri din clasament, cu tot ce oferă local pipeline-ul BSD
   pentru ele: formă, H2H (inclusiv ultimele meciuri directe), cote reale de
   piață, aliniere probabilă/jucători cheie (când există), vreme, derby local.

Analizând profund doar un set mic, curat, putem folosi un model mai bun
(Sonnet, cu thinking) și mai multe date per meci, fără să explodeze costul —
opusul variantei anterioare (Haiku, fără thinking, pe toate cele ~280 meciuri
deodată, cu date minime per meci).
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

MODEL = "claude-sonnet-5"
HOURS_AHEAD = int(os.environ.get("CLAUDE_HOURS_AHEAD", "720"))
# Plafon de siguranță pe mărimea "pool"-ului local (gratuit) din care clasăm meciurile —
# rareori atins, doar o limită superioară rezonabilă.
MAX_EVENTS = int(os.environ.get("CLAUDE_MAX_EVENTS", "350"))
# Câte meciuri (cele cu cel mai puternic semnal BSD) primesc efectiv analiză Claude.
# Ăsta e principalul buton de cost: număr mic + model bun + date bogate per meci.
TOP_N_DEEP = int(os.environ.get("CLAUDE_TOP_N_DEEP", "55"))
BATCH_SIZE = int(os.environ.get("CLAUDE_BATCH_SIZE", "10"))
# Prag minim de semnal BSD (cea mai mare probabilitate dintre toate piețele) ca să intre
# meciul în clasamentul pentru analiză profundă — filtrează meciurile "monedă aruncată"
# (~50/50 peste tot), care oricum nu produc verdicte utile pentru acumulator.
MIN_BSD_SIGNAL = float(os.environ.get("CLAUDE_MIN_BSD_SIGNAL", "62"))
# Cotă minimă ca o piață să fie considerată pentru acumulator — sub acest prag, riscul
# (orice contra-rezultat pică tot biletul) nu se justifică față de cât plătește piciorul.
MIN_LEG_ODDS = float(os.environ.get("CLAUDE_MIN_LEG_ODDS", "1.10"))
# Buget de timp intern (secunde) — ne oprim și salvăm ce avem înainte ca
# GitHub Actions să omoare jobul la timeout, ca să nu pierdem apelurile deja plătite.
MAX_RUNTIME_SECONDS = int(os.environ.get("CLAUDE_MAX_RUNTIME_SECONDS", "600"))

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
                        "minimum": 0,
                        "maximum": 100,
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
                        "description": "true doar dacă probabilitatea e foarte mare (>=78), risk_tier e foarte_sigur/sigur, și nu există semnale contradictorii.",
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

SYSTEM_PROMPT = """Ești un analist cantitativ de pariuri sportive pentru un motor de acumulatoare —
miza e să găsești DOAR pick-uri cu adevărat solide, nu să acoperi fiecare meci primit. Meciurile
primite au fost deja pre-filtrate local (au un semnal BSD real pe cel puțin o piață), deci merită
o analiză atentă — dar tot nu toate vor avea un pick suficient de sigur după ce le analizezi tu.

Primești loturi de meciuri de fotbal cu date bogate:
- bsd: probabilități dintr-un model ML extern (1x2, over/under, btts) + xG așteptat
- market_odds: cote reale de piață (de la case de pariuri)
- form_home / form_away: formă ultimele 5 meciuri (rezultate, goluri marcate/primite, % over/btts)
- h2h: istoric direct — statistici sumare + ultimele meciuri directe concrete (scoruri)
- lineups: aliniere probabilă/confirmată și jucători cheie, când e disponibilă (nu la toate meciurile)
- weather: condiții meteo la meci; is_local_derby: dacă e derby local (variație mai mare)
- player_impact: scor de echipă recalculat după calitatea/disponibilitatea reală a jucătorilor
  (nu doar formă generică) — delta_score = diferența de putere gazdă vs oaspete atribuibilă
  lotului disponibil; adjustment_pp = cât ar trebui ajustate probabilitățile 1x2 (puncte
  procentuale) din cauza absențelor/titularilor; reliability = cât de completă e informația
  de lot (sub ~0.3 înseamnă date parțiale, tratează adjustment_pp cu prudență)
- standings_home / standings_away: poziție în clasament, puncte, formă pe tot sezonul (nu doar
  ultimele 5), gd (diferență goluri), xgd (diferență xG) și total_teams (câte echipe are liga) —
  folosește-le pentru context de miză (ex. echipă de mijlocul clasamentului fără nimic de jucat
  vs. luptă la retrogradare/promovare/cupe europene, care cresc variația rezultatului)
Nu toate meciurile au date complete pe toate categoriile — folosește ce ai disponibil.

Pentru fiecare meci, scanează METODIC toate piețele din bsd — prob_home, prob_draw, prob_away,
over_15/25/35 (și complementul lor under), btts_yes (și complementul btts_no) — și alege piața
cu cea mai mare probabilitate reală, nu prima piață plauzibilă. Nu te opri implicit la 1x2 sau
la "gazda câștigă" doar pentru că e prima piață din date: de multe ori un market de goluri
(ex. under 2.5 la 72%) e un pick mult mai solid decât rezultatul exact (ex. gazdă favorită la
doar 32%). Preferă piețe cu variație mică (șansă dublă, over/under, ambele echipe marchează)
față de rezultate exacte greu de anticipat, DAR doar dintre cele cu adevărat probabile.

Folosește activ datele bogate, nu doar bsd: formă + ultimele meciuri H2H concrete pot confirma
sau contrazice modelul BSD (citează-le în rationale cu cifre/rezultate reale); alinierea/jucătorii
cheie lipsă pot schimba un pick (ex. atacant titular absent → scade probabilitatea de over/goluri
gazdă); derby local sau vreme extremă cresc variația — tratează-le cu mai multă prudență
(risk_tier mai conservator) chiar dacă BSD arată un procent ridicat.

Compară probabilitatea BSD cu cota reală de piață (probabilitate implicită = 1/cotă) — dacă
sunt apropiate, piața confirmă semnalul; dacă BSD e mult peste piață, tratează cu suspiciune
(poate fi zgomot de model, nu edge real).

IMPORTANT — nu e obligatoriu un verdict per meci. Omite complet din răspuns orice meci unde:
- nicio piață nu atinge o probabilitate reală de succes de cel puțin ~60%, SAU
- semnalele se contrazic puternic (BSD favorizează o parte dar forma/H2H/alinierea arată
  contrariul) fără o explicație clară de ce probabilitatea rămâne totuși ridicată.
E mult mai valoros să întorci verdicte solide pentru jumătate din lot decât un verdict slab
pentru fiecare meci primit.

Fii strict la accumulator_eligible: marchează true doar când probabilitatea calibrată este
foarte ridicată (>=78), risk_tier e "foarte_sigur" sau "sigur", ȘI datele nu se contrazic.

Răspunde STRICT conform schemei JSON, în română, concis dar concret (citează cifre/rezultate
reale din datele primite, nu generalități)."""


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

        bsd = {
            "prob_home": mr.get("prob_home"), "prob_draw": mr.get("prob_draw"), "prob_away": mr.get("prob_away"),
            "xg_home": xg.get("home"), "xg_away": xg.get("away"),
            "over_15": ou.get("prob_over_15"), "over_25": ou.get("prob_over_25"), "over_35": ou.get("prob_over_35"),
            "btts_yes": btts.get("prob_yes"), "most_likely_score": score.get("most_likely"),
        }
        if best_bsd_signal(bsd) < MIN_BSD_SIGNAL:
            continue  # niciun market nu are un semnal real — nu merită trimis la Claude

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
        })

    # Clasăm după puterea semnalului BSD — cele mai "sigure" meciuri ajung primele
    # în listă, gata pentru selecția top TOP_N_DEEP din main().
    candidates.sort(key=lambda c: best_bsd_signal(c["bsd"]), reverse=True)
    return candidates[:MAX_EVENTS]


def call_claude(client, batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    import anthropic  # local import: opțional, doar dacă rulăm efectiv

    payload = batch  # include market_odds, lineups etc. — Claude analizează cu tot ce avem
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=8192,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            output_config={
                "format": {"type": "json_schema", "schema": VERDICT_SCHEMA},
                "effort": "medium",
            },
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
    ca frontend-ul să aleagă direct setul potrivit, fără nicio recalculare în browser."""
    now = datetime.now(timezone.utc)
    by_period: Dict[str, List[Dict[str, Any]]] = {}
    for key, days in ACCUMULATOR_PERIODS:
        cutoff = now + timedelta(days=days)
        window = [r for r in results if (dt := parse_dt(r.get("event_date"))) and dt <= cutoff]
        by_period[key] = build_accumulators(window)
    return by_period


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

    pool = build_candidates()
    candidates = pool[:TOP_N_DEEP]
    print(f"[ClaudeAnalysis] {len(pool)} meciuri cu semnal BSD real în următoarele {HOURS_AHEAD}h "
          f"(prag {MIN_BSD_SIGNAL}) — analizăm profund primele {len(candidates)} (TOP_N_DEEP={TOP_N_DEEP}).")
    if not candidates:
        save(DATA / "claude_predictions.json", {
            "updated_at": datetime.now(timezone.utc).isoformat(), "model": MODEL, "count": 0, "results": [],
        })
        save(DATA / "claude_accumulators.json", {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "tickets_by_period": {key: [] for key, _ in ACCUMULATOR_PERIODS},
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
            odds_bucket = c.get("market_odds") or {}
            odds = market_odds_for(odds_bucket, market_key)
            bookmaker = market_bookmaker_for(odds_bucket, market_key) if odds is not None else None
            prob = v.get("probability")
            risk_tier = v.get("risk_tier")
            fair_odds = round(100.0 / prob, 3) if prob and prob > 0 else None
            # Edge/Value — cât de mult diferă probabilitatea noastră de cea implicită
            # a pieței (1/cotă); doar când avem o cotă reală de piață, nu cotă fair sintetică.
            edge_pp = None
            value_pct = None
            if odds is not None and prob is not None:
                implied_pct = 100.0 / odds
                edge_pp = round(prob - implied_pct, 1)
                value_pct = round((prob / 100.0) * odds * 100 - 100, 1)
            final_odds = odds if odds is not None else fair_odds
            # Plasă de siguranță independentă de model: eligibilitatea pentru acumulator
            # nu se bazează doar pe ce spune Claude — o forțăm pe praguri stricte aici.
            # Cotele sub MIN_LEG_ODDS sunt excluse: riscul de a strica tot biletul nu se
            # justifică pentru ce plătește piciorul respectiv.
            accumulator_eligible = (
                bool(v.get("accumulator_eligible"))
                and prob is not None and prob >= 78
                and risk_tier in ("foarte_sigur", "sigur")
                and final_odds is not None and final_odds >= MIN_LEG_ODDS
            )
            results.append({
                "event_id": c["event_id"], "home_team": c["home_team"], "away_team": c["away_team"],
                "league": c["league"], "event_date": c["event_date"],
                "market": market_key, "market_label": MARKET_LABELS.get(market_key, market_key),
                "probability": prob, "risk_tier": risk_tier,
                "rationale": v.get("rationale"), "accumulator_eligible": accumulator_eligible,
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
            })

    save(DATA / "claude_predictions.json", {
        "updated_at": datetime.now(timezone.utc).isoformat(), "model": MODEL,
        "hours_ahead": HOURS_AHEAD, "pool_size": len(pool), "analyzed": len(candidates),
        "count": len(results), "results": results,
    })

    tickets_by_period = build_accumulators_by_period(results)
    save(DATA / "claude_accumulators.json", {
        "updated_at": datetime.now(timezone.utc).isoformat(), "tickets_by_period": tickets_by_period,
    })
    total_tickets = sum(len(v) for v in tickets_by_period.values())
    print(f"[ClaudeAnalysis] {len(results)} verdicte scrise, {total_tickets} bilete acumulator generate "
          f"({', '.join(f'{k}={len(v)}' for k, v in tickets_by_period.items())}).")


if __name__ == "__main__":
    main()
