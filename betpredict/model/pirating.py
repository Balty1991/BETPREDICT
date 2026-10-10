"""Pi-ratings (Constantinou & Fenton, 2013): rating separat acasă / deplasare, actualizat după eroarea de diferență de goluri."""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

LAM, GAM, B, C = 0.06, 0.6, 10.0, 3.0
PI_NAMES = ["pi_hh", "pi_aa", "pi_gd"]


def _psi(r: float) -> float:
    return math.copysign(B ** (abs(r) / C) - 1, r)


def _w(e: float) -> float:
    return math.copysign(C * math.log10(1 + abs(e)), e)


def pi_features(home: Sequence[int], away: Sequence[int], gh: Sequence[float], ga: Sequence[float],
                extra: Optional[List[Tuple[int, int]]] = None) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    RH: Dict[int, float] = {}
    RA: Dict[int, float] = {}
    out = np.empty((len(home), 3), dtype=np.float32)
    for i, (h, a, x, y) in enumerate(zip(home, away, gh, ga)):
        rh, ra = RH.get(h, 0.0), RA.get(a, 0.0)
        exp = _psi(rh) - _psi(ra)
        out[i] = (rh, ra, exp)
        e = (x - y) - exp
        wh, wa = _w(e) * LAM, -_w(e) * LAM
        RH[h] = rh + wh
        RA[h] = RA.get(h, 0.0) + wh * GAM
        RA[a] = ra + wa
        RH[a] = RH.get(a, 0.0) + wa * GAM
    Xe = None
    if extra:
        Xe = np.array([(RH.get(h, 0.0), RA.get(a, 0.0), _psi(RH.get(h, 0.0)) - _psi(RA.get(a, 0.0))) for h, a in extra], dtype=np.float32)
    return out, Xe
