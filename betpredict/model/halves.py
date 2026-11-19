"""Modelul pe reprize pentru piețele recomandate: R2 1-3 (H2G13), R2 1-2 (H2G12), R1 sub 1.5 (H1U15),
Peste 1.5 (O15), gazdă / oaspete (HOME / AWAY).

Pornește de la prețurile Superbet ale meciului (Final 1X2 + liniile „Total goluri”), scoate marja (metoda puterii),
potrivește golurile așteptate ale celor două echipe (Poisson cu corecția Dixon-Coles pe scorurile mici) și le împarte
pe reprize (prima repriză ~44.6% din goluri; ponderea pe ligă e disponibilă, dar n-a ajutat în afara eșantionului).
Apoi o recalibrare logistică pe piață, învățată pe football-data (2020–2024) și verificată pe 2024–2026.

Ajustarea cu forța echipelor (Dixon-Coles cu decădere în timp, pe tot meciul și pe prima repriză) a fost măsurată în
afara eșantionului și NU a îmbunătățit nimic peste prețul pieței (vezi DC_W / SHARE_W = 0 și raportul din teste);
rămâne disponibilă prin `dc_weight` pentru experimente, implicit oprită.

Rezultatul e o probabilitate „onestă” per piață: aproape de prețul Superbet fără marjă. Nu e o sursă de valoare;
e un filtru: cât de mult pierde selecția la prețul cerut (ev = p × cotă − 1).

Măsurători în afara eșantionului (parametri învățați doar pe football-data până la 2024-06):
- football-data 2024-07…2026-11 (17.7k meciuri, cote medii de închidere): calibrare bună pe chintile la toate cheile;
  Dixon-Coles singur e mai slab decât piața (HOME log-loss 0.646 vs 0.622), amestecat cu piața strică (w 0.05…0.3).
- cote de închidere Superbet 13–19.11 (220 de meciuri): log-loss model vs Superbet fără marjă, câștig ± eroare:
  H2G13 +0.006 ± 0.004, AWAY +0.003 ± 0.002, celelalte ≈ 0 sau ușor negative → fără avantaj semnificativ.
  Selecțiile cu ev > 0 sunt aproape inexistente (modelul ≈ prețul fără marjă); nu se pretinde valoare."""

from __future__ import annotations

import math
import sqlite3
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from scipy.special import gammaln

KEYS = ("H2G13", "H2G12", "H1U15", "O15", "HOME", "AWAY", "DRAW")
ALIASES = {"OVER": "O15", "1": "HOME", "2": "AWAY", "X": "DRAW"}
# selecția Superbet care se joacă pentru fiecare cheie (prețul folosit la ev / ROI)
SB_MARKET = {
    "H2G13": ("A doua repriză - Interval goluri", "1-3"),
    "H2G12": ("A doua repriză - Interval goluri", "1-2"),
    "H1U15": ("Prima repriză - Total goluri", "Sub 1.5"),
    "O15": ("Total goluri", "Peste 1.5"),
    "HOME": ("Final", "1"),
    "AWAY": ("Final", "2"),
    "DRAW": ("Final", "X"),
}
LINES = (0.5, 1.5, 2.5, 3.5, 4.5)
RHO = -0.05
MAXG = 10
H1_SHARE = 0.446          # ponderea golurilor din prima repriză (football-data 2020–2024, 22 de ligi); vezi league_h1_share
SHARE_PRIOR = 400.0       # câte goluri „virtuale” trag ponderea ligii spre medie
# Recalibrare logistică logit(p') = a + b·logit(p), învățată pe football-data 2020-08…2024-06 (cote de închidere medii)
CALIB: Dict[str, Tuple[float, float]] = {
    "H2G13": (0.0169, 1.1022), "H2G12": (0.1569, 0.7539), "H1U15": (-0.0536, 1.0795), "O15": (-0.0048, 1.0102),
    "HOME": (-0.0129, 1.0612), "AWAY": (0.0385, 1.0693), "DRAW": (0.1991, 1.1480),
}
DC_W = 0.0                # greutatea forței Dixon-Coles în golurile așteptate (0 = doar piața; măsurat: nu ajută)
# Ponderea pe ligă (league_h1_share) și cea pe echipe (Dixon-Coles pe golurile de la pauză) au fost măsurate pe
# football-data 2024–2026: log-loss egal sau mai slab decât media globală → implicit se folosește H1_SHARE.


