"""Metrici: logloss, Brier, ECE (10 coșuri), ROI simulat pe cote disponibile, CLV."""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np

EPS = 1e-6


def logloss_bin(p, y) -> float:
    p = np.clip(p, EPS, 1 - EPS)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def brier_bin(p, y) -> float:
    return float(np.mean((p - y) ** 2))


def ece(p, y, bins: int = 10) -> float:
    p, y = np.asarray(p), np.asarray(y, dtype=float)
    if len(p) == 0:
        return float("nan")
    idx = np.minimum((p * bins).astype(int), bins - 1)
    tot = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            tot += m.sum() * abs(p[m].mean() - y[m].mean())
    return float(tot / len(p))


def logloss_multi(P, y) -> float:
    return float(-np.mean(np.log(np.clip(P[np.arange(len(y)), y], EPS, 1))))


def brier_multi(P, y) -> float:
    Y = np.eye(P.shape[1])[y]
    return float(np.mean(np.sum((P - Y) ** 2, 1)))


def roi(p, odds, won, ev_min: float = 0.0, p_min: float = 0.0, odds_min: float = 1.15, odds_max: float = 100.0,
        void: Optional[np.ndarray] = None) -> Dict[str, float]:
    """Pariu plat 1u pe fiecare selecție cu EV > ev_min (p·cotă − 1)."""
    p, odds, won = np.asarray(p, float), np.asarray(odds, float), np.asarray(won, float)
    ok = np.isfinite(odds) & (odds >= odds_min) & (odds <= odds_max) & (p * odds - 1 > ev_min) & (p >= p_min)
    if void is not None:
        ok &= ~void
    n = int(ok.sum())
    if n == 0:
        return {"n": 0, "roi": None, "hit": None, "se": None, "avg_odds": None}
    prof = np.where(won[ok] > 0, odds[ok] - 1, -1.0)
    return {"n": n, "roi": round(float(prof.mean()), 4), "hit": round(float(won[ok].mean()), 4),
            "se": round(float(prof.std(ddof=1) / np.sqrt(n)) if n > 1 else 0.0, 4), "avg_odds": round(float(odds[ok].mean()), 3)}
