#!/usr/bin/env python3
"""BETPREDICT 2.0 — AI Insight generator, deterministic/no external LLM."""
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

def idx(payload):
    return {str(r.get('event_id') or r.get('id')):r for r in payload.get('results',[]) if isinstance(r,dict) and (r.get('event_id') or r.get('id'))}

def clean(s): return str(s or '').replace('_',' ').strip()

def market_phrase(sig):
    m=str(sig.get('market_label') or sig.get('market') or 'selecția').replace('G',' goluri')
    return m

def form_note(sig):
    ls=sig.get('league_strength') or {}; h=ls.get('home') or {}; a=ls.get('away') or {}
    hg=f(h.get('gf'),None); ag=f(a.get('gf'),None); hp=f(h.get('played'),0); ap=f(a.get('played'),0)
    if hp and ap and hg is not None and ag is not None:
        if 'over' in str(sig.get('market','')).lower() and (hg/hp + ag/ap)>=2.4:
            return 'ritmul ofensiv recent susține linia de goluri'
        if 'under' in str(sig.get('market','')).lower() and (hg/hp + ag/ap)<=1.9:
            return 'producția ofensivă recentă indică un ritm controlat'
    if abs(f(sig.get('league_strength_delta'))) >= 25:
        return 'diferența de forță dintre echipe este clară în datele de ligă'
    return 'modelul are acord bun între probabilitate, cotă și edge'

def context_note(eid, ctx, lineup, player, matchi, sig):
    parts=[]
    c=ctx.get(eid,{}) or {}
    summary=c.get('summary') or c.get('context_summary')
    if summary: parts.append(str(summary).strip())
    li=lineup.get(eid,{}) or {}; st=li.get('lineup_status')
    if st=='confirmed': parts.append('echipele de start sunt confirmate')
    elif st=='predicted': parts.append('lineup-ul probabil nu contrazice selecția')
    pi=player.get(eid,{}) or {}
    if f(pi.get('reliability'))>0.12: parts.append('impactul jucătorilor este inclus în scor')
    mi=matchi.get(eid,{}) or {}; al=clean(mi.get('alignment'))
    if al and 'no event' not in al and 'missing' not in al: parts.append(al)
    if not parts:
        parts.append(form_note(sig))
    return parts[:2]

def risk_note(sig, clv=None):
    if clv and clv.get('clv_reliable') and f(clv.get('clv_pct'))<0:
        return 'dar piața nu confirmă încă prețul'
    if f(sig.get('edge_pp'))<3:
        return 'cu edge moderat, deci miza trebuie păstrată disciplinat'
    if not sig.get('odds_real'):
        return 'verifică manual cota reală înainte de execuție'
    return 'iar cota oferă încă valoare față de probabilitatea estimată'

def main():
    sp=load(DATA/'signals.json',{'signals':[]}); sigs=sp.get('signals',[])
    ctx=load(DATA/'context_scores.json',{}).get('by_event',{})
    lineup=idx(load(DATA/'lineup_intelligence.json',{})); player=idx(load(DATA/'player_impact.json',{})); matchi=idx(load(DATA/'event_match_intelligence.json',{}))
    clv_by=load(DATA/'clv_tracker.json',{}).get('by_event_market',{})
    insights={}
    for sig in sigs:
        eid=str(sig.get('event_id') or '')
        key=f"{eid}|{str(sig.get('market') or '').replace('_','')}" # fallback only
        rec=None
        for k,v in clv_by.items():
            if k.startswith(eid+'|') and str(sig.get('market','')).lower().replace('_','') in k.lower().replace('_',''):
                rec=v; break
        reasons=context_note(eid,ctx,lineup,player,matchi,sig)
        sentence=f"Recomandăm {market_phrase(sig)} deoarece {', iar '.join(reasons)}; {risk_note(sig,rec)}."
        # Keep it short for mobile cards.
        if len(sentence)>210:
            sentence=sentence[:207].rstrip()+'.'
        insights[eid+'|'+str(sig.get('market'))]={'event_id':sig.get('event_id'),'market':sig.get('market'),'insight':sentence,'confidence_note':'AI Insight determinist din BSD/context/CLV'}
        sig['ai_insight']=sentence
    sp['_ai_insights']={'updated_at':datetime.now(timezone.utc).isoformat(),'count':len(insights)}
    save(DATA/'signals.json',sp)
    save(DATA/'ai_insights.json',{'updated_at':datetime.now(timezone.utc).isoformat(),'source':'betpredict_20_ai_insight_generator','count':len(insights),'by_signal':insights})
    print(f"[insights] generated={len(insights)}")
if __name__=='__main__': main()
