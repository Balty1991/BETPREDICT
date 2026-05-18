#!/usr/bin/env python3
"""
BetPredict Pro — Daily Data Fetcher (v6 — Full VEYRA Merge)
============================================================
Features:
  - Strategii backtestale din VEYRA (engine_overall, best_single, conservative, smart_ev, over15)
  - Multiple piețe: 1X2, Over1.5, Over2.5, Under2.5, Under3.5, BTTS
  - Triple blend: BSD 50% + Poisson 25% + Blended 25%
  - Signal generation per strategie → data/signals.json
  - Dashboard KPIs → data/meta.json
  - Structura corectă BSD v2
"""

import os, json, requests, sys, math
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Fix sys.path — analytics_core.py e la rădăcina repo
_ROOT = Path(__file__).parent.parent.resolve()
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from analytics_core import (
        normalize_no_vig, expected_value_decimal, kelly_fraction as ac_kelly,
        poisson_market_probabilities, quality_grade, blend_probabilities, safe_float
    )
    no_vig_prob = normalize_no_vig
    HAS_AC = True; print("analytics_core: OK")
except ImportError:
    HAS_AC = False; print("analytics_core: SKIP")

# ── Config ──────────────────────────────────────────────────────────────────
API_KEY  = os.environ.get("BSD_API_KEY", "")
BASE_V2  = "https://sports.bzzoiro.com/api/v2"
BASE_V1  = "https://sports.bzzoiro.com/api"
HEADERS  = {"Authorization": f"Token {API_KEY}"}
DATA_DIR = Path(__file__).parent.parent / "data"

LEAGUES = {
    23: "Superliga României", 1: "Premier League",   7: "Champions League",
    3:  "La Liga",            4: "Serie A",           5: "Bundesliga",
    6:  "Ligue 1",            8: "Europa League",     2: "Liga Portugal",
    10: "Eredivisie",        27: "World Cup 2026",   12: "Championship",
}

# ── Strategii din VEYRA (backtested) ─────────────────────────────────────────
STRATEGIES = {
    "engine_overall": {
        "label": "Engine Overall", "icon": "🎯",
        "markets": ["homeWin","draw","awayWin","over15","under25","under35"],
        "min_adj": 66.0, "min_conf": 0.0, "min_edge": 8.0,
        "odd_min": 1.15, "odd_max": 1.65,
        "color": "#00e87a",
    },
    "best_single": {
        "label": "Evenimentul zilei", "icon": "⭐",
        "markets": ["homeWin","over15","over25","under35"],
        "min_adj": 72.0, "min_conf": 50.0, "min_edge": 8.0,
        "odd_min": 1.20, "odd_max": 1.95,
        "color": "#ffb830",
    },
    "conservative": {
        "label": "Bilet conservator", "icon": "🛡️",
        "markets": ["over15","under35"],
        "min_adj": 74.0, "min_conf": 50.0, "min_edge": 5.0,
        "odd_min": 1.12, "odd_max": 1.65,
        "color": "#4a9eff",
    },
    "smart_ev": {
        "label": "Smart EV", "icon": "💡",
        "markets": ["homeWin","awayWin","over15","over25","under35"],
        "min_adj": 66.0, "min_conf": 0.0, "min_edge": 2.0,
        "odd_min": 1.20, "odd_max": 2.20,
        "color": "#a78bfa",
    },
    "over15_specialist": {
        "label": "Over 1.5G Specialist", "icon": "⚽",
        "markets": ["over15"],
        "min_adj": 76.0, "min_conf": 50.0, "min_edge": 8.0,
        "odd_min": 1.43, "odd_max": 1.60,
        "color": "#22d3ee",
    },
}

MARKET_LABELS = {
    "homeWin": "1 Victorie acasă",
    "draw":    "X Egal",
    "awayWin": "2 Victorie deplasare",
    "over15":  "Over 1.5G",
    "over25":  "Over 2.5G",
    "under25": "Under 2.5G",
    "under35": "Under 3.5G",
    "btts":    "BTTS",
}

