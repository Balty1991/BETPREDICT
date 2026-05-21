#!/usr/bin/env python3
"""Statistical core for BetAnalytics Pro: no-vig, EV, Kelly, calibration, Poisson and ELO.

v6.0 additions (backward-compatible — toate functiile existente neatinse):
  - blend_3way()              — media ponderata a 3 surse (BSD, ML, Poisson)
  - consensus_agreement()     — masura de acord intre estimatii multiple
  - apply_calibration_state() — aplica un calibrator din calibration_engine
  - ev_calibrated()           — EV calculat pe probabilitate calibrata
  - smartbet_score_v6()       — scor v6 cu bonus consens + penalizare bias
  - quality_grade_v6()        — grad A+/A/B/C/D/E cu calibrare inclusa
"""
from __future__ import annotations
from dataclasses import dataclass, field
from math import exp, factorial, log, sqrt
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence

EPS=1e-12

# ============================================================
# v5 CORE — NEATINS (backward-compatible)
# ============================================================

def safe_float(v:Any, default:float=0.0)->float:
    try:
        if v is None or v=='': return default
        x=float(v)
        return default if x!=x else x
    except Exception:
        return default

def clamp(v:float, lo:float, hi:float)->float:
    return max(lo,min(hi,v))

def decimal_to_implied_probability(odds:Any)->Optional[float]:
    o=safe_float(odds,0.0)
    return None if o<=1.01 else 1.0/o

def normalize_no_vig(odds:Sequence[Any], min_valid:int=2)->List[Optional[float]]:
    implied=[decimal_to_implied_probability(o) for o in odds]
    valid=[p for p in implied if p is not None and p>0]
    if len(valid)<min_valid: return [None for _ in odds]
    margin=sum(valid)
    if margin<=EPS: return [None for _ in odds]
    return [None if p is None else p/margin for p in implied]

def expected_value_decimal(probability:Any, odds:Any)->Optional[float]:
    p=clamp(safe_float(probability,-1.0),0.0,1.0); o=safe_float(odds,0.0)
    if p<0 or o<=1.01: return None
    return p*(o-1.0)-(1.0-p)

def kelly_fraction(probability:Any, odds:Any, fraction:float=0.25, cap:float=0.08)->float:
    p=clamp(safe_float(probability,0.0),0.0,1.0); o=safe_float(odds,0.0)
    if p<=0 or o<=1.01: return 0.0
    b=o-1.0; raw=(p*b-(1.0-p))/b
    return round(clamp(raw*safe_float(fraction,0.25),0.0,cap),6)

def brier_binary(y_true:Sequence[Any], y_prob:Sequence[Any])->Optional[float]:
    pairs=[(safe_float(y),clamp(safe_float(p),0.0,1.0)) for y,p in zip(y_true,y_prob)]
    return None if not pairs else sum((p-y)**2 for y,p in pairs)/len(pairs)

def log_loss_binary(y_true:Sequence[Any], y_prob:Sequence[Any])->Optional[float]:
    pairs=[(safe_float(y),clamp(safe_float(p),EPS,1.0-EPS)) for y,p in zip(y_true,y_prob)]
    return None if not pairs else -sum(y*log(p)+(1-y)*log(1-p) for y,p in pairs)/len(pairs)

def calibration_bins(y_true:Sequence[Any], y_prob:Sequence[Any], bins:int=10)->List[Dict[str,float]]:
    pairs=[(safe_float(y),clamp(safe_float(p),0.0,1.0)) for y,p in zip(y_true,y_prob)]
    out=[]; bins=max(2,int(bins))
    if not pairs: return out
    for i in range(bins):
        lo=i/bins; hi=(i+1)/bins
        bucket=[(y,p) for y,p in pairs if p>=lo and (p<hi or i==bins-1)]
        if not bucket:
            out.append({'bin':i+1,'lo':round(lo,4),'hi':round(hi,4),'n':0,'predicted':0.0,'actual':0.0,'gap':0.0}); continue
        pred=sum(p for _,p in bucket)/len(bucket); actual=sum(y for y,_ in bucket)/len(bucket)
        out.append({'bin':i+1,'lo':round(lo,4),'hi':round(hi,4),'n':len(bucket),'predicted':round(pred,6),'actual':round(actual,6),'gap':round(pred-actual,6)})
    return out

def expected_calibration_error(y_true:Sequence[Any], y_prob:Sequence[Any], bins:int=10, min_bin_size:int=1)->Optional[float]:
    pairs=list(zip(y_true,y_prob))
    if not pairs: return None
    total=len(pairs); ece=0.0
    for row in calibration_bins(y_true,y_prob,bins):
        n=int(row.get('n',0))
        if n>=min_bin_size: ece+=abs(row['gap'])*n/total
    return ece

