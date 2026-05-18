#!/usr/bin/env python3
"""
BetPredict Pro — Daily Data Fetcher (v8 — Full API Audit)
==========================================================
FEATURES COMPLETE:
  [1] Predictions globale + paginare → 200+ predicții
  [2] compare_odds per event → 15 bookmakers + SHORTENING/DRIFTING
  [3] Value Bets reale (edge vs Pinnacle no-vig)
  [4] Polymarket odds (al 3-lea model de referință)
  [5] Match details (H2H, form, lineup, preview AI)
  [6] Referee stats per ligă
  [7] Manager tactical profiles
  [8] Team logos + league logos (FREE CDN)
  [9] Signals / strategii backtestale
  [10] Standings cu formă

STRUCTURA BSD v2 CONFIRMATĂ LIVE:
  p.event.league_id / league_name   (FLAT)
  p.markets.match_result.prob_home/draw/away  (0-100)
  p.markets.expected_goals.home/away
  p.markets.over_under.prob_over_15/25/35     (0-100)
  p.markets.btts.prob_yes                     (0-100)
  p.model.confidence                          (0-1)
  compare_odds → HOME/DRAW/AWAY.bookmakers.{slug}.decimal_odds + movement
  compare_odds → HOME.best_odds, HOME.best_bookmaker_slug
"""

import os, json, requests, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

_ROOT = Path(__file__).parent.parent.resolve()
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from analytics_core import (
        normalize_no_vig, expected_value_decimal,
        kelly_fraction as ac_kelly,
        poisson_market_probabilities, quality_grade,
        blend_probabilities, safe_float
    )
    no_vig_prob = normalize_no_vig
    HAS_AC = True; print("analytics_core: OK")
except ImportError:
    HAS_AC = False; print("analytics_core: SKIP")

# ── Config ──────────────────────────────────────────────────────────────────
API_KEY  = os.environ.get("BSD_API_KEY", "")
BASE_V2  = "https://sports.bzzoiro.com/api/v2"
BASE_V1  = "https://sports.bzzoiro.com/api"
IMG_BASE = "https://sports.bzzoiro.com/img"
HEADERS  = {"Authorization": f"Token {API_KEY}"}
DATA_DIR = Path(__file__).parent.parent / "data"

# Ligi priority (primele 12 pt standings/details)
LEAGUES_PRIORITY = [23, 1, 7, 3, 4, 5, 6, 8, 2, 10, 27, 12]

LEAGUES = {
    1:"Premier League", 2:"Liga Portugal", 3:"La Liga", 4:"Serie A", 5:"Bundesliga",
    6:"Ligue 1", 7:"Champions League", 8:"Europa League", 9:"Brasileirao", 10:"Eredivisie",
    11:"Veikkausliiga", 12:"Championship", 13:"Scottish Prem", 14:"Pro League BE",
    15:"Super League CH", 16:"Trendyol Super Lig", 17:"Saudi Pro League",
    18:"Coppa Italia", 19:"Liga MX", 20:"Liga MX Ap", 21:"Copa del Rey",
    22:"Parva Liga", 23:"Superliga România", 24:"Super League GR", 25:"Ekstraklasa",
    26:"Allsvenskan", 27:"World Cup 2026", 28:"Copa Libertadores", 29:"Copa Sudamericana",
    30:"MLS", 31:"DFB Pokal", 32:"FA Cup", 33:"Carabao Cup", 34:"J1 League",
    35:"K League 1", 36:"Chinese Super League", 37:"Brasileirao B",
    38:"Eliteserien", 39:"Africa Cup", 40:"CAF Champions",
}

STRATEGIES = {
    "engine_overall":    {"label":"Engine Overall","icon":"🎯","markets":["homeWin","draw","awayWin","over15","under25","under35"],"min_adj":66.0,"min_edge":8.0,"odd_min":1.15,"odd_max":1.65,"color":"#00e87a"},
    "best_single":       {"label":"Evenimentul zilei","icon":"⭐","markets":["homeWin","over15","over25","under35"],"min_adj":72.0,"min_edge":8.0,"odd_min":1.20,"odd_max":1.95,"color":"#ffb830"},
    "conservative":      {"label":"Bilet conservator","icon":"🛡️","markets":["over15","under35"],"min_adj":74.0,"min_edge":5.0,"odd_min":1.12,"odd_max":1.65,"color":"#4a9eff"},
    "smart_ev":          {"label":"Smart EV","icon":"💡","markets":["homeWin","awayWin","over15","over25","under35"],"min_adj":66.0,"min_edge":2.0,"odd_min":1.20,"odd_max":2.20,"color":"#a78bfa"},
    "over15_specialist": {"label":"Over 1.5G","icon":"⚽","markets":["over15"],"min_adj":76.0,"min_edge":8.0,"odd_min":1.43,"odd_max":1.60,"color":"#22d3ee"},
}

MARKET_LABELS = {
    "homeWin":"1 Victorie acasă","draw":"X Egal","awayWin":"2 Victorie deplasare",
    "over15":"Over 1.5G","over25":"Over 2.5G","under25":"Under 2.5G",
    "under35":"Under 3.5G","btts":"BTTS",
}

