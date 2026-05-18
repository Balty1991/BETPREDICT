#!/usr/bin/env python3
"""
BetPredict Pro — Daily Data Fetcher (Merged v5)
================================================
Combină BSD API v2 cu analytics_core din VEYRA:
  - Poisson + Dixon-Coles score matrix
  - No-vig EV calculation
  - SmartBet Score v2
  - Quality grade (A/B/C/D/E)
  - ELO ratings blending
  - Fetch per ligă (stabil)
  - Protecție anti-overwrite

BSD v2 structură reală:
  p.event.league_id / league_name  (FLAT)
  p.markets.match_result.prob_home/draw/away (0-100)
  p.markets.expected_goals.home/away
  p.markets.over_under.prob_over_25
  p.markets.btts.prob_yes
  p.model.confidence
  standings: data["standings"] cu team_name, pts, form
"""

import os, json, requests, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Import analytics_core (din VEYRA) ──────────────────────────────────────
try:
    from analytics_core import (
        no_vig_prob, expected_value_decimal, kelly_fraction as ac_kelly,
        poisson_market_probabilities, quality_grade, blend_probabilities,
        EloRatings, EloConfig, safe_float
    )
    HAS_ANALYTICS = True
    print("analytics_core: OK")
except ImportError:
    HAS_ANALYTICS = False
    print("analytics_core: nu a fost gasit, continuam fara")

# ── Config ──────────────────────────────────────────────────────────────────
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
            if code in (401, 403): return None
            if attempt == 2: return None
        except Exception as e:
            if attempt == 2: print(f"  ERR: {e}"); return None

def paginate(url, params=None):
    params = params or {}; params.setdefault("limit", 100)
    results, page_url, seen = [], url, set()
    while page_url and page_url not in seen:
        seen.add(page_url)
        data = get(page_url, params if page_url == url else None)
        if not data: break
        results.extend(data.get("results", []))
        page_url = data.get("next"); params = {}
    return results

def save(filename, data, protect_empty=True):
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / filename
    if isinstance(data, dict):
        new_cnt = len(data.get("results", data.get("events", data.get("standings", []))))
    else:
        new_cnt = len(data)
    if protect_empty and new_cnt == 0 and path.exists():
        try:
            old = json.loads(path.read_text())
            old_cnt = len(old.get("results", old.get("events", old.get("standings", [])))
                          if isinstance(old, dict) else old)
            if old_cnt > 0:
                print(f"  SKIP {filename} (0 nou, pastrez {old_cnt} vechi)"); return
        except: pass
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    print(f"  OK {filename} ({new_cnt})")

def now_iso(): return datetime.now(timezone.utc).isoformat()
def today_iso(): return (datetime.now(timezone.utc)+timedelta(hours=4)).strftime("%Y-%m-%d")

# ── SmartBet Score v2 (din ev_calculator.py VEYRA) ──────────────────────────
def smartbet_score(model_prob, edge_pp):
    """Score 0-100 combinând probabilitate + edge."""
    if model_prob is None: return 0
    p = safe_float(model_prob, 0.0) if HAS_ANALYTICS else float(model_prob or 0)
    e = safe_float(edge_pp, 0.0) if HAS_ANALYTICS else float(edge_pp or 0)
    prob_norm  = min(100.0, max(0.0, (p - 0.50) / 0.30 * 100.0))
    edge_norm  = min(100.0, max(0.0, e / 15.0 * 100.0))
    score = prob_norm * 0.60 + edge_norm * 0.40
    return round(min(100.0, max(0.0, score)), 1)

