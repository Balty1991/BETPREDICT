"""Strategy lab: mii de strategii de bilete (loterie) testate pe football-data 2021–2026.

* Probabilitatea de selecție = piața de DESCHIDERE fără marjă (Poisson ajustat pe 1X2 + Peste/Sub 2.5) — info pre-meci.
* Prețul jucat = închiderea: 1X2 și Peste/Sub 2.5 la cota medie reală; restul liniilor derivate din piața de închidere
  cu marjă tip Superbet (overround 1.05, măsurat pe oferta Superbet: liniile 0.5–5.5 au 1.045–1.053), proporțional, min 1.01.
* Rezultatul = scorul real. Antrenare 21/22–23/24, test 24/25–26/27 (selecția strategiilor doar pe antrenare)."""

from __future__ import annotations

import itertools
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

OVERROUND = 1.05
TOP_DIVS = {"E0", "D1", "I1", "SP1", "F1", "N1", "P1", "B1", "T1", "SC0", "G1"}
MARKET_SETS = {
    "sigure_mix": ("DC1X", "DCX2", "DC12", "O05", "O15", "U35", "U45", "H", "A"),
    "goluri_peste": ("O05", "O15"),
    "goluri_sub": ("U35", "U45"),
    "sansa_dubla": ("DC1X", "DCX2", "DC12"),
    "favoriti_1x2": ("H", "A"),
    "goluri_mix": ("O05", "O15", "U35", "U45", "BTTSN"),
}
BANDS = ((1.01, 1.10), (1.03, 1.15), (1.10, 1.25), (1.15, 1.40), (1.25, 1.60), (1.40, 2.00), (1.60, 2.60))
TIERS = (50, 100, 500, 1000, 2000)
SYSTEMS = (0, 1, 2, 3)  # 0 = acumulator; k = sistem (N−k)/N
MAX_LEGS = 30
SPLIT = "2425"  # sezonul de la care începe perioada de test


def _pois_cdf(k: int, lam: np.ndarray) -> np.ndarray:
    t = np.exp(-lam)
    s = t.copy()
    for i in range(1, k + 1):
        t = t * lam / i
        s = s + t
    return s


