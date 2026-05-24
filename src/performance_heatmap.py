#!/usr/bin/env python3
"""BETPREDICT 2.0 — League/market performance heatmap."""
from __future__ import annotations
import json, math, statistics
from collections import defaultdict
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

def grade(sample,roi,wr,vol):
    if sample<5: return 'N/A'
    score=50+roi*2.2+(wr-55)*0.9-min(vol,5)*4
    if sample>=25: score+=6
    elif sample>=12: score+=3
    if score>=82: return 'A+'
    if score>=74: return 'A'
    if score>=64: return 'B'
    if score>=54: return 'C'
    return 'D'

# Numeric rank for grade so sorting puts A+ > A > B > C > D > N/A (instead of
# alphabetic which makes "N/A" outrank "A+" and pushes small-sample noise on top).
_GRADE_RANK = {'A+': 6, 'A': 5, 'B': 4, 'C': 3, 'D': 2, 'N/A': 0}
def grade_rank(g): return _GRADE_RANK.get(g, 0)

def calc(rows):
    n=len(rows); wins=sum(1 for r in rows if str(r.get('result','')).upper()=='WIN'); losses=sum(1 for r in rows if str(r.get('result','')).upper()=='LOSS')
    profits=[f(r.get('profit_units')) for r in rows]
    profit=round(sum(profits),3); roi=round(profit/n*100,2) if n else 0; wr=round(wins/(wins+losses)*100,1) if wins+losses else 0
    vol=round(statistics.pstdev(profits),3) if len(profits)>1 else 0
    return {'sample':n,'wins':wins,'losses':losses,'win_rate':wr,'profit_units':profit,'roi_pct':roi,'volatility':vol,'grade':grade(n,roi,wr,vol),'risk':'LOW' if vol<=0.65 and n>=8 else 'MEDIUM' if vol<=1.0 else 'HIGH'}

def main():
    journal=load(DATA/'selection_journal.json',{})
    rows=[r for r in journal.get('results',[]) if isinstance(r,dict) and str(r.get('status','')).lower()=='settled']
    by_league=defaultdict(list); by_market=defaultdict(list); matrix=defaultdict(list)
    for r in rows:
        lg=str(r.get('league') or r.get('league_name') or 'unknown')
        mk=str(r.get('market_canonical') or r.get('market') or 'unknown')
        by_league[lg].append(r); by_market[mk].append(r); matrix[f'{lg}|{mk}'].append(r)
    leagues={k:calc(v) for k,v in by_league.items()}
    markets={k:calc(v) for k,v in by_market.items()}
    cells=[]
    for key,v in matrix.items():
        lg,mk=key.split('|',1); c=calc(v); c.update({'league':lg,'market':mk}); cells.append(c)
    cells.sort(key=lambda x:(grade_rank(x['grade']),x['roi_pct'],x['sample']), reverse=True)
    out={'updated_at':datetime.now(timezone.utc).isoformat(),'source':'betpredict_20_performance_heatmap','summary':calc(rows),'leagues':dict(sorted(leagues.items(), key=lambda kv:(grade_rank(kv[1]['grade']),kv[1]['roi_pct'],kv[1]['sample']), reverse=True)),'markets':markets,'cells':cells[:120]}
    save(DATA/'performance_heatmap.json',out)
    print(f"[heatmap] settled={len(rows)} leagues={len(leagues)}")
if __name__=='__main__': main()