ODDS_MARKETS_MAP = {
    "1x2":         {"HOME":"homeWin","DRAW":"draw","AWAY":"awayWin"},
    "over_under_15":{"over":"over15","under":"under15"},
    "over_under_25":{"over":"over25","under":"under25"},
    "over_under_35":{"over":"over35","under":"under35"},
    "btts":        {"yes":"btts","no":"btts_no"},
}

# ── HTTP ──────────────────────────────────────────────────────────────────────
def get(url, params=None):
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=30)
            r.raise_for_status(); return r.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code in (401,403,404): return None
            if attempt == 2: return None
        except Exception as e:
            if attempt == 2: print(f"  ERR: {e}"); return None

def get_all_pages(url, params=None, max_pages=30):
    params = params or {}; params.setdefault("limit",100)
    results, page_url, seen, page = [], url, set(), 0
    while page_url and page_url not in seen and page < max_pages:
        seen.add(page_url)
        data = get(page_url, params if page_url==url else None)
        if not data: break
        batch = data.get("results",[])
        results.extend(batch); page += 1
        if len(batch): print(f"    p{page}: +{len(batch)} (Σ{len(results)})")
        page_url = data.get("next"); params = {}
    return results

def save(filename, data, protect_empty=True):
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR/filename
    keys = ("results","signals","events","standings","referees","managers")
    new_cnt = len(next((data[k] for k in keys if k in data),[]) if isinstance(data,dict) else data)
    if protect_empty and new_cnt==0 and path.exists():
        try:
            old = json.loads(path.read_text())
            old_cnt = len(next((old[k] for k in keys if k in old),[]) if isinstance(old,dict) else old)
            if old_cnt>0: print(f"  SKIP {filename} (0 nou, {old_cnt} vechi)"); return
        except: pass
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    tmp.replace(path); print(f"  OK {filename} ({new_cnt})")

def now_iso(): return datetime.now(timezone.utc).isoformat()
def today_iso(): return (datetime.now(timezone.utc)+timedelta(hours=4)).strftime("%Y-%m-%d")
def logo_url(typ,id_): return f"{IMG_BASE}/{typ}/{id_}/" if id_ else None

# ── Normalize BSD v2 ──────────────────────────────────────────────────────────
def normalize_pred(p, fallback_lid=None, fallback_lname=""):
    ev      = p.get("event") or {}
    markets = p.get("markets") or {}
    mr  = markets.get("match_result") or {}
    xg  = markets.get("expected_goals") or {}
    ou  = markets.get("over_under") or {}
    bt  = markets.get("btts") or {}
    sc  = markets.get("score") or {}
    mdl = p.get("model") or {}

    lid   = ev.get("league_id") or fallback_lid
    lname = ev.get("league_name") or LEAGUES.get(int(lid) if lid else 0, f"Liga {lid}") or fallback_lname
    htid  = ev.get("home_team_id")
    atid  = ev.get("away_team_id")

    p["_league_id"]      = lid
    p["_league_name"]    = lname
    p["_home_team_id"]   = htid
    p["_away_team_id"]   = atid
    p["_team_logo_home"] = logo_url("team", htid)
    p["_team_logo_away"] = logo_url("team", atid)
    p["_league_logo"]    = logo_url("league", lid)

    ph, pd_, pa = mr.get("prob_home"), mr.get("prob_draw"), mr.get("prob_away")
    if ph  is not None: p["home_win_probability"] = round(float(ph)/100, 4)
    if pd_ is not None: p["draw_probability"]     = round(float(pd_)/100, 4)
    if pa  is not None: p["away_win_probability"] = round(float(pa)/100, 4)

    p["recommended_bet"] = {"H":"1","D":"X","A":"2"}.get(mr.get("predicted",""), "")
    p["bet_favorite"]    = p.get("recommendations",{}).get("bet_favorite", False)

    if xg.get("home") is not None:
        p["predicted_home_goals"] = xg["home"]
        p["predicted_away_goals"] = xg.get("away")

    o15=ou.get("prob_over_15"); o25=ou.get("prob_over_25"); o35=ou.get("prob_over_35")
    if o15 is not None: p["over_15_probability"]  = round(float(o15)/100, 4)
    if o25 is not None:
        p["over_25_probability"]  = round(float(o25)/100, 4)
        p["under_25_probability"] = round(1-float(o25)/100, 4)
    if o35 is not None:
        p["over_35_probability"]  = round(float(o35)/100, 4)
        p["under_35_probability"] = round(1-float(o35)/100, 4)

    pbtts = bt.get("prob_yes")
    if pbtts is not None: p["btts_probability"] = round(float(pbtts)/100, 4)

    p["confidence"]        = mdl.get("confidence")
    p["most_likely_score"] = sc.get("most_likely")
    return p

