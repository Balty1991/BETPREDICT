#!/usr/bin/env python3
"""BETPREDICT 2.0 — Pyramid Assistant: step-ready execution plans.

Reparat (Faza 0+1, cerut explicit de utilizator dupa un audit onest):
  1. Cota afisata e acum cea REALA Superbet (superbet_live_odds.json), nu cea mai
     buna cota cross-book — acelasi bug gasit si reparat in smart_accumulator.py.
     Daca nu gasim sigur meciul la Superbet, piciorul e exclus (nu recomandam
     cote inaccesibile).
  2. Piata dovedita prost calibrata (CRITICAL, ECE mare) ramane blocata tare.
     Piata cu esantion insuficient (NO_DATA) NU mai e blocata total — trece cu
     scor redus + avertisment vizibil, ca sa nu ramana pool-ul gol degeaba cand
     n e doar mic, nu dovedit gresit.
  3. Fiecare plan include acum sansa REALA (istorica, din superbet_edge_history.json,
     nu presupusa) de a ajunge la fiecare pas — calculata din win-rate-ul chiar
     al platformei pe picioare deja decontate. Pas 17 la 1.4 NU e un obiectiv
     sistematic — cifrele din 'realistic_completion' arata de ce.
"""
from __future__ import annotations
import json, math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
ROOT=Path(__file__).resolve().parent.parent; DATA=ROOT/'data'
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from superbet_live_odds import find_live_match
except Exception:
    def find_live_match(live_matches, home_team, away_team, event_dt, min_score=0.6):
        return None

def load(p,default):
    try: return json.load(open(p,encoding='utf-8'))
    except Exception: return default

def save(p,obj):
    p.parent.mkdir(parents=True,exist_ok=True); tmp=p.with_suffix(p.suffix+'.tmp')
    json.dump(obj,open(tmp,'w',encoding='utf-8'),ensure_ascii=False,indent=2,default=str); open(tmp,'a',encoding='utf-8').write('\n'); tmp.replace(p)

def f(v,d=0.0):
    try:
        if isinstance(v,str): v=v.replace('%','').replace(',','.').strip()
        x=float(v); return d if math.isnan(x) or math.isinf(x) else x
    except Exception: return d

def _parse_dt(s: Any) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace('Z', '+00:00'))
    except Exception:
        return None


# Fus orar România pentru definirea "zilei curente" (piramidele analizează DOAR azi).
try:
    from zoneinfo import ZoneInfo
    _TZ_RO = ZoneInfo('Europe/Bucharest')
except Exception:  # fallback EEST (vara) daca tzdata lipseste
    _TZ_RO = timezone(timedelta(hours=3))


def _is_today_ro(sig: Dict[str, Any]) -> bool:
    """True daca meciul se joaca azi, in ziua calendaristica din România."""
    d = _local_date_ro(sig)
    return d is not None and d == datetime.now(_TZ_RO).date()


def _local_date_ro(sig: Dict[str, Any]):
    """Data (RO) la care se joaca meciul, sau None."""
    dt = _parse_dt(sig.get('event_date'))
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_TZ_RO).date()


def _target_day_signals(signals):
    """Pastreaza DOAR meciurile din ziua curenta; daca azi nu sunt meciuri,
    cade automat pe cea mai apropiata zi VIITOARE cu meciuri (nu forteaza zile
    indepartate, dar nici nu lasa piramidele goale degeaba)."""
    today = datetime.now(_TZ_RO).date()
    days = sorted({d for d in (_local_date_ro(s) for s in signals) if d is not None and d >= today})
    if not days:
        return [], None
    target = days[0]
    return [s for s in signals if _local_date_ro(s) == target], target

# market-ul din signals.json -> (market, outcome) din superbet_live_odds.json
MARKET_MAP = {
    'homeWin': ('1x2', 'HOME'), 'draw': ('1x2', 'DRAW'), 'awayWin': ('1x2', 'AWAY'),
    'btts': ('btts', 'YES'), 'no_btts': ('btts', 'NO'),
    'over15': ('over_under_15', 'OVER'), 'under15': ('over_under_15', 'UNDER'),
    'over25': ('over_under_25', 'OVER'), 'under25': ('over_under_25', 'UNDER'),
    'over35': ('over_under_35', 'OVER'), 'under35': ('over_under_35', 'UNDER'),
}