# ── HTTP ──────────────────────────────────────────────────────────────────────
def get(url, params=None):
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError as e:
            code = e.response.status_code
            if code in (401,403): return None
            if attempt == 2: return None
        except Exception as e:
            if attempt == 2: print(f"  ERR: {e}"); return None

def paginate(url, params=None):
    params = params or {}; params.setdefault("limit",100)
    results, page_url, seen = [], url, set()
    while page_url and page_url not in seen:
        seen.add(page_url)
        data = get(page_url, params if page_url==url else None)
        if not data: break
        results.extend(data.get("results",[]))
        page_url = data.get("next"); params = {}
    return results

def save(filename, data, protect_empty=True):
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR/filename
    if isinstance(data, dict):
        new_cnt = len(data.get("results", data.get("signals", data.get("events", data.get("standings",[])))))
    else:
        new_cnt = len(data)
    if protect_empty and new_cnt==0 and path.exists():
        try:
            old = json.loads(path.read_text())
            old_cnt = len(old.get("results", old.get("signals", old.get("events", old.get("standings",[])))) if isinstance(old,dict) else old)
            if old_cnt > 0: print(f"  SKIP {filename} (0 nou, pastrez {old_cnt})"); return
        except: pass
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    print(f"  OK {filename} ({new_cnt})")

def now_iso(): return datetime.now(timezone.utc).isoformat()
def today_iso(): return (datetime.now(timezone.utc)+timedelta(hours=4)).strftime("%Y-%m-%d")

# ── Normalize BSD v2 prediction ───────────────────────────────────────────────
def normalize_pred(p, fallback_lid=None, fallback_lname=""):
    ev = p.get("event") or {}
    markets = p.get("markets") or {}
    mr  = markets.get("match_result") or {}
    xg  = markets.get("expected_goals") or {}
    ou  = markets.get("over_under") or {}
    bt  = markets.get("btts") or {}
    sc  = markets.get("score") or {}
    mdl = p.get("model") or {}

    p["_league_id"]   = ev.get("league_id") or fallback_lid
    p["_league_name"] = ev.get("league_name") or LEAGUES.get(ev.get("league_id")) or fallback_lname

    # 1X2 (0-100 → 0-1)
    ph, pd_, pa = mr.get("prob_home"), mr.get("prob_draw"), mr.get("prob_away")
    if ph is not None: p["home_win_probability"] = round(float(ph)/100,4)
    if pd_ is not None: p["draw_probability"]    = round(float(pd_)/100,4)
    if pa is not None: p["away_win_probability"] = round(float(pa)/100,4)

    p["recommended_bet"] = {"H":"1","D":"X","A":"2"}.get(mr.get("predicted",""), "")

    # xG
    if xg.get("home") is not None:
        p["predicted_home_goals"] = xg["home"]
        p["predicted_away_goals"] = xg.get("away")

    # Over/Under múltiple thresholds (0-100 → 0-1)
    o15 = ou.get("prob_over_15"); o25 = ou.get("prob_over_25"); o35 = ou.get("prob_over_35")
    if o15 is not None: p["over_15_probability"]  = round(float(o15)/100,4)
    if o25 is not None:
        p["over_25_probability"]  = round(float(o25)/100,4)
        p["under_25_probability"] = round(1-float(o25)/100,4)
    if o35 is not None:
        p["over_35_probability"]  = round(float(o35)/100,4)
        p["under_35_probability"] = round(1-float(o35)/100,4)

    # BTTS
    pbtts = bt.get("prob_yes")
    if pbtts is not None: p["btts_probability"] = round(float(pbtts)/100,4)

    p["confidence"]        = mdl.get("confidence")
    p["most_likely_score"] = sc.get("most_likely")
    return p

