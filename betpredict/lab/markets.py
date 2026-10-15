"""Laboratorul de piețe: piețele Superbet care se decid din scor, scorul la pauză și cornere, testate pe istoric.

Pe fiecare meci din football-data (``fd_match``):
* λ gazde/oaspeți din piața de DESCHIDERE (1X2 + Peste/Sub 2.5, fără marjă) → șansa de selecție (info pre-meci);
* λ din ÎNCHIDERE → prețul jucat: 1X2 și Peste/Sub 2.5 la cota medie reală, restul = 1 / (șansă × marjă Superbet)
  (simple 1.05, combinații 1.08, cornere 1.07). Cornere: medie EWMA pe echipă, doar din meciurile anterioare;
* împărțirea golurilor pe reprize învățată doar pe perioada de antrenare.

Ce măsoară, cinstit: la piețele fără cote istorice, „ROI” arată unde modelul simplu (Poisson) greșește sistematic față de
realitate. Dacă o piață intră mai des decât spune modelul și în antrenare, și în test, e o candidată; verdictul îl dă
urmărirea zilnică la cotele Superbet reale (Stil Supersocial, ``ss_track``), nu acest test.

``python -m betpredict.lab.markets <fd.db> [out.json]``"""

from __future__ import annotations

import json
import math
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from betpredict.lab.engine import SPLIT, lambdas_from_market, metrics, novig, round_key

G = np.arange(11)
LOWER = {"E1", "E2", "E3", "EC", "SC1", "SC2", "SC3", "D2", "SP2", "I2", "F2", "SC0", "G1", "B1", "T1", "P1", "N1"}
OR_SINGLE, OR_COMBO, OR_CORNERS = 1.05, 1.08, 1.07
PLAYABLE = (1.12, 5.00)
BANDS = ((1.12, 1.30), (1.20, 1.45), (1.35, 1.70), (1.55, 2.10))
TIERS = (10, 50, 100, 500, 1000, 5000)
MAX_LEGS = 40
MIN_N = 30