# claude_predictions.json foloseste piete in format "local"; le mapam la compact.
_CLAUDE_TO_COMPACT = {
    'home_win': 'homeWin', 'draw': 'draw', 'away_win': 'awayWin',
    'btts_yes': 'btts', 'btts_no': 'no_btts',
    'over_15': 'over15', 'under_15': 'under15',
    'over_25': 'over25', 'under_25': 'under25',
    'over_35': 'over35', 'under_35': 'under35',
}


def today_offer_candidates() -> List[Dict[str, Any]]:
    """Candidati din OFERTA REALA de azi (claude_predictions.json): pronosticuri
    cu cota si probabilitate. Sursa piramidei cand signals.json nu are meciuri azi
    — asa piramida sigura arata cele mai sigure pronosticuri ale zilei."""
    data = load(DATA/'claude_predictions.json', {})
    rows = data.get('results', []) or []
    today = datetime.now(_TZ_RO).date()
    out: List[Dict[str, Any]] = []
    for x in rows:
        if _local_date_ro(x) != today:
            continue
        odds = f(x.get('odds')); prob = f(x.get('probability'))
        if odds <= 1.0 or prob <= 0:
            continue
        out.append({
            'event_id': x.get('event_id'),
            'market': _CLAUDE_TO_COMPACT.get(str(x.get('market') or ''), str(x.get('market') or '')),
            'market_label': x.get('market_label'),
            'home_team': x.get('home_team', ''), 'away_team': x.get('away_team', ''),
            'league': x.get('league', ''), 'event_date': x.get('event_date', ''),
            'adj_prob': prob, 'edge_pp': f(x.get('edge_pp')),
            '_superbet_odds': odds, 'odds': odds, 'odds_real': True,
            'source': 'daily_offer',
        })
    return out

def _resolve_superbet_odds(sig: Dict[str, Any], live_matches: List[Dict[str, Any]]) -> Optional[float]:
    sm, so = MARKET_MAP.get(str(sig.get('market') or ''), (None, None))
    if not sm:
        return None
    event_dt = _parse_dt(sig.get('event_date'))
    m = find_live_match(live_matches, sig.get('home_team', ''), sig.get('away_team', ''), event_dt)
    if not m:
        return None
    price = (m.get('markets', {}).get(sm) or {}).get(so)
    return price if price else None

def market_score(sig):
    direct=f(sig.get('display_score') or sig.get('market_signal_score') or sig.get('smartbet_score_v6'),None)
    if direct is not None and direct>0: return min(100,max(0,direct))
    prob=f(sig.get('adj_prob')); edge=max(0,f(sig.get('edge_pp'))); ev=f(sig.get('ev_calibrated_pct') or sig.get('ev_pct'))
    odds=f(sig.get('_superbet_odds'))
    odds_score=100 if 1.25<=odds<=1.65 else 70 if 1.18<=odds<=2.10 else 35
    return round(min(100,max(0,(prob-60)/30*50 + min(edge/8*100,100)*.25 + min(max(ev,0)/12*100,100)*.20 + odds_score*.05)),1)

def ctx_idx():
    return load(DATA/'context_scores.json',{}).get('by_event',{})

def clv_idx():
    return load(DATA/'clv_tracker.json',{}).get('by_event_market',{})

def heat_leagues():
    return load(DATA/'performance_heatmap.json',{}).get('leagues',{})

def league_grade_value(g):
    return {'A+':12,'A':9,'B':5,'C':1,'D':-5,'N/A':0}.get(str(g),0)

