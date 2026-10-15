"""Tipare de tipster (Supersocial) testate în laborator, doar perioada de test raportată.

(a) Peste 0.5 R1 & Peste 0.5 R2 (combinație în același meci)   (b) goluri 1–3 total și „1–3 în fiecare repriză”
(e) R1 Peste 0.5 & final Peste 1.5   (f) interval goluri 2–4 / 2–5 (ligi: Belgia din date; Suedia/Elveția/Cehia/Serbia lipsesc)
(c) cornere total Peste 7.5 / 8.5 (Liga 1/2 Anglia și restul)     (d) GG sau Peste 2.5 / Peste 2.5 (ligi mici)
Selecție: λ din piața de DESCHIDERE; preț: λ din ÎNCHIDERE + marjă (combinații în același meci: 1.08, ca un Bet Builder;
cornere: fără cote istorice → preț = model EWMA pre-meci + marjă 1.07, deci ROI-ul la cornere măsoară doar calibrarea)."""

from __future__ import annotations

import itertools
import math
from collections import defaultdict
from typing import Any, Dict, List

import numpy as np

from betpredict.lab.engine import (Leg, lambdas_from_market, metrics, novig, round_key, SPLIT, ticket_return)

LOWER = {"E2", "E3", "EC", "SC1", "D2", "SP2", "I2", "F2", "SC0", "G1", "B1", "T1"}
OR_SINGLE, OR_COMBO, OR_CORNERS = 1.05, 1.08, 1.07
PATTERNS = {"r1r2_peste05": ("R1R2",), "goluri_1_3": ("G13", "H13x2"), "cornere": ("C75", "C85"),
            "gg_sau_o25": ("GGO25", "O25"), "r1_o15": ("R1O15",), "interval_2_4_2_5": ("G24", "G25"),
            "mix_tipster": ("R1R2", "G13", "H13x2", "C75", "C85", "GGO25", "O25", "R1O15", "G24", "G25")}
BANDS = ((1.25, 1.55), (1.40, 1.70), (1.60, 2.10), (1.25, 2.10), (1.25, 1.40))
TIERS = (50, 100, 150, 205)
LEAGUES = ("all", "lower", "E2E3")
MAX_LEGS = 17
MIN_LEGS = 4


def _pois(lam, k):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def _probs(lh: float, la: float, share: float, lc: float | None) -> Dict[str, float]:
    t = lh + la
    l1, l2 = t * share, t * (1 - share)
    p1 = [_pois(l1, k) for k in range(12)]
    p2 = [_pois(l2, k) for k in range(12)]
    pt = [_pois(t, k) for k in range(15)]
    # GG sau Peste 2.5 = 1 − P(≤2 goluri și nu ambele marchează)
    ph = [_pois(lh, k) for k in range(4)]
    pa = [_pois(la, k) for k in range(4)]
    not_gg_u25 = sum(ph[i] * pa[j] for i in range(3) for j in range(3) if i + j <= 2 and (i == 0 or j == 0))
    out = {"R1R2": (1 - p1[0]) * (1 - p2[0]), "G13": sum(pt[1:4]), "H13x2": sum(p1[1:4]) * sum(p2[1:4]),
           "GGO25": 1 - not_gg_u25, "O25": 1 - sum(pt[:3]),
           "GG": (1 - ph[0]) * (1 - pa[0]),
           # X2 & Peste 1.5 = P(oaspeți ≥ gazde) − P(0-0) − P(0-1)
           "DCX2_O15": sum(_pois(lh, i) * _pois(la, j) for i in range(12) for j in range(12) if j >= i) - ph[0] * pa[0] - ph[0] * pa[1],
           # R1 Peste 0.5 & final Peste 1.5 = 1 − P(R1=0) − P(R1≥1 și total=1)
           "R1O15": 1 - p1[0] - p1[1] * p2[0],
           # R1 Peste 0.5 & final Peste 2.5 = Σ P(R1=k) · P(R2 ≥ 3−k), k ≥ 1
           "H1O05": 1 - p1[0], "H1O15": 1 - p1[0] - p1[1], "H2G13": sum(p2[1:4]),
           "R1O25": sum(p1[k] * (1 - sum(p2[:max(0, 3 - k)])) for k in range(1, 12)), "G24": sum(pt[2:5]), "G25": sum(pt[2:6])}
    if lc:
        out["C75"] = 1 - sum(_pois(lc, k) for k in range(8))
        out["C85"] = 1 - sum(_pois(lc, k) for k in range(9))
    return out


def _won(sel, r) -> bool:
    h, a, hh, ha = r["fthg"], r["ftag"], r["hthg"], r["htag"]
    t, t1 = h + a, hh + ha
    t2 = t - t1
    return {"R1R2": t1 > 0 and t2 > 0, "G13": 1 <= t <= 3, "H13x2": 1 <= t1 <= 3 and 1 <= t2 <= 3,
            "GGO25": (h > 0 and a > 0) or t > 2, "O25": t > 2, "R1O15": t1 > 0 and t > 1, "R1O25": t1 > 0 and t > 2, "H1O05": t1 > 0, "GG": h > 0 and a > 0, "DCX2_O15": a >= h and t > 1, "H1O15": t1 > 1, "H2G13": 1 <= t2 <= 3, "G24": 2 <= t <= 4, "G25": 2 <= t <= 5,
            "C75": (r["hc"] or 0) + (r["ac"] or 0) > 7, "C85": (r["hc"] or 0) + (r["ac"] or 0) > 8}[sel]