# cheie → (etichetă Superbet, familie, marjă). Familia „real” = cotă istorică reală.
MARKETS: Dict[str, Tuple[str, str, float]] = {
    "H": ("Final 1", "real", 0), "A": ("Final 2", "real", 0), "O25": ("Total goluri Peste 2.5", "real", 0),
    "U25": ("Total goluri Sub 2.5", "real", 0),
    "O05": ("Total goluri Peste 0.5", "goluri", OR_SINGLE), "O15": ("Total goluri Peste 1.5", "goluri", OR_SINGLE),
    "O35": ("Total goluri Peste 3.5", "goluri", OR_SINGLE), "U35": ("Total goluri Sub 3.5", "goluri", OR_SINGLE),
    "U45": ("Total goluri Sub 4.5", "goluri", OR_SINGLE),
    "G13": ("Interval goluri 1-3", "goluri", OR_SINGLE), "G23": ("Interval goluri 2-3", "goluri", OR_SINGLE),
    "G24": ("Interval goluri 2-4", "goluri", OR_SINGLE), "G25": ("Interval goluri 2-5", "goluri", OR_SINGLE),
    "GG": ("Ambele echipe marchează Da", "goluri", OR_SINGLE), "NG": ("Ambele echipe marchează Nu", "goluri", OR_SINGLE),
    "DC1X": ("Șansă dublă 1X", "goluri", OR_SINGLE), "DCX2": ("Șansă dublă X2", "goluri", OR_SINGLE),
    "DC12": ("Șansă dublă 12", "goluri", OR_SINGLE),
    "HO05": ("Total goluri gazde Peste 0.5", "echipe", OR_SINGLE), "HO15": ("Total goluri gazde Peste 1.5", "echipe", OR_SINGLE),
    "AO05": ("Total goluri oaspeți Peste 0.5", "echipe", OR_SINGLE), "AO15": ("Total goluri oaspeți Peste 1.5", "echipe", OR_SINGLE),
    "HU15": ("Total goluri gazde Sub 1.5", "echipe", OR_SINGLE), "AU15": ("Total goluri oaspeți Sub 1.5", "echipe", OR_SINGLE),
    "HSBH": ("Gazdele marchează în ambele reprize", "echipe", OR_COMBO),
    "HWEH": ("Gazdele câștigă oricare repriză", "echipe", OR_SINGLE), "AWEH": ("Oaspeții câștigă oricare repriză", "echipe", OR_SINGLE),
    "H1O05": ("Prima repriză Peste 0.5", "reprize", OR_SINGLE), "H1O15": ("Prima repriză Peste 1.5", "reprize", OR_SINGLE),
    "H1U15": ("Prima repriză Sub 1.5", "reprize", OR_SINGLE), "H2O05": ("A doua repriză Peste 0.5", "reprize", OR_SINGLE),
    "H2O15": ("A doua repriză Peste 1.5", "reprize", OR_SINGLE), "H2G13": ("A doua repriză 1-3 goluri", "reprize", OR_SINGLE),
    "H2MORE": ("Repriza cu mai multe goluri: a doua", "reprize", OR_SINGLE),
    "R1R2": ("Gol în ambele reprize", "reprize", OR_COMBO), "H13x2": ("1-3 goluri în fiecare repriză", "reprize", OR_COMBO),
    "R1O15": ("R1 Peste 0.5 & meci Peste 1.5", "combo", OR_COMBO), "R1O25": ("R1 Peste 0.5 & meci Peste 2.5", "combo", OR_COMBO),
    "GGO25": ("GG sau Peste 2.5", "combo", OR_COMBO), "DC1X_O15": ("1X & Peste 1.5", "combo", OR_COMBO),
    "DCX2_O15": ("X2 & Peste 1.5", "combo", OR_COMBO), "H_O15": ("1 & Peste 1.5", "combo", OR_COMBO),
    "C65": ("Total cornere Peste 6.5", "cornere", OR_CORNERS), "C75": ("Total cornere Peste 7.5", "cornere", OR_CORNERS),
    "C85": ("Total cornere Peste 8.5", "cornere", OR_CORNERS), "C95": ("Total cornere Peste 9.5", "cornere", OR_CORNERS),
    "C105": ("Total cornere Peste 10.5", "cornere", OR_CORNERS),
    "CU105": ("Total cornere Sub 10.5", "cornere", OR_CORNERS), "CU115": ("Total cornere Sub 11.5", "cornere", OR_CORNERS),
    "CU125": ("Total cornere Sub 12.5", "cornere", OR_CORNERS), "CU135": ("Total cornere Sub 13.5", "cornere", OR_CORNERS),
    "BB_C65_U145": ("Cornere 7-14 (Peste 6.5 & Sub 14.5)", "cornere", OR_COMBO),
    "HC35": ("Cornere gazde Peste 3.5", "cornere", OR_CORNERS), "HC45": ("Cornere gazde Peste 4.5", "cornere", OR_CORNERS),
    "AC25": ("Cornere oaspeți Peste 2.5", "cornere", OR_CORNERS), "AC35": ("Cornere oaspeți Peste 3.5", "cornere", OR_CORNERS),
    # runda 2: rezultat pe reprize, pauză/final, handicap, echipe pe reprize, cartonașe (galbene)
    "H1H": ("Prima repriză: 1", "reprize_1x2", 1.07), "H1D": ("Prima repriză: X", "reprize_1x2", 1.07),
    "H1A": ("Prima repriză: 2", "reprize_1x2", 1.07), "H2H": ("A doua repriză: 1", "reprize_1x2", 1.07),
    "H2D": ("A doua repriză: X", "reprize_1x2", 1.07), "H2A": ("A doua repriză: 2", "reprize_1x2", 1.07),
    "HTFT_11": ("Pauză/Final 1/1", "pauza_final", 1.15), "HTFT_X1": ("Pauză/Final X/1", "pauza_final", 1.15),
    "HTFT_XX": ("Pauză/Final X/X", "pauza_final", 1.15), "HTFT_X2": ("Pauză/Final X/2", "pauza_final", 1.15),
    "HTFT_22": ("Pauză/Final 2/2", "pauza_final", 1.15),
    "HCP_H15": ("Handicap gazde −1.5 (câștigă la 2+)", "handicap", OR_SINGLE),
    "HCP_A15P": ("Handicap oaspeți +1.5", "handicap", OR_SINGLE),
    "HCP_A15": ("Handicap oaspeți −1.5 (câștigă la 2+)", "handicap", OR_SINGLE),
    "HCP_H15P": ("Handicap gazde +1.5", "handicap", OR_SINGLE),
    "HH1": ("Gazdele marchează în prima repriză", "echipe_reprize", 1.06), "AH1": ("Oaspeții marchează în prima repriză", "echipe_reprize", 1.06),
    "HH2": ("Gazdele marchează în a doua repriză", "echipe_reprize", 1.06), "AH2": ("Oaspeții marchează în a doua repriză", "echipe_reprize", 1.06),
    "HG13": ("Multigoluri gazde 1-3", "echipe_reprize", 1.06), "AG12": ("Multigoluri oaspeți 1-2", "echipe_reprize", 1.06),
    "HWTN": ("Gazdele câștigă fără gol primit", "echipe_reprize", 1.06), "AWTN": ("Oaspeții câștigă fără gol primit", "echipe_reprize", 1.06),
    "HCS": ("Gazdele nu primesc gol", "echipe_reprize", 1.06), "ACS": ("Oaspeții nu primesc gol", "echipe_reprize", 1.06),
    "YC35": ("Cartonașe galbene Peste 3.5", "cartonase", 1.08), "YC45": ("Cartonașe galbene Peste 4.5", "cartonase", 1.08),
    "YC55": ("Cartonașe galbene Peste 5.5", "cartonase", 1.08), "YCU35": ("Cartonașe galbene Sub 3.5", "cartonase", 1.08),
    "YCU45": ("Cartonașe galbene Sub 4.5", "cartonase", 1.08), "YCU55": ("Cartonașe galbene Sub 5.5", "cartonase", 1.08),
    "HY15": ("Cartonașe gazde Peste 1.5", "cartonase", 1.08), "AY15": ("Cartonașe oaspeți Peste 1.5", "cartonase", 1.08),
    "AY25": ("Cartonașe oaspeți Peste 2.5", "cartonase", 1.08),
    "BOTH15": ("Fiecare echipă peste 1.5 cartonașe", "cartonase", 1.08),
}
FAMILY_SETS = {
    "reprize": ("H1O05", "H2O05", "R1R2", "H2G13", "H13x2", "H2MORE"),
    "combo": ("R1O15", "R1O25", "GGO25", "DC1X_O15", "DCX2_O15", "H_O15"),
    "goluri_sigure": ("O05", "O15", "U45", "DC1X", "DCX2", "DC12", "HO05", "AO05"),
    "intervale": ("G13", "G23", "G24", "G25"),
    "cornere_peste": ("C65", "C75", "C85", "C95"),
    "cornere_sub": ("CU105", "CU115", "CU125", "CU135", "BB_C65_U145"),
    "cornere_echipe": ("HC35", "HC45", "AC25", "AC35"),
    "reprize_1x2": ("H1H", "H1D", "H1A", "H2H", "H2D", "H2A"),
    "pauza_final": ("HTFT_11", "HTFT_22", "HTFT_XX", "HTFT_X1", "HTFT_X2"),
    "handicap": ("HCP_H15", "HCP_A15P", "HCP_A15", "HCP_H15P"),
    "echipe_reprize": ("HH1", "AH1", "HH2", "AH2", "HG13", "AG12", "HWTN", "AWTN", "HCS", "ACS"),
    "cartonase_peste": ("YC35", "YC45", "YC55", "HY15", "AY15", "AY25", "BOTH15"),
    "cartonase_sub": ("YCU35", "YCU45", "YCU55"),
}