# Extins la 10 pasi (inainte se opreste la 5 si repeta regula pasului 5 pt. 6-10 —
# gap descoperit acum, la cererea de a face un plan pe 10 pasi). Pragurile continua
# aceeasi tendinta: prob. minima ceruta scade usor, plaja de cota se largeste usor.
def step_rule(step:int, avg_odds:float=1.30):
    base={
        1:(85,1.25,1.42), 2:(83,1.25,1.48), 3:(80,1.25,1.55), 4:(78,1.28,1.65), 5:(75,1.30,1.80),
        6:(73,1.32,1.90), 7:(71,1.34,2.00), 8:(70,1.36,2.10), 9:(69,1.38,2.15), 10:(68,1.40,2.20),
    }
    p,lo,hi=base.get(min(max(step,1),10),base[10])
    # adapt to requested average odds
    shift=(avg_odds-1.30)*0.65
    lo2=max(1.08,lo+shift)
    hi2=hi+shift
    p2=max(65,p-(step-1)*0.3)
    # ---- Piramida RISC (avg_odds > 1.30) ----
    # Bug vechi: pragul de probabilitate ramanea ~85% chiar si la cota ~2.1, iar
    # cota era plafonata la 2.20. Un pick de 85% NU se ofera niciodata la 2.0+, deci
    # piramida risc era MEREU goala. Fix: la cote mari, largim fereastra de cota si
    # legam pragul de break-even (nu poti cere 85% la cota 2.5).
    if avg_odds>1.30:
        hi2=min(3.4,hi2+(avg_odds-1.30)*0.5)   # spatiu real spre ~2.5-3.0
        mid=(lo2+hi2)/2.0
        be=100.0/mid                            # probabilitatea break-even a benzii
        p2=max(50.0,min(p2,be+8.0))             # break-even + marja, dar minim 50%
    else:
        # Piramida SIGURA: coboram pragul de cota ca sa includem si cei mai siguri
        # pronostici ai zilei (cota <1.25), care altfel erau exclusi absurd.
        lo2=max(1.10,lo2-0.13)
        p2=min(p2,80.0)   # prag realist: oferta zilei e adesea 80-88%, nu 85%+
    return p2, lo2, hi2

def clv_for_signal(sig, by):
    eid=str(sig.get('event_id') or '')
    mk=str(sig.get('market') or '').lower().replace('_','')
    for k,v in by.items():
        if k.startswith(eid+'|') and mk in k.lower().replace('_',''):
            return v
    return {}

def pyramid_score(sig, step, avg_odds, ctx, clv, leagues):
    odds=f(sig.get('_superbet_odds'))
    if odds<=0: return 0
    prob=f(sig.get('adj_prob')); edge=f(sig.get('edge_pp'))
    minp,lo,hi=step_rule(step,avg_odds)
    if odds<lo or odds>hi or prob<minp: return 0
    sc=market_score(sig)
    c=ctx.get(str(sig.get('event_id')),{}) or {}; ctxs=f(c.get('context_score'),60)
    cl=clv_for_signal(sig,clv); clvp=f(cl.get('clv_pct'),0); clvrel=bool(cl.get('clv_reliable'))
    lg=leagues.get(str(sig.get('league') or ''),{}) or {}; lgboost=league_grade_value(lg.get('grade'))
    volatility=f(lg.get('volatility'),0.8)
    stability=max(0,18-volatility*12)
    price_fit=max(0,10-abs(odds-avg_odds)*18)
    score=sc*.42+prob*.22+min(max(edge,0)*6,18)+ctxs*.12+stability+lgboost+price_fit
    if clvrel and clvp>0: score+=6
    if clvrel and clvp<0: score-=9
    if sig.get('odds_real'): score+=2
    return round(max(0,min(100,score)),1)

def _calibration_health() -> Dict[str, Dict[str, Any]]:
    """Mapeaza market -> record complet (status/n/reason), nu doar status —
    NO_DATA are nevoie de 'n' pt. avertismentul afisat utilizatorului."""
    return load(DATA/'calibration_health.json', {}).get('per_market', {})

