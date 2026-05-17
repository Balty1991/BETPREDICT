#!/usr/bin/env python3
"""
BetPredict Pro — Daily Data Fetcher
====================================
Rulează zilnic la 06:00 UTC via GitHub Actions.
Colectează: predicții ML, meciuri de azi, cele mai bune cote, clasamente.
Calculează: Value Bets cu EV și Kelly Criterion.

Endpoints BSD API v2 folosite:
  GET /api/v2/events/          — lista meciuri
  GET /api/v2/predictions/     — predicții ML CatBoost
  GET /api/v2/best-odds/       — cele mai bune cote per bookmaker
  GET /api/v2/standings/       — clasament ligă
  GET /api/v2/leagues/         — lista ligilor
"""

import os
import json
import requests
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Config ─────────────────────────────────────────────────────────────────
API_KEY  = os.environ.get("BSD_API_KEY", "")
BASE_V2  = "https://sports.bzzoiro.com/api/v2"
BASE_V1  = "https://sports.bzzoiro.com/api"
HEADERS  = {"Authorization": f"Token {API_KEY}"}
DATA_DIR = Path(__file__).parent.parent / "data"

# Ligi urmărite — ID → Nume afișat
LEAGUES = {
    23: "Superliga României",
    1:  "Premier League",
    7:  "Champions League",
    3:  "La Liga",
    4:  "Serie A",
    5:  "Bundesliga",
    6:  "Ligue 1",
    8:  "Europa League",
    2:  "Liga Portugal",
    10: "Eredivisie",
}

# ── Helpers ─────────────────────────────────────────────────────────────────
def get(url, params=None):
    """GET cu 3 reîncercări."""
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError as e:
            print(f"  ✗ HTTP {e.response.status_code} la {url}")
            if e.response.status_code in (401, 403):
                print("  ⚠ API key invalidă sau expirata!")
                return None
            if attempt == 2:
                return None
        except Exception as e:
            if attempt == 2:
                print(f"  ✗ EROARE la {url}: {e}")
                return None

def paginate(url, params=None):
    """Colectează toate paginile unui endpoint paginat."""
    params = params or {}
    params.setdefault("limit", 100)
    results = []
    page_url = url
    seen_urls = set()
    
    while page_url and page_url not in seen_urls:
        seen_urls.add(page_url)
        data = get(page_url, params if page_url == url else None)
        if not data:
            break
        results.extend(data.get("results", []))
        page_url = data.get("next")
        params = {}   # next URL conține deja query params
    
    return results

def save_atomic(filename, data):
    """Scriere atomică în data/ (tmp → replace)."""
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / filename
    tmp  = path.with_suffix(".tmp")
    
    try:
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        tmp.replace(path)
        count = len(data) if isinstance(data, list) else (
            len(data.get("results", data.get("events", [])))
            if isinstance(data, dict) else "—"
        )
        print(f"  ✓ {filename} ({count} înregistrări)")
    except Exception as e:
        print(f"  ✗ Nu s-a putut salva {filename}: {e}")

def today_iso():
    """Data de azi în fusul orar Dubai (UTC+4) — BSD folosește Asia/Dubai."""
    now = datetime.now(timezone.utc) + timedelta(hours=4)
    return now.strftime("%Y-%m-%d")

def now_iso():
    return datetime.now(timezone.utc).isoformat()

# ── 1. Predicții ML ─────────────────────────────────────────────────────────
def fetch_predictions():
    print("\n📊 Predicții ML...")
    
    # Încearcă v2 mai întâi
    data = get(f"{BASE_V2}/predictions/")
    
    # Fallback la v1 dacă v2 nu funcționează
    if not data:
        print("  → fallback la v1...")
        data = get(f"{BASE_V1}/predictions/")
    
    if not data:
        print("  ✗ Predicțiile nu sunt disponibile.")
        save_atomic("predictions.json", {
            "updated_at": now_iso(), "count": 0, "results": []
        })
        return

    predictions = data.get("results", [])
    league_ids  = set(LEAGUES.keys())
    
    # Filtrează doar ligile urmărite
    filtered = [
        p for p in predictions
        if (p.get("event", {}).get("league", {}).get("id") in league_ids)
        or (p.get("league_id") in league_ids)
    ] or predictions  # dacă filtrarea returnează gol, păstrează tot
    
    # Normalizează câmpurile de probabilitate
    for p in filtered:
        ev = p.get("event", {})
        # Asigură câmpuri de fallback
        p.setdefault("home_win_probability", p.get("prob_home") or p.get("home_win"))
        p.setdefault("draw_probability",     p.get("prob_draw") or p.get("draw"))
        p.setdefault("away_win_probability", p.get("prob_away") or p.get("away_win"))
        p.setdefault("_league_name", ev.get("league", {}).get("name", ""))
    
    save_atomic("predictions.json", {
        "updated_at": now_iso(),
        "count":      len(filtered),
        "results":    filtered
    })