def _pmf(lam: np.ndarray) -> np.ndarray:
    return np.exp(-lam[:, None]) * lam[:, None] ** G[None, :] / np.array([math.factorial(int(x)) for x in G])[None, :]


def _grid(lh: np.ndarray, la: np.ndarray) -> np.ndarray:
    return _pmf(lh)[:, :, None] * _pmf(la)[:, None, :]


def _diff(M: np.ndarray) -> np.ndarray:
    """Distribuția diferenței gazde − oaspeți (index 10 = egal) dintr-o grilă de scoruri."""
    D = np.zeros((M.shape[0], 21))
    for i in G:
        for j in G:
            D[:, i - j + 10] += M[:, i, j]
    return D


def _poisson_tail(lam: np.ndarray, k: int) -> np.ndarray:
    """P(X > k) pentru X ~ Poisson(lam)."""
    K = np.arange(k + 1)
    return 1 - (np.exp(-lam[:, None]) * lam[:, None] ** K[None, :] / np.array([math.factorial(int(x)) for x in K])[None, :]).sum(1)


def probs(lh: np.ndarray, la: np.ndarray, share: float, lc: Optional[np.ndarray] = None,
          lch: Optional[np.ndarray] = None, lca: Optional[np.ndarray] = None,
          lyh: Optional[np.ndarray] = None, lya: Optional[np.ndarray] = None) -> Dict[str, np.ndarray]:
    """Șansele tuturor piețelor (Poisson independent pe echipe și reprize). ``lc`` = media cornerelor totale."""
    tot = G[:, None] + G[None, :]
    M = _grid(lh, la)
    M1, M2 = _grid(lh * share, la * share), _grid(lh * (1 - share), la * (1 - share))
    pt, p1, p2 = _pmf(lh + la), _pmf((lh + la) * share), _pmf((lh + la) * (1 - share))
    ph, pa = _pmf(lh), _pmf(la)
    cdf2 = np.cumsum(p2, axis=1)
    H, D, A = np.tril(M, -1).sum((1, 2)), np.trace(M, axis1=1, axis2=2), np.triu(M, 1).sum((1, 2))
    home_ge, away_ge = (G[:, None] >= G[None, :]), (G[None, :] >= G[:, None])
    win1h, win2h = np.tril(M1, -1).sum((1, 2)), np.tril(M2, -1).sum((1, 2))
    win1a, win2a = np.triu(M1, 1).sum((1, 2)), np.triu(M2, 1).sum((1, 2))
    gg = 1 - ph[:, 0] - pa[:, 0] + ph[:, 0] * pa[:, 0]
    out = {
        "H": H, "A": A, "O25": 1 - pt[:, :3].sum(1), "U25": pt[:, :3].sum(1),
        "O05": 1 - pt[:, 0], "O15": 1 - pt[:, :2].sum(1), "O35": 1 - pt[:, :4].sum(1), "U35": pt[:, :4].sum(1), "U45": pt[:, :5].sum(1),
        "G13": pt[:, 1:4].sum(1), "G23": pt[:, 2:4].sum(1), "G24": pt[:, 2:5].sum(1), "G25": pt[:, 2:6].sum(1),
        "GG": gg, "NG": 1 - gg, "DC1X": H + D, "DCX2": D + A, "DC12": H + A,
        "HO05": 1 - ph[:, 0], "HO15": 1 - ph[:, :2].sum(1), "AO05": 1 - pa[:, 0], "AO15": 1 - pa[:, :2].sum(1),
        "HU15": ph[:, :2].sum(1), "AU15": pa[:, :2].sum(1),
        "HSBH": (1 - np.exp(-lh * share)) * (1 - np.exp(-lh * (1 - share))),
        "HWEH": 1 - (1 - win1h) * (1 - win2h), "AWEH": 1 - (1 - win1a) * (1 - win2a),
        "H1O05": 1 - p1[:, 0], "H1O15": 1 - p1[:, :2].sum(1), "H1U15": p1[:, :2].sum(1),
        "H2O05": 1 - p2[:, 0], "H2O15": 1 - p2[:, :2].sum(1), "H2G13": p2[:, 1:4].sum(1),
        "H2MORE": (p1[:, :, None] * p2[:, None, :] * (G[None, :] > G[:, None])[None]).sum((1, 2)),
        "R1R2": (1 - p1[:, 0]) * (1 - p2[:, 0]), "H13x2": p1[:, 1:4].sum(1) * p2[:, 1:4].sum(1),
        "R1O15": 1 - p1[:, 0] - p1[:, 1] * p2[:, 0],
        "R1O25": sum(p1[:, k] * (1 - (cdf2[:, 2 - k] if k <= 2 else 0)) for k in range(1, 11)),
        "GGO25": 1 - (M * ((tot <= 2) & ((G[:, None] == 0) | (G[None, :] == 0)))[None]).sum((1, 2)),
        "DC1X_O15": (M * (home_ge & (tot >= 2))[None]).sum((1, 2)), "DCX2_O15": (M * (away_ge & (tot >= 2))[None]).sum((1, 2)),
        "H_O15": (M * ((G[:, None] > G[None, :]) & (tot >= 2))[None]).sum((1, 2)),
        "H1H": win1h, "H1D": np.trace(M1, axis1=1, axis2=2), "H1A": win1a,
        "H2H": win2h, "H2D": np.trace(M2, axis1=1, axis2=2), "H2A": win2a,
        "HH1": 1 - np.exp(-lh * share), "AH1": 1 - np.exp(-la * share),
        "HH2": 1 - np.exp(-lh * (1 - share)), "AH2": 1 - np.exp(-la * (1 - share)),
        "HG13": ph[:, 1:4].sum(1), "AG12": pa[:, 1:3].sum(1),
        "HWTN": (1 - ph[:, 0]) * pa[:, 0], "AWTN": (1 - pa[:, 0]) * ph[:, 0], "HCS": pa[:, 0], "ACS": ph[:, 0],
    }
    Dft = _diff(M)
    out["HCP_H15"] = Dft[:, 12:].sum(1)
    out["HCP_A15P"] = 1 - out["HCP_H15"]
    out["HCP_A15"] = Dft[:, :9].sum(1)
    out["HCP_H15P"] = 1 - out["HCP_A15"]
    # pauză/final: diferența la pauză (R1) + diferența din R2, independente
    D1, D2 = _diff(M1), _diff(M2)
    c2 = np.cumsum(D2, axis=1)  # c2[:, k] = P(d2 ≤ k − 10)
    def p_d2_le(x):  # P(d2 ≤ x), x întreg
        return c2[:, min(max(x + 10, -1), 20)] if x + 10 >= 0 else np.zeros(len(lh))
    htft = {k: np.zeros(len(lh)) for k in ("11", "X1", "XX", "X2", "22")}
    for idx in range(21):
        d1 = idx - 10
        w = D1[:, idx]
        fin_h = 1 - p_d2_le(-d1)            # d1 + d2 > 0
        fin_a = p_d2_le(-d1 - 1)            # d1 + d2 < 0
        fin_d = 1 - fin_h - fin_a
        if d1 > 0:
            htft["11"] += w * fin_h
        elif d1 == 0:
            htft["X1"] += w * fin_h; htft["XX"] += w * fin_d; htft["X2"] += w * fin_a
        else:
            htft["22"] += w * fin_a
    out.update({f"HTFT_{k}": v for k, v in htft.items()})
    if lyh is not None and lya is not None:
        ly = lyh + lya
        for key, k in (("YC35", 3), ("YC45", 4), ("YC55", 5)):
            out[key] = _poisson_tail(ly, k)
            out["YCU" + key[2:]] = 1 - out[key]
        out["HY15"], out["AY15"], out["AY25"] = _poisson_tail(lyh, 1), _poisson_tail(lya, 1), _poisson_tail(lya, 2)
        out["BOTH15"] = out["HY15"] * out["AY15"]
    if lc is not None:
        K = np.arange(26)
        pc = np.exp(-lc[:, None]) * lc[:, None] ** K[None, :] / np.array([math.factorial(int(k)) for k in K])[None, :]
        cdf = np.cumsum(pc, axis=1)
        for key, k in (("C65", 6), ("C75", 7), ("C85", 8), ("C95", 9), ("C105", 10)):
            out[key] = 1 - cdf[:, k]
        for key, k in (("CU105", 10), ("CU115", 11), ("CU125", 12), ("CU135", 13)):
            out[key] = cdf[:, k]
        out["BB_C65_U145"] = cdf[:, 14] - cdf[:, 6]
        for key, lam, k in (("HC35", lch, 3), ("HC45", lch, 4), ("AC25", lca, 2), ("AC35", lca, 3)):
            pk = np.exp(-lam[:, None]) * lam[:, None] ** K[None, :] / np.array([math.factorial(int(x)) for x in K])[None, :]
            out[key] = 1 - pk[:, :k + 1].sum(1)
    return out


