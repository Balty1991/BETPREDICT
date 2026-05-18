#!/usr/bin/env python3
"""
BetPredict Pro — Daily Data Fetcher (v4)
=========================================

FIX v4:
  - fetch predictions PER LIGĂ (nu global) → endpoint sigur funcțional
  - nu suprascrie fișierele existente dacă noul fetch returnează 0 rezultate
  - structura corectă BSD v2:
      predictions: p.markets.match_result.prob_home (0-100)
                   p.event.league_id / p.event.league_name (FLAT)
      standings:   data["standings"] (nu data["results"])
                   r.team_name, r.pts, r.form
"""

import os, json, requests, sys
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
}

# ── HTTP helpers ─────────────────────────────────────────────────────────────
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
                print("  STOP: API key invalida!")
                return None
            if attempt == 2: return None
        except Exception as e:
            if attempt == 2:
                print(f"  ERR: {e}")
                return None

def paginate(url, params=None):
    params = params or {}
    params.setdefault("limit", 100)
    results, page_url, seen = [], url, set()
    while page_url and page_url not in seen:
        seen.add(page_url)
        data = get(page_url, params if page_url == url else None)
        if not data: break
        results.extend(data.get("results", []))
        page_url = data.get("next")
        params = {}
    return results

def save(filename, data, protect_empty=True):
    """
    Scriere atomică. Dacă protect_empty=True și noul data are 0 rezultate,
    nu suprascrie fișierul existent (păstrează datele vechi).
    """
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / filename

    # Număr înregistrări noi
    if isinstance(data, dict):
        new_cnt = len(data.get("results", data.get("events", data.get("standings", []))))
    else:
        new_cnt = len(data)

    # Protecție: nu suprascrie dacă nou = 0 și există deja date
    if protect_empty and new_cnt == 0 and path.exists():
        try:
            old = json.loads(path.read_text())
            old_cnt = (len(old.get("results", old.get("events", old.get("standings", []))))
                       if isinstance(old, dict) else len(old))
            if old_cnt > 0:
                print(f"  SKIP {filename} (0 rezultate noi, păstrez {old_cnt} vechi)")
                return
        except: pass

    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    print(f"  OK {filename} ({new_cnt})")

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def today_iso():
    return (datetime.now(timezone.utc) + timedelta(hours=4)).strftime("%Y-%m-%d")

# ── Normalizare structură BSD v2 ─────────────────────────────────────────────
def normalize_pred(p, fallback_league_id=None, fallback_league_name=""):
    """
    BSD v2 /predictions/ structură reală:
      p.event.league_id   (int, FLAT)
      p.event.league_name (str, FLAT)
      p.markets.match_result.prob_home/draw/away  (float 0-100)
      p.markets.expected_goals.home/away
      p.markets.over_under.prob_over_25
      p.markets.btts.prob_yes
      p.markets.match_result.predicted  → "H"/"D"/"A"
      p.model.confidence  (float 0-1)
    """
    ev      = p.get("event") or {}
    markets = p.get("markets") or {}
    mr      = markets.get("match_result") or {}
    xg      = markets.get("expected_goals") or {}
    ou      = markets.get("over_under") or {}
    bt      = markets.get("btts") or {}
    sc      = markets.get("score") or {}
    model   = p.get("model") or {}

    # Liga (FLAT pe event în BSD v2)
    p["_league_id"]   = ev.get("league_id") or fallback_league_id
    p["_league_name"] = (ev.get("league_name") or
                         LEAGUES.get(ev.get("league_id")) or
                         fallback_league_name)

    # Probabilități 0-100 → 0-1
    ph = mr.get("prob_home")
    pd = mr.get("prob_draw")
    pa = mr.get("prob_away")
    if ph is not None: p["home_win_probability"] = round(float(ph) / 100, 4)
    if pd is not None: p["draw_probability"]     = round(float(pd) / 100, 4)
    if pa is not None: p["away_win_probability"] = round(float(pa) / 100, 4)

    # Recomandat: "H"→"1", "D"→"X", "A"→"2"
    rec_map = {"H": "1", "D": "X", "A": "2"}
    p["recommended_bet"] = rec_map.get(mr.get("predicted", ""), "")

    # xG
    if xg.get("home") is not None:
        p["predicted_home_goals"] = xg["home"]
        p["predicted_away_goals"] = xg.get("away")

    # BTTS 0-100 → 0-1
    if bt.get("prob_yes") is not None:
        p["btts_probability"] = round(float(bt["prob_yes"]) / 100, 4)

    # Over 2.5 0-100 → 0-1
    if ou.get("prob_over_25") is not None:
        p["over_25_probability"] = round(float(ou["prob_over_25"]) / 100, 4)

    # Confidence (deja 0-1)
    p["confidence"] = model.get("confidence")

    # Scor probabil
    p["most_likely_score"] = sc.get("most_likely")

    return p

