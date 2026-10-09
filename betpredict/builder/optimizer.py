"""Optimizatorul de acumulatoare (folosit de constructorul de bilete și de piramidă).

  * probabilitatea unei selecții: model calibrat tras spre piața fără marjă (shrink pe piață, învățat)
    + corecția pe tipul de selecție (piață × bandă de cotă) învățată din rezultate;
  * probabilitatea biletului: Monte Carlo cu incertitudine pe probabilități (factor comun pe ligă,
    pe ora de start și pe fiecare selecție) → medie, interval, EV și varianța câștigului;
  * filtre de selecții învățate (tipuri blocate, p minim pe nivel), bonus pentru cote reale,
    penalizare pentru reutilizarea aceleiași selecții în mai multe bilete (expunere de portofoliu);
  * „Siguranță”: combină șansa și încrederea — mare doar dacă AMBELE sunt mari.

Strategia curentă (parametrii) stă în ``ingest_state['tickets.strategy']`` și e actualizată
săptămânal de ``betpredict.learn_tickets`` (cu campion/challenger pe simulare istorică)."""

from __future__ import annotations

import json
import math
import sqlite3
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

KEY = "tickets.strategy"

DEFAULT_STRATEGY: Dict[str, Any] = {
    "version": 1,
    "shrink_w": {"default": 0.5},          # ponderea modelului (logit) vs piață; restul = piața
    "leg_bias": {},                         # tip selecție → corecție logit (din rezultate)
    "blocked_leg_types": [],                # tipuri care pică sistematic → excluse din bilete
    "min_leg_p": {"50": 0.42, "100": 0.38, "500": 0.33},
    "variant_weights": {},                  # nivel → {variantă: pondere 0–1} (bandit)
    "sigma": {"leg": 0.22, "league": 0.12, "slot": 0.08},  # incertitudine (logit) pentru Monte Carlo
    "reuse_penalty": 0.30,                  # penalizare în scorul selecției / utilizare anterioară
    "max_uses_per_selection": 2,
    "real_odds_bonus": 0.04,                # preferă cotele reale (consens BSD recent)
    "updated_at": None,
}

_CACHE: Dict[str, Any] = {"strategy": None}


# ------------------------------------------------------------------ strategia
def _merge(base: Dict[str, Any], over: Dict[str, Any]) -> Dict[str, Any]:
    out = json.loads(json.dumps(base))
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out