def won(key: str, r: Dict[str, Any]) -> Optional[bool]:
    h, a, hh, ha = int(r["fthg"]), int(r["ftag"]), int(r["hthg"]), int(r["htag"])
    t, t1 = h + a, hh + ha
    t2, h2, a2 = t - t1, h - hh, a - ha
    if MARKETS[key][1] == "cornere":
        if r.get("hc") is None or r.get("ac") is None:
            return None
        hc, ac = int(r["hc"]), int(r["ac"])
        c = hc + ac
        return {"C65": c > 6, "C75": c > 7, "C85": c > 8, "C95": c > 9, "C105": c > 10, "CU105": c <= 10, "CU115": c <= 11,
                "CU125": c <= 12, "CU135": c <= 13, "BB_C65_U145": 7 <= c <= 14, "HC35": hc > 3, "HC45": hc > 4,
                "AC25": ac > 2, "AC35": ac > 3}[key]
    if MARKETS[key][1] == "cartonase":
        if r.get("hy") is None or r.get("ay") is None:
            return None
        hy, ay = int(r["hy"]), int(r["ay"])
        y = hy + ay
        return {"YC35": y > 3, "YC45": y > 4, "YC55": y > 5, "YCU35": y <= 3, "YCU45": y <= 4, "YCU55": y <= 5,
                "HY15": hy > 1, "AY15": ay > 1, "AY25": ay > 2, "BOTH15": hy > 1 and ay > 1}[key]
    r1 = "1" if hh > ha else "X" if hh == ha else "2"
    r2 = "1" if h > a else "X" if h == a else "2"
    extra = {"H1H": hh > ha, "H1D": hh == ha, "H1A": ha > hh, "H2H": h2 > a2, "H2D": h2 == a2, "H2A": a2 > h2,
             "HTFT_11": (r1, r2) == ("1", "1"), "HTFT_X1": (r1, r2) == ("X", "1"), "HTFT_XX": (r1, r2) == ("X", "X"),
             "HTFT_X2": (r1, r2) == ("X", "2"), "HTFT_22": (r1, r2) == ("2", "2"),
             "HCP_H15": h - a >= 2, "HCP_A15P": h - a <= 1, "HCP_A15": a - h >= 2, "HCP_H15P": a - h <= 1,
             "HH1": hh > 0, "AH1": ha > 0, "HH2": h2 > 0, "AH2": a2 > 0, "HG13": 1 <= h <= 3, "AG12": 1 <= a <= 2,
             "HWTN": h > a and a == 0, "AWTN": a > h and h == 0, "HCS": a == 0, "ACS": h == 0}
    if key in extra:
        return extra[key]
    return {"H": h > a, "A": a > h, "O25": t > 2, "U25": t < 3, "O05": t > 0, "O15": t > 1, "O35": t > 3, "U35": t < 4,
            "U45": t < 5, "G13": 1 <= t <= 3, "G23": 2 <= t <= 3, "G24": 2 <= t <= 4, "G25": 2 <= t <= 5,
            "GG": h > 0 and a > 0, "NG": h == 0 or a == 0, "DC1X": h >= a, "DCX2": a >= h, "DC12": h != a,
            "HO05": h > 0, "HO15": h > 1, "AO05": a > 0, "AO15": a > 1, "HU15": h < 2, "AU15": a < 2,
            "HSBH": hh > 0 and h2 > 0, "HWEH": hh > ha or h2 > a2, "AWEH": ha > hh or a2 > h2,
            "H1O05": t1 > 0, "H1O15": t1 > 1, "H1U15": t1 < 2, "H2O05": t2 > 0, "H2O15": t2 > 1, "H2G13": 1 <= t2 <= 3,
            "H2MORE": t2 > t1, "R1R2": t1 > 0 and t2 > 0, "H13x2": 1 <= t1 <= 3 and 1 <= t2 <= 3,
            "R1O15": t1 > 0 and t > 1, "R1O25": t1 > 0 and t > 2, "GGO25": (h > 0 and a > 0) or t > 2,
            "DC1X_O15": h >= a and t > 1, "DCX2_O15": a >= h and t > 1, "H_O15": h > a and t > 1}[key]