def build(rows: List[Dict[str, Any]]):
    rows = [r for r in rows if r.get("hthg") is not None and r.get("fthg") is not None and all(
        r.get(k) for k in ("avg_h", "avg_d", "avg_a", "avg_o25", "avg_u25", "avgc_h", "avgc_d", "avgc_a", "avgc_o25", "avgc_u25"))]
    rows.sort(key=lambda r: r["day"])
    # cota de goluri din R1 învățată doar pe perioada de antrenare
    tr = [r for r in rows if r["season"] < SPLIT]
    share = sum(r["hthg"] + r["htag"] for r in tr) / max(1, sum(r["fthg"] + r["ftag"] for r in tr))

    def lam(prefix):
        pH = np.array([novig(r[f"{prefix}_h"], r[f"{prefix}_d"], r[f"{prefix}_a"])[0] for r in rows])
        pA = np.array([novig(r[f"{prefix}_h"], r[f"{prefix}_d"], r[f"{prefix}_a"])[2] for r in rows])
        pO = np.array([novig(r[f"{prefix}_o25"], r[f"{prefix}_u25"])[0] for r in rows])
        return lambdas_from_market(pH, pA, pO)
    (oh, oa), (ch, ca) = lam("avg"), lam("avgc")
    # cornere: EWMA pe echipă (pentru/contra, acasă+deplasare), doar meciuri anterioare
    ew: Dict[str, Dict[str, float]] = {}
    lg: Dict[str, float] = defaultdict(lambda: 10.0)
    A = 0.12
    legs: List[List[Leg]] = []
    for i, r in enumerate(rows):
        lc = None
        eh, ea = ew.get(r["div"] + r["home"]), ew.get(r["div"] + r["away"])
        if eh and ea and eh["n"] >= 5 and ea["n"] >= 5 and r.get("hc") is not None:
            lc = 0.5 * (eh["f"] + ea["a"]) + 0.5 * (ea["f"] + eh["a"])
            lc = 0.8 * lc + 0.2 * lg[r["div"]]
        po = _probs(float(oh[i]), float(oa[i]), share, lc)
        pc = _probs(float(ch[i]), float(ca[i]), share, lc)
        L = []
        for sel, p in po.items():
            if sel == "O25":
                odds, oo = r["avgc_o25"], r["avg_o25"]
            else:
                orr = OR_CORNERS if sel.startswith("C") else OR_COMBO if sel in ("R1R2", "H13x2", "GGO25", "R1O15") else OR_SINGLE
                odds = max(1.01, round(1 / (pc[sel] * orr), 2))
                oo = max(1.01, round(1 / (p * orr), 2))
            L.append(Leg(i, sel, p, float(odds), _won(sel, r), odds / oo - 1, r["div"] in LOWER))
        legs.append(L)
        if r.get("hc") is not None and r.get("ac") is not None:
            for team, f, a in ((r["home"], r["hc"], r["ac"]), (r["away"], r["ac"], r["hc"])):
                e = ew.setdefault(r["div"] + team, {"f": 5.0, "a": 5.0, "n": 0})
                e["f"] += A * (f - e["f"]); e["a"] += A * (a - e["a"]); e["n"] += 1
            lg[r["div"]] += 0.02 * (r["hc"] + r["ac"] - lg[r["div"]])
    return rows, legs, share


def run(rows_in: List[Dict[str, Any]], log=print) -> Dict[str, Any]:
    rows, legs, share = build(rows_in)
    log(f"meciuri {len(rows)}, cota R1 {share:.3f}")
    rounds: Dict[str, List[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        rounds[round_key(r["day"])].append(i)
    rk = sorted(rounds)
    per = {k: "train" if rows[rounds[k][0]]["season"] < SPLIT else "test" for k in rk}
    res = {}
    for pat, band, key, lgf in itertools.product(PATTERNS, BANDS, ("p", "value"), LEAGUES):
        sels = set(PATTERNS[pat])
        rets = defaultdict(lambda: {"train": [], "test": []})
        nl = defaultdict(list)
        for k in rk:
            best = {}
            for i in rounds[k]:
                r = rows[i]
                if lgf == "lower" and r["div"] not in LOWER or lgf == "E2E3" and r["div"] not in ("E2", "E3"):
                    continue
                for l in legs[i]:
                    if l.sel in sels and band[0] <= l.odds <= band[1]:
                        sc = l.p if key == "p" else l.p * l.odds
                        if i not in best or sc > best[i][0]:
                            best[i] = (sc, l)
            cands = [l for _, l in sorted(best.values(), key=lambda x: -x[0])]
            for tier in TIERS:
                t, tot = [], 1.0
                for l in cands:
                    t.append(l); tot *= l.odds
                    if tot >= tier or len(t) >= MAX_LEGS:
                        break
                if tot < tier or len(t) < MIN_LEGS:
                    continue
                for sk in (0, 1, 2):
                    rets[(tier, sk)][per[k]].append(ticket_return(t, sk))
                nl[tier].append(len(t))
        for (tier, sk), v in rets.items():
            name = f"tipster:{pat}|{band[0]:.2f}-{band[1]:.2f}|{key}|{lgf}|T{tier}|{'acca' if not sk else f'N-{sk}'}"
            res[name] = {"pattern": pat, "market_set": pat, "band": list(band), "key": key, "league": lgf, "tier": tier,
                         "system": sk, "drift_filter": False, "avg_legs": round(float(np.mean(nl[tier])), 1),
                         "train": metrics(v["train"]), "test": metrics(v["test"])}
    return res