# ---------------------------------------------------------------- marjă
def demargin(odds: Sequence[float]) -> List[float]:
    """Metoda puterii: p_i = (1/o_i)^k cu Σ p_i = 1 (marja cade mai mult pe cotele mari, ca la Superbet)."""
    inv = np.array([1.0 / o for o in odds], dtype=float)
    if len(inv) == 0 or np.any(~np.isfinite(inv)) or np.any(inv <= 0):
        return [float("nan")] * len(inv)
    if abs(inv.sum() - 1) < 1e-9:
        return list(inv)
    lo, hi = 0.2, 5.0
    for _ in range(60):
        k = (lo + hi) / 2
        s = float(np.sum(inv ** k))
        if s > 1:
            lo = k
        else:
            hi = k
    p = inv ** ((lo + hi) / 2)
    return list(p / p.sum())


# ---------------------------------------------------------------- Poisson + Dixon-Coles
def _pois(lam: np.ndarray) -> np.ndarray:
    g = np.arange(MAXG + 1)
    lam = np.maximum(lam, 1e-6)
    return np.exp(g[None, :] * np.log(lam[:, None]) - lam[:, None] - gammaln(g + 1)[None, :])


def score_matrix(lh: np.ndarray, la: np.ndarray, rho: float = RHO) -> np.ndarray:
    M = _pois(lh)[:, :, None] * _pois(la)[:, None, :]
    M[:, 0, 0] *= 1 - lh * la * rho
    M[:, 0, 1] *= 1 + lh * rho
    M[:, 1, 0] *= 1 + la * rho
    M[:, 1, 1] *= 1 - rho
    M = np.clip(M, 0, None)
    return M / M.sum(axis=(1, 2), keepdims=True)


_G = np.arange(MAXG + 1)
_DIFF = _G[:, None] - _G[None, :]
_TOT = _G[:, None] + _G[None, :]


def ft_probs(lh: np.ndarray, la: np.ndarray) -> np.ndarray:
    """(N, 2 + len(LINES)): P(gazdă), P(oaspete), P(total > linie) pentru LINES."""
    M = score_matrix(lh, la)
    cols = [(M * (_DIFF > 0)).sum(axis=(1, 2)), (M * (_DIFF < 0)).sum(axis=(1, 2))]
    cols += [(M * (_TOT > ln)).sum(axis=(1, 2)) for ln in LINES]
    return np.stack(cols, axis=1)


def fit_lambdas(target: np.ndarray, iters: int = 30) -> Tuple[np.ndarray, np.ndarray]:
    """Golurile așteptate (gazdă, oaspete) care reproduc cel mai bine probabilitățile fără marjă.

    target: (N, 2 + len(LINES)) cu NaN unde lipsește prețul. Levenberg-Marquardt vectorizat, reziduuri
    ponderate cu 1/sqrt(p(1-p)) (≈ divergența KL pe fiecare linie)."""
    target = np.asarray(target, dtype=float)
    n = len(target)
    mask = np.isfinite(target)
    t = np.where(mask, np.clip(target, 0.01, 0.99), 0.5)
    wt = np.where(mask, 1.0 / np.sqrt(t * (1 - t)), 0.0)
    # start: total din O2.5 (dacă există), diferența din 1X2
    tot0 = np.full(n, 2.6)
    ph, pa = np.where(mask[:, 0], t[:, 0], 0.45), np.where(mask[:, 1], t[:, 1], 0.30)
    sup = np.clip(np.log(np.maximum(ph, 0.02) / np.maximum(pa, 0.02)) * 0.55, -2.5, 2.5)
    x = np.stack([np.log(tot0 / 2) + sup / 2, np.log(tot0 / 2) - sup / 2], axis=1)
    mu = np.full(n, 1e-2)

    def resid(xx):
        return (ft_probs(np.exp(xx[:, 0]), np.exp(xx[:, 1])) - t) * wt

    r = resid(x)
    cost = (r ** 2).sum(axis=1)
    eps = 1e-4
    for _ in range(iters):
        J0 = (resid(x + np.array([eps, 0.0])) - r) / eps
        J1 = (resid(x + np.array([0.0, eps])) - r) / eps
        a, b, d = (J0 * J0).sum(1) + mu, (J0 * J1).sum(1), (J1 * J1).sum(1) + mu
        g0, g1 = (J0 * r).sum(1), (J1 * r).sum(1)
        det = a * d - b * b
        det = np.where(np.abs(det) < 1e-12, 1e-12, det)
        dx = np.stack([-(d * g0 - b * g1) / det, -(a * g1 - b * g0) / det], axis=1)
        dx = np.clip(dx, -0.5, 0.5)
        xn = np.clip(x + dx, math.log(0.05), math.log(6.0))
        rn = resid(xn)
        cn = (rn ** 2).sum(axis=1)
        ok = cn < cost
        x = np.where(ok[:, None], xn, x)
        r = np.where(ok[:, None], rn, r)
        cost = np.where(ok, cn, cost)
        mu = np.where(ok, mu * 0.3, mu * 10)
    return np.exp(x[:, 0]), np.exp(x[:, 1])