def poisson_pmf(lam:Any, goals:int)->float:
    lam=clamp(safe_float(lam,0.0),0.0,10.0); goals=max(0,int(goals))
    return exp(-lam)*(lam**goals)/factorial(goals)

def dixon_coles_tau(h:int,a:int,lh:float,la:float,rho:float=-0.08)->float:
    lh=clamp(lh,0.05,10.0); la=clamp(la,0.05,10.0); r=clamp(rho,-0.30,0.30)
    if h==0 and a==0: return max(0.01,1-lh*la*r)
    if h==0 and a==1: return max(0.01,1+lh*r)
    if h==1 and a==0: return max(0.01,1+la*r)
    if h==1 and a==1: return max(0.01,1-r)
    return 1.0

def football_score_matrix(lambda_home:Any, lambda_away:Any, max_goals:int=8, rho:Optional[float]=-0.08)->List[List[float]]:
    lh=clamp(safe_float(lambda_home,1.35),0.05,6.0); la=clamp(safe_float(lambda_away,1.05),0.05,6.0); max_goals=max(3,int(max_goals))
    matrix=[]; total=0.0
    for h in range(max_goals+1):
        row=[]
        for a in range(max_goals+1):
            p=poisson_pmf(lh,h)*poisson_pmf(la,a)
            if rho is not None: p*=dixon_coles_tau(h,a,lh,la,rho)
            row.append(p); total+=p
        matrix.append(row)
    if total>EPS: matrix=[[p/total for p in row] for row in matrix]
    return matrix

def poisson_market_probabilities(lambda_home:Any, lambda_away:Any, max_goals:int=8, rho:Optional[float]=-0.08)->Dict[str,Any]:
    m=football_score_matrix(lambda_home,lambda_away,max_goals,rho); home=draw=away=btts=o15=o25=o35=0.0; best=('0-0',-1.0); scores=[]
    for h,row in enumerate(m):
        for a,p in enumerate(row):
            if h>a: home+=p
            elif h==a: draw+=p
            else: away+=p
            if h>0 and a>0: btts+=p
            if h+a>1.5: o15+=p
            if h+a>2.5: o25+=p
            if h+a>3.5: o35+=p
            if p>best[1]: best=(f'{h}-{a}',p)
            scores.append({'score':f'{h}-{a}','prob':p})
    scores.sort(key=lambda x:x['prob'], reverse=True)
    return {'home_win':round(home,6),'draw':round(draw,6),'away_win':round(away,6),'over15':round(o15,6),'under15':round(1-o15,6),'over25':round(o25,6),'under25':round(1-o25,6),'over35':round(o35,6),'under35':round(1-o35,6),'btts':round(btts,6),'no_btts':round(1-btts,6),'most_likely_score':best[0],'most_likely_score_prob':round(best[1],6),'top_correct_scores':[{'score':x['score'],'prob':round(x['prob'],6)} for x in scores[:8]]}

@dataclass
class EloConfig:
    start_rating:float=1500.0; k_factor:float=26.0; home_advantage:float=55.0; draw_value:float=0.5; goal_diff_multiplier:bool=True

@dataclass
class EloRatings:
    config:EloConfig=field(default_factory=EloConfig); ratings:MutableMapping[str,float]=field(default_factory=dict)
    def rating(self,team_id:Any)->float:
        k=str(team_id)
        if k not in self.ratings: self.ratings[k]=float(self.config.start_rating)
        return self.ratings[k]
    def expected_home(self,home_id:Any,away_id:Any)->float:
        return 1.0/(1.0+10**((self.rating(away_id)-(self.rating(home_id)+self.config.home_advantage))/400.0))
    def update(self,home_id:Any,away_id:Any,home_goals:Any,away_goals:Any)->Dict[str,float]:
        hp=self.rating(home_id); ap=self.rating(away_id); hg=safe_float(home_goals); ag=safe_float(away_goals); exp_home=self.expected_home(home_id,away_id)
        actual=1.0 if hg>ag else (0.0 if hg<ag else self.config.draw_value); gd=abs(hg-ag); mult=1.0+(max(0.0,gd-1.0)*0.35 if self.config.goal_diff_multiplier else 0.0); mult=min(2.2,mult)
        delta=self.config.k_factor*mult*(actual-exp_home); self.ratings[str(home_id)]=hp+delta; self.ratings[str(away_id)]=ap-delta
        return {'home_pre':round(hp,4),'away_pre':round(ap,4),'expected_home':round(exp_home,6),'delta_home':round(delta,4),'home_post':round(hp+delta,4),'away_post':round(ap-delta,4)}