def enrich_analytics(p):
    if not HAS_AC:
        p["quality_grade"] = "—"; p["smartbet_score"] = 0; return p

    pH = p.get("home_win_probability",0)
    pD = p.get("draw_probability",0)
    pA = p.get("away_win_probability",0)
    xgH = p.get("predicted_home_goals")
    xgA = p.get("predicted_away_goals")

    if xgH and xgA and float(xgH)>0 and float(xgA)>0:
        try:
            poi = poisson_market_probabilities(float(xgH),float(xgA))
            p.update({
                "poisson_home":round(poi["home_win"],4),"poisson_draw":round(poi["draw"],4),
                "poisson_away":round(poi["away_win"],4),"poisson_btts":round(poi["btts"],4),
                "poisson_over15":round(poi.get("over15",0),4),"poisson_over25":round(poi.get("over25",0),4),
                "poisson_under35":round(poi.get("under35",0),4),"top_scores":poi.get("top_correct_scores",[])[:4],
            })
            if not p.get("most_likely_score"): p["most_likely_score"] = poi["most_likely_score"]
            if pH>0:
                p["blended_home"] = round(blend_probabilities({"b":pH,"p":poi["home_win"]},{"b":.65,"p":.35}) or pH,4)
                p["blended_draw"] = round(blend_probabilities({"b":pD,"p":poi["draw"]},    {"b":.65,"p":.35}) or pD,4)
                p["blended_away"] = round(blend_probabilities({"b":pA,"p":poi["away_win"]},{"b":.65,"p":.35}) or pA,4)
            delta = round((poi["home_win"]-pH)*100,1) if pH>0 else 0
            p["poisson_delta"]     = delta
            p["poisson_direction"] = "value" if delta>5 else ("risk" if delta<-5 else "flat")
        except: pass

    best_p = max(p.get("blended_home") or pH, p.get("blended_draw") or pD, p.get("blended_away") or pA)
    edge_pp = (best_p-0.5)*100
    p["smartbet_score"] = round(min(100,min(100,max(0,(best_p-0.5)/0.3*100))*0.6+min(100,max(0,edge_pp/15*100))*0.4),1)
    p["edge_pp"] = round(edge_pp,2)
    gs = (p.get("confidence") or best_p or 0)*100*0.6 + p["smartbet_score"]*0.4
    p["quality_grade"] = quality_grade(gs)
    return p

# ── compare_odds per event → REAL bookmaker data ──────────────────────────────
def fetch_compare_odds_for_event(event_id):
    """
    Fetch odds de la 15 bookmakers pentru un eveniment.
    Returnează dict cu best_odds, movement, pinnacle_odds.
    Structura returnată de BSD:
      HOME/DRAW/AWAY.best_odds, .best_bookmaker_slug
      HOME.bookmakers.{slug}.decimal_odds, .movement (SHORTENING/DRIFTING)
    """
    markets_to_fetch = ["1x2", "over_under_25", "over_under_15", "over_under_35", "btts"]
    result = {"event_id": event_id, "markets": {}}

    for market in markets_to_fetch:
        for url_pattern in [
            f"{BASE_V2}/events/{event_id}/odds/?market={market}",
            f"{BASE_V2}/odds/?event={event_id}&market={market}",
            f"{BASE_V2}/compare-odds/?event={event_id}&market={market}",
            f"{BASE_V1}/odds/compare/?event={event_id}&market={market}",
        ]:
            data = get(url_pattern)
            if data and data.get("markets"):
                result["markets"][market] = data["markets"].get(market, {})
                result["event_id"]    = data.get("event_id", event_id)
                result["home_team"]   = data.get("home_team","")
                result["away_team"]   = data.get("away_team","")
                break

    return result if result["markets"] else None

def extract_best_and_pinnacle(odds_data, market="1x2"):
    """
    Din răspunsul compare_odds, extrage:
    - best odds per outcome
    - Pinnacle odds (referință no-vig)
    - movement (SHORTENING/DRIFTING) per outcome
    """
    if not odds_data: return {}
    mkt = odds_data.get("markets",{}).get(market,{})
    result = {}
    for outcome_key, outcome_data in mkt.items():
        if not isinstance(outcome_data, dict): continue
        bk = outcome_data.get("bookmakers",{})
        result[outcome_key] = {
            "best_odds":      outcome_data.get("best_odds"),
            "best_bookmaker": outcome_data.get("best_bookmaker_slug",""),
            "pinnacle_odds":  bk.get("pinnacle",{}).get("decimal_odds"),
            "movement":       bk.get("pinnacle",{}).get("movement","") or bk.get("bet365",{}).get("movement",""),
            "shortening_count": sum(1 for bk_data in bk.values() if isinstance(bk_data,dict) and bk_data.get("movement")=="SHORTENING"),
            "bookmakers_count": len(bk),
        }
    return result

# ── Market probabilities ──────────────────────────────────────────────────────
def get_all_markets(pred):
    pH = pred.get("blended_home") or pred.get("home_win_probability") or 0
    pD = pred.get("blended_draw") or pred.get("draw_probability") or 0
    pA = pred.get("blended_away") or pred.get("away_win_probability") or 0
    return {
        "homeWin":pH,"draw":pD,"awayWin":pA,
        "over15": pred.get("poisson_over15")  or pred.get("over_15_probability") or 0,
        "over25": pred.get("poisson_over25")  or pred.get("over_25_probability") or 0,
        "under25":pred.get("under_25_probability") or 0,
        "under35":pred.get("poisson_under35") or pred.get("under_35_probability") or 0,
        "btts":   pred.get("poisson_btts")    or pred.get("btts_probability") or 0,
    }