# ── 2. Meciuri de azi ────────────────────────────────────────────────────────
def fetch_matches_today():
    print("\n📅 Meciuri de azi...")
    today       = today_iso()
    all_matches = []
    
    for league_id, league_name in LEAGUES.items():
        # Încearcă v2 events
        matches = paginate(f"{BASE_V2}/events/", {
            "date_from": today,
            "date_to":   today,
            "league_id": league_id,
            "limit":     50
        })
        
        # Dacă v2 nu returnează nimic, încearcă fără filtrare de dată
        if not matches:
            matches = paginate(f"{BASE_V2}/events/", {
                "league_id": league_id,
                "status":    "notstarted",
                "limit":     20
            })
        
        for m in matches:
            m["_league_name"]   = league_name
            m["_league_id"]     = league_id
        
        all_matches.extend(matches)
    
    # Sortează după dată/oră
    all_matches.sort(key=lambda m: m.get("event_date") or m.get("date") or "")
    
    save_atomic("matches_today.json", {
        "date":       today,
        "updated_at": now_iso(),
        "count":      len(all_matches),
        "results":    all_matches
    })

# ── 3. Best Odds ─────────────────────────────────────────────────────────────
def fetch_best_odds():
    print("\n💰 Best Odds...")
    markets    = ["1x2", "over_under_25", "btts"]
    all_odds   = []
    
    for market in markets:
        # Best odds globale (toate ligile, 2 zile înainte)
        data = get(f"{BASE_V2}/best-odds/", {"days": 2, "market": market})
        
        if not data:
            # Fallback: încearcă per ligă
            for league_id in list(LEAGUES.keys())[:5]:  # primele 5 ligi
                data = get(f"{BASE_V2}/best-odds/", {
                    "days":      2,
                    "market":    market,
                    "league_id": league_id
                })
                if data:
                    results = data.get("results", data if isinstance(data, list) else [])
                    for item in results:
                        item["_market"] = market
                    all_odds.extend(results)
            continue
        
        results = data.get("results", data if isinstance(data, list) else [])
        for item in results:
            item["_market"] = market
        all_odds.extend(results)
    
    save_atomic("best_odds.json", {
        "updated_at": now_iso(),
        "count":      len(all_odds),
        "results":    all_odds
    })

# ── 4. Clasamente ─────────────────────────────────────────────────────────────
def fetch_standings():
    print("\n🏆 Clasamente...")
    standings_data = {}
    
    for league_id, league_name in LEAGUES.items():
        # v2
        data = get(f"{BASE_V2}/standings/", {"league_id": league_id})
        
        if not data:
            # Fallback v1
            data = get(f"{BASE_V1}/standings/", {"league_id": league_id})
        
        if not data:
            continue
        
        rows = data.get("results", data if isinstance(data, list) else [])
        
        standings_data[str(league_id)] = {
            "league_name": league_name,
            "league_id":   league_id,
            "updated_at":  now_iso(),
            "standings":   rows
        }
    
    save_atomic("standings.json", {
        "updated_at": now_iso(),
        "leagues":    standings_data
    })