def blend_probabilities(probabilities:Mapping[str,Any], weights:Mapping[str,Any], default:Optional[float]=None)->Optional[float]:
    num=den=0.0
    for k,v in probabilities.items():
        p=safe_float(v,-1.0); w=max(0.0,safe_float(weights.get(k),0.0))
        if 0<=p<=1 and w>0: num+=p*w; den+=w
    return default if den<=EPS else clamp(num/den,0.0,1.0)

def quality_grade(score:Any)->str:
    s=safe_float(score,0.0)
    return 'A' if s>=85 else ('B' if s>=72 else ('C' if s>=60 else ('D' if s>=45 else 'E')))


# ============================================================
# v6.0 ADDITIONS — functii noi (backward-compatible)
# ============================================================

def blend_3way(
    bsd: Any,
    ml: Any,
    poisson: Any = None,
    w_bsd: float = 0.40,
    w_ml: float = 0.40,
    w_poisson: float = 0.20,
) -> Optional[float]:
    """
    Media ponderata a 3 surse de predictie: BSD API, ML Ensemble, Poisson standalone.

    Daca o sursa lipseste (None sau <0), greutatea ei se redistribuie proportional
    catre celelalte surse active.

    Greutati implicite v6.0:
    - BSD API:   40% (sursa principala, date reale din market)
    - ML Ensemble: 40% (invatat din rezultate istorice)
    - Poisson standalone: 20% (model teoretic ca ancora)

    Args:
        bsd: probabilitate BSD (float 0-1 sau None)
        ml: probabilitate ML ensemble (float 0-1 sau None)
        poisson: probabilitate Poisson standalone (float 0-1 sau None)
        w_bsd, w_ml, w_poisson: greutati; suma nu trebuie sa fie 1 (normalizate intern)

    Returns:
        probabilitate blended 0.01-0.99 sau None daca nicio sursa valida
    """
    sources = {}
    raw_weights = {}

    p_bsd = safe_float(bsd, -1.0)
    if 0.0 <= p_bsd <= 1.0:
        sources['bsd'] = p_bsd
        raw_weights['bsd'] = max(0.0, float(w_bsd))

    p_ml = safe_float(ml, -1.0)
    if 0.0 <= p_ml <= 1.0:
        sources['ml'] = p_ml
        raw_weights['ml'] = max(0.0, float(w_ml))

    p_poi = safe_float(poisson, -1.0)
    if 0.0 <= p_poi <= 1.0:
        sources['poisson'] = p_poi
        raw_weights['poisson'] = max(0.0, float(w_poisson))

    if not sources:
        return None

    total_w = sum(raw_weights.values())
    if total_w <= EPS:
        # Fallback: media simpla
        return clamp(sum(sources.values()) / len(sources), 0.01, 0.99)

    blended = sum(sources[k] * raw_weights[k] for k in sources) / total_w
    return round(clamp(blended, 0.01, 0.99), 4)


def consensus_agreement(probs: Sequence[Any]) -> float:
    """
    Masura de acord intre estimatii multiple (surse diverse).

    Formula: agreement = max(0, 1 - 2 * std(probs))
    - Cand toate sursele sunt identice: agreement = 1.0
    - Cand sursele difera cu ±25pp: agreement ≈ 0.0
    - Cand o sursa spune 90% si alta spune 40%: agreement ≈ 0.0

    Args:
        probs: lista de probabilitati float (0-1). Valorile invalide (<0) ignorate.

    Returns:
        float 0.0-1.0 (1.0 = consens perfect)
    """
    valid = [clamp(safe_float(p, -1.0), 0.0, 1.0)
             for p in probs if safe_float(p, -1.0) >= 0.0]
    n = len(valid)
    if n < 2:
        return 1.0
    mean = sum(valid) / n
    variance = sum((p - mean) ** 2 for p in valid) / n
    std = sqrt(variance)
    return round(max(0.0, 1.0 - 2.0 * std), 4)