def compute_signals_from_preds(preds, odds_idx):
    seen={}; all_sigs=[]
    for pred in preds:
        ev=pred.get("event") or {}; eid=str(ev.get("id",""))
        if not eid: continue
        conf=(pred.get("confidence") or 0)*100; sb=pred.get("smartbet_score",0)
        grade=pred.get("quality_grade","—"); mkts=get_all_markets(pred)
        bo=(odds_idx.get(eid) or {}).get("1x2",{})
        for sk,strat in STRATEGIES.items():
            for mk in strat["markets"]:
                prob01=mkts.get(mk,0)
                if prob01<=0: continue
                adj=prob01*100
                if adj<strat["min_adj"]: continue
                if strat.get("min_conf",0)>0 and conf>0 and conf<strat["min_conf"]: continue
                def get_odd(mk_,prob):
                    if mk_ in ("homeWin","draw","awayWin") and bo:
                        for f in {"homeWin":["home_odds","odds_1"],"draw":["draw_odds","odds_x"],"awayWin":["away_odds","odds_2"]}.get(mk_,[]):
                            v=bo.get(f)
                            if v and float(v)>1: return float(v),True
                    return round(1/(prob*1.05),2) if prob>0.05 else 0,False
                odd,is_real=get_odd(mk,prob01)
                if odd<strat["odd_min"] or odd>strat["odd_max"]: continue
                ev_val=prob01*odd-1
                is_bin=mk not in ("homeWin","draw","awayWin")
                edge_pp=(prob01-1/odd)*100 if is_real and odd>1 else (prob01-(0.5 if is_bin else 0.333))*100
                if edge_pp<strat["min_edge"]: continue
                kelly=min(0.08,max(0,(prob01*odd-1)/(odd-1)))*100 if odd>1 else 0
                sig_key=f"{eid}_{mk}"
                if sig_key in seen and sb<=seen[sig_key]: continue
                seen[sig_key]=sb
                all_sigs.append({
                    "event_id":int(eid) if eid.isdigit() else 0,
                    "home_team":ev.get("home_team","—"),"away_team":ev.get("away_team","—"),
                    "home_team_id":ev.get("home_team_id"),"away_team_id":ev.get("away_team_id"),
                    "league":pred.get("_league_name","—"),"league_id":pred.get("_league_id"),
                    "event_date":ev.get("event_date"),"market":mk,
                    "market_label":MARKET_LABELS.get(mk,mk),"adj_prob":round(adj,1),
                    "confidence":round(conf,1),"smartbet_score":sb,"quality_grade":grade,
                    "odds":round(odd,2),"odds_real":is_real,
                    "ev":round(ev_val,4),"ev_pct":f"{ev_val*100:.1f}%",
                    "edge_pp":round(edge_pp,2),"kelly_pct":f"{kelly:.1f}%",
                    "strategy":sk,"strategy_label":strat["label"],"strategy_icon":strat["icon"],"strategy_color":strat["color"],
                    "most_likely_score":pred.get("most_likely_score"),
                    "xg_home":pred.get("predicted_home_goals"),"xg_away":pred.get("predicted_away_goals"),
                })
    all_sigs.sort(key=lambda x:(x["smartbet_score"],x["adj_prob"]),reverse=True)
    by_strat={}
    for s in all_sigs: by_strat.setdefault(s["strategy"],[]).append(s)
    return all_sigs,by_strat

# ═══════════════════════════════════════════════════════════════════════════════
# [1/8] PREDICTIONS
# ═══════════════════════════════════════════════════════════════════════════════
def fetch_predictions():
    print("\n[1/8] Predictions (global + paginated)...")
    all_preds, seen = [], set()
    for base in [BASE_V2, BASE_V1]:
        url = f"{base}/predictions/"
        print(f"  → {url}...")
        raw = get(url)
        if not raw or not raw.get("results"): continue
        batch = list(raw.get("results",[]))
        next_url = raw.get("next"); page=1
        print(f"    p1: {len(batch)}")
        while next_url and page<30:
            nd=get(next_url)
            if not nd: break
            nb=nd.get("results",[]); batch.extend(nb); page+=1
            print(f"    p{page}: +{len(nb)} (Σ{len(batch)})")
            next_url=nd.get("next")
        for p in batch:
            pid=p.get("id")
            if pid and pid in seen: continue
            if pid: seen.add(pid)
            p=normalize_pred(p); p=enrich_analytics(p); all_preds.append(p)
        if all_preds:
            print(f"  global OK: {len(all_preds)}")
            break
    if not all_preds:
        print("  fallback per-ligă...")
        for lid,lname in list(LEAGUES.items())[:20]:
            for url,pk in [(f"{BASE_V2}/predictions/","league"),(f"{BASE_V2}/predictions/","league_id")]:
                raw=get(url,{pk:lid})
                if raw and raw.get("results"):
                    cnt=0
                    for p in raw["results"]:
                        pid=p.get("id")
                        if pid and pid in seen: continue
                        if pid: seen.add(pid)
                        p=normalize_pred(p,lid,lname); p=enrich_analytics(p); all_preds.append(p); cnt+=1
                    if cnt: print(f"  {lname}: {cnt}")
                    break
    n_p=sum(1 for p in all_preds if p.get("home_win_probability") is not None)
    n_g=sum(1 for p in all_preds if p.get("quality_grade") not in (None,"—"))
    print(f"  TOTAL: {len(all_preds)} | prob:{n_p} | grade:{n_g}")
    save("predictions.json",{"updated_at":now_iso(),"count":len(all_preds),"results":all_preds},protect_empty=True)