# ── Analytics enrichment ──────────────────────────────────────────────────────
def enrich_analytics(p):
    if not HAS_AC:
        p["quality_grade"] = "—"; p["smartbet_score"] = 0; return p

    pH = p.get("home_win_probability",0)
    pD = p.get("draw_probability",0)
    pA = p.get("away_win_probability",0)
    xgH = p.get("predicted_home_goals")
    xgA = p.get("predicted_away_goals")

    # Poisson (dacă avem xG)
    if xgH and xgA and xgH > 0 and xgA > 0:
        try:
            poi = poisson_market_probabilities(xgH, xgA)
            p.update({
                "poisson_home":    round(poi["home_win"],4),
                "poisson_draw":    round(poi["draw"],4),
                "poisson_away":    round(poi["away_win"],4),
                "poisson_btts":    round(poi["btts"],4),
                "poisson_over25":  round(poi["over25"],4),
                "poisson_over15":  round(poi.get("over15",0),4),
                "poisson_under35": round(poi.get("under35",0),4),
                "top_scores":      poi.get("top_correct_scores",[])[:4],
            })
            if not p.get("most_likely_score"):
                p["most_likely_score"] = poi["most_likely_score"]

            # Blend 65% BSD + 35% Poisson
            if pH > 0:
                p["blended_home"] = round(blend_probabilities({"b":pH,"p":poi["home_win"]},{"b":.65,"p":.35}) or pH,4)
                p["blended_draw"] = round(blend_probabilities({"b":pD,"p":poi["draw"]},    {"b":.65,"p":.35}) or pD,4)
                p["blended_away"] = round(blend_probabilities({"b":pA,"p":poi["away_win"]},{"b":.65,"p":.35}) or pA,4)

            # Poisson delta pentru alerte
            delta = round((poi["home_win"] - pH)*100,1) if pH > 0 else 0
            p["poisson_delta"]     = delta
            p["poisson_direction"] = "value" if delta>5 else ("risk" if delta<-5 else "flat")
        except Exception as e:
            print(f"  Poisson warn: {e}")

    # SmartBet Score
    best_p = max(
        p.get("blended_home") or pH,
        p.get("blended_draw") or pD,
        p.get("blended_away") or pA
    )
    edge_pp = (best_p - 0.5)*100
    p_n = min(100,max(0,(best_p-0.5)/0.30*100))
    e_n = min(100,max(0,edge_pp/15*100))
    p["smartbet_score"] = round(min(100,p_n*0.6+e_n*0.4),1)
    p["edge_pp"]        = round(edge_pp,2)

    # Quality grade
    conf = p.get("confidence") or best_p
    gs = (conf or 0)*100*0.6 + p["smartbet_score"]*0.4
    p["quality_grade"] = quality_grade(gs)
    return p

# ── Get all market probabilities for a pred ──────────────────────────────────
def get_all_markets(pred):
    pH = pred.get("blended_home") or pred.get("home_win_probability") or 0
    pD = pred.get("blended_draw") or pred.get("draw_probability") or 0
    pA = pred.get("blended_away") or pred.get("away_win_probability") or 0

    # Over/Under: prefer Poisson se ai xG, altfel BSD
    o15  = pred.get("poisson_over15")  or pred.get("over_15_probability") or 0
    o25  = pred.get("poisson_over25")  or pred.get("over_25_probability") or 0
    u35  = pred.get("poisson_under35") or pred.get("under_35_probability") or 0
    btts = pred.get("poisson_btts")    or pred.get("btts_probability") or 0
    u25  = pred.get("under_25_probability") or (1-o25 if o25 else 0)

    return {
        "homeWin": pH, "draw": pD, "awayWin": pA,
        "over15": o15, "over25": o25,
        "under25": u25, "under35": u35, "btts": btts,
    }

