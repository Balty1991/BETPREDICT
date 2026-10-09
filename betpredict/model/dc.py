"""Dixon-Coles vectorizat: atac/apărare pe echipă, nivel pe ligă, avantaj de teren pe ligă
(micșorat spre global), decădere exponențială în timp (timp de înjumătățire reglabil) și
corecția rho pentru scoruri mici. Probabilitățile pe toate piețele dintr-o singură matrice."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

import numpy as np
from scipy.special import gammaln

from betpredict.model.data import History

MAXG = 10


@dataclass
class DCModel:
    t_ref: float = 0.0
    half_life: float = 180.0
    rho: float = -0.08
    home_adv: float = 0.25
    global_mu: float = 0.1
    league_mu: Dict[int, float] = field(default_factory=dict)
    league_home: Dict[int, float] = field(default_factory=dict)
    attack: Dict[int, float] = field(default_factory=dict)
    defense: Dict[int, float] = field(default_factory=dict)
    games: Dict[int, float] = field(default_factory=dict)

    def lambdas(self, home: np.ndarray, away: np.ndarray, league: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        mu = np.array([self.league_mu.get(int(l), self.global_mu) for l in league])
        ha = np.array([self.league_home.get(int(l), self.home_adv) for l in league])
        ah = np.array([self.attack.get(int(t), 0.0) for t in home])
        dh = np.array([self.defense.get(int(t), 0.0) for t in home])
        aa = np.array([self.attack.get(int(t), 0.0) for t in away])
        da = np.array([self.defense.get(int(t), 0.0) for t in away])
        cov = np.minimum(np.array([self.games.get(int(t), 0.0) for t in home]),
                         np.array([self.games.get(int(t), 0.0) for t in away]))
        lh = np.clip(np.exp(mu + ha + ah - da), 0.05, 6.0)
        la = np.clip(np.exp(mu + aa - dh), 0.05, 6.0)
        return lh, la, np.minimum(1.0, cov / 10.0)


def fit_dc(hist: History, t_ref: float, half_life: float = 180.0, years: float = 3.0, shrink: float = 3.0,
           iters: int = 25, rho: Optional[float] = None, league_home_shrink: float = 200.0) -> DCModel:
    m = (hist.t < t_ref) & (hist.t >= t_ref - 365 * years)
    model = DCModel(t_ref=t_ref, half_life=half_life)
    if m.sum() < 50:
        return model
    H, A, L = hist.home[m], hist.away[m], hist.league[m]
    gh, ga = hist.gh[m], hist.ga[m]
    w = np.power(0.5, (t_ref - hist.t[m]) / half_life)
    teams, inv = np.unique(np.concatenate([H, A]), return_inverse=True)
    n = len(H)
    hi, ai = inv[:n], inv[n:]
    leagues, li = np.unique(L, return_inverse=True)
    T, NL = len(teams), len(leagues)
    att, dfn = np.zeros(T), np.zeros(T)
    mu = np.full(NL, math.log(max(0.1, (gh.sum() + ga.sum()) / (2 * n))))
    hl = np.full(NL, 0.25)
    c = 1.3
    for _ in range(iters):
        eh = np.exp(mu[li] + hl[li] + att[hi] - dfn[ai])
        ea = np.exp(mu[li] + att[ai] - dfn[hi])
        S = np.bincount(hi, w * gh, T) + np.bincount(ai, w * ga, T)
        E = np.bincount(hi, w * eh / np.exp(att[hi]), T) + np.bincount(ai, w * ea / np.exp(att[ai]), T)
        att = np.log((S + shrink * c) / (E + shrink * c))
        eh = np.exp(mu[li] + hl[li] + att[hi] - dfn[ai])
        ea = np.exp(mu[li] + att[ai] - dfn[hi])
        C = np.bincount(ai, w * gh, T) + np.bincount(hi, w * ga, T)
        B = np.bincount(ai, w * eh * np.exp(dfn[ai]), T) + np.bincount(hi, w * ea * np.exp(dfn[hi]), T)
        dfn = -np.log((C + shrink * c) / (B + shrink * c))
        eh = np.exp(mu[li] + hl[li] + att[hi] - dfn[ai])
        ea = np.exp(mu[li] + att[ai] - dfn[hi])
        G = np.bincount(li, w * (gh + ga), NL)
        BL = np.bincount(li, w * (eh + ea) / np.exp(mu[li]), NL)
        gm = float(np.log(max(1e-9, (w * (gh + ga)).sum()) / max(1e-9, (w * (eh + ea) / np.exp(mu[li])).sum())))
        mu = np.log((G + 20 * math.exp(gm)) / (BL + 20))
        eh = np.exp(mu[li] + hl[li] + att[hi] - dfn[ai])
        gh_l = np.bincount(li, w * gh, NL)
        eh_l = np.bincount(li, w * eh, NL)
        wn = np.bincount(li, w, NL)
        step = hl + np.log(np.maximum(1e-9, gh_l) / np.maximum(1e-9, eh_l))
        hglob = float(np.average(step, weights=wn + 1e-9))
        # avantaj de teren pe ligă, micșorat spre global (ligile mici ≈ global)
        hl = (wn * step + league_home_shrink * hglob) / (wn + league_home_shrink)
    wl = np.bincount(li, w, NL) + 1e-9
    model.home_adv = float(np.average(hl, weights=wl))
    model.league_mu = {int(l): float(mu[i]) for i, l in enumerate(leagues)}
    model.league_home = {int(l): float(hl[i]) for i, l in enumerate(leagues)}
    model.global_mu = float(np.average(mu, weights=wl))
    model.attack = {int(t): float(att[i]) for i, t in enumerate(teams)}
    model.defense = {int(t): float(dfn[i]) for i, t in enumerate(teams)}
    games = np.bincount(hi, w, T) + np.bincount(ai, w, T)
    model.games = {int(t): float(games[i]) for i, t in enumerate(teams)}
    if rho is None:
        lh, la, _ = model.lambdas(H[-20000:], A[-20000:], L[-20000:])
        model.rho = fit_rho(lh, la, gh[-20000:], ga[-20000:])
    else:
        model.rho = rho
    return model


def _tau(x, y, lh, la, rho):
    t = np.ones_like(lh)
    t = np.where((x == 0) & (y == 0), 1 - lh * la * rho, t)
    t = np.where((x == 0) & (y == 1), 1 + lh * rho, t)
    t = np.where((x == 1) & (y == 0), 1 + la * rho, t)
    t = np.where((x == 1) & (y == 1), 1 - rho, t)
    return t


def fit_rho(lh, la, gh, ga) -> float:
    best, bl = -0.05, -np.inf
    lp = (gh * np.log(lh) - lh - gammaln(gh + 1)) + (ga * np.log(la) - la - gammaln(ga + 1))
    for r in np.arange(-0.20, 0.051, 0.01):
        tau = _tau(gh, ga, lh, la, r)
        ll = float(np.sum(np.log(np.clip(tau, 1e-9, None)) + lp))
        if ll > bl:
            best, bl = float(r), ll
    return round(best, 3)


def score_matrix(lh: np.ndarray, la: np.ndarray, rho: float) -> np.ndarray:
    """(N, MAXG+1, MAXG+1) probabilități de scor, normalizate."""
    g = np.arange(MAXG + 1)
    ph = np.exp(g[None, :] * np.log(lh[:, None]) - lh[:, None] - gammaln(g + 1)[None, :])
    pa = np.exp(g[None, :] * np.log(la[:, None]) - la[:, None] - gammaln(g + 1)[None, :])
    M = ph[:, :, None] * pa[:, None, :]
    M[:, 0, 0] *= 1 - lh * la * rho
    M[:, 0, 1] *= 1 + lh * rho
    M[:, 1, 0] *= 1 + la * rho
    M[:, 1, 1] *= 1 - rho
    M = np.clip(M, 0, None)
    return M / M.sum(axis=(1, 2), keepdims=True)


def market_probs_from_matrix(M: np.ndarray) -> Dict[str, np.ndarray]:
    g = np.arange(MAXG + 1)
    diff = g[:, None] - g[None, :]
    tot = g[:, None] + g[None, :]
    H = (M * (diff > 0)).sum(axis=(1, 2))
    D = (M * (diff == 0)).sum(axis=(1, 2))
    A = 1 - H - D
    out = {"H": H, "D": D, "A": A}
    for ln, k in ((1.5, "15"), (2.5, "25"), (3.5, "35")):
        o = (M * (tot > ln)).sum(axis=(1, 2))
        out["O" + k], out["U" + k] = o, 1 - o
    by = M[:, 1:, 1:].sum(axis=(1, 2))
    out["BY"], out["BN"] = by, 1 - by
    return out