# ═══════════════════════════════════════════════════════════════════════════════
# [2/8] COMPARE ODDS → REAL VALUE BETS (15 bookmakers + movement)
# ═══════════════════════════════════════════════════════════════════════════════
def fetch_odds_and_value_bets():
    print("\n[2/8] Compare Odds + Real Value Bets...")
    pred_path = DATA_DIR/"predictions.json"
    if not pred_path.exists():
        save("value_bets.json",{"updated_at":now_iso(),"count":0,"results":[]},protect_empty=False)
        return

    preds = json.loads(pred_path.read_text())["results"]

    # Selectăm top predicții pentru compare_odds (max 40 API calls)
    # Sortăm după confidence descrescătoare
    top_preds = sorted(
        [p for p in preds if p.get("home_win_probability") is not None],
        key=lambda x: (x.get("confidence") or 0), reverse=True
    )[:40]

    all_odds_data = {}
    value_bets = []
    odds_cache = []

    print(f"  Fetch compare_odds pentru {len(top_preds)} meciuri top...")

    for pred in top_preds:
        ev  = pred.get("event") or {}
        eid = ev.get("id")
        if not eid: continue

        # Încearcă compare_odds pentru mai multe piețe
        for market, bsd_market_key in [("1x2","1x2"),("over_under_25","over_under_25"),("btts","btts")]:
            odds_resp = None
            for url_pattern in [
                f"{BASE_V2}/events/{eid}/odds/?market={bsd_market_key}",
                f"{BASE_V2}/odds/?event={eid}&market={bsd_market_key}",
                f"{BASE_V2}/compare-odds/?event={eid}&market={bsd_market_key}",
                f"{BASE_V1}/odds/compare/?event={eid}&market={bsd_market_key}",
            ]:
                r = get(url_pattern)
                if r and r.get("markets"):
                    odds_resp = r; break

            if not odds_resp: continue

            all_odds_data.setdefault(str(eid), {})[market] = odds_resp

            mkt_data = odds_resp.get("markets",{}).get(market,{})

            # ── Compute Value Bets cu odds reale ──
            # BSD model prob vs Pinnacle implied (no-vig reference)
            outcome_map = {
                "1x2":{"HOME":"home_win_probability","DRAW":"draw_probability","AWAY":"away_win_probability"},
                "over_under_25":{"over":"over_25_probability","under":"under_25_probability"},
                "btts":{"yes":"btts_probability","no":None},
            }

            for outcome_key, prob_field in (outcome_map.get(market) or {}).items():
                if not prob_field: continue
                model_prob = (pred.get("blended_home") or pred.get("home_win_probability")) if outcome_key=="HOME" else \
                             (pred.get("blended_draw") or pred.get("draw_probability"))     if outcome_key=="DRAW" else \
                             (pred.get("blended_away") or pred.get("away_win_probability")) if outcome_key=="AWAY" else \
                             pred.get(prob_field)

                if model_prob is None or model_prob <= 0: continue

                outcome_data = mkt_data.get(outcome_key,{})
                if not outcome_data: continue

                best_odds_val   = outcome_data.get("best_odds")
                best_bookmaker  = outcome_data.get("best_bookmaker_slug","")
                pinnacle_odds   = (outcome_data.get("bookmakers") or {}).get("pinnacle",{}).get("decimal_odds")
                movement        = (outcome_data.get("bookmakers") or {}).get("pinnacle",{}).get("movement","")
                shortening_cnt  = sum(1 for bkd in (outcome_data.get("bookmakers") or {}).values()
                                      if isinstance(bkd,dict) and bkd.get("movement")=="SHORTENING")
                total_bk        = len(outcome_data.get("bookmakers") or {})

                if not best_odds_val or float(best_odds_val) <= 1: continue

                best_odds_f = float(best_odds_val)

                # EV vs best available odds
                ev_val = model_prob * best_odds_f - 1
                if ev_val <= 0.02: continue  # prag minim 2%

                # Edge vs Pinnacle no-vig (cel mai precis bookmaker)
                pinnacle_impl_prob = (1/float(pinnacle_odds)) if pinnacle_odds and float(pinnacle_odds)>1 else None
                edge_vs_pinnacle = round((model_prob - pinnacle_impl_prob)*100, 2) if pinnacle_impl_prob else None

                # Kelly fraction
                kf = min(0.08, max(0,(model_prob*best_odds_f-1)/(best_odds_f-1))) if best_odds_f>1 else 0

                # Fair odd (no-vig estimate)
                fair_odd = round(1/(model_prob*1.02), 2) if model_prob>0.05 else None

                label_map = {
                    "HOME":"1 Victorie acasă","DRAW":"X Egal","AWAY":"2 Victorie deplasare",
                    "over":"Over 2.5G","under":"Under 2.5G","yes":"BTTS Da","no":"BTTS Nu"
                }

                value_bets.append({
                    "source":          "compare_odds",
                    "confidence":      round(pred.get("smartbet_score",0)),
                    "tier":            "strong" if shortening_cnt >= total_bk*0.5 else "neutral",
                    "market":          f"{market}_{outcome_key}",
                    "market_label":    label_map.get(outcome_key, outcome_key),
                    "market_odds":     round(best_odds_f,3),
                    "best_bookmaker":  best_bookmaker,
                    "pinnacle_odds":   round(float(pinnacle_odds),3) if pinnacle_odds else None,
                    "model_probability": round(model_prob*100,1),
                    "market_probability":round((1/best_odds_f)*100,1) if best_odds_f>1 else None,
                    "pinnacle_probability": round(pinnacle_impl_prob*100,1) if pinnacle_impl_prob else None,
                    "edge":            round(ev_val,4),
                    "edge_pct":        f"+{ev_val*100:.1f}%",
                    "edge_vs_pinnacle": edge_vs_pinnacle,
                    "fair_odd":        fair_odd,
                    "movement":        movement,
                    "shortening_count": shortening_cnt,
                    "bookmakers_count": total_bk,
                    "kelly_pct":       f"{kf*100:.1f}%",
                    "kelly_fraction":  round(kf,4),
                    "event_id":        int(eid),
                    "home_team":       ev.get("home_team","—"),
                    "away_team":       ev.get("away_team","—"),
                    "home_team_id":    ev.get("home_team_id"),
                    "away_team_id":    ev.get("away_team_id"),
                    "league":          pred.get("_league_name","—"),
                    "league_id":       pred.get("_league_id"),
                    "event_date":      ev.get("event_date"),
                    "quality_grade":   pred.get("quality_grade","—"),
                    "most_likely_score": pred.get("most_likely_score"),
                    "xg_home":         pred.get("predicted_home_goals"),
                    "xg_away":         pred.get("predicted_away_goals"),
                })

    # Dacă am obținut date reale, salvăm
    if value_bets:
        value_bets.sort(key=lambda x: (-x["edge"],-x["shortening_count"]))
        print(f"  REAL Value Bets: {len(value_bets)}")
        save("value_bets.json",{"source":"compare_odds","updated_at":now_iso(),"count":len(value_bets),"results":value_bets},protect_empty=False)

        # Salvăm și cached odds pentru frontend (mișcare cote)
        save("odds_cache.json",{"updated_at":now_iso(),"odds":all_odds_data},protect_empty=False)
        return

    # Fallback: value bets din semnale (best_single strategy)
    print("  compare_odds indisponibil → fallback din semnale...")
    sig_path = DATA_DIR/"signals.json"
    if sig_path.exists():
        sigs = json.loads(sig_path.read_text())
        best_sigs = sorted(
            sigs.get("signals",[]),
            key=lambda x: (x.get("smartbet_score",0), x.get("adj_prob",0)),
            reverse=True
        )[:30]

        for sig in best_sigs:
            ev_val = sig.get("ev", 0)
            if ev_val > -0.02:  # include chiar și la EV ușor negativ dacă SmartBet score e înalt
                prob = sig.get("adj_prob",0)/100
                odd  = sig.get("odds",0)
                value_bets.append({
                    "source":           "model_pick",
                    "confidence":       sig.get("smartbet_score",0),
                    "tier":             "strong" if sig.get("smartbet_score",0)>=65 else "neutral",
                    "market":           sig.get("market",""),
                    "market_label":     sig.get("market_label",""),
                    "market_odds":      odd,
                    "model_probability":sig.get("adj_prob",0),
                    "market_probability":round(100/odd,1) if odd>1 else None,
                    "edge":             ev_val,
                    "edge_pct":         sig.get("ev_pct","—"),
                    "edge_vs_pinnacle": sig.get("edge_pp"),
                    "fair_odd":         None,
                    "movement":         "",
                    "kelly_pct":        sig.get("kelly_pct","—"),
                    "event_id":         sig.get("event_id",0),
                    "home_team":        sig.get("home_team","—"),
                    "away_team":        sig.get("away_team","—"),
                    "home_team_id":     sig.get("home_team_id"),
                    "away_team_id":     sig.get("away_team_id"),
                    "league":           sig.get("league","—"),
                    "league_id":        sig.get("league_id"),
                    "event_date":       sig.get("event_date"),
                    "quality_grade":    sig.get("quality_grade","—"),
                    "most_likely_score":sig.get("most_likely_score"),
                    "xg_home":          sig.get("xg_home"),
                    "xg_away":          sig.get("xg_away"),
                })
        if value_bets:
            save("value_bets.json",{"source":"model_pick","updated_at":now_iso(),"count":len(value_bets),"results":value_bets},protect_empty=False)
            return

    save("value_bets.json",{"updated_at":now_iso(),"count":0,"results":[]},protect_empty=False)