# ── Signal generation (strategii VEYRA) ──────────────────────────────────────
def compute_signals_from_preds(preds, odds_idx):
    seen_event_market = {}  # deduplicate
    all_signals = []

    for pred in preds:
        ev  = pred.get("event") or {}
        eid = str(ev.get("id",""))
        if not eid: continue

        conf  = (pred.get("confidence") or 0)*100
        sb    = pred.get("smartbet_score", 0)
        grade = pred.get("quality_grade","—")
        mkts  = get_all_markets(pred)

        bo = (odds_idx.get(eid) or {}).get("1x2", {})

        for strat_key, strat in STRATEGIES.items():
            for market_key in strat["markets"]:
                prob01 = mkts.get(market_key, 0)
                if prob01 <= 0: continue
                adj_prob = prob01 * 100

                if adj_prob < strat["min_adj"]: continue
                if conf > 0 and strat["min_conf"] > 0 and conf < strat["min_conf"]: continue

                # Obții cotă: reală dacă e disponibilă, altfel estimată no-vig
                def get_odd_for_market(mk, prob):
                    if mk in ("homeWin","draw","awayWin") and bo:
                        field_map = {"homeWin":["home_odds","odds_1"],"draw":["draw_odds","odds_x"],"awayWin":["away_odds","odds_2"]}
                        for f in field_map.get(mk,[]):
                            v = bo.get(f)
                            if v and float(v)>1: return float(v), True
                    return round(1/(prob*1.05),2) if prob>0.05 else 0, False

                odd, is_real = get_odd_for_market(market_key, prob01)
                if odd < strat["odd_min"] or odd > strat["odd_max"]: continue

                ev_val = prob01 * odd - 1
                edge_pp = (prob01 - 1/odd)*100 if odd>1 else 0

                if edge_pp < strat["min_edge"]: continue

                kelly = min(0.08, max(0, (prob01*odd-1)/(odd-1)))*100 if odd>1 else 0

                sig_key = f"{eid}_{market_key}"
                # Dacă același event+market există deja, ține doar cu cel mai mare SmartBet score
                if sig_key in seen_event_market:
                    if sb <= seen_event_market[sig_key]: continue
                seen_event_market[sig_key] = sb

                signal = {
                    "event_id":      int(eid) if eid.isdigit() else 0,
                    "home_team":     ev.get("home_team","—"),
                    "away_team":     ev.get("away_team","—"),
                    "league":        pred.get("_league_name","—"),
                    "event_date":    ev.get("event_date"),
                    "market":        market_key,
                    "market_label":  MARKET_LABELS.get(market_key, market_key),
                    "adj_prob":      round(adj_prob,1),
                    "confidence":    round(conf,1),
                    "smartbet_score":sb,
                    "quality_grade": grade,
                    "odds":          round(odd,2),
                    "odds_real":     is_real,
                    "ev":            round(ev_val,4),
                    "ev_pct":        f"{ev_val*100:.1f}%",
                    "edge_pp":       round(edge_pp,2),
                    "kelly_pct":     f"{kelly:.1f}%",
                    "strategy":      strat_key,
                    "strategy_label":strat["label"],
                    "strategy_icon": strat["icon"],
                    "strategy_color":strat["color"],
                    "most_likely_score": pred.get("most_likely_score"),
                    "xg_home":      pred.get("predicted_home_goals"),
                    "xg_away":      pred.get("predicted_away_goals"),
                }
                all_signals.append(signal)

    # Re-sort și dedup final
    all_signals.sort(key=lambda x: (x["smartbet_score"], x["adj_prob"]), reverse=True)

    # Grupează pe strategie
    by_strat = {}
    for sig in all_signals:
        sk = sig["strategy"]
        by_strat.setdefault(sk, []).append(sig)

    return all_signals, by_strat

# ── [1/6] Predictions ─────────────────────────────────────────────────────────
def fetch_predictions():
    print("\n[1/6] Predictions per liga...")
    all_preds, seen = [], set()
    for lid, lname in LEAGUES.items():
        for url, pk in [(f"{BASE_V2}/predictions/","league"),(f"{BASE_V2}/predictions/","league_id"),(f"{BASE_V1}/predictions/","league")]:
            data = get(url, {pk: lid})
            if data and data.get("results"):
                cnt = 0
                for p in data["results"]:
                    pid = p.get("id")
                    if pid and pid in seen: continue
                    if pid: seen.add(pid)
                    p = normalize_pred(p, lid, lname)
                    p = enrich_analytics(p)
                    all_preds.append(p); cnt += 1
                if cnt: print(f"  {lname}: {cnt}")
                break

    n_p = sum(1 for p in all_preds if p.get("home_win_probability") is not None)
    n_g = sum(1 for p in all_preds if p.get("quality_grade") not in (None,"—"))
    print(f"  TOTAL: {len(all_preds)} | prob:{n_p} | grade:{n_g}")

    save("predictions.json", {"updated_at":now_iso(),"count":len(all_preds),"results":all_preds}, protect_empty=True)