def raw_probs(lh: np.ndarray, la: np.ndarray, share: np.ndarray) -> Dict[str, np.ndarray]:
    """Probabilitățile brute pe chei, cu golurile din prima repriză ~ Poisson(share·Λ), a doua ~ Poisson((1-share)·Λ)."""
    lh, la, share = (np.asarray(v, dtype=float) for v in (lh, la, share))
    tot = lh + la
    p1 = _pois(tot * share)
    p2 = _pois(tot * (1 - share))
    M = score_matrix(lh, la)
    return {
        "H2G13": p2[:, 1:4].sum(1),
        "H2G12": p2[:, 1:3].sum(1),
        "H1U15": p1[:, :2].sum(1),
        "O15": (M * (_TOT > 1.5)).sum(axis=(1, 2)),
        "HOME": (M * (_DIFF > 0)).sum(axis=(1, 2)),
        "AWAY": (M * (_DIFF < 0)).sum(axis=(1, 2)),
        "DRAW": (M * (_DIFF == 0)).sum(axis=(1, 2)),
    }


def _logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def calibrate(key: str, p: np.ndarray, calib: Optional[Dict[str, Tuple[float, float]]] = None) -> np.ndarray:
    a, b = (CALIB if calib is None else calib).get(key, (0.0, 1.0))
    return 1 / (1 + np.exp(-(a + b * _logit(np.asarray(p, dtype=float)))))


def fit_calib(p: np.ndarray, y: np.ndarray) -> Tuple[float, float]:
    """Regresie logistică pe logit(p) (Newton, 2 parametri)."""
    z = _logit(np.asarray(p, dtype=float))
    y = np.asarray(y, dtype=float)
    w = np.array([0.0, 1.0])
    for _ in range(25):
        q = 1 / (1 + np.exp(-(w[0] + w[1] * z)))
        g = np.array([(q - y).sum(), ((q - y) * z).sum()])
        s = q * (1 - q)
        H = np.array([[s.sum(), (s * z).sum()], [(s * z).sum(), (s * z * z).sum()]]) + 1e-6 * np.eye(2)
        w = w - np.linalg.solve(H, g)
    return float(w[0]), float(w[1])


def outcomes(fh, fa, hh, ha) -> Dict[str, np.ndarray]:
    """Rezultatul fiecărei chei din scorul final (fh, fa) și de la pauză (hh, ha)."""
    fh, fa, hh, ha = (np.asarray(v, dtype=float) for v in (fh, fa, hh, ha))
    h1 = hh + ha
    h2 = fh + fa - h1
    return {"H2G13": (h2 >= 1) & (h2 <= 3), "H2G12": (h2 >= 1) & (h2 <= 2), "H1U15": h1 <= 1, "O15": fh + fa >= 2,
            "HOME": fh > fa, "AWAY": fa > fh, "DRAW": fh == fa}


# ---------------------------------------------------------------- date din DB
def league_h1_share(conn: sqlite3.Connection, until_utc: Optional[str] = None,
                    prior: float = SHARE_PRIOR) -> Dict[int, float]:
    """Ponderea golurilor din prima repriză pe ligă (meciuri terminate cu scor la pauză), micșorată spre medie."""
    q = ("SELECT league_id, SUM(ht_home+ht_away), SUM(ft_home+ft_away) FROM match WHERE status='finished' "
         "AND ht_home IS NOT NULL AND ft_home IS NOT NULL AND ht_away IS NOT NULL AND ft_away IS NOT NULL "
         "AND ht_home+ht_away <= ft_home+ft_away")
    args: List = []
    if until_utc:
        q += " AND kickoff_utc < ?"
        args.append(until_utc)
    rows = conn.execute(q + " GROUP BY league_id", args).fetchall()
    h1 = sum(r[1] or 0 for r in rows)
    ft = sum(r[2] or 0 for r in rows)
    glob = h1 / ft if ft > 500 else H1_SHARE
    return {int(r[0]): float(((r[1] or 0) + prior * glob) / ((r[2] or 0) + prior)) for r in rows if r[0] is not None} | {-1: glob}