# ═══════════════════════════════════════════════════════════════════════════════
# [3/8] MATCHES TODAY
# ═══════════════════════════════════════════════════════════════════════════════
def fetch_matches_today():
    print("\n[3/8] Meciuri azi...")
    today = today_iso()
    all_m = get_all_pages(f"{BASE_V2}/events/", {"date_from":today,"date_to":today,"limit":100})
    if not all_m:
        for lid,lname in list(LEAGUES.items())[:15]:
            ms = get_all_pages(f"{BASE_V2}/events/", {"date_from":today,"date_to":today,"league_id":lid,"limit":50})
            for m in ms: m["_league_name"]=lname; m["_league_id"]=lid
            all_m.extend(ms)
    for m in all_m:
        htid=m.get("home_team_id"); atid=m.get("away_team_id"); lid=m.get("league_id")
        m["_team_logo_home"] = logo_url("team",htid)
        m["_team_logo_away"] = logo_url("team",atid)
        m["_league_logo"]    = logo_url("league",lid)
        m["_league_name"]    = m.get("league_name") or LEAGUES.get(int(lid) if lid else 0,"")
    all_m.sort(key=lambda m: m.get("event_date") or "")
    save("matches_today.json",{"date":today,"updated_at":now_iso(),"count":len(all_m),"results":all_m},protect_empty=False)

