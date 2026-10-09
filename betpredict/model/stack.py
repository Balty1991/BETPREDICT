"""Stacking + calibrare pe piață (beta-calibrare generalizată).

Pentru piețele binare: logit p = Σ_s (a_s·ln p_s − b_s·ln(1−p_s)) + c — exact calibrarea „beta”
aplicată simultan fiecărei surse (model, Dixon-Coles, piață fără marjă), cu regularizare L2 spre o
ancoră (prior). Pentru 1X2: regresie logistică multinomială pe log-probabilitățile surselor.
Când nu există cote, se folosește stacker-ul „fără piață”; cu cote, cel „cu piață”, care învață
cât să se micșoreze predicția spre piață (shrink)."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import numpy as np
from scipy.optimize import minimize

EPS = 1e-4


def _clip(p):
    return np.clip(p, EPS, 1 - EPS)


def beta_design(sources: Sequence[np.ndarray]) -> np.ndarray:
    cols = []
    for p in sources:
        p = _clip(np.asarray(p, dtype=float))
        cols += [np.log(p), -np.log(1 - p)]
    cols.append(np.ones_like(cols[0]))
    return np.stack(cols, 1)


def fit_binary(sources: Sequence[np.ndarray], y: np.ndarray, prior: Optional[np.ndarray] = None, l2: float = 2.0,
               weight: Optional[np.ndarray] = None) -> np.ndarray:
    Xd = beta_design(sources)
    n, k = Xd.shape
    if prior is None:  # implicit: media surselor, calibrare identitate
        prior = np.zeros(k)
        prior[:-1] = 1.0 / len(sources)
    w = np.ones(n) if weight is None else weight
    y = np.asarray(y, dtype=float)

    def f(b):
        z = Xd @ b
        ll = np.sum(w * (np.logaddexp(0, z) - y * z))
        r = b - prior
        return ll + l2 * np.dot(r[:-1], r[:-1]), Xd.T @ (w * (1 / (1 + np.exp(-z)) - y)) + 2 * l2 * np.r_[r[:-1], 0.0]

    res = minimize(f, prior.copy(), jac=True, method="L-BFGS-B")
    return res.x


def apply_binary(coef: np.ndarray, sources: Sequence[np.ndarray]) -> np.ndarray:
    z = beta_design(sources) @ np.asarray(coef)
    return 1 / (1 + np.exp(-z))


def multi_design(sources: Sequence[np.ndarray]) -> np.ndarray:
    """sources: listă de (N,3) probabilități → (N, 3·S + 1) log-probabilități + intercept."""
    cols = [np.log(np.clip(s, EPS, 1)) for s in sources]
    return np.concatenate(cols + [np.ones((cols[0].shape[0], 1))], 1)


def fit_multi(sources: Sequence[np.ndarray], y: np.ndarray, l2: float = 2.0, prior: Optional[np.ndarray] = None) -> np.ndarray:
    """Coeficienți (k, 3): softmax(X @ B). Prior = medie geometrică a surselor."""
    Xd = multi_design(sources)
    n, k = Xd.shape
    S = len(sources)
    if prior is None:
        prior = np.zeros((k, 3))
        for s in range(S):
            for j in range(3):
                prior[3 * s + j, j] = 1.0 / S
    Y = np.eye(3)[y]

    def f(bflat):
        B = bflat.reshape(k, 3)
        Z = Xd @ B
        Z = Z - Z.max(1, keepdims=True)
        lse = np.log(np.exp(Z).sum(1))
        ll = np.sum(lse - (Z * Y).sum(1))
        P = np.exp(Z - lse[:, None])
        R = B - prior
        R[-1] = 0
        g = Xd.T @ (P - Y) + 2 * l2 * R
        return ll + l2 * np.sum(R * R), g.ravel()

    res = minimize(f, prior.ravel().copy(), jac=True, method="L-BFGS-B")
    return res.x.reshape(k, 3)


def apply_multi(B: np.ndarray, sources: Sequence[np.ndarray]) -> np.ndarray:
    Z = multi_design(sources) @ B
    Z = Z - Z.max(1, keepdims=True)
    P = np.exp(Z)
    return P / P.sum(1, keepdims=True)


# --------------------------------------------------------------- calibrare izotonă (diagnostic/alternativă)
def fit_isotonic(p: np.ndarray, y: np.ndarray, bins: int = 400) -> Dict[str, List[float]]:
    """PAV pe cuantile (rapid); returnează puncte (x, y) pentru interpolare."""
    o = np.argsort(p)
    ps, ys = p[o], y[o].astype(float)
    edges = np.linspace(0, len(ps), min(bins, len(ps)) + 1).astype(int)
    xs = [ps[a:b].mean() for a, b in zip(edges[:-1], edges[1:]) if b > a]
    vs = [ys[a:b].mean() for a, b in zip(edges[:-1], edges[1:]) if b > a]
    ws = [b - a for a, b in zip(edges[:-1], edges[1:]) if b > a]
    blocks: List[List[float]] = []
    for x, v, w in zip(xs, vs, ws):
        blocks.append([v, w, x, x])
        while len(blocks) > 1 and blocks[-2][0] > blocks[-1][0]:
            v2, w2, a2, _ = blocks.pop(-2)
            v1, w1, _, b1 = blocks.pop(-1)
            blocks.append([(v1 * w1 + v2 * w2) / (w1 + w2), w1 + w2, a2, b1])
    X = [(b[2] + b[3]) / 2 for b in blocks]
    Y = [b[0] for b in blocks]
    return {"x": [float(v) for v in X], "y": [float(v) for v in Y]}


def apply_isotonic(iso: Dict[str, List[float]], p: np.ndarray) -> np.ndarray:
    return np.clip(np.interp(p, iso["x"], iso["y"]), 0.005, 0.995)