def _line(outcome: str, line: Optional[str]) -> Optional[float]:
    try:
        return float(line) if line not in (None, "") else float(outcome.split()[-1])
    except (ValueError, IndexError):
        return None


def sb_prices(conn: sqlite3.Connection, match_ids: Iterable[int], table: str = "sb_offer") -> Dict[int, Dict]:
    """Prețurile Superbet necesare: 1X2, totaluri (meci, R1, R2) și selecțiile jucate (SB_MARKET)."""
    ids = [int(m) for m in match_ids]
    if not ids or table not in ("sb_offer", "sb_offer_close"):
        return {}
    names = ("Final", "Total goluri", "Prima repriză - Total goluri", "A doua repriză - Total goluri",
             "A doua repriză - Interval goluri")
    out: Dict[int, Dict] = {}
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        rows = conn.execute(
            f"SELECT match_id, market_name, outcome, line, price FROM {table} WHERE match_id IN "
            f"({','.join('?' * len(chunk))}) AND market_name IN ({','.join('?' * len(names))})", chunk + list(names)).fetchall()
        for mid, mk, oc, ln, pr in rows:
            if not pr or pr <= 1.0:
                continue
            d = out.setdefault(int(mid), {"1x2": {}, "ft": {}, "h1": {}, "h2": {}, "sel": {}})
            if mk == "Final":
                d["1x2"][oc] = float(pr)
            elif mk.endswith("Total goluri"):
                side = {"Total goluri": "ft", "Prima repriză - Total goluri": "h1"}.get(mk, "h2")
                x = _line(oc, ln)
                if x is not None and oc.split()[0] in ("Peste", "Sub"):
                    d[side].setdefault(x, {})[oc.split()[0]] = float(pr)
            for k, (m2, o2) in SB_MARKET.items():
                if mk == m2 and oc == o2:
                    d["sel"][k] = float(pr)
    return out


def _pairs(side: Dict[float, Dict[str, float]]) -> Dict[float, float]:
    """linie → P(peste) fără marjă, doar unde există ambele prețuri și marja e plauzibilă."""
    res = {}
    for x, d in side.items():
        if "Peste" in d and "Sub" in d and 1.0 <= 1 / d["Peste"] + 1 / d["Sub"] <= 1.20:
            res[x] = demargin([d["Peste"], d["Sub"]])[0]
    return res


def implied(pr: Dict) -> Dict[str, float]:
    """Probabilitățile Superbet fără marjă pentru chei, din piețele lor directe."""
    out: Dict[str, float] = {}
    x = pr.get("1x2", {})
    if all(k in x for k in ("1", "X", "2")) and 1.0 <= sum(1 / x[k] for k in "1X2") <= 1.25:
        ph, pd, pa = demargin([x["1"], x["X"], x["2"]])
        out.update(HOME=ph, DRAW=pd, AWAY=pa)
    ft, h1, h2 = _pairs(pr.get("ft", {})), _pairs(pr.get("h1", {})), _pairs(pr.get("h2", {}))
    if 1.5 in ft:
        out["O15"] = ft[1.5]
    if 1.5 in h1:
        out["H1U15"] = 1 - h1[1.5]
    if 0.5 in h2 and 3.5 in h2:
        out["H2G13"] = h2[0.5] - h2[3.5]
    if 0.5 in h2 and 2.5 in h2:
        out["H2G12"] = h2[0.5] - h2[2.5]
    return out


def target_row(pr: Dict) -> np.ndarray:
    """Vectorul pentru fit_lambdas din prețurile 1X2 + totaluri ale meciului."""
    row = np.full(2 + len(LINES), np.nan)
    imp = implied(pr)
    if "HOME" in imp:
        row[0], row[1] = imp["HOME"], imp["AWAY"]
    ft = _pairs(pr.get("ft", {}))
    for j, ln in enumerate(LINES):
        if ln in ft:
            row[2 + j] = ft[ln]
    return row


# ---------------------------------------------------------------- Dixon-Coles (opțional)
_DC_CACHE: Dict[Tuple[int, str], Tuple] = {}