# ═══════════════════════════════════════════════════════════════════════════════
# [4/8] POLYMARKET ODDS
# ═══════════════════════════════════════════════════════════════════════════════
def fetch_polymarket():
    print("\n[4/8] Polymarket odds...")
    pred_path = DATA_DIR/"predictions.json"
    if not pred_path.exists():
        save("polymarket.json",{"updated_at":now_iso(),"count":0,"results":[]},protect_empty=False); return

    preds = json.loads(pred_path.read_text())["results"]
    top_by_league = {}
    for p in preds:
        lid = str(p.get("_league_id",""))
        if lid not in top_by_league:
            top_by_league[lid] = p

    polymarket_data = []
    for p in list(top_by_league.values())[:10]:
        ev  = p.get("event") or {}
        eid = ev.get("id"); lid = ev.get("league_id")
        if not eid: continue

        for url_pattern in [
            f"{BASE_V2}/polymarket/?event={eid}",
            f"{BASE_V2}/events/{eid}/polymarket/",
            f"{BASE_V2}/odds/polymarket/?event={eid}",
        ]:
            r = get(url_pattern)
            if r and (r.get("markets") or r.get("results")):
                polymarket_data.append({
                    "event_id": eid,
                    "home_team": ev.get("home_team",""),
                    "away_team": ev.get("away_team",""),
                    "league": p.get("_league_name",""),
                    "event_date": ev.get("event_date"),
                    "data": r
                })
                break

    save("polymarket.json",{"updated_at":now_iso(),"count":len(polymarket_data),"results":polymarket_data},protect_empty=False)

# ═══════════════════════════════════════════════════════════════════════════════
# [5/8] BEST ODDS (global)
# ═══════════════════════════════════════════════════════════════════════════════
def fetch_best_odds():
    print("\n[5/8] Best Odds...")
    all_odds=[]
    for market in ["1x2","over_under_25","over_under_15","btts"]:
        for url in [f"{BASE_V2}/best-odds/",f"{BASE_V1}/best-odds/"]:
            data=get(url,{"days":3,"market":market})
            if data:
                for item in data.get("results",data if isinstance(data,list) else []):
                    item["_market"]=market; all_odds.append(item)
                break
    save("best_odds.json",{"updated_at":now_iso(),"count":len(all_odds),"results":all_odds},protect_empty=False)

# ═══════════════════════════════════════════════════════════════════════════════
# [6/8] STANDINGS
# ═══════════════════════════════════════════════════════════════════════════════
def fetch_standings():
    print("\n[6/8] Clasamente...")
    data={}
    for lid in LEAGUES_PRIORITY:
        lname=LEAGUES.get(lid,f"Liga {lid}")
        for url,params in [
            (f"{BASE_V2}/standings/{lid}/",None),(f"{BASE_V2}/standings/",{"league_id":lid}),
            (f"{BASE_V2}/leagues/{lid}/standings/",None),(f"{BASE_V1}/standings/",{"league_id":lid}),
        ]:
            d=get(url,params)
            if d:
                rows=d.get("standings",d.get("results",[]))
                if rows:
                    data[str(lid)]={"league_name":lname,"league_id":lid,"standings":rows,"league_logo":logo_url("league",lid)}
                    print(f"  {lname}: {len(rows)}")
                    break
    save("standings.json",{"updated_at":now_iso(),"leagues":data},protect_empty=True)