def plan_for_step(signals, step, avg_odds, ctx, clv, leagues, health=None):
    rows=[]
    minp,lo,hi=step_rule(step,avg_odds)
    health = health if health is not None else _calibration_health()
    for sig in signals:
        mk = str(sig.get('market') or '')
        rec = health.get(mk, {}) or {}
        status = rec.get('status', 'UNKNOWN')
        if status == 'CRITICAL':
            continue  # dovedit prost calibrat (ECE mare) — blocat tare, nu doar penalizat
        if not sig.get('_superbet_odds'):
            continue  # nu gasim sigur cota reala Superbet — nu poti paria pe asta oricum
        ps=pyramid_score(sig,step,avg_odds,ctx,clv,leagues)
        if ps<=0: continue
        if status == 'NO_DATA':
            ps = round(ps*0.6, 1)  # esantion insuficient — nu blocat, dar scor redus + flag
        row=dict(sig)
        row['odds']=sig['_superbet_odds']; row['bookmaker']='Superbet'
        row['pyramid_ready_score']=ps; row['pyramid_step']=step
        row['pyramid_rule']={'min_prob':round(minp,1),'odds_min':round(lo,2),'odds_max':round(hi,2)}
        row['execution_note']=f"Pas {step}: prob. minimă {minp:.0f}%, cotă {lo:.2f}-{hi:.2f}, scor stabilitate {ps:.0f}/100."
        row['calibration_status']=status
        if status == 'NO_DATA':
            row['calibration_warning']=f"Eșantion insuficient (n={rec.get('n', '?')}) — probabilitate neverificată statistic, tratează cu prudență."
        rows.append(row)
    rows.sort(key=lambda r:(r.get('pyramid_ready_score',0),f(r.get('adj_prob')), -abs(f(r.get('odds'))-avg_odds)), reverse=True)
    return rows[:8]

def _historical_leg_win_rate() -> Dict[str, Any]:
    """Win-rate REAL, din picioarele Superbet Edge deja decontate — nu o presupunere.
    Folosit ca sa aratam sansa REALISTA de a ajunge la fiecare pas, nu una optimista."""
    hist = load(DATA/'superbet_edge_history.json', {}) or {}
    summary = hist.get('legs_summary', {}) or {}
    by_conf = hist.get('legs_by_confidence', {}) or {}
    tickets = hist.get('tickets_summary', {}) or {}
    return {
        'n_legs_settled': summary.get('n_settled', 0),
        'leg_win_rate_pct': summary.get('win_rate_pct'),
        'by_confidence': by_conf,
        'tickets_settled': tickets.get('n_settled', 0),
        'ticket_win_rate_pct': tickets.get('win_rate_pct'),
    }

def _realistic_completion(win_rate_pct: Optional[float], max_step: int) -> Dict[str, Any]:
    """P(a ajunge la pasul N) = (win_rate real)^N — matematica simpla a compunerii
    de evenimente independente, aplicata pe cifra REALA masurata, nu pe o speranta."""
    if not win_rate_pct or win_rate_pct <= 0:
        return {'note': 'insuficiente picioare decontate pentru o estimare — nu inventam un numar'}
    p = min(1.0, win_rate_pct / 100.0)
    out = {}
    for s in range(1, max_step + 1):
        prob = p ** s
        out[str(s)] = {
            'probability_pct': round(prob * 100, 4),
            'one_in': round(1 / prob) if prob > 0 else None,
        }
    return out