def _dc_lambdas(conn: sqlite3.Connection, rows: List[Tuple[int, int, int, int, str]]) -> Dict[int, Tuple[float, float]]:
    from betpredict.model.data import load_history
    from betpredict.model.dc import fit_dc

    if not rows:
        return {}
    ref = min(r[4] for r in rows)
    key = (id(conn), ref[:10])
    if key not in _DC_CACHE:
        hist = load_history(conn, until_utc=ref[:10])
        t_ref = float(np.datetime64(ref[:10]).astype("datetime64[s]").astype(np.int64)) / 86400.0
        _DC_CACHE.clear()
        _DC_CACHE[key] = (fit_dc(hist, t_ref, half_life=180.0, years=2.0),)
    model = _DC_CACHE[key][0]
    H = np.array([r[1] or -1 for r in rows])
    A = np.array([r[2] or -1 for r in rows])
    L = np.array([r[3] if r[3] is not None else -1 for r in rows])
    lh, la, cov = model.lambdas(H, A, L)
    return {r[0]: (float(lh[i]), float(la[i]), float(cov[i])) for i, r in enumerate(rows)}


# ---------------------------------------------------------------- API
def batch(conn: sqlite3.Connection, match_ids: Iterable[int], table: Optional[str] = None,
          dc_weight: float = DC_W, shares: Optional[Dict[int, float]] = None) -> Dict[int, Dict]:
    """Pentru fiecare meci cu 1X2 + totaluri Superbet: {"p": {cheie: p}, "implied": {cheie: p Superbet fără marjă},
    "price": {cheie: cota}, "ev": {cheie: p·cotă − 1}, "lh", "la", "share"}. Meciurile fără prețuri lipsesc.

    table=None: oferta curentă (sb_offer), cu completare din cotele de închidere (sb_offer_close)."""
    ids = list(dict.fromkeys(int(m) for m in match_ids))
    if table:
        prices = sb_prices(conn, ids, table)
    else:
        prices = sb_prices(conn, ids, "sb_offer")
        miss = [m for m in ids if m not in prices or not prices[m]["1x2"]]
        prices.update(sb_prices(conn, miss, "sb_offer_close"))
    mids = [m for m in ids if m in prices]
    if not mids:
        return {}
    T = np.stack([target_row(prices[m]) for m in mids])
    ok = np.isfinite(T[:, :2]).all(1) & (np.isfinite(T[:, 2:]).sum(1) >= 1)
    mids = [m for m, k in zip(mids, ok) if k]
    if not mids:
        return {}
    lh, la = fit_lambdas(T[ok])
    meta = {int(r[0]): r for r in conn.execute(
        f"SELECT id, home_id, away_id, league_id, kickoff_utc FROM match WHERE id IN ({','.join('?' * len(mids))})", mids)}
    shares = shares or {}
    share = np.array([shares.get(meta[m][3] if m in meta and meta[m][3] is not None else -1, shares.get(-1, H1_SHARE))
                      for m in mids])
    if dc_weight > 0:
        dcl = _dc_lambdas(conn, [tuple(meta[m]) for m in mids if m in meta])
        for i, m in enumerate(mids):
            if m in dcl:
                w = dc_weight * dcl[m][2]
                lh[i] = lh[i] ** (1 - w) * dcl[m][0] ** w
                la[i] = la[i] ** (1 - w) * dcl[m][1] ** w
    raw = raw_probs(lh, la, share)
    out: Dict[int, Dict] = {}
    for i, m in enumerate(mids):
        p = {k: float(calibrate(k, raw[k][i:i + 1])[0]) for k in KEYS}
        price = dict(prices[m]["sel"])
        out[m] = {"p": p, "implied": implied(prices[m]), "price": price,
                  "ev": {k: p[k] * price[k] - 1 for k in price if k in p},
                  "lh": float(lh[i]), "la": float(la[i]), "share": float(share[i])}
    return out


def prob(conn: sqlite3.Connection, match_id: int, key: str, table: Optional[str] = None) -> Optional[float]:
    """Probabilitatea modelului pentru o cheie (H2G13, H2G12, H1U15, O15/OVER, HOME/1, AWAY/2, DRAW/X); None fără prețuri."""
    key = ALIASES.get(key, key)
    if key not in KEYS:
        raise KeyError(key)
    r = batch(conn, [match_id], table=table).get(int(match_id))
    return None if r is None else r["p"][key]