# ── 1. Predictions — FETCH PER LIGĂ ─────────────────────────────────────────
def fetch_predictions():
    """
    Fetch predictions per ligă în loc de un singur call global.
    Motivul: /api/v2/predictions/ fără params returnează uneori 0 rezultate.
    Cu ?league=X funcționează garantat (testat live).
    """
    print("\n[1/5] Predictii ML (per liga)...")
    all_preds = []
    seen_ids  = set()

    for league_id, league_name in LEAGUES.items():
        # Încearcă v2 cu parametrul league
        for url, param_key in [
            (f"{BASE_V2}/predictions/", "league"),
            (f"{BASE_V2}/predictions/", "league_id"),
            (f"{BASE_V1}/predictions/", "league"),
            (f"{BASE_V1}/predictions/", "league_id"),
        ]:
            data = get(url, {param_key: league_id})
            if data and data.get("results"):
                preds = data["results"]
                new_count = 0
                for p in preds:
                    pid = p.get("id")
                    if pid and pid in seen_ids:
                        continue
                    if pid:
                        seen_ids.add(pid)
                    np = normalize_pred(p, league_id, league_name)
                    all_preds.append(np)
                    new_count += 1
                if new_count:
                    print(f"  {league_name}: {new_count} pred (via {param_key})")
                break  # endpoint funcționat, treci la liga urm.

    n_probs  = sum(1 for p in all_preds if p.get("home_win_probability") is not None)
    n_league = sum(1 for p in all_preds if p.get("_league_name"))
    print(f"  TOTAL: {len(all_preds)} pred, {n_probs} cu prob, {n_league} cu liga")

    save("predictions.json", {
        "updated_at": now_iso(),
        "count": len(all_preds),
        "results": all_preds
    }, protect_empty=True)

# ── 2. Meciuri azi ───────────────────────────────────────────────────────────
def fetch_matches_today():
    print("\n[2/5] Meciuri de azi...")
    today = today_iso()
    all_m = []
    for lid, lname in LEAGUES.items():
        ms = paginate(f"{BASE_V2}/events/", {
            "date_from": today, "date_to": today, "league_id": lid, "limit": 50
        })
        if not ms:
            ms = paginate(f"{BASE_V2}/events/", {
                "league_id": lid, "status": "notstarted", "limit": 20
            })
        for m in ms:
            m["_league_name"] = lname
            m["_league_id"]   = lid
        all_m.extend(ms)
    all_m.sort(key=lambda m: m.get("event_date") or "")
    save("matches_today.json", {
        "date": today, "updated_at": now_iso(),
        "count": len(all_m), "results": all_m
    }, protect_empty=False)

# ── 3. Best Odds ─────────────────────────────────────────────────────────────
def fetch_best_odds():
    print("\n[3/5] Best Odds...")
    all_odds = []
    for market in ["1x2", "over_under_25", "btts"]:
        for url in [f"{BASE_V2}/best-odds/", f"{BASE_V2}/odds/best/", f"{BASE_V1}/best-odds/"]:
            data = get(url, {"days": 2, "market": market})
            if data:
                results = data.get("results", data if isinstance(data, list) else [])
                for item in results:
                    item["_market"] = market
                    all_odds.append(item)
                break
    save("best_odds.json", {
        "updated_at": now_iso(), "count": len(all_odds), "results": all_odds
    }, protect_empty=False)

# ── 4. Standings ─────────────────────────────────────────────────────────────
def fetch_standings():
    print("\n[4/5] Clasamente...")
    standings_data = {}
    for lid, lname in LEAGUES.items():
        data = None
        for url in [f"{BASE_V2}/standings/", f"{BASE_V1}/standings/"]:
            data = get(url, {"league_id": lid})
            if data: break
        if not data: continue
        # BSD v2: data["standings"], nu data["results"]
        rows = data.get("standings", data.get("results", []))
        if rows:
            standings_data[str(lid)] = {
                "league_name": lname,
                "league_id":   lid,
                "standings":   rows
            }
    save("standings.json", {
        "updated_at": now_iso(), "leagues": standings_data
    }, protect_empty=True)

# ── 5. Value Bets ─────────────────────────────────────────────────────────────
def compute_value_bets():
    print("\n[5/5] Value Bets...")
    pred_path = DATA_DIR / "predictions.json"
    odds_path = DATA_DIR / "best_odds.json"
    if not pred_path.exists():
        save("value_bets.json", {"updated_at": now_iso(), "count": 0, "results": []},
             protect_empty=False)
        return

    preds = json.loads(pred_path.read_text())["results"]

    odds_idx = {}
    if odds_path.exists():
        for o in json.loads(odds_path.read_text())["results"]:
            ev_obj = o.get("event") or {}
            eid = (ev_obj.get("id") if isinstance(ev_obj, dict) else None) or o.get("event_id")
            if eid:
                odds_idx.setdefault(str(eid), {})[o.get("_market", "1x2")] = o

    vbs = []
    for pred in preds:
        ev  = pred.get("event") or {}
        eid = str(ev.get("id", ""))
        if not eid: continue
        pH = pred.get("home_win_probability")
        pD = pred.get("draw_probability")
        pA = pred.get("away_win_probability")
        if not (pH and pD and pA): continue

        bo = (odds_idx.get(eid) or {}).get("1x2", {})
        has_real = bool(bo)

        def get_odd(prob, fields):
            for f in fields:
                v = bo.get(f)
                if v and float(v) > 1: return float(v)
            return round(1 / (prob * 1.05), 2) if prob > 0.05 else 0

        for outcome, prob, fields in [
            ("1", pH, ["home_odds","odds_1","home","odd_1"]),
            ("X", pD, ["draw_odds","odds_x","draw","odd_x"]),
            ("2", pA, ["away_odds","odds_2","away","odd_2"]),
        ]:
            odd = get_odd(prob, fields)
            if odd <= 1.01: continue
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
    save("value_bets.json", {
        "updated_at": now_iso(), "count": len(vbs), "results": vbs
    }, protect_empty=False)

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not API_KEY:
        print("BSD_API_KEY nu este setat!"); sys.exit(1)
    print(f"=== BetPredict Pro — {today_iso()} ===")
    fetch_predictions()
    fetch_matches_today()
    fetch_best_odds()
    fetch_standings()
    compute_value_bets()
    print("\nGata!")