def lambdas_from_market(pH: np.ndarray, pA: np.ndarray, pO25: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """λ total din P(Peste 2.5) (bisecție), apoi împărțirea din P(1) − P(2) (bisecție pe supremație)."""
    lo, hi = np.full_like(pO25, 0.2), np.full_like(pO25, 7.0)
    for _ in range(40):
        mid = (lo + hi) / 2
        f = 1 - _pois_cdf(2, mid) - pO25
        lo, hi = np.where(f < 0, mid, lo), np.where(f < 0, hi, mid)
    tot = (lo + hi) / 2
    g = np.arange(11)
    target = pH - pA
    slo, shi = np.full_like(tot, -0.95), np.full_like(tot, 0.95)
    for _ in range(30):
        s = (slo + shi) / 2
        lh, la = tot * (1 + s) / 2, tot * (1 - s) / 2
        ph = _pmf(lh, g); pa = _pmf(la, g)
        M = ph[:, :, None] * pa[:, None, :]
        d = np.tril(M, -1).sum((1, 2)) - np.triu(M, 1).sum((1, 2))
        slo, shi = np.where(d < target, s, slo), np.where(d < target, shi, s)
    s = (slo + shi) / 2
    return tot * (1 + s) / 2, tot * (1 - s) / 2


def _pmf(lam: np.ndarray, g: np.ndarray) -> np.ndarray:
    return np.exp(-lam[:, None]) * lam[:, None] ** g[None, :] / np.array([math.factorial(int(x)) for x in g])[None, :]


def market_probs(lh: np.ndarray, la: np.ndarray) -> Dict[str, np.ndarray]:
    g = np.arange(11)
    M = _pmf(lh, g)[:, :, None] * _pmf(la, g)[:, None, :]
    tot = g[:, None] + g[None, :]
    H, D, A = np.tril(M, -1).sum((1, 2)), np.trace(M, axis1=1, axis2=2), np.triu(M, 1).sum((1, 2))
    under = lambda k: (M * (tot <= k)).sum((1, 2))  # noqa: E731
    return {"H": H, "A": A, "DC1X": H + D, "DCX2": D + A, "DC12": H + A, "O05": 1 - under(0), "O15": 1 - under(1),
            "U35": under(3), "U45": under(4), "O25": 1 - under(2), "BTTSN": M[:, 0, :].sum(1) + M[:, :, 0].sum(1) - M[:, 0, 0]}


def won(sel: str, h: int, a: int) -> bool:
    t = h + a
    return {"H": h > a, "A": a > h, "DC1X": h >= a, "DCX2": a >= h, "DC12": h != a, "O05": t > 0, "O15": t > 1,
            "U35": t < 4, "U45": t < 5, "O25": t > 2, "BTTSN": h == 0 or a == 0}[sel]


def novig(*odds):
    inv = [1 / o for o in odds]
    s = sum(inv)
    return [x / s for x in inv]


@dataclass
class Leg:
    match: int
    sel: str
    p: float      # pre-meci (deschidere)
    odds: float   # jucat (închidere, marjă Superbet)
    win: bool
    drift: float  # cotă închidere / deschidere − 1
    top: bool


def build_legs(rows: Sequence[Dict[str, Any]]) -> List[List[Leg]]:
    """rows: dict cu div, fthg, ftag, avg_h/d/a, avg_o25/u25 (deschidere), avgc_* (închidere)."""
    def probs(prefix):
        pH = np.array([novig(r[f"{prefix}_h"], r[f"{prefix}_d"], r[f"{prefix}_a"])[0] for r in rows])
        pA = np.array([novig(r[f"{prefix}_h"], r[f"{prefix}_d"], r[f"{prefix}_a"])[2] for r in rows])
        pO = np.array([novig(r[f"{prefix}_o25"], r[f"{prefix}_u25"])[0] for r in rows])
        return market_probs(*lambdas_from_market(pH, pA, pO))
    Po, Pc = probs("avg"), probs("avgc")
    out = []
    for i, r in enumerate(rows):
        legs = []
        for sel in Po:
            if sel == "O25":
                continue
            if sel in ("H", "A"):
                odds = r["avgc_h"] if sel == "H" else r["avgc_a"]
                o_open = r["avg_h"] if sel == "H" else r["avg_a"]
            else:
                odds = max(1.01, round(1 / (Pc[sel][i] * OVERROUND), 2))
                o_open = max(1.01, round(1 / (Po[sel][i] * OVERROUND), 2))
            legs.append(Leg(i, sel, float(Po[sel][i]), float(odds), won(sel, r["fthg"], r["ftag"]), odds / o_open - 1, r["div"] in TOP_DIVS))
        out.append(legs)
    return out


def esym_payout(win_odds: List[float], k: int) -> float:
    """Σ peste toate combinațiile de k selecții câștigătoare a produsului cotelor (polinom simetric elementar)."""
    e = [1.0] + [0.0] * k
    for o in win_odds:
        for j in range(k, 0, -1):
            e[j] += e[j - 1] * o
    return e[k]


def ticket_return(legs: List[Leg], system: int) -> float:
    """Câștig pentru miză totală 1 (sistem (N−k)/N: miza împărțită egal pe C(N, N−k) combinații)."""
    n = len(legs)
    if system == 0:
        return math.prod(l.odds for l in legs) if all(l.win for l in legs) else 0.0
    k = n - system
    if k < 2:
        return 0.0
    wins = [l.odds for l in legs if l.win]
    if len(wins) < k:
        return 0.0
    return esym_payout(wins, k) / math.comb(n, k)


def pick(cands: List[Leg], target: float) -> Optional[List[Leg]]:
    out, tot = [], 1.0
    for l in cands:
        out.append(l)
        tot *= l.odds
        if tot >= target:
            return out
        if len(out) >= MAX_LEGS:
            return None
    return None


def candidates(round_legs: List[List[Leg]], mset: Tuple[str, ...], band, key: str, drift: bool, league: str) -> List[Leg]:
    lo, hi = band
    best: Dict[int, Leg] = {}
    for legs in round_legs:
        for l in legs:
            if l.sel not in mset or not (lo <= l.odds <= hi):
                continue
            if drift and l.drift > 0.03:
                continue
            if league == "top" and not l.top:
                continue
            sc = l.p if key == "p" else l.p * l.odds
            if l.match not in best or sc > (best[l.match].p if key == "p" else best[l.match].p * best[l.match].odds):
                best[l.match] = l
    return sorted(best.values(), key=(lambda l: -l.p) if key == "p" else (lambda l: -l.p * l.odds))


def metrics(rets: List[float]) -> Dict[str, Any]:
    n = len(rets)
    if not n:
        return {"n": 0}
    pnl = np.cumsum(np.array(rets) - 1)
    dd = float(np.max(np.maximum.accumulate(np.concatenate([[0], pnl])) - np.concatenate([[0], pnl])))
    streak = cur = 0
    for r in rets:
        cur = cur + 1 if r <= 0 else 0
        streak = max(streak, cur)
    roi = float(sum(rets) / n - 1)
    sd = float(np.std(rets) / math.sqrt(n)) if n > 1 else None
    return {"n": n, "hit_rate": round(sum(1 for r in rets if r > 0) / n, 4), "roi": round(roi, 4), "roi_se": round(sd, 4) if sd else None,
            "max_drawdown_u": round(dd, 2), "longest_losing_streak": streak, "profit_u": round(float(pnl[-1]), 2)}


def round_key(day: str) -> str:
    d = date.fromisoformat(day)
    y, w, wd = d.isocalendar()
    return f"{y}-W{w:02d}-{'we' if wd in (5, 6, 7, 1) else 'mw'}"


def run_lab(rows: List[Dict[str, Any]], log=print) -> Dict[str, Any]:
    rows = [r for r in rows if all(r.get(k) for k in ("avg_h", "avg_d", "avg_a", "avg_o25", "avg_u25", "avgc_h", "avgc_d", "avgc_a",
                                                         "avgc_o25", "avgc_u25")) and r.get("fthg") is not None]
    log(f"meciuri cu cote deschidere+închidere: {len(rows)}")
    legs = build_legs(rows)
    rounds: Dict[str, List[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        rounds[round_key(r["day"])].append(i)
    rkeys = sorted(rounds)
    period = {k: ("train" if rows[rounds[k][0]]["season"] < SPLIT else "test") for k in rkeys}
    res = {}
    base = list(itertools.product(MARKET_SETS, BANDS, ("p", "value"), (False, True), ("all", "top")))
    for mname, band, key, drift, league in base:
        rets = defaultdict(lambda: {"train": [], "test": []})
        legs_n = defaultdict(list)
        for k in rkeys:
            cands = candidates([legs[i] for i in rounds[k]], MARKET_SETS[mname], band, key, drift, league)
            for tier in TIERS:
                t = pick(cands, tier)
                if not t:
                    continue
                for sysk in SYSTEMS:
                    if sysk and len(t) - sysk < 2:
                        continue
                    rets[(tier, sysk)][period[k]].append(ticket_return(t, sysk))
                legs_n[tier].append(len(t))
        for (tier, sysk), v in rets.items():
            name = f"{mname}|{band[0]:.2f}-{band[1]:.2f}|{key}|{'drift' if drift else 'nodrift'}|{league}|T{tier}|{'acca' if not sysk else f'N-{sysk}'}"
            res[name] = {"market_set": mname, "band": list(band), "key": key, "drift_filter": drift, "league": league, "tier": tier,
                         "system": sysk, "avg_legs": round(float(np.mean(legs_n[tier])), 1),
                         "train": metrics(v["train"]), "test": metrics(v["test"])}
    return summarize(res, len(rows), sum(1 for k in rkeys if period[k] == "train"), sum(1 for k in rkeys if period[k] == "test"))


def summarize(res: Dict[str, Dict[str, Any]], n_matches: int, n_train_rounds: int, n_test_rounds: int, min_n: int = 30) -> Dict[str, Any]:
    ok = {k: v for k, v in res.items() if v["train"].get("n", 0) >= min_n and v["test"].get("n", 0) >= min_n}
    test_pos = sum(1 for v in ok.values() if v["test"]["roi"] > 0)
    train_pos = sum(1 for v in ok.values() if v["train"]["roi"] > 0)
    # zero-ipoteză (strategiile nu au nicio legătură între perioade): pozitive în ambele ≈ train_pos × test_pos / total
    null_both = round(train_pos * test_pos / max(1, len(ok)), 1)
    sig = sum(1 for v in ok.values() if v["train"]["roi"] > 0 and v["test"]["roi"] > 0 and v["test"].get("roi_se")
              and v["test"]["roi"] / v["test"]["roi_se"] > 2)
    both = {k: v for k, v in ok.items() if v["train"]["roi"] > 0 and v["test"]["roi"] > 0}
    top_train = sorted(ok.items(), key=lambda kv: -kv[1]["train"]["roi"])[:20]
    # robust = pozitiv în ambele perioade; ordonat după ROI minim pe cele două perioade (conservator)
    robust = sorted(both.items(), key=lambda kv: -min(kv[1]["train"]["roi"], kv[1]["test"]["roi"]))
    # „Super bilete”: pe fiecare țintă, strategia pozitivă în ambele perioade cu cel mai bun ROI minim (doar dintre cele
    # implementabile zilnic: max 20 selecții în medie). ATENȚIE: numărul lor nu depășește ce s-ar obține din întâmplare.
    super_ = []
    for t in TIERS:
        xs = [(k, v) for k, v in robust if v["tier"] == t and v["avg_legs"] <= 20]
        if xs:
            k, v = xs[0]
            super_.append({"name": k, **v})
    tiers = {}
    for t in TIERS:
        xs = [v for v in ok.values() if v["tier"] == t]
        if xs:
            tiers[str(t)] = {"configs": len(xs), "median_test_roi": round(float(np.median([v["test"]["roi"] for v in xs])), 4),
                             "share_test_positive": round(sum(1 for v in xs if v["test"]["roi"] > 0) / len(xs), 3)}
    return {"schema": "betpredict.lab.v1", "matches": n_matches, "rounds": {"train": n_train_rounds, "test": n_test_rounds},
            "split": f"antrenare 2021/22–2023/24 · test 2024/25–2026/27", "configs_tested": len(res), "configs_eligible": len(ok),
            "test_positive": test_pos, "train_positive": train_pos, "both_positive": len(both),
            "both_positive_expected_by_chance": null_both, "both_positive_significant_test_t2": sig, "overround": OVERROUND,
            "top_by_train_then_test": [{"name": k, **v} for k, v in top_train],
            "robust": [{"name": k, **v} for k, v in robust[:30]], "tiers": tiers, "super": super_}