def main():
    sp=load(DATA/'signals.json',{'signals':[]}); signals=sp.get('signals',[])
    # Piramidele analizeaza DOAR ziua curenta (cerut explicit).
    signals=[s for s in signals if _is_today_ro(s)]
    ctx=ctx_idx(); clv=clv_idx(); leagues=heat_leagues()
    live_odds = load(DATA/'superbet_live_odds.json', {}) or {}
    live_matches = live_odds.get('matches') or []

    for sig in signals:
        sig['_superbet_odds'] = _resolve_superbet_odds(sig, live_matches)
    # Alimenteaza din OFERTA REALA de azi (predictii cu cota+probabilitate),
    # ca piramida sigura sa arate cele mai sigure pronosticuri ale zilei chiar
    # daca signals.json (value Superbet) nu are meciuri azi.
    seen={(str(s.get('event_id')),str(s.get('market'))) for s in signals}
    for c in today_offer_candidates():
        k=(str(c.get('event_id')),str(c.get('market')))
        if k not in seen:
            signals.append(c); seen.add(k)
    n_total = len(signals)
    print(f"[pyramid] candidati azi: {n_total}")
    n_matched = sum(1 for s in signals if s.get('_superbet_odds'))

    hist = _historical_leg_win_rate()

    plans=[]
    for steps in [3,5,7,10]:
        avg=1.30 if steps<=5 else 1.25
        step_rows={}
        for step in range(1,steps+1):
            step_rows[str(step)]=plan_for_step(signals,step,avg,ctx,clv,leagues)
        plans.append({
            'name':f'Pyramid {steps} pași','steps':steps,'avg_odds':avg,'step_plans':step_rows,
            'realistic_completion': _realistic_completion(hist.get('leg_win_rate_pct'), steps),
        })
    # Default pool pentru UI (avg=1.30) + pool-uri per target comun — acum pana la pasul 10
    by_current={str(s):plan_for_step(signals,s,1.30,ctx,clv,leagues) for s in range(1,11)}
    COMMON_TARGETS=[1.20,1.30,1.50,1.70,2.00,2.50]
    # target 2.50 = folosit de pyramid_tracker.py pt. piramida "risc" — extins la 5 pasi
    # (restul target-urilor raman la 3, doar afisate ca optiuni in UI, nu urmarite de tracker).
    STEPS_PER_TARGET={'t2_50':5}
    pools_by_target={}
    for t in COMMON_TARGETS:
        tk=f't{str(t).replace(".","_")}'
        n_steps=STEPS_PER_TARGET.get(tk,3)
        pools_by_target[tk]={str(s):plan_for_step(signals,s,t,ctx,clv,leagues) for s in range(1,n_steps+1)}
    best={}
    for s in range(1,11):
        for r in by_current[str(s)]:
            k=str(r.get('event_id'))+'|'+str(r.get('market'))
            best[k]=max(best.get(k,0),r.get('pyramid_ready_score',0))
    for t in COMMON_TARGETS:
        tk=f't{str(t).replace(".","_")}'
        for s in range(1,STEPS_PER_TARGET.get(tk,3)+1):
            for r in pools_by_target[tk].get(str(s),[]):
                k=str(r.get('event_id'))+'|'+str(r.get('market'))
                best[k]=max(best.get(k,0),r.get('pyramid_ready_score',0))
    for sig in signals:
        k=str(sig.get('event_id'))+'|'+str(sig.get('market'))
        if k in best:
            sig['pyramid_ready_score']=best[k]; sig['pyramid_ready']=best[k]>=72
        sig.pop('_superbet_odds', None)  # intern, nu il salvam in signals.json
    sp['_pyramid_assistant']={'updated_at':datetime.now(timezone.utc).isoformat(),'eligible':sum(1 for s in signals if s.get('pyramid_ready'))}
    save(DATA/'signals.json',sp)
    save(DATA/'pyramid_assistant.json',{
        'updated_at':datetime.now(timezone.utc).isoformat(),
        'source':'betpredict_20_pyramid_assistant',
        'objective':'selectează opțiuni cu probabilitate mare, cotă controlată, context stabil și ligă cu istoric acceptabil',
        'disclaimer': ('Compunerea (piramida) NU crește edge-ul — doar reformulează variance-ul. '
                        'Sansa de a ajunge la un pas e (win-rate real)^pas, nu o presupunere optimistă. '
                        'Vezi "historical_track_record" si "realistic_completion" din fiecare plan pentru cifrele REALE, '
                        'calculate din picioarele Superbet Edge deja decontate — nu din speranta.'),
        'historical_track_record': hist,
        'coverage': {'n_signals_total': n_total, 'n_matched_superbet_live_odds': n_matched},
        'current_step_pool':by_current,
        'pools_by_target':pools_by_target,
        'plans':plans,
    })
    print(f"[pyramid] eligible={sum(1 for s in signals if s.get('pyramid_ready'))} | "
          f"superbet_matched={n_matched}/{n_total} | leg_win_rate={hist.get('leg_win_rate_pct')}% (n={hist.get('n_legs_settled')})")
if __name__=='__main__': main()
