"""Modele simple, testate walk-forward (vezi docs/analysis-2026-10-10.md):

* goluri pe echipă: Poisson pe λ-urile Dixon-Coles ale meciului;
* goluri pe reprize: λ_repriză = f × λ_total, f = cota golurilor din prima repriză (ligă, din istoric; implicit 0.44);
* cornere: binomial negativ, media = medie (cornere câștigate echipă ↔ cedate adversar), dispersie fixă;
* cartonașe (galbene): binomial negativ, media echipelor × factorul arbitrului (tras spre 1)."""

from __future__ import annotations

import math
from typing import Dict, Iterable, Optional, Tuple

H1_SHARE_DEFAULT = 0.44
CORNER_R = 18.0   # dispersie NB (fit pe sezoanele 21/22–24/25)
CARD_R = 9.0
REF_SHRINK_N = 15.0  # meciuri „virtuale” spre media ligii pentru factorul arbitrului


def pois_cdf(k: int, lam: float) -> float:
    lam = max(1e-9, lam)
    t = s = math.exp(-lam)
    for i in range(1, k + 1):
        t *= lam / i
        s += t
    return min(1.0, s)


def nb_cdf(k: int, mean: float, r: float) -> float:
    mean = max(1e-6, mean)
    p = r / (r + mean)
    t = s = p ** r
    for i in range(1, k + 1):
        t *= (i - 1 + r) / i * (1 - p)
        s += t
    return min(1.0, s)


def p_over_pois(line: float, lam: float) -> float:
    return 1.0 - pois_cdf(int(math.floor(line)), lam)


def p_over_nb(line: float, mean: float, r: float) -> float:
    return 1.0 - nb_cdf(int(math.floor(line)), mean, r)


def goal_markets(lh: float, la: float, h1_share: float = H1_SHARE_DEFAULT) -> Dict[Tuple[str, float, str], float]:
    out: Dict[Tuple[str, float, str], float] = {}
    tot = lh + la
    for ln in (0.5, 1.5):
        for mk, lam in (("team_home", lh), ("team_away", la), ("h1", h1_share * tot), ("h2", (1 - h1_share) * tot)):
            po = p_over_pois(ln, lam)
            out[(mk, ln, "OVER")], out[(mk, ln, "UNDER")] = po, 1 - po
    return out


def corner_mean(h_for: float, h_against: float, a_for: float, a_against: float) -> float:
    return (h_for + a_against) / 2 + (a_for + h_against) / 2


def card_mean(h_cards: float, a_cards: float, ref_avg: Optional[float], ref_n: int, league_avg: float) -> float:
    base = h_cards + a_cards
    if ref_avg and league_avg > 0:
        w = ref_n / (ref_n + REF_SHRINK_N)
        base *= (1 - w) + w * (ref_avg / league_avg)
    return base


def count_markets(kind: str, mean: float, lines: Iterable[float]) -> Dict[Tuple[str, float, str], float]:
    r = CORNER_R if kind == "corners" else CARD_R
    out = {}
    for ln in lines:
        po = p_over_nb(ln, mean, r)
        out[(kind, ln, "OVER")], out[(kind, ln, "UNDER")] = po, 1 - po
    return out


CORNER_LINES = (8.5, 9.5, 10.5)
CARD_LINES = (3.5, 4.5)