class Leg:
    __slots__ = ("i", "key", "p", "odds", "win", "lower")

    def __init__(self, i, key, p, odds, win, lower):
        self.i, self.key, self.p, self.odds, self.win, self.lower = i, key, p, odds, win, lower


def _corner_means(rows: Sequence[Dict[str, Any]]):
    return _team_means(rows, "hc", "ac", 5.3, 4.4)


def _team_means(rows: Sequence[Dict[str, Any]], hk: str, ak: str, h0: float, a0: float):
    """Media pe meci și pe echipă (cornere, cartonașe) din meciurile ANTERIOARE (EWMA pe echipă, corectată cu
    avantajul terenului din ligă), amestecată cu media ligii."""
    ew: Dict[str, Dict[str, float]] = {}
    lgh: Dict[str, float] = defaultdict(lambda: h0)
    lga: Dict[str, float] = defaultdict(lambda: a0)
    A = 0.12
    n = len(rows)
    lc, lch, lca = np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.nan)
    for i, r in enumerate(rows):
        d = r["div"]
        eh, ea = ew.get(d + r["home"]), ew.get(d + r["away"])
        if eh and ea and eh["n"] >= 5 and ea["n"] >= 5:
            mid = (lgh[d] + lga[d]) / 2
            lch[i] = 0.8 * 0.5 * (eh["f"] + ea["a"]) * lgh[d] / mid + 0.2 * lgh[d]
            lca[i] = 0.8 * 0.5 * (ea["f"] + eh["a"]) * lga[d] / mid + 0.2 * lga[d]
            lc[i] = lch[i] + lca[i]
        if r.get(hk) is not None and r.get(ak) is not None:
            mid = (lgh[d] + lga[d]) / 2
            # ratele echipelor pe teren neutru: scoatem avantajul terenului înainte de medie
            for team, f, a, kf, ka in ((r["home"], r[hk], r[ak], lgh[d], lga[d]), (r["away"], r[ak], r[hk], lga[d], lgh[d])):
                e = ew.setdefault(d + team, {"f": mid, "a": mid, "n": 0})
                e["f"] += A * (f * mid / kf - e["f"]); e["a"] += A * (a * mid / ka - e["a"]); e["n"] += 1
            lgh[d] += 0.02 * (r[hk] - lgh[d])
            lga[d] += 0.02 * (r[ak] - lga[d])
    return lc, lch, lca