def apply_calibration_state(prob: Any, state: Optional[Dict[str, Any]]) -> float:
    """
    Aplica un calibrator state (din calibration_engine.py) pe o probabilitate.

    State dict format (din calibration_engine.fit_calibrator_state):
      {"type": "isotonic", "iso": <IsotonicRegression>}
      {"type": "shift", "shift": -0.15}
      {"type": "identity"}

    Args:
        prob: probabilitate raw (float sau Any parsabil)
        state: dict de calibrator. Daca None -> identity.

    Returns:
        float 0.01-0.99 calibrat
    """
    p = clamp(safe_float(prob, 0.5), 0.01, 0.99)
    if not state:
        return p
    t = state.get('type', 'identity')
    if t == 'identity':
        return p
    if t == 'shift':
        shift = safe_float(state.get('shift', 0.0))
        return clamp(p + shift, 0.01, 0.99)
    if t == 'isotonic':
        iso = state.get('iso')
        if iso is None:
            return p
        try:
            out = iso.predict([p])
            return clamp(float(out[0]), 0.01, 0.99)
        except Exception:
            return p
    return p


def ev_calibrated(
    raw_prob: Any,
    odds: Any,
    calibration_state: Optional[Dict[str, Any]] = None,
) -> Optional[float]:
    """
    Expected Value calculat pe probabilitate CALIBRATA.

    Diferenta vs expected_value_decimal():
    - Aplica automat calibration_state inainte de a calcula EV.
    - EV cu probabilitate calibrata este mai corect decat EV raw.

    Args:
        raw_prob: probabilitate raw a modelului (0-1)
        odds: cota bookmaker (>1.0)
        calibration_state: dict din calibration_engine (optional)

    Returns:
        float EV sau None daca date invalide
    """
    p = apply_calibration_state(raw_prob, calibration_state)
    o = safe_float(odds, 0.0)
    if o <= 1.01:
        return None
    return round(p * (o - 1.0) - (1.0 - p), 4)


def smartbet_score_v6(
    bsd_prob: Any,
    ml_prob: Any = None,
    poisson_prob: Any = None,
    calibration_state: Optional[Dict[str, Any]] = None,
    consensus_ag: float = 1.0,
    league_strength_delta: float = 0.0,
) -> float:
    """
    SmartBet Score v6.0 — formula actualizata cu ML + calibrare + consens.

    Compozitie:
    - Probabilitate blended (BSD+ML+Poisson):      50% din scor
    - Consens agreement:                           25% din scor
    - Bonus league strength:                        10% din scor
    - Penalty calibrare (daca modelul are bias):   -15% maxim

    Returns:
        float 0.0-100.0
    """
    # 1. Probabilitate blended calibrata
    p_blended = blend_3way(bsd_prob, ml_prob, poisson_prob) or safe_float(bsd_prob, 0.5)
    p_calibrated = apply_calibration_state(p_blended, calibration_state)

    # 2. Scor de baza din probabilitate (0-100)
    # Escale: 50% prob = 0 scor; 85% prob = 100 scor
    prob_score = clamp((p_calibrated - 0.50) / 0.35 * 100, 0.0, 100.0)

    # 3. Bonus consens (0-15 puncte)
    ag = clamp(safe_float(consensus_ag, 1.0), 0.0, 1.0)
    consensus_bonus = ag * 15.0

    # 4. Bonus league strength (0-8 puncte)
    delta = abs(safe_float(league_strength_delta, 0.0))
    ls_bonus = clamp((delta - 8.0) / 35.0 * 8.0, 0.0, 8.0)

    # 5. Penalty calibrare: daca p_calibrated << p_blended -> penalizare
    cal_diff = p_blended - p_calibrated
    cal_penalty = clamp(cal_diff * 50.0, 0.0, 20.0)  # max -20 puncte

    raw = prob_score * 0.77 + consensus_bonus + ls_bonus - cal_penalty
    return round(clamp(raw, 0.0, 100.0), 1)


def quality_grade_v6(smartbet_v6: Any, consensus: float = 1.0) -> str:
    """
    Grad calitate v6 cu A+ pentru semnale exceptionale.

    Grade:
    - A+: smartbet>=88 AND consensus>=0.80
    - A:  smartbet>=80
    - B:  smartbet>=65
    - C:  smartbet>=50
    - D:  smartbet>=35
    - E:  sub 35

    Args:
        smartbet_v6: scor SmartBet v6 (0-100)
        consensus: agreement score din consensus_agreement() (0-1)
    """
    s = safe_float(smartbet_v6, 0.0)
    ag = clamp(safe_float(consensus, 1.0), 0.0, 1.0)
    if s >= 88 and ag >= 0.80:
        return 'A+'
    if s >= 80:
        return 'A'
    if s >= 65:
        return 'B'
    if s >= 50:
        return 'C'
    if s >= 35:
        return 'D'
    return 'E'