# ── [2/6] Meciuri ─────────────────────────────────────────────────────────────
def fetch_matches_today():
    print("\n[2/6] Meciuri azi...")
    today, all_m = today_iso(), []
    for lid, lname in LEAGUES.items():
        ms = paginate(f"{BASE_V2}/events/", {"date_from":today,"date_to":today,"league_id":lid,"limit":50})
        if not ms: ms = paginate(f"{BASE_V2}/events/", {"league_id":lid,"status":"notstarted","limit":20})
        for m in ms: m["_league_name"]=lname; m["_league_id"]=lid
        all_m.extend(ms)
    all_m.sort(key=lambda m: m.get("event_date") or "")
    save("matches_today.json", {"date":today,"updated_at":now_iso(),"count":len(all_m),"results":all_m}, protect_empty=False)

# ── [3/6] Best Odds ───────────────────────────────────────────────────────────
def fetch_best_odds():
    print("\n[3/6] Best Odds...")
    all_odds = []
    for market in ["1x2","over_under_25","btts"]:
        for url in [f"{BASE_V2}/best-odds/",f"{BASE_V2}/odds/best/",f"{BASE_V1}/best-odds/"]:
            data = get(url, {"days":2,"market":market})
            if data:
                for item in data.get("results", data if isinstance(data,list) else []):
                    item["_market"]=market; all_odds.append(item)
                break
    save("best_odds.json", {"updated_at":now_iso(),"count":len(all_odds),"results":all_odds}, protect_empty=False)

# ── [4/6] Standings ───────────────────────────────────────────────────────────
def fetch_standings():
    print("\n[4/6] Clasamente...")
    data = {}
    for lid, lname in LEAGUES.items():
        for url, params in [
            (f"{BASE_V2}/standings/{lid}/", None),
            (f"{BASE_V2}/standings/", {"league_id":lid}),
            (f"{BASE_V2}/leagues/{lid}/standings/", None),
            (f"{BASE_V1}/standings/{lid}/", None),
            (f"{BASE_V1}/standings/", {"league_id":lid}),
        ]:
            d = get(url, params)
            if d:
                rows = d.get("standings", d.get("results",[]))
                if rows:
                    data[str(lid)] = {"league_name":lname,"league_id":lid,"standings":rows}
                    print(f"  {lname}: {len(rows)} echipe")
                    break
    save("standings.json", {"updated_at":now_iso(),"leagues":data}, protect_empty=True)

# ── [5/6] Signals (strategii VEYRA) ──────────────────────────────────────────
def compute_signals():
    print("\n[5/6] Signals (strategii)...")
    pred_path = DATA_DIR/"predictions.json"
    odds_path = DATA_DIR/"best_odds.json"
    if not pred_path.exists():
        save("signals.json",{"updated_at":now_iso(),"count":0,"signals":[],"by_strategy":{}},protect_empty=False); return

    preds = json.loads(pred_path.read_text())["results"]

    odds_idx = {}
    if odds_path.exists():
        for o in json.loads(odds_path.read_text())["results"]:
            ev_obj = o.get("event") or {}
            eid = (ev_obj.get("id") if isinstance(ev_obj,dict) else None) or o.get("event_id")
            if eid: odds_idx.setdefault(str(eid),{})[o.get("_market","1x2")] = o

    signals, by_strat = compute_signals_from_preds(preds, odds_idx)

    # Stats per strategie
    strat_stats = {}
    for sk, sigs in by_strat.items():
        strat_stats[sk] = {
            "label":  STRATEGIES[sk]["label"],
            "icon":   STRATEGIES[sk]["icon"],
            "color":  STRATEGIES[sk]["color"],
            "count":  len(sigs),
            "avg_score": round(sum(s["smartbet_score"] for s in sigs)/len(sigs),1) if sigs else 0,
        }

    print(f"  TOTAL: {len(signals)} semnale | {', '.join(f'{sk}:{len(v)}' for sk,v in by_strat.items())}")
    save("signals.json", {"updated_at":now_iso(),"count":len(signals),"signals":signals,"by_strategy":by_strat,"strategy_stats":strat_stats}, protect_empty=True)

