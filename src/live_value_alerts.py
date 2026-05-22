#!/usr/bin/env python3
"""BETPREDICT 2.0 — Live/current market discrepancy alerts."""
from __future__ import annotations
import json, math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple
ROOT=Path(__file__).resolve().parent.parent; DATA=ROOT/'data'

def load(p,default):
    try: return json.load(open(p,encoding='utf-8'))
    except Exception: return default

def save(p,obj):
    p.parent.mkdir(parents=True,exist_ok=True); tmp=p.with_suffix(p.suffix+'.tmp')
    json.dump(obj,open(tmp,'w',encoding='utf-8'),ensure_ascii=False,indent=2,default=str); open(tmp,'a',encoding='utf-8').write('\n'); tmp.replace(p)

def f(v,d=None):
    try:
        if isinstance(v,str): v=v.replace('%','').replace(',','.').strip()
        x=float(v); return d if math.isnan(x) or math.isinf(x) else x
    except Exception: return d

def norm_market(m):
    s=str(m or '').lower().replace(' ','_').replace('-','_')
    return {'over15':'over_under_15','over25':'over_under_25','under35':'over_under_35','btts':'btts','homewin':'1x2','draw':'1x2','awaywin':'1x2'}.get(s,s)

def outcome(m):
    s=str(m or '').lower().replace('_','')
    if 'over15' in s: return 'OVER 1.50'
    if 'over25' in s: return 'OVER 2.50'
    if 'under35' in s: return 'UNDER 3.50'
    if 'btts' in s: return 'YES'
    if 'home' in s: return 'HOME'
    if 'draw' in s or s=='x': return 'DRAW'
    if 'away' in s: return 'AWAY'
    return ''

def movement_idx(payload):
    idx={}
    for r in payload.get('results',[]) if isinstance(payload,dict) else []:
        eid=str(r.get('event_id') or ''); mk=norm_market(r.get('market')); out=str(r.get('outcome') or '').upper()
        odds=f(r.get('decimal_odds'))
        if eid and mk and out and odds: idx[(eid,mk,out)]={'odds':odds,'bookmaker':r.get('bookmaker'),'movement':r.get('movement'),'delta':f(r.get('delta'),0),'source':'odds_movement'}
    return idx

def main():
    sp=load(DATA/'signals.json',{'signals':[]}); sigs=sp.get('signals',[])
    mi=movement_idx(load(DATA/'odds_movement.json',{}))
    alerts=[]
    for sig in sigs:
        prob=f(sig.get('adj_prob'),0)/100
        if prob<=0: continue
        fair=round(1/prob,3)
        eid=str(sig.get('event_id') or ''); mk=norm_market(sig.get('odds_market') or sig.get('market')); out=outcome(sig.get('market')).upper()
        cur=mi.get((eid,mk,out))
        if not cur:
            # Nu marcăm VALUE ACUM fără o linie curentă din odds_movement.
            # Altfel, am transforma simplul EV prematch în alertă live falsă.
            continue
        cur_odds=f(cur.get('odds'))
        if not cur_odds or cur_odds<=1: continue
        ev=round((prob*cur_odds-1)*100,2)
        discrepancy=round((cur_odds/fair-1)*100,2)
        is_value=ev>=3 and cur_odds>=fair*1.03
        if is_value or (ev>=1.5 and str(cur.get('movement'))=='DRIFTING'):
            alert={'event_id':sig.get('event_id'),'home_team':sig.get('home_team'),'away_team':sig.get('away_team'),'league':sig.get('league'),'event_date':sig.get('event_date'),'market':sig.get('market'),'market_label':sig.get('market_label'),'model_probability':round(prob*100,1),'fair_odd':fair,'current_odds':round(cur_odds,3),'bookmaker':cur.get('bookmaker') or 'market','current_ev_pct':ev,'discrepancy_pct':discrepancy,'label':'VALUE ACUM' if is_value else 'Watch value','movement':cur.get('movement')}
            alerts.append(alert)
            sig['live_value_label']=alert['label']; sig['live_value_ev_pct']=ev; sig['live_fair_odd']=fair
    alerts.sort(key=lambda x:(x['label']=='VALUE ACUM',x['current_ev_pct'],x['discrepancy_pct']), reverse=True)
    sp['_live_value_alerts']={'updated_at':datetime.now(timezone.utc).isoformat(),'count':len(alerts)}
    save(DATA/'signals.json',sp)
    save(DATA/'live_value_alerts.json',{'updated_at':datetime.now(timezone.utc).isoformat(),'source':'betpredict_20_live_value_alerts','note':'Snapshot din odds_movement; pentru push real se poate conecta Telegram/notifications peste acest fișier.','count':len(alerts),'alerts':alerts[:40]})
    print(f"[live-value] alerts={len(alerts)}")
if __name__=='__main__': main()