def build(rows_in: Sequence[Dict[str, Any]]):
    rows = [r for r in rows_in if r.get("hthg") is not None and r.get("fthg") is not None and all(
        r.get(k) for k in ("avg_h", "avg_d", "avg_a", "avg_o25", "avg_u25", "avgc_h", "avgc_d", "avgc_a", "avgc_o25", "avgc_u25"))]
    rows.sort(key=lambda r: r["day"])
    if not rows:
        return [], [], 0.45, "—", []
    # antrenare = sezoanele dinainte de SPLIT dacă există destule; altfel primele 60% din zile
    tr_n = sum(1 for r in rows if r["season"] < SPLIT)
    if tr_n >= 0.3 * len(rows) and tr_n < 0.9 * len(rows):
        is_train = [r["season"] < SPLIT for r in rows]
        split = "antrenare înainte de 2024/25 · test 2024/25–prezent"
    else:
        cut = rows[int(0.6 * len(rows))]["day"]
        is_train = [r["day"] < cut for r in rows]
        split = f"antrenare până la {cut} · test după"
    tr = [r for r, t in zip(rows, is_train) if t]
    share = sum(r["hthg"] + r["htag"] for r in tr) / max(1, sum(r["fthg"] + r["ftag"] for r in tr))

    def lam(prefix):
        pH = np.array([novig(r[f"{prefix}_h"], r[f"{prefix}_d"], r[f"{prefix}_a"])[0] for r in rows])
        pA = np.array([novig(r[f"{prefix}_h"], r[f"{prefix}_d"], r[f"{prefix}_a"])[2] for r in rows])
        pO = np.array([novig(r[f"{prefix}_o25"], r[f"{prefix}_u25"])[0] for r in rows])
        return lambdas_from_market(pH, pA, pO)

    (oh, oa), (ch, ca) = lam("avg"), lam("avgc")
    lc, lch, lca = _corner_means(rows)
    ly, lyh, lya = _team_means(rows, "hy", "ay", 1.9, 2.2)
    has_c, has_y = ~np.isnan(lc), ~np.isnan(ly)
    fill = lambda x: np.where(np.isnan(x), 1.0, x)  # noqa: E731 — rândurile fără medie sunt ignorate la cornere/cartonașe
    Po = probs(oh, oa, share, fill(lc), fill(lch), fill(lca), fill(lyh), fill(lya))
    Pc = probs(ch, ca, share, fill(lc), fill(lch), fill(lca), fill(lyh), fill(lya))
    real = {"H": "avgc_h", "A": "avgc_a", "O25": "avgc_o25", "U25": "avgc_u25"}
    legs: List[List[Leg]] = []
    for i, r in enumerate(rows):
        L = []
        for key, (_, fam, orr) in MARKETS.items():
            if fam == "cornere" and not has_c[i] or fam == "cartonase" and not has_y[i]:
                continue
            w = won(key, r)
            if w is None:
                continue
            odds = float(r[real[key]]) if key in real else max(1.01, round(1 / (float(Pc[key][i]) * orr), 2))
            if not PLAYABLE[0] <= odds <= PLAYABLE[1]:
                continue
            L.append(Leg(i, key, float(Po[key][i]), odds, bool(w), r["div"] in LOWER))
        legs.append(L)
    return rows, legs, share, split, is_train