# ── [6/6] Value Bets ──────────────────────────────────────────────────────────
def compute_value_bets():
    print("\n[6/6] Value Bets...")
    pred_path = DATA_DIR/"predictions.json"
    odds_path = DATA_DIR/"best_odds.json"
    if not pred_path.exists():
        save("value_bets.json",{"updated_at":now_iso(),"count":0,"results":[]},protect_empty=False); return

    preds = json.loads(pred_path.read_text())["results"]
    odds_idx = {}
    if odds_path.exists():
        for o in json.loads(odds_path.read_text())["results"]:
            ev_obj = o.get("event") or {}
            eid = (ev_obj.get("id") if isinstance(ev_obj,dict) else None) or o.get("event_id")
            if eid: odds_idx.setdefault(str(eid),{})[o.get("_market","1x2")] = o

    vbs = []
    for pred in preds:
        ev  = pred.get("event") or {}
        eid = str(ev.get("id",""))
        if not eid: continue
        pH = pred.get("blended_home") or pred.get("home_win_probability")
        pD = pred.get("blended_draw") or pred.get("draw_probability")
        pA = pred.get("blended_away") or pred.get("away_win_probability")
        if not (pH and pD and pA): continue

        bo = (odds_idx.get(eid) or {}).get("1x2",{})
        has_real = bool(bo)
        raw = [bo.get("home_odds") or bo.get("odds_1"), bo.get("draw_odds") or bo.get("odds_x"), bo.get("away_odds") or bo.get("odds_2")]

        nv_home = nv_draw = nv_away = None
        if HAS_AC and has_real and all(raw):
            nv = no_vig_prob(raw)
            nv_home,nv_draw,nv_away = nv[0],nv[1],nv[2]

        def get_odd(prob, fields):
            for f in fields:
                v = bo.get(f)
                if v and float(v)>1: return float(v)
            return round(1/(prob*1.05),2) if prob>0.05 else 0

        for outcome, prob, nv_p, fields in [
            ("1",pH,nv_home,["home_odds","odds_1"]),
            ("X",pD,nv_draw,["draw_odds","odds_x"]),
            ("2",pA,nv_away,["away_odds","odds_2"]),
        ]:
            odd = get_odd(prob, fields)
            if odd <= 1.01: continue
            ev_val = prob*odd-1
            if ev_val <= 0.05: continue
            kf = min(0.08,max(0,(prob*odd-1)/(odd-1))) if odd>1 else 0
            edge_nv = round((prob-nv_p)*100,2) if nv_p else None
            vbs.append({
                "event_id": int(eid),
                "home_team": ev.get("home_team","—"), "away_team": ev.get("away_team","—"),
                "event_date": ev.get("event_date"), "league": pred.get("_league_name","—"),
                "quality_grade": pred.get("quality_grade","—"), "smartbet_score": pred.get("smartbet_score",0),
                "outcome": outcome, "probability": round(prob,3), "best_odds": round(odd,2),
                "ev": round(ev_val,4), "ev_pct": f"{ev_val*100:.1f}%",
                "kelly_pct": f"{kf*100:.1f}%", "kelly_fraction": round(kf,4),
                "edge_nv_pp": edge_nv, "odds_source": "bookmaker" if has_real else "estimated"
            })

    vbs.sort(key=lambda x:(x.get("smartbet_score",0)*0.4+x["ev"]*60),reverse=True)
    save("value_bets.json",{"updated_at":now_iso(),"count":len(vbs),"results":vbs},protect_empty=False)

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not API_KEY: print("BSD_API_KEY nu este setat!"); sys.exit(1)
    print(f"=== BetPredict Pro v6 — {today_iso()} (analytics: {'YES' if HAS_AC else 'NO'}) ===")
    fetch_predictions()
    fetch_matches_today()
    fetch_best_odds()
    fetch_standings()
    compute_signals()
    compute_value_bets()
    print("\nGata!")