# ── Normalizare BSD v2 ───────────────────────────────────────────────────────
def normalize_pred(p, fallback_league_id=None, fallback_league_name=""):
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
    p["_league_name"] = ev.get("league_name") or LEAGUES.get(ev.get("league_id")) or fallback_league_name

    # Probabilități 0-100 → 0-1
    ph = mr.get("prob_home"); pd = mr.get("prob_draw"); pa = mr.get("prob_away")
    if ph is not None: p["home_win_probability"] = round(float(ph)/100, 4)
    if pd is not None: p["draw_probability"]     = round(float(pd)/100, 4)
    if pa is not None: p["away_win_probability"] = round(float(pa)/100, 4)

    rec_map = {"H":"1","D":"X","A":"2"}
    p["recommended_bet"] = rec_map.get(mr.get("predicted",""), "")

    # xG
    if xg.get("home") is not None:
        p["predicted_home_goals"] = xg["home"]
        p["predicted_away_goals"] = xg.get("away")

    # BTTS / O2.5
    if bt.get("prob_yes") is not None:
        p["btts_probability"] = round(float(bt["prob_yes"])/100, 4)
    if ou.get("prob_over_25") is not None:
        p["over_25_probability"] = round(float(ou["prob_over_25"])/100, 4)

    p["confidence"]       = model.get("confidence")
    p["most_likely_score"] = sc.get("most_likely")

    return p

# ── Analytics enrichment (din VEYRA analytics_core) ─────────────────────────
def enrich_analytics(p):
    """
    Adaugă layerul analitic:
    - Poisson probabilities ca al doilea model
    - Blend BSD + Poisson
    - SmartBet Score
    - Quality grade
    - No-vig edge (dacă avem cote)
    """
    if not HAS_ANALYTICS:
        p["quality_grade"] = "—"
        p["smartbet_score"] = 0
        return p

    pH = p.get("home_win_probability", 0)
    pD = p.get("draw_probability", 0)
    pA = p.get("away_win_probability", 0)
    xgH = p.get("predicted_home_goals")
    xgA = p.get("predicted_away_goals")

    # ── Poisson predictions (dacă avem xG) ──
    if xgH and xgA and xgH > 0 and xgA > 0:
        try:
            poi = poisson_market_probabilities(xgH, xgA)
            p["poisson_home"]   = round(poi["home_win"], 4)
            p["poisson_draw"]   = round(poi["draw"], 4)
            p["poisson_away"]   = round(poi["away_win"], 4)
            p["poisson_btts"]   = round(poi["btts"], 4)
            p["poisson_over25"] = round(poi["over25"], 4)

            # Top 3 scoruri probabile din Poisson
            p["top_scores"] = poi.get("top_correct_scores", [])[:3]

            # Scor Poisson dacă BSD nu l-a dat
            if not p.get("most_likely_score"):
                p["most_likely_score"] = poi["most_likely_score"]

            # Blend 65% BSD + 35% Poisson
            if pH > 0:
                p["blended_home"] = round(blend_probabilities(
                    {"bsd": pH, "poisson": poi["home_win"]}, {"bsd": 0.65, "poisson": 0.35}
                ) or pH, 4)
                p["blended_draw"] = round(blend_probabilities(
                    {"bsd": pD, "poisson": poi["draw"]},    {"bsd": 0.65, "poisson": 0.35}
                ) or pD, 4)
                p["blended_away"] = round(blend_probabilities(
                    {"bsd": pA, "poisson": poi["away_win"]}, {"bsd": 0.65, "poisson": 0.35}
                ) or pA, 4)
        except Exception as e:
            print(f"  Poisson warn: {e}")

    # ── Folosim blended dacă disponibil, altfel BSD direct ──
    best_pH = p.get("blended_home") or pH
    best_pD = p.get("blended_draw") or pD
    best_pA = p.get("blended_away") or pA

    # ── SmartBet Score (edge simplu vs 50%) ──
    best_p = max(best_pH, best_pD, best_pA)
    edge_pp = (best_p - 0.5) * 100.0
    p["smartbet_score"] = smartbet_score(best_p, edge_pp)
    p["edge_pp"]        = round(edge_pp, 2)

    # ── Quality grade pe baza confidence + smartbet score ──
    conf = p.get("confidence") or best_p
    grade_score = (conf or 0) * 100 * 0.6 + p["smartbet_score"] * 0.4
    p["quality_grade"] = quality_grade(grade_score)

    return p