def _market_stats(legs: List[List[Leg]], is_train: List[bool]) -> List[Dict[str, Any]]:
    agg: Dict[Tuple[str, str], List[float]] = defaultdict(lambda: [0, 0, 0.0, 0.0])
    for L in legs:
        for l in L:
            a = agg[(l.key, "train" if is_train[l.i] else "test")]
            a[0] += 1; a[1] += l.win; a[2] += 1 / l.odds; a[3] += l.odds * l.win
    out = []
    for key, (label, fam, orr) in MARKETS.items():
        row = {"key": key, "label": label, "family": fam, "price": "reală" if fam == "real" else "estimată"}
        for per in ("train", "test"):
            n, w, inv, ret = agg.get((key, per), [0, 0, 0.0, 0.0])
            if not n:
                row[per] = {"n": 0}
                continue
            hit, imp = w / n, inv / n / (1.05 if fam == "real" else orr)  # cât promite prețul, fără marjă
            se = math.sqrt(max(hit * (1 - hit), 1e-4) / n)
            row[per] = {"n": int(n), "hit": round(hit, 4), "implied": round(imp, 4), "lift": round(hit / imp, 4) if imp else None,
                        "lift_z": round((hit - imp) / se, 2), "roi": round(ret / n - 1, 4)}
        out.append(row)
    return out


def _select(round_legs: List[Leg], keys: set, band, league: str, key: str) -> List[Leg]:
    best: Dict[int, Leg] = {}
    for l in round_legs:
        if l.key not in keys or not band[0] <= l.odds <= band[1]:
            continue
        if league == "lower" and not l.lower or league == "top" and l.lower:
            continue
        sc = l.p if key == "p" else l.p * l.odds
        b = best.get(l.i)
        if b is None or sc > (b.p if key == "p" else b.p * b.odds):
            best[l.i] = l
    return sorted(best.values(), key=(lambda l: -l.p) if key == "p" else (lambda l: -l.p * l.odds))


