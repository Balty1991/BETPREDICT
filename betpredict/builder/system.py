"""Variante „sistem” Superbet (k/n) pentru orice bilet: miza împărțită egal pe toate combinațiile de k selecții.

Pentru fiecare variantă: numărul de combinații, miza pe combinație, EV exact (Σ_combinații Π p·c / C − 1),
probabilitatea de 0/1/2 ratări (Poisson-binomial) și câștigul la 0/1/2 ratări (min/mediu/max după care ratează)."""

from __future__ import annotations

import math
from itertools import combinations
from typing import Any, Dict, List, Sequence


def _misses_dist(ps: Sequence[float]) -> List[float]:
    d = [1.0]
    for p in ps:
        nd = [0.0] * (len(d) + 1)
        for j, v in enumerate(d):
            nd[j] += v * p          # câștigă → ratările rămân j
            nd[j + 1] += v * (1 - p)
        d = nd
    return d  # d[j] = P(exact j ratări)


def _esym(xs: Sequence[float], k: int) -> float:
    """Suma elementară simetrică de ordin k (Σ peste combinații de k a produselor)."""
    e = [1.0] + [0.0] * k
    for x in xs:
        for j in range(k, 0, -1):
            e[j] += e[j - 1] * x
    return e[k]


def system_variant(odds: Sequence[float], ps: Sequence[float], k: int, stake: float) -> Dict[str, Any]:
    n = len(odds)
    C = math.comb(n, k)
    per = stake / C
    ev = _esym([p * o for p, o in zip(ps, odds)], k) / C - 1
    dist = _misses_dist(ps)
    table = []
    for j in range(0, min(2, n - k) + 1):
        pays = []
        for miss in combinations(range(n), j):
            rest = [odds[i] for i in range(n) if i not in miss]
            pays.append(per * _esym(rest, k))
        table.append({"misses": j, "prob": round(dist[j], 5), "payout_min": round(min(pays), 2),
                      "payout_avg": round(sum(pays) / len(pays), 2), "payout_max": round(max(pays), 2)})
    p_return = sum(dist[: n - k + 1])
    return {"system": f"{k}/{n}", "k": k, "n": n, "combos": C, "stake_total": round(stake, 2), "stake_per_combo": round(per, 4),
            "ev": round(ev, 4), "p_any_return": round(p_return, 4), "table": table}


def system_variants(odds: Sequence[float], ps: Sequence[float], stake: float) -> List[Dict[str, Any]]:
    n = len(odds)
    out = []
    if n >= 3:
        out.append(system_variant(odds, ps, n - 1, stake))
    if n >= 5:
        out.append(system_variant(odds, ps, n - 2, stake))
    if n >= 9:
        out.append(system_variant(odds, ps, n - 3, stake))
    return out
