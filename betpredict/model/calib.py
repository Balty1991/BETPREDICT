"""v4: de-vig Shin, grupuri de ligi, calibrare rolling pe piață × grup, ECE debiased, blend logit cu piața.

Toate funcțiile sunt pure (numpy) ca să poată fi testate și backtestate pe predicțiile OOS ale artefactului."""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from betpredict.model.stack import apply_isotonic, fit_isotonic

# ------------------------------------------------------------------ de-vig
def shin(odds: Sequence[float], iters: int = 60) -> Optional[List[float]]:
    """Probabilități fără marjă prin metoda Shin (corectează biasul favorit–outsider).
    Revine la proporțional dacă nu converge sau marja e negativă."""
    if not odds or any((o is None) or not (o > 1.0) for o in odds):
        return None
    pi = [1.0 / o for o in odds]
    s = sum(pi)
    if s <= 1.0 or len(pi) < 2:
        return [x / s for x in pi]
    lo, hi = 0.0, 0.4
    def total(z: float) -> float:
        return sum((math.sqrt(z * z + 4 * (1 - z) * (p * p) / s) - z) / (2 * (1 - z)) for p in pi)
    for _ in range(iters):
        z = (lo + hi) / 2
        if total(z) > 1.0:
            lo = z
        else:
            hi = z
    z = (lo + hi) / 2
    out = [(math.sqrt(z * z + 4 * (1 - z) * (p * p) / s) - z) / (2 * (1 - z)) for p in pi]
    t = sum(out)
    return [x / t for x in out]


def proportional(odds: Sequence[float]) -> Optional[List[float]]:
    if not odds or any((o is None) or not (o > 1.0) for o in odds):
        return None
    inv = [1.0 / o for o in odds]
    s = sum(inv)
    return [x / s for x in inv]


DEVIG = {"shin": shin, "proportional": proportional}

# ------------------------------------------------------------------ grupuri de ligi
TOP = {1, 2, 3, 4, 5, 6, 7, 8, 10, 83}                        # top-5 + PT/NL + cupe europene
SECOND = {9, 11, 12, 13, 14, 18, 23, 24, 25, 26, 34, 38, 49, 50, 52, 54, 84, 85, 86, 87, 88, 89}


def league_group(league_id: Any) -> str:
    try:
        lid = int(league_id)
    except (TypeError, ValueError):
        return "other"
    return "top" if lid in TOP else "second" if lid in SECOND else "other"


GROUPS = ("top", "second", "other")