def run(rows_in: Sequence[Dict[str, Any]], log: Callable[[str], None] = print) -> Dict[str, Any]:
    rows, legs, share, split, is_train = build(rows_in)
    log(f"laborator piețe: {len(rows)} meciuri, cota R1 {share:.3f}")
    if not rows:
        return {"schema": "betpredict.lab.markets.v1", "matches": 0}
    markets = _market_stats(legs, is_train)
    rounds: Dict[str, List[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        rounds[round_key(r["day"])].append(i)
    rk = sorted(rounds)
    per = {k: "train" if is_train[rounds[k][0]] else "test" for k in rk}
    round_legs = {k: [l for i in rounds[k] for l in legs[i]] for k in rk}
    sets = {f"piata:{k}": (k,) for k in MARKETS}
    sets.update({f"familie:{k}": v for k, v in FAMILY_SETS.items()})
    res: Dict[str, Dict[str, Any]] = {}
    for sname, keys in sets.items():
        ks = set(keys)
        for band in BANDS:
            for league in ("all", "lower", "top"):
                for sel in ("p", "value"):
                    rets = {t: {"train": [], "test": []} for t in TIERS}
                    nl = {t: [] for t in TIERS}
                    for k in rk:
                        cands = _select(round_legs[k], ks, band, league, sel)
                        tot, n, i = 1.0, 0, 0
                        allwin = True
                        for t in TIERS:
                            while tot < t and i < len(cands) and n < MAX_LEGS:
                                tot *= cands[i].odds; allwin &= cands[i].win; n += 1; i += 1
                            if tot < t or n < 2:
                                break
                            rets[t][per[k]].append(tot if allwin else 0.0)
                            nl[t].append(n)
                    for t in TIERS:
                        if len(rets[t]["train"]) < MIN_N or len(rets[t]["test"]) < MIN_N:
                            continue
                        name = f"{sname}|{band[0]:.2f}-{band[1]:.2f}|{league}|{sel}|T{t}"
                        res[name] = {"set": sname, "markets": list(keys), "band": list(band), "league": league, "key": sel,
                                     "tier": t, "avg_legs": round(float(np.mean(nl[t])), 1),
                                     "train": metrics(rets[t]["train"]), "test": metrics(rets[t]["test"])}
    pos_tr = sum(1 for v in res.values() if v["train"]["roi"] > 0)
    pos_te = sum(1 for v in res.values() if v["test"]["roi"] > 0)
    both = [(k, v) for k, v in res.items() if v["train"]["roi"] > 0 and v["test"]["roi"] > 0]
    both.sort(key=lambda kv: -min(kv[1]["train"]["roi"], kv[1]["test"]["roi"]))
    sig = [(k, v) for k, v in both if v["test"].get("roi_se") and v["test"]["roi"] / v["test"]["roi_se"] > 2
           and v["train"].get("roi_se") and v["train"]["roi"] / v["train"]["roi_se"] > 2]
    # piețe candidate: intră cu peste 3% mai des decât promite prețul în ambele perioade, cu z > 2 în fiecare
    cand = [m for m in markets if m["train"].get("n", 0) >= 200 and m["test"].get("n", 0) >= 200
            and (m["train"].get("lift") or 0) > 1.03 and (m["test"].get("lift") or 0) > 1.03
            and (m["train"].get("lift_z") or 0) > 2 and (m["test"].get("lift_z") or 0) > 2]
    cand.sort(key=lambda m: -min(m["train"]["lift"], m["test"]["lift"]))
    tiers = {}
    for t in TIERS:
        xs = [v for v in res.values() if v["tier"] == t]
        if xs:
            tiers[str(t)] = {"configs": len(xs), "median_test_roi": round(float(np.median([v["test"]["roi"] for v in xs])), 4),
                             "share_test_positive": round(sum(1 for v in xs if v["test"]["roi"] > 0) / len(xs), 3),
                             "best_test_hit": max((v["test"]["hit_rate"] for v in xs), default=0)}
    return {"schema": "betpredict.lab.markets.v1", "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "matches": len(rows), "split": split, "h1_share": round(share, 4),
            "rounds": {"train": sum(1 for k in rk if per[k] == "train"), "test": sum(1 for k in rk if per[k] == "test")},
            "markets": markets, "candidates": [m["key"] for m in cand],
            "configs_tested": len(res), "train_positive": pos_tr, "test_positive": pos_te, "both_positive": len(both),
            "both_positive_expected_by_chance": round(pos_tr * pos_te / max(1, len(res)), 1), "significant_both": len(sig),
            "robust": [{"name": k, **v} for k, v in both[:40]], "significant": [{"name": k, **v} for k, v in sig[:20]],
            "tiers": tiers}


# ---- stocare: rezultatul (calculat săptămânal) se publică la fiecare rulare ----
KV = "CREATE TABLE IF NOT EXISTS lab_store (name TEXT PRIMARY KEY, body TEXT NOT NULL, updated_at TEXT NOT NULL)"


def save(conn: sqlite3.Connection, doc: Dict[str, Any]) -> None:
    conn.execute(KV)
    conn.execute("INSERT INTO lab_store(name, body, updated_at) VALUES ('markets', ?, ?) ON CONFLICT(name) DO UPDATE SET "
                 "body=excluded.body, updated_at=excluded.updated_at", (json.dumps(doc, ensure_ascii=False), doc.get("generated_at", "")))


def load(conn: sqlite3.Connection) -> Optional[Dict[str, Any]]:
    conn.execute(KV)
    r = conn.execute("SELECT body FROM lab_store WHERE name='markets'").fetchone()
    return json.loads(r[0]) if r else None


def run_db(conn: sqlite3.Connection, log: Callable[[str], None] = print) -> Dict[str, Any]:
    rows = [dict(r) for r in conn.execute("SELECT * FROM fd_match ORDER BY day")]
    doc = run(rows, log)
    save(conn, doc)
    return {k: doc.get(k) for k in ("matches", "configs_tested", "both_positive", "both_positive_expected_by_chance", "significant_both", "candidates")}


if __name__ == "__main__":
    c = sqlite3.connect(sys.argv[1])
    c.row_factory = sqlite3.Row
    d = run([dict(r) for r in c.execute("SELECT * FROM fd_match ORDER BY day")])
    out = sys.argv[2] if len(sys.argv) > 2 else "markets_lab.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    print({k: d.get(k) for k in ("matches", "configs_tested", "both_positive", "both_positive_expected_by_chance", "significant_both", "candidates")})