def load_strategy(conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    raw = None
    if conn is not None:
        try:
            r = conn.execute("SELECT value FROM ingest_state WHERE key=?", (KEY,)).fetchone()
            raw = r[0] if r else None
        except sqlite3.Error:
            raw = None
    s = _merge(DEFAULT_STRATEGY, json.loads(raw) if raw else {})
    _CACHE["strategy"] = s
    return s


def save_strategy(conn: sqlite3.Connection, s: Dict[str, Any]) -> None:
    from betpredict.store import repo

    s = dict(s)
    s["updated_at"] = repo.now_iso()
    with conn:
        repo.set_state(conn, KEY, json.dumps(s, ensure_ascii=False))
    _CACHE["strategy"] = s


def strategy() -> Dict[str, Any]:
    return _CACHE["strategy"] or _merge(DEFAULT_STRATEGY, {})


def use_strategy(s: Optional[Dict[str, Any]]) -> None:
    """Setează strategia activă (simulare / teste)."""
    _CACHE["strategy"] = _merge(DEFAULT_STRATEGY, s or {})


# ------------------------------------------------------------------ selecții
def _logit(p: float) -> float:
    p = min(1 - 1e-6, max(1e-6, p))
    return math.log(p / (1 - p))


def _sig(z: float) -> float:
    return 1 / (1 + math.exp(-z))


def odds_band(odds: float) -> str:
    return "<1.40" if odds < 1.40 else ("1.40-1.80" if odds < 1.80 else ("1.80-2.40" if odds < 2.40 else "2.40+"))


def leg_type(market: str, line: float, odds: float) -> str:
    mk = market if not line else f"{market}_{line:g}"
    return f"{mk}|{odds_band(odds)}"


def market_group(market: str, line: float) -> str:
    return market if not line else f"{market}_{line:g}"


def leg_p(p_model: float, p_market: Optional[float], odds: float, market: str, line: float,
          s: Optional[Dict[str, Any]] = None) -> float:
    """Probabilitatea prudentă a unei selecții: logit-blend model/piață + corecția tipului."""
    s = s or strategy()
    pm = p_market if (p_market is not None and 0 < p_market < 1) else min(0.97, (1.0 / odds) / 1.05)
    sw = s["shrink_w"]
    w = float(sw.get(market_group(market, line), sw.get("default", 0.5)))
    z = w * _logit(p_model) + (1 - w) * _logit(pm)
    z += float(s.get("leg_bias", {}).get(leg_type(market, line, odds), 0.0))
    return min(0.995, max(0.005, _sig(z)))


def leg_ok(c, target: int, s: Optional[Dict[str, Any]] = None) -> bool:
    """Filtrul învățat pentru biletele de cotă mare."""
    s = s or strategy()
    if leg_type(c.market, c.line or 0.0, c.odds) in set(s.get("blocked_leg_types") or []):
        return False
    mp = s.get("min_leg_p", {}).get(str(target))
    return mp is None or c.p_adj >= float(mp)


def is_real_odds(c) -> bool:
    return bool(getattr(c, "odds_source", None)) and getattr(c, "odds_source", "") != "legacy"


def leg_bonus(c, s: Optional[Dict[str, Any]] = None) -> float:
    s = s or strategy()
    return float(s.get("real_odds_bonus", 0.0)) if is_real_odds(c) else 0.0


def reuse_penalty(c, sel_used: Optional[Dict[int, int]], s: Optional[Dict[str, Any]] = None) -> float:
    s = s or strategy()
    if not sel_used:
        return 0.0
    return float(s.get("reuse_penalty", 0.3)) * sel_used.get(c.prediction_id, 0)


def available(pool: Sequence, sel_used: Optional[Dict[int, int]], s: Optional[Dict[str, Any]] = None) -> List:
    s = s or strategy()
    cap = int(s.get("max_uses_per_selection", 2))
    return [c for c in pool if not sel_used or sel_used.get(c.prediction_id, 0) < cap]


def variant_order(target: int, variants: Iterable[str], s: Optional[Dict[str, Any]] = None,
                  min_weight: float = 0.08) -> List[str]:
    """Variantele în ordinea ponderilor bandit (cele cu pondere sub prag sunt sărite, dar
    cel puțin două rămân pentru explorare)."""
    s = s or strategy()
    w = (s.get("variant_weights") or {}).get(str(target)) or {}
    vs = list(variants)
    ranked = sorted(vs, key=lambda v: -float(w.get(v, 1.0 / max(1, len(vs)))))
    keep = [v for v in ranked if float(w.get(v, 1.0)) >= min_weight]
    return keep if len(keep) >= 2 else ranked[:2]


# ------------------------------------------------------------------ siguranță
def safety(p: Optional[float], confidence: Optional[float], grade: Optional[str] = None) -> Dict[str, Any]:
    """„Siguranță” 0–100 (aceeași formulă ca în aplicație, ``publish.safety``): mare doar dacă AMBELE —
    șansa și încrederea — sunt mari. Nivel: ≥ 70 „ridicată”, 55–69 „medie”, altfel „scăzută”."""
    from betpredict.publish.safety import safety_score

    sc = safety_score(p, confidence, grade)
    if sc is None:
        return {"score": None, "level": None}
    return {"score": sc, "level": "ridicată" if sc >= 70 else "medie" if sc >= 55 else "scăzută"}


# ------------------------------------------------------------------ biletul: Monte Carlo
def ticket_eval(legs: Sequence, n_sims: int = 20000, seed: int = 11, s: Optional[Dict[str, Any]] = None,
                probs: Optional[Sequence[float]] = None) -> Dict[str, float]:
    """Probabilitatea biletului sub incertitudinea probabilităților:
    logit p_i' = logit p_i + σ_leg·ε_i + σ_ligă·η_ligă + σ_slot·ζ_oră; rezultatul i ~ Bernoulli(p_i').
    Întoarce p (medie), p_naiv (produs), interval 10–90%, EV, varianța profitului la 1u."""
    s = s or strategy()
    if not legs:
        return {"p": 0.0, "p_naive": 0.0, "p_lo": 0.0, "p_hi": 0.0, "ev": -1.0, "var": 0.0, "sd": 0.0, "odds": 1.0}
    ps = np.array([float(x) for x in (probs if probs is not None else [c.p_adj for c in legs])])
    odds = float(np.prod([c.odds for c in legs]))
    sg = s.get("sigma", {})
    rng = np.random.default_rng(seed)
    z = np.log(ps / (1 - ps))[None, :].repeat(n_sims, 0)
    z += float(sg.get("leg", 0.22)) * rng.standard_normal((n_sims, len(legs)))
    for key, sig in ((lambda c: c.league_id, float(sg.get("league", 0.12))),
                     (lambda c: (c.kickoff_utc or "")[:13], float(sg.get("slot", 0.08)))):
        groups: Dict[Any, List[int]] = {}
        for i, c in enumerate(legs):
            k = key(c)
            if k is not None:
                groups.setdefault(k, []).append(i)
        for idx in groups.values():
            if len(idx) > 1 and sig > 0:
                z[:, idx] += sig * rng.standard_normal((n_sims, 1))
    pt = np.prod(1 / (1 + np.exp(-z)), axis=1)
    p = float(pt.mean())
    ev = p * odds - 1
    var = odds * odds * p * (1 - p)
    return {"p": p, "p_naive": float(np.prod(ps)), "p_lo": float(np.quantile(pt, 0.1)), "p_hi": float(np.quantile(pt, 0.9)),
            "ev": ev, "var": var, "sd": math.sqrt(var), "odds": odds}


def ticket_probability(legs: Sequence, adjusted: bool = True) -> float:
    """Compatibil cu ``pool.ticket_probability`` (folosit și de piramidă): Monte Carlo rapid."""
    if not legs:
        return 0.0
    probs = [c.p_adj if adjusted else c.p for c in legs]
    return ticket_eval(legs, n_sims=3000, probs=probs)["p"]


# ------------------------------------------------------------------ portofoliu
def portfolio_select(tickets: List[Dict[str, Any]], max_uses: Optional[int] = None,
                     max_match_stake: float = 0.6, s: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Alegere lacomă a biletelor după EV/abatere (Sharpe), respectând: aceeași selecție în cel mult
    ``max_uses`` bilete și miza totală pe un meci ≤ ``max_match_stake`` unități.
    ``tickets``: dict cu ``legs`` (Cand), ``ev``, ``sd``, ``stake``."""
    s = s or strategy()
    max_uses = int(max_uses or s.get("max_uses_per_selection", 2))
    uses: Dict[int, int] = {}
    stake_on: Dict[int, float] = {}
    out = []
    for t in sorted(tickets, key=lambda t: -(t["ev"] / max(1e-6, t["sd"]))):
        legs = t["legs"]
        if any(uses.get(c.prediction_id, 0) >= max_uses for c in legs):
            continue
        if any(stake_on.get(c.match_id, 0.0) + t.get("stake", 0.0) > max_match_stake for c in legs):
            continue
        for c in legs:
            uses[c.prediction_id] = uses.get(c.prediction_id, 0) + 1
            stake_on[c.match_id] = stake_on.get(c.match_id, 0.0) + t.get("stake", 0.0)
        out.append(t)
    return out
