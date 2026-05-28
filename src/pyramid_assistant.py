#!/usr/bin/env python3
"""BETPREDICT 2.0 — Pyramid Assistant: step-ready execution plans."""
from __future__ import annotations
import json, math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
ROOT=Path(__file__).resolve().parent.parent; DATA=ROOT/'data'

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

def market_score(sig):
    direct=f(sig.get('display_score') or sig.get('market_signal_score') or sig.get('smartbet_score_v6'),None)
    if direct is not None and direct>0: return min(100,max(0,direct))
    prob=f(sig.get('adj_prob')); edge=max(0,f(sig.get('edge_pp'))); ev=f(sig.get('ev_calibrated_pct') or sig.get('ev_pct'))
    odds=f(sig.get('odds'))
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

def step_rule(step:int, avg_odds:float=1.30):
    base={1:(85,1.25,1.42),2:(83,1.25,1.48),3:(80,1.25,1.55),4:(78,1.28,1.65),5:(75,1.30,1.80)}
    p,lo,hi=base.get(min(max(step,1),5),base[5])
    # adapt to requested average odds
    shift=(avg_odds-1.30)*0.65
    return max(72,p-(step-1)*0.5), max(1.08,lo+shift), min(2.2,hi+shift)

def clv_for_signal(sig, by):
    eid=str(sig.get('event_id') or '')
    mk=str(sig.get('market') or '').lower().replace('_','')
    for k,v in by.items():
        if k.startswith(eid+'|') and mk in k.lower().replace('_',''):
            return v
    return {}

def pyramid_score(sig, step, avg_odds, ctx, clv, leagues):
    prob=f(sig.get('adj_prob')); odds=f(sig.get('odds')); edge=f(sig.get('edge_pp'))
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

def _calibration_health():
    """Mapează market → status pentru a sări peste cele CRITICAL/NO_DATA."""
    h = load(DATA/'calibration_health.json', {}).get('per_market', {})
    return {mk: rec.get('status') for mk, rec in h.items()}

def plan_for_step(signals, step, avg_odds, ctx, clv, leagues, health=None):
    rows=[]
    minp,lo,hi=step_rule(step,avg_odds)
    health = health if health is not None else _calibration_health()
    for sig in signals:
        mk = str(sig.get('market') or '')
        if health.get(mk) in ("CRITICAL", "NO_DATA"):  # market necalibrat → exclude
            continue
        ps=pyramid_score(sig,step,avg_odds,ctx,clv,leagues)
        if ps<=0: continue
        row=dict(sig); row['pyramid_ready_score']=ps; row['pyramid_step']=step; row['pyramid_rule']={'min_prob':round(minp,1),'odds_min':round(lo,2),'odds_max':round(hi,2)}
        row['execution_note']=f"Pas {step}: prob. minimă {minp:.0f}%, cotă {lo:.2f}-{hi:.2f}, scor stabilitate {ps:.0f}/100."
        row['calibration_status']=health.get(mk, 'UNKNOWN')
        rows.append(row)
    rows.sort(key=lambda r:(r.get('pyramid_ready_score',0),f(r.get('adj_prob')), -abs(f(r.get('odds'))-avg_odds)), reverse=True)
    return rows[:8]

def main():
    sp=load(DATA/'signals.json',{'signals':[]}); signals=sp.get('signals',[])
    ctx=ctx_idx(); clv=clv_idx(); leagues=heat_leagues()
    plans=[]; pools=[]
    for steps in [3,5,7]:
        avg=1.30 if steps<=5 else 1.25
        step_rows={}
        for step in range(1,steps+1):
            step_rows[str(step)]=plan_for_step(signals,step,avg,ctx,clv,leagues)
        plans.append({'name':f'Pyramid {steps} pași','steps':steps,'avg_odds':avg,'step_plans':step_rows})
    # Default pool pentru UI (avg=1.30) + pool-uri per target comun
    by_current={str(s):plan_for_step(signals,s,1.30,ctx,clv,leagues) for s in range(1,6)}
    COMMON_TARGETS=[1.20,1.30,1.50,1.70,2.00,2.50]
    pools_by_target={}
    for t in COMMON_TARGETS:
        tk=f't{str(t).replace(".","_")}'
        pools_by_target[tk]={str(s):plan_for_step(signals,s,t,ctx,clv,leagues) for s in range(1,4)}
    best={}
    for s in range(1,6):
        for r in by_current[str(s)]:
            k=str(r.get('event_id'))+'|'+str(r.get('market'))
            best[k]=max(best.get(k,0),r.get('pyramid_ready_score',0))
    for t in COMMON_TARGETS:
        tk=f't{str(t).replace(".","_")}'
        for s in range(1,4):
            for r in pools_by_target[tk].get(str(s),[]):
                k=str(r.get('event_id'))+'|'+str(r.get('market'))
                best[k]=max(best.get(k,0),r.get('pyramid_ready_score',0))
    for sig in signals:
        k=str(sig.get('event_id'))+'|'+str(sig.get('market'))
        if k in best:
            sig['pyramid_ready_score']=best[k]; sig['pyramid_ready']=best[k]>=72
    sp['_pyramid_assistant']={'updated_at':datetime.now(timezone.utc).isoformat(),'eligible':sum(1 for s in signals if s.get('pyramid_ready'))}
    save(DATA/'signals.json',sp)
    save(DATA/'pyramid_assistant.json',{'updated_at':datetime.now(timezone.utc).isoformat(),'source':'betpredict_20_pyramid_assistant','objective':'selectează opțiuni cu probabilitate mare, cotă controlată, context stabil și ligă cu istoric acceptabil','current_step_pool':by_current,'pools_by_target':pools_by_target,'plans':plans})
    print(f"[pyramid] eligible={sum(1 for s in signals if s.get('pyramid_ready'))}")
if __name__=='__main__': main()