# ------------------------------------------------------------------ ECE
def ece(p: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    p, y = np.asarray(p, float), np.asarray(y, float)
    if len(p) == 0:
        return float("nan")
    idx = np.minimum(bins - 1, (p * bins).astype(int))
    tot = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            tot += m.sum() * abs(p[m].mean() - y[m].mean())
    return tot / len(p)


def ece_debiased(p: np.ndarray, y: np.ndarray, bins: int = 10, sims: int = 100, seed: int = 7) -> float:
    """ECE minus ECE-ul așteptat al unui model PERFECT calibrat cu aceleași p (zgomotul de eșantion)."""
    p = np.asarray(p, float)
    rng = np.random.default_rng(seed)
    noise = float(np.mean([ece(p, (rng.random(len(p)) < p).astype(float), bins) for _ in range(sims)]))
    return max(0.0, ece(p, y, bins) - noise)


def _ll(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


# ------------------------------------------------------------------ calibrare rolling
WINDOW_D, MIN_N, MAX_WINDOW_D, HOLDOUT_D, ECE_BLOCK = 60.0, 300, 365.0, 30.0, 0.03


def _window(t: np.ndarray, base: np.ndarray, t_end: float) -> np.ndarray:
    w = WINDOW_D
    while True:
        m = base & (t >= t_end - w) & (t < t_end)
        if m.sum() >= MIN_N or w >= MAX_WINDOW_D:
            return m
        w = min(MAX_WINDOW_D, w * 2)


def _temp(p: np.ndarray, y: np.ndarray) -> float:
    """Temperature scaling (un parametru) pe logit."""
    z = np.log(np.clip(p, 1e-6, 1 - 1e-6) / np.clip(1 - p, 1e-6, 1))
    best, bt = 1e9, 1.0
    for T in np.linspace(0.6, 1.6, 41):
        v = _ll(1 / (1 + np.exp(-z / T)), y)
        if v < best:
            best, bt = v, float(T)
    return bt


def apply_cal(c: Optional[Dict[str, Any]], p: np.ndarray) -> np.ndarray:
    if not c:
        return p
    if c.get("iso"):
        return np.clip(apply_isotonic(c["iso"], p), 1e-4, 1 - 1e-4)
    if c.get("T"):
        z = np.log(np.clip(p, 1e-6, 1 - 1e-6) / np.clip(1 - p, 1e-6, 1))
        return 1 / (1 + np.exp(-z / c["T"]))
    return p


def _fit_one(p: np.ndarray, y: np.ndarray) -> Dict[str, Any]:
    if len(p) >= MIN_N:
        return {"iso": fit_isotonic(p, y, bins=min(400, max(50, len(p) // 20))), "n": int(len(p))}
    if len(p) >= 60:
        return {"T": _temp(p, y), "n": int(len(p))}
    return {}


def fit_group_calibration(P: Dict[str, np.ndarray], Y: Dict[str, np.ndarray], t: np.ndarray, league: np.ndarray,
                          mask: np.ndarray, t_end: float, keys: Iterable[str]) -> Dict[str, Any]:
    """Pentru fiecare piață × grup: (a) backtest — calibrator pe [t_end−30−fereastră, t_end−30), evaluat pe ultimele 30 zile;
    se păstrează doar dacă logloss-ul pe holdout nu crește; (b) refit pe fereastra finală pentru live.
    ECE debiased pe holdout după calibrare > 3% → piață × grup blocată (nu intră în recomandări/bilete)."""
    grp = np.array([league_group(x) for x in league])
    out: Dict[str, Any] = {"cal": {}, "blocked": [], "report": []}
    for k in keys:
        ok = mask & np.isfinite(P[k]) & np.isfinite(Y[k])
        for g in GROUPS:
            base = ok & (grp == g)
            tr = _window(t, base, t_end - HOLDOUT_D)
            ho = base & (t >= t_end - HOLDOUT_D) & (t < t_end)
            if tr.sum() < 60 or ho.sum() < 50:
                continue
            c = _fit_one(P[k][tr], Y[k][tr])
            raw, cal = P[k][ho], apply_cal(c, P[k][ho])
            ll0, ll1 = _ll(raw, Y[k][ho]), _ll(cal, Y[k][ho])
            keep = bool(c) and ll1 <= ll0 + 1e-5
            e_after = ece_debiased(cal if keep else raw, Y[k][ho])
            rec = {"key": k, "group": g, "n_fit": int(tr.sum()), "n_holdout": int(ho.sum()), "ll_raw": round(ll0, 5),
                   "ll_cal": round(ll1, 5), "kept": keep, "ece_raw": round(ece(raw, Y[k][ho]), 4), "ece_debiased": round(e_after, 4)}
            out["report"].append(rec)
            if keep:  # refit pe fereastra cea mai recentă (inclusiv holdout-ul)
                fin = _window(t, base, t_end)
                out["cal"][f"{k}|{g}"] = _fit_one(P[k][fin], Y[k][fin])
            if ho.sum() >= MIN_N and e_after > ECE_BLOCK:
                out["blocked"].append(f"{k}|{g}")
    return out


def calibrate_dict(S: Dict[str, np.ndarray], cal: Dict[str, Any], groups: np.ndarray) -> Dict[str, np.ndarray]:
    """Aplică calibrarea pe grup (H/D/A renormalizate; binarele independente; monotonie O/U păstrată)."""
    out = {k: np.array(v, float, copy=True) for k, v in S.items()}
    for k in list(S):
        for g in GROUPS:
            c = cal.get(f"{k}|{g}")
            m = groups == g
            if c and m.any():
                out[k][m] = apply_cal(c, out[k][m])
    if all(k in out for k in ("H", "D", "A")):
        s = out["H"] + out["D"] + out["A"]
        for k in ("H", "D", "A"):
            out[k] = out[k] / s
    if "O15" in out and "O25" in out:
        out["O25"] = np.minimum(out["O25"], out["O15"])
    if "O25" in out and "O35" in out:
        out["O35"] = np.minimum(out["O35"], out["O25"])
    return out


# ------------------------------------------------------------------ blend logit cu piața, w pe ligă
def _lg(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def fit_w(pm: np.ndarray, pk: np.ndarray, y: np.ndarray) -> float:
    best, bw = 1e9, 0.7
    for w in np.linspace(0.0, 1.0, 41):
        v = _ll(1 / (1 + np.exp(-(w * _lg(pk) + (1 - w) * _lg(pm)))), y)
        if v < best:
            best, bw = v, float(w)
    return bw


W_PRIOR_N = 150.0


def fit_league_weights(Pm: Dict[str, np.ndarray], MK: Dict[str, np.ndarray], Y: Dict[str, np.ndarray], league: np.ndarray,
                       mask: np.ndarray, keys: Sequence[str]) -> Dict[str, Any]:
    """w global pe piață, apoi w pe grup și pe ligă micșorat bayesian spre nivelul de deasupra (n/(n+150))."""
    grp = np.array([league_group(x) for x in league])
    out: Dict[str, Any] = {}
    for k in keys:
        ok = mask & np.isfinite(Pm[k]) & np.isfinite(MK[k])
        if ok.sum() < 200:
            continue
        wg = fit_w(Pm[k][ok], MK[k][ok], Y[k][ok])
        d = {"global": round(wg, 3), "group": {}, "league": {}}
        for g in GROUPS:
            m = ok & (grp == g)
            n = int(m.sum())
            wgg = wg if n < 50 else (n * fit_w(Pm[k][m], MK[k][m], Y[k][m]) + W_PRIOR_N * wg) / (n + W_PRIOR_N)
            d["group"][g] = round(float(wgg), 3)
        for lg in np.unique(league[ok]):
            m = ok & (league == lg)
            n = int(m.sum())
            if n < 50:
                continue
            base = d["group"][league_group(lg)]
            d["league"][str(int(lg))] = round(float((n * fit_w(Pm[k][m], MK[k][m], Y[k][m]) + W_PRIOR_N * base) / (n + W_PRIOR_N)), 3)
        out[k] = d
    return out


def league_w(weights: Dict[str, Any], k: str, league_id: Any) -> Optional[float]:
    d = weights.get(k)
    if not d:
        return None
    w = d["league"].get(str(league_id))
    return float(w if w is not None else d["group"].get(league_group(league_id), d["global"]))


def blend(pm: np.ndarray, pk: np.ndarray, w: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-(w * _lg(pk) + (1 - w) * _lg(pm))))
