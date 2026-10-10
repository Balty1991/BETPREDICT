"""Feature-uri xG (Understat), secvențiale: starea echipei ÎNAINTEA meciului (EWMA xG marcat / primit).

NaN unde echipa are < MIN_N meciuri cu xG (LightGBM tratează NaN nativ) — acoperire doar top-5 + RFPL."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

ALPHA, MIN_N = 0.1, 3
N_FEAT = 5


def _state(st: Dict[int, List[float]], h: int, a: int) -> List[float]:
    sh, sa = st.get(h), st.get(a)
    nan = float("nan")
    hf, ha = (sh[0], sh[1]) if sh and sh[2] >= MIN_N else (nan, nan)
    af, aa = (sa[0], sa[1]) if sa and sa[2] >= MIN_N else (nan, nan)
    return [hf, ha, af, aa, (hf - ha) - (af - aa)]


def xg_features(ids: Sequence[int], home: Sequence[int], away: Sequence[int], xg: Dict[int, Tuple[float, float]],
                extra: Optional[List[Tuple[int, int]]] = None) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    st: Dict[int, List[float]] = {}
    out = np.empty((len(ids), N_FEAT), dtype=np.float32)
    for i, (mid, h, a) in enumerate(zip(ids, home, away)):
        out[i] = _state(st, h, a)
        v = xg.get(int(mid))
        if v is None:
            continue
        for tm, f, g in ((h, v[0], v[1]), (a, v[1], v[0])):
            r = st.get(tm)
            if r is None:
                st[tm] = [f, g, 1]
            else:
                r[0] += ALPHA * (f - r[0])
                r[1] += ALPHA * (g - r[1])
                r[2] += 1
    Xe = np.array([_state(st, h, a) for h, a in extra], dtype=np.float32) if extra else None
    return out, Xe
