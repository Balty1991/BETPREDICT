"""Motivația din clasament: miza meciului (titlu / cupe europene / retrogradare / „meci fără miză”).

Pentru fiecare echipă, înainte de meci: distanța în puncte până la locul 1, locul 4 și primul loc retrogradabil,
raportată la punctele încă disponibile (3 × meciuri rămase). „Fără miză” = nu mai poate prinde nicio zonă și nu
mai poate fi prinsă de retrogradare."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

STAKES_NAMES = ["title_h", "europe_h", "releg_h", "dead_h", "title_a", "europe_a", "releg_a", "dead_a"]


def _team_stakes(tab: Dict[int, List[float]], team: int) -> Tuple[float, float, float, float]:
    if team not in tab or len(tab) < 8:
        return (np.nan, np.nan, np.nan, np.nan)
    order = sorted(tab.items(), key=lambda kv: -kv[1][0])
    nt = len(order)
    total = 2 * (nt - 1)
    pts, played = tab[team][0], tab[team][1]
    left = max(0.0, total - played) * 3.0
    if left <= 0:
        return (0.0, 0.0, 0.0, 1.0)
    p1 = order[0][1][0]
    p4 = order[min(3, nt - 1)][1][0]
    pr = order[max(0, nt - 3)][1][0]
    title = (p1 - pts) / left
    europe = (p4 - pts) / left
    releg = (pts - pr) / left
    dead = 1.0 if (europe > 1.0 and releg > 1.0) else 0.0
    return (title, europe, releg, dead)


def stakes_features(home: Sequence[int], away: Sequence[int], league: Sequence[int], season: Sequence[int],
                    gh: Sequence[float], ga: Sequence[float],
                    extra: Optional[List[Tuple[int, int, int, int]]] = None) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    tabs: Dict[Tuple[int, int], Dict[int, List[float]]] = defaultdict(dict)
    out = np.empty((len(home), 8), dtype=np.float32)
    for i, (h, a, l, s, x, y) in enumerate(zip(home, away, league, season, gh, ga)):
        tab = tabs[(l, s)]
        out[i] = _team_stakes(tab, h) + _team_stakes(tab, a)
        for tm, f, g in ((h, x, y), (a, y, x)):
            r = tab.setdefault(tm, [0.0, 0.0])
            r[0] += 3 if f > g else (1 if f == g else 0)
            r[1] += 1
    Xe = None
    if extra:
        Xe = np.array([_team_stakes(tabs[(l, s)], h) + _team_stakes(tabs[(l, s)], a) for h, a, l, s in extra], dtype=np.float32)
    return out, Xe