# ── 1. Predictions — FETCH PER LIGĂ ─────────────────────────────────────────
def fetch_predictions():
    print("\n[1/5] Predictii ML (per liga)...")
    all_preds, seen_ids = [], set()

    for league_id, league_name in LEAGUES.items():
        for url, param_key in [
            (f"{BASE_V2}/predictions/", "league"),
            (f"{BASE_V2}/predictions/", "league_id"),
            (f"{BASE_V1}/predictions/", "league"),
        ]:
            data = get(url, {param_key: league_id})
            if data and data.get("results"):
                new_count = 0
                for p in data["results"]:
                    pid = p.get("id")
                    if pid and pid in seen_ids: continue
                    if pid: seen_ids.add(pid)
                    np = normalize_pred(p, league_id, league_name)
                    np = enrich_analytics(np)
                    all_preds.append(np)
                    new_count += 1
                if new_count:
                    print(f"  {league_name}: {new_count}")
                break

    n_probs  = sum(1 for p in all_preds if p.get("home_win_probability") is not None)
    n_grade  = sum(1 for p in all_preds if p.get("quality_grade") not in (None,"—"))
    n_poi    = sum(1 for p in all_preds if p.get("poisson_home") is not None)
    print(f"  TOTAL: {len(all_preds)} | prob:{n_probs} | grade:{n_grade} | poisson:{n_poi}")

    save("predictions.json", {
        "updated_at": now_iso(), "count": len(all_preds), "results": all_preds
    }, protect_empty=True)

# ── 2. Meciuri azi ───────────────────────────────────────────────────────────
def fetch_matches_today():
    print("\n[2/5] Meciuri de azi...")
    today, all_m = today_iso(), []
    for lid, lname in LEAGUES.items():
        ms = paginate(f"{BASE_V2}/events/", {
            "date_from": today, "date_to": today, "league_id": lid, "limit": 50
        })
        if not ms:
            ms = paginate(f"{BASE_V2}/events/", {"league_id": lid, "status": "notstarted", "limit": 20})
        for m in ms:
            m["_league_name"] = lname; m["_league_id"] = lid
        all_m.extend(ms)
    all_m.sort(key=lambda m: m.get("event_date") or "")
    save("matches_today.json", {
        "date": today, "updated_at": now_iso(), "count": len(all_m), "results": all_m
    }, protect_empty=False)

# ── 3. Best Odds ─────────────────────────────────────────────────────────────
def fetch_best_odds():
    print("\n[3/5] Best Odds...")
    all_odds = []
    for market in ["1x2", "over_under_25", "btts"]:
        for url in [f"{BASE_V2}/best-odds/", f"{BASE_V2}/odds/best/", f"{BASE_V1}/best-odds/"]:
            data = get(url, {"days": 2, "market": market})
            if data:
                for item in data.get("results", data if isinstance(data, list) else []):
                    item["_market"] = market; all_odds.append(item)
                break
    save("best_odds.json", {"updated_at": now_iso(), "count": len(all_odds), "results": all_odds},
         protect_empty=False)

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
        rows = data.get("standings", data.get("results", []))
        if rows:
            standings_data[str(lid)] = {"league_name": lname, "league_id": lid, "standings": rows}
    save("standings.json", {"updated_at": now_iso(), "leagues": standings_data}, protect_empty=True)

