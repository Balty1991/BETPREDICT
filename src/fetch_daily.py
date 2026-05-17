#!/usr/bin/env python3
"""
BetPredict Pro — Daily Data Fetcher (v2)
=========================================
Rulează zilnic la 06:00 UTC via GitHub Actions.
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
    27: "World Cup 2026",
    12: "Championship",
    13: "Scottish Premiership",
    17: "Saudi Pro League",
    9:  "Brasileirao Serie A",
    25: "Ekstraklasa",
}

# ── Helpers ─────────────────────────────────────────────────────────────────
def get(url, params=None):
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError as e:
            code = e.response.status_code
            print(f"  HTTP {code}: {url}")
            if code in (401, 403):
                return None
            if attempt == 2:
                return None
        except Exception as e:
            if attempt == 2:
                print(f"  EROARE: {e}")
                return None

def paginate(url, params=None):
    params = params or {}
    params.setdefault("limit", 100)
    results = []
    page_url = url
    seen = set()
    while page_url and page_url not in seen:
        seen.add(page_url)
        data = get(page_url, params if page_url == url else None)
        if not data:
            break
        results.extend(data.get("results", []))
        page_url = data.get("next")
        params = {}
    return results

def save(filename, data):
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / filename
    tmp  = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    cnt = (len(data.get("results", data.get("events", [])))
           if isinstance(data, dict) else len(data))
    print(f"  OK {filename} ({cnt})")

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def today_iso():
    now = datetime.now(timezone.utc) + timedelta(hours=4)
    return now.strftime("%Y-%m-%d")

# ── League name extraction ────────────────────────────────────────────────────
def extract_league(raw, fallback_id=None):
    """Extrage (id, name) din orice format: dict, int, str."""
    if isinstance(raw, dict):
        lid  = raw.get("id") or raw.get("league_id")
        name = raw.get("name") or raw.get("league_name") or LEAGUES.get(lid, "")
        return lid, name
    elif isinstance(raw, int):
        return raw, LEAGUES.get(raw, f"Liga {raw}")
    elif isinstance(raw, str) and raw:
        return fallback_id, raw
    lid = fallback_id
    return lid, LEAGUES.get(lid, "")

# ── Probability extraction ────────────────────────────────────────────────────
def try_fields(obj, *keys):
    """Cauta prima valoare validă [0,1] sau (0,100]."""
    if not isinstance(obj, dict):
        return None
    for k in keys:
        v = obj.get(k)
        if v is not None:
            try:
                f = float(v)
                if 0 < f <= 1:
                    return f
                if 1 < f <= 100:
                    return f / 100.0
            except:
                pass
    return None

def extract_probs(p):
    """Returnează (pH, pD, pA) din orice structura BSD API."""

    pH = (try_fields(p,
        "home_win_probability", "prob_home", "home_win",
        "win_home", "home_probability", "home_chance", "p_home") or
        try_fields(p.get("catboost") or {}, "home_win", "home", "1") or
        try_fields(p.get("predictions") or {}, "home_win_probability", "home_win", "home") or
        try_fields(p.get("ml") or {}, "home", "home_win") or
        try_fields(p.get("probabilities") or {}, "home", "1", "home_win"))

    pD = (try_fields(p,
        "draw_probability", "prob_draw", "draw",
        "draw_chance", "p_draw") or
        try_fields(p.get("catboost") or {}, "draw", "X") or
        try_fields(p.get("predictions") or {}, "draw_probability", "draw") or
        try_fields(p.get("ml") or {}, "draw", "X") or
        try_fields(p.get("probabilities") or {}, "draw", "X"))

    pA = (try_fields(p,
        "away_win_probability", "prob_away", "away_win",
        "win_away", "away_probability", "away_chance", "p_away") or
        try_fields(p.get("catboost") or {}, "away_win", "away", "2") or
        try_fields(p.get("predictions") or {}, "away_win_probability", "away_win", "away") or
        try_fields(p.get("ml") or {}, "away", "away_win") or
        try_fields(p.get("probabilities") or {}, "away", "2", "away_win"))

    return pH, pD, pA

# ── Normalize prediction ──────────────────────────────────────────────────────
def normalize_pred(p, fallback_league_id=None):
    ev = p.get("event") or {}

    # League
    lid, lname = extract_league(ev.get("league") or p.get("league") or {}, fallback_league_id)
    p["_league_id"]   = lid
    p["_league_name"] = lname

    # Probabilities
    pH, pD, pA = extract_probs(p)
    if pH: p["home_win_probability"] = round(pH, 4)
    if pD: p["draw_probability"]     = round(pD, 4)
    if pA: p["away_win_probability"] = round(pA, 4)

    # xG
    for kh, ka in [("predicted_home_goals","predicted_away_goals"),
                   ("xg_home","xg_away"), ("home_xg","away_xg"),
                   ("home_goals_expected","away_goals_expected")]:
        if p.get(kh) is not None:
            p.setdefault("predicted_home_goals", p[kh])
            p.setdefault("predicted_away_goals", p.get(ka))
            break

    # BTTS
    for k in ("btts_probability","btts","both_teams_score_probability","both_score"):
        v = p.get(k)
        if v is not None:
            p.setdefault("btts_probability", float(v) if float(v) <= 1 else float(v)/100)
            break

    # Over 2.5
    for k in ("over_25_probability","over_2_5","over25","over_under_25","over25_probability"):
        v = p.get(k)
        if v is not None:
            p.setdefault("over_25_probability", float(v) if float(v) <= 1 else float(v)/100)
            break

    return p

# ── 1. Predictions ─────────────────────────────────────────────────────────
def fetch_predictions():
    print("\n[1/5] Predictii ML...")
    raw = None
    for url in [f"{BASE_V2}/predictions/", f"{BASE_V1}/predictions/"]:
        raw = get(url)
        if raw:
            print(f"  endpoint: {url}")
            break

    if not raw:
        save("predictions.json", {"updated_at": now_iso(), "count": 0, "results": []})
        return

    preds = raw.get("results", [])
    print(f"  brut: {len(preds)} inregistrari")

    # Salveaza debug (primul record) pentru a vedea structura reala
    if preds:
        first = preds[0]
        save("_debug.json", {
            "note": "Debug: structura primului record din /predictions/",
            "top_keys": sorted(first.keys()),
            "event_keys": sorted((first.get("event") or {}).keys()),
            "has_probs": any(k in first for k in ["home_win_probability","prob_home","home_win","catboost","predictions","ml","probabilities"]),
            "sample": first
        })
        print(f"  chei top-level: {sorted(first.keys())}")

    normalized = [normalize_pred(p) for p in preds]
    n_probs  = sum(1 for p in normalized if p.get("home_win_probability"))
    n_league = sum(1 for p in normalized if p.get("_league_name"))
    print(f"  cu prob: {n_probs}/{len(normalized)}, cu liga: {n_league}/{len(normalized)}")

    save("predictions.json", {"updated_at": now_iso(), "count": len(normalized), "results": normalized})

# ── 2. Meciuri azi ──────────────────────────────────────────────────────────
def fetch_matches_today():
    print("\n[2/5] Meciuri de azi...")
    today = today_iso()
    all_m = []
    for lid, lname in LEAGUES.items():
        ms = paginate(f"{BASE_V2}/events/", {"date_from": today, "date_to": today, "league_id": lid, "limit": 50})
        if not ms:
            ms = paginate(f"{BASE_V2}/events/", {"league_id": lid, "status": "notstarted", "limit": 20})
        for m in ms:
            m["_league_name"] = lname
            m["_league_id"]   = lid
        all_m.extend(ms)
    all_m.sort(key=lambda m: m.get("event_date") or "")
    save("matches_today.json", {"date": today, "updated_at": now_iso(), "count": len(all_m), "results": all_m})

# ── 3. Best Odds ────────────────────────────────────────────────────────────
def fetch_best_odds():
    print("\n[3/5] Best Odds...")
    all_odds = []
    for market in ["1x2", "over_under_25", "btts"]:
        for url in [f"{BASE_V2}/best-odds/", f"{BASE_V2}/odds/best/", f"{BASE_V1}/best-odds/"]:
            data = get(url, {"days": 2, "market": market})
            if data:
                for item in data.get("results", data if isinstance(data, list) else []):
                    item["_market"] = market
                    all_odds.append(item)
                break
    save("best_odds.json", {"updated_at": now_iso(), "count": len(all_odds), "results": all_odds})

# ── 4. Standings ────────────────────────────────────────────────────────────
def fetch_standings():
    print("\n[4/5] Clasamente...")
    data = {}
    for lid, lname in LEAGUES.items():
        for url in [f"{BASE_V2}/standings/", f"{BASE_V1}/standings/"]:
            d = get(url, {"league_id": lid})
            if d:
                rows = d.get("results", d if isinstance(d, list) else [])
                if rows:
                    data[str(lid)] = {"league_name": lname, "league_id": lid, "standings": rows}
                break
    save("standings.json", {"updated_at": now_iso(), "leagues": data})

# ── 5. Value Bets ────────────────────────────────────────────────────────────
def compute_value_bets():
    print("\n[5/5] Value Bets...")
    pred_path = DATA_DIR / "predictions.json"
    odds_path = DATA_DIR / "best_odds.json"
    if not pred_path.exists():
        save("value_bets.json", {"updated_at": now_iso(), "count": 0, "results": []})
        return

    preds = json.loads(pred_path.read_text())["results"]
    odds_idx = {}
    if odds_path.exists():
        for o in json.loads(odds_path.read_text())["results"]:
            ev_obj = o.get("event") or {}
            eid = (ev_obj.get("id") if isinstance(ev_obj, dict) else None) or o.get("event_id") or o.get("event")
            if eid:
                odds_idx.setdefault(str(eid), {})[o.get("_market","1x2")] = o

    vbs = []
    for pred in preds:
        ev  = pred.get("event") or {}
        eid = str(ev.get("id",""))
        if not eid:
            continue
        pH = pred.get("home_win_probability")
        pD = pred.get("draw_probability")
        pA = pred.get("away_win_probability")
        if not (pH and pD and pA):
            continue

        bo = (odds_idx.get(eid) or {}).get("1x2", {})
        has_real = bool(bo)

        def get_odd(prob, fields):
            for f in fields:
                v = bo.get(f)
                if v and float(v) > 1:
                    return float(v)
            return round(1 / (prob * 1.05), 2) if prob and prob > 0.05 else 0

        for outcome, prob, fields in [
            ("1", pH, ["home_odds","odds_1","home","odd_1"]),
            ("X", pD, ["draw_odds","odds_x","draw","odd_x"]),
            ("2", pA, ["away_odds","odds_2","away","odd_2"]),
        ]:
            odd = get_odd(prob, fields)
            if odd <= 1.01:
                continue
            ev_val = prob * odd - 1
            if ev_val > 0.05:
                kelly = min(0.25, max(0, (prob * odd - 1) / (odd - 1)))
                vbs.append({
                    "event_id": int(eid),
                    "home_team": ev.get("home_team","—"),
                    "away_team": ev.get("away_team","—"),
                    "event_date": ev.get("event_date"),
                    "league": pred.get("_league_name","—"),
                    "outcome": outcome,
                    "probability": round(prob, 3),
                    "best_odds": round(odd, 2),
                    "ev": round(ev_val, 4),
                    "ev_pct": f"{ev_val*100:.1f}%",
                    "kelly_pct": f"{kelly*100:.1f}%",
                    "kelly_fraction": round(kelly, 4),
                    "odds_source": "bookmaker" if has_real else "estimated"
                })

    vbs.sort(key=lambda x: x["ev"], reverse=True)
    save("value_bets.json", {"updated_at": now_iso(), "count": len(vbs), "results": vbs})

# ── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not API_KEY:
        print("BSD_API_KEY nu este setat!")
        sys.exit(1)
    print(f"=== BetPredict Pro — {today_iso()} ===")
    fetch_predictions()
    fetch_matches_today()
    fetch_best_odds()
    fetch_standings()
    compute_value_bets()
    print("\nGata!")