# ── 5. Value Bets (calcul local) ──────────────────────────────────────────────
def compute_value_bets():
    """
    EV = (prob_ML × best_odds) − 1
    Kelly fraction = (prob × odd − 1) / (odd − 1)
    Threshold: EV > 5%, prob > 0.40
    """
    print("\n💎 Calcul Value Bets...")
    
    pred_path = DATA_DIR / "predictions.json"
    odds_path = DATA_DIR / "best_odds.json"
    
    if not pred_path.exists():
        print("  ⚠ predictions.json lipsă, skip.")
        save_atomic("value_bets.json", {"updated_at": now_iso(), "count": 0, "results": []})
        return
    
    predictions = json.loads(pred_path.read_text())["results"]
    
    # ── Helper: extrage câmpurile de probabilitate ──
    def get_probs(p):
        pH = (p.get("home_win_probability") or p.get("prob_home") or
              p.get("home_win") or p.get("win_home") or 0)
        pD = (p.get("draw_probability") or p.get("prob_draw") or
              p.get("draw") or 0)
        pA = (p.get("away_win_probability") or p.get("prob_away") or
              p.get("away_win") or p.get("win_away") or 0)
        return float(pH or 0), float(pD or 0), float(pA or 0)
    
    # ── Construiește index odds din best_odds.json ──
    odds_index = {}
    if odds_path.exists():
        best_odds_raw = json.loads(odds_path.read_text())["results"]
        for o in best_odds_raw:
            eid = (o.get("event", {}).get("id") if isinstance(o.get("event"), dict)
                   else o.get("event_id") or o.get("event"))
            if eid:
                odds_index.setdefault(str(eid), {}).update({
                    o.get("_market", "1x2"): o
                })
    
    value_bets = []
    
    for pred in predictions:
        event  = pred.get("event", {})
        eid    = str(event.get("id", ""))
        if not eid:
            continue
        
        pH, pD, pA = get_probs(pred)
        if not (pH + pD + pA):
            continue
        
        # ── Cote din predicție (fallback dacă nu avem best_odds) ──
        def build_outcome_list():
            outcomes = []
            
            # Din best_odds index
            if eid in odds_index and "1x2" in odds_index[eid]:
                bo = odds_index[eid]["1x2"]
                outcomes = [
                    ("1", pH, float(bo.get("home_odds") or bo.get("odds_1") or 0)),
                    ("X", pD, float(bo.get("draw_odds") or bo.get("odds_x") or 0)),
                    ("2", pA, float(bo.get("away_odds") or bo.get("odds_2") or 0)),
                ]
            
            # Fallback: cote estimate din probabilități (no-vig)
            if not outcomes or not any(o[2] > 1 for o in outcomes):
                def safe_odd(p): return round(1/p, 2) if p > 0.05 else 0
                outcomes = [
                    ("1", pH, safe_odd(pH)),
                    ("X", pD, safe_odd(pD)),
                    ("2", pA, safe_odd(pA)),
                ]
            
            return outcomes
        
        for outcome, prob, odd in build_outcome_list():
            if not odd or odd <= 1.01 or not prob:
                continue
            
            ev = (prob * odd) - 1
            
            if ev > 0.05 and prob > 0.40:
                kelly = max(0, (prob * odd - 1) / (odd - 1)) if odd > 1 else 0
                value_bets.append({
                    "event_id":     int(eid),
                    "home_team":    event.get("home_team", "—"),
                    "away_team":    event.get("away_team", "—"),
                    "event_date":   event.get("event_date"),
                    "league":       event.get("league", {}).get("name", pred.get("_league_name", "—")),
                    "outcome":      outcome,
                    "probability":  round(prob, 3),
                    "best_odds":    round(odd, 2),
                    "ev":           round(ev, 4),
                    "ev_pct":       f"{ev*100:.1f}%",
                    "kelly_pct":    f"{kelly*100:.1f}%",
                    "kelly_fraction": round(kelly, 4)
                })
    
    # Sortează descrescător după EV
    value_bets.sort(key=lambda x: x["ev"], reverse=True)
    
    # Aplică filtru anti-overbet (Kelly > 25% → taie la 25%)
    for vb in value_bets:
        if vb["kelly_fraction"] > 0.25:
            vb["kelly_fraction"] = 0.25
            vb["kelly_pct"] = "25.0%"
    
    save_atomic("value_bets.json", {
        "updated_at": now_iso(),
        "count":      len(value_bets),
        "results":    value_bets
    })

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not API_KEY:
        print("✗ BSD_API_KEY nu este setat!")
        sys.exit(1)
    
    print(f"=== BetPredict Pro — Daily Fetch ({today_iso()}) ===")
    
    fetch_predictions()
    fetch_matches_today()
    fetch_best_odds()
    fetch_standings()
    compute_value_bets()
    
    print("\n✅ Fetch complet!")