# ── 5. Value Bets cu no-vig ───────────────────────────────────────────────────
def compute_value_bets():
    print("\n[5/5] Value Bets...")
    pred_path = DATA_DIR / "predictions.json"
    odds_path = DATA_DIR / "best_odds.json"
    if not pred_path.exists():
        save("value_bets.json", {"updated_at": now_iso(), "count": 0, "results": []},
             protect_empty=False); return

    preds = json.loads(pred_path.read_text())["results"]

    odds_idx = {}
    if odds_path.exists():
        for o in json.loads(odds_path.read_text())["results"]:
            ev_obj = o.get("event") or {}
            eid = (ev_obj.get("id") if isinstance(ev_obj, dict) else None) or o.get("event_id")
            if eid: odds_idx.setdefault(str(eid), {})[o.get("_market","1x2")] = o

    vbs = []
    for pred in preds:
        ev  = pred.get("event") or {}
        eid = str(ev.get("id",""))
        if not eid: continue

        # Folosim blended dacă există, altfel BSD direct
        pH = pred.get("blended_home") or pred.get("home_win_probability")
        pD = pred.get("blended_draw") or pred.get("draw_probability")
        pA = pred.get("blended_away") or pred.get("away_win_probability")
        if not (pH and pD and pA): continue

        bo = (odds_idx.get(eid) or {}).get("1x2", {})
        has_real = bool(bo)

        # No-vig calculation (analytics_core)
        raw_odds = [bo.get("home_odds") or bo.get("odds_1"),
                    bo.get("draw_odds") or bo.get("odds_x"),
                    bo.get("away_odds") or bo.get("odds_2")]

        if HAS_ANALYTICS and has_real and all(raw_odds):
            nv = no_vig_prob(raw_odds)
            nv_home, nv_draw, nv_away = (nv[0] or 0), (nv[1] or 0), (nv[2] or 0)
        else:
            nv_home = nv_draw = nv_away = None

        def get_odd(prob, fields):
            for f in fields:
                v = bo.get(f)
                if v and float(v) > 1: return float(v)
            return round(1/(prob*1.05), 2) if prob > 0.05 else 0

        for outcome, prob, nv_prob, fields in [
            ("1", pH, nv_home, ["home_odds","odds_1","home"]),
            ("X", pD, nv_draw, ["draw_odds","odds_x","draw"]),
            ("2", pA, nv_away, ["away_odds","odds_2","away"]),
        ]:
            odd = get_odd(prob, fields)
            if odd <= 1.01: continue

            # EV standard
            if HAS_ANALYTICS:
                ev_val = expected_value_decimal(prob, odd)
                kf     = ac_kelly(prob, odd, fraction=0.25, cap=0.08)
            else:
                ev_val = prob * odd - 1
                kf     = max(0, min(0.08, (prob*odd-1)/(odd-1))) if odd > 1 else 0

            if ev_val is None or ev_val <= 0.05: continue

            # Edge no-vig
            edge_nv = round((prob - nv_prob)*100, 2) if nv_prob else None

            vbs.append({
                "event_id":    int(eid),
                "home_team":   ev.get("home_team","—"),
                "away_team":   ev.get("away_team","—"),
                "event_date":  ev.get("event_date"),
                "league":      pred.get("_league_name","—"),
                "quality_grade": pred.get("quality_grade","—"),
                "smartbet_score": pred.get("smartbet_score", 0),
                "outcome":     outcome,
                "probability": round(prob, 3),
                "best_odds":   round(odd, 2),
                "ev":          round(ev_val, 4),
                "ev_pct":      f"{ev_val*100:.1f}%",
                "kelly_pct":   f"{kf*100:.1f}%",
                "kelly_fraction": round(kf, 4),
                "edge_nv_pp":  edge_nv,
                "odds_source": "bookmaker" if has_real else "estimated"
            })

    vbs.sort(key=lambda x: (x.get("smartbet_score",0)*0.4 + x["ev"]*60), reverse=True)
    save("value_bets.json", {"updated_at": now_iso(), "count": len(vbs), "results": vbs},
         protect_empty=False)

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not API_KEY:
        print("BSD_API_KEY nu este setat!"); sys.exit(1)
    print(f"=== BetPredict Pro — {today_iso()} (analytics_core: {'YES' if HAS_ANALYTICS else 'NO'}) ===")
    fetch_predictions()
    fetch_matches_today()
    fetch_best_odds()
    fetch_standings()
    compute_value_bets()
    print("\nGata!")