# ═══════════════════════════════════════════════════════════════════════════════
# [7/8] REFEREE STATS + MANAGER PROFILES (context per meci)
# ═══════════════════════════════════════════════════════════════════════════════
def fetch_referee_and_manager_context():
    print("\n[7/8] Referee + Manager context...")
    pred_path = DATA_DIR/"predictions.json"
    if not pred_path.exists():
        save("context.json",{"updated_at":now_iso(),"referees":{},"managers":{}},protect_empty=False); return

    preds = json.loads(pred_path.read_text())["results"]
    referee_ids = set(); manager_ids = set()

    # Colectăm referee_id și coach_id din match details (din predictions event)
    for p in preds[:20]:  # primele 20 meciuri
        ev = p.get("event") or {}
        if ev.get("referee_id"): referee_ids.add(ev["referee_id"])
        if ev.get("home_coach_id"): manager_ids.add(ev["home_coach_id"])
        if ev.get("away_coach_id"): manager_ids.add(ev["away_coach_id"])

    referees = {}
    managers = {}

    # Fetch referee stats
    for league_id in LEAGUES_PRIORITY[:6]:
        data = get(f"{BASE_V2}/referees/", {"league_id": league_id})
        if data:
            for ref in data.get("results", data if isinstance(data, list) else []):
                rid = ref.get("id")
                if rid: referees[str(rid)] = {
                    "name":        ref.get("name",""),
                    "country":     ref.get("country",""),
                    "games":       ref.get("games") or ref.get("total_games"),
                    "yellow_cards_per_game": ref.get("yellow_cards_per_game") or ref.get("avg_yellow_cards"),
                    "red_cards_per_game":    ref.get("red_cards_per_game") or ref.get("avg_red_cards"),
                    "goals_per_game":        ref.get("goals_per_game") or ref.get("avg_goals"),
                }

    # Fetch manager profiles
    for mid in list(manager_ids)[:10]:
        data = get(f"{BASE_V2}/managers/{mid}/")
        if not data: data = get(f"{BASE_V1}/managers/{mid}/")
        if data:
            managers[str(mid)] = {
                "name":               data.get("name",""),
                "team":               data.get("team","") or data.get("current_team",""),
                "preferred_formation":data.get("preferred_formation",""),
                "style":              data.get("style","") or data.get("tactical_style",""),
                "pressing_intensity": data.get("pressing_intensity"),
                "defensive_line":     data.get("defensive_line",""),
                "win_rate":           data.get("win_rate"),
                "avg_goals_scored":   data.get("avg_goals_scored"),
            }

    print(f"  referees: {len(referees)}, managers: {len(managers)}")
    save("context.json",{"updated_at":now_iso(),"referees":referees,"managers":managers},protect_empty=False)

# ═══════════════════════════════════════════════════════════════════════════════
# [8/8] SIGNALS (strategii backtestale)
# ═══════════════════════════════════════════════════════════════════════════════
def compute_signals():
    print("\n[8/8] Signals...")
    pred_path=DATA_DIR/"predictions.json"; odds_path=DATA_DIR/"best_odds.json"
    if not pred_path.exists():
        save("signals.json",{"updated_at":now_iso(),"count":0,"signals":[],"by_strategy":{},"strategy_stats":{}},protect_empty=False); return
    preds=json.loads(pred_path.read_text())["results"]
    odds_idx={}
    if odds_path.exists():
        for o in json.loads(odds_path.read_text())["results"]:
            ev_obj=o.get("event") or {}
            eid=(ev_obj.get("id") if isinstance(ev_obj,dict) else None) or o.get("event_id")
            if eid: odds_idx.setdefault(str(eid),{})[o.get("_market","1x2")]=o
    signals,by_strat=compute_signals_from_preds(preds,odds_idx)
    strat_stats={
        sk:{"label":STRATEGIES[sk]["label"],"icon":STRATEGIES[sk]["icon"],"color":STRATEGIES[sk]["color"],
            "count":len(sigs),"avg_score":round(sum(s["smartbet_score"] for s in sigs)/len(sigs),1) if sigs else 0}
        for sk,sigs in by_strat.items()
    }
    print(f"  TOTAL: {len(signals)} | "+", ".join(f"{sk}:{len(v)}" for sk,v in by_strat.items()))
    save("signals.json",{"updated_at":now_iso(),"count":len(signals),"signals":signals,"by_strategy":by_strat,"strategy_stats":strat_stats},protect_empty=True)

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not API_KEY: print("BSD_API_KEY nu este setat!"); sys.exit(1)
    print(f"=== BetPredict Pro v8 — {today_iso()} (AC:{'YES' if HAS_AC else 'NO'}) ===")
    fetch_predictions()      # [1] 200+ predicții globale
    compute_signals()        # [8] Semnale din predicții (înainte de odds)
    fetch_odds_and_value_bets()  # [2] compare_odds → real value bets
    fetch_matches_today()    # [3] meciuri azi
    fetch_polymarket()       # [4] Polymarket odds
    fetch_best_odds()        # [5] best odds
    fetch_standings()        # [6] clasamente
    fetch_referee_and_manager_context()  # [7] context arbitru + manager
    print("\nGata!")
