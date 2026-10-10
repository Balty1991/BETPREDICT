"""v4: simularea comună a unui meci (goluri pe reprize și echipe, momentul golurilor, cornere) pentru:

* piețe noi experimentale: total pe echipă, goluri pe reprize, repriza cu mai multe goluri, cornere (total/pauză);
* SuperAvantaj Superbet (echipa care conduce cu 2 goluri oricând câștigă pariul 1/2);
* Bet Builder: probabilitatea COMUNĂ a selecțiilor din același meci (inclusiv combinațiile cu preț public Superbet).

Goluri: Poisson pe echipă cu λ din model, împărțite pe reprize (s ≈ 0,444 în R1, estimat din istoricul cu scor la pauză).
Momentul golurilor: uniform în repriză. Cornere: binomial negativ (μ din predicția BSD pe linii + linia Superbet,
dispersie k), împărțite pe echipe după raportul λ și pe reprize (46% în R1).
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

HALF_SHARE = 0.444
CORNER_HT_SHARE = 0.46
DEFAULT_CORNERS = (9.8, 9.0)  # μ, k
N_SIM = 20000
MAX_G = 8


def nb_sample(rng, mu: np.ndarray, k: float, size) -> np.ndarray:
    p = k / (k + mu)
    return rng.negative_binomial(k, p, size=size)


def nb_over(mu: float, k: float, line: float) -> float:
    p = k / (k + mu)
    cdf, pmf = 0.0, p ** k
    for x in range(int(math.floor(line)) + 1):
        if x > 0:
            pmf *= (x - 1 + k) / x * (1 - p)
        cdf += pmf
    return 1 - cdf


def fit_corners(points: Sequence[Tuple[float, float]]) -> Tuple[float, float]:
    """(linie, P(peste)) → (μ, k) prin căutare pe grilă (minim pătratic)."""
    if not points:
        return DEFAULT_CORNERS
    best, bmk = 1e9, DEFAULT_CORNERS
    for mu in np.arange(5.0, 15.01, 0.1):
        for k in (5.0, 7.0, 9.0, 12.0, 18.0, 30.0):
            e = sum((nb_over(mu, k, ln) - p) ** 2 for ln, p in points)
            if e < best:
                best, bmk = e, (float(round(mu, 2)), k)
    return bmk


def simulate(lh: float, la: float, corners: Tuple[float, float] = DEFAULT_CORNERS, n: int = N_SIM, seed: int = 5,
             half_share: float = HALF_SHARE) -> Dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    s = half_share
    h1, a1 = rng.poisson(lh * s, n), rng.poisson(la * s, n)
    h2, a2 = rng.poisson(lh * (1 - s), n), rng.poisson(la * (1 - s), n)
    mu, k = corners
    sh = 0.5 + 0.25 * (lh - la) / max(0.2, lh + la)  # favorita are mai multe cornere
    ch = nb_sample(rng, np.full(n, mu * sh), k, n)
    ca = nb_sample(rng, np.full(n, mu * (1 - sh)), k, n)
    ch1, ca1 = rng.binomial(ch, CORNER_HT_SHARE), rng.binomial(ca, CORNER_HT_SHARE)
    return {"h1": h1, "a1": a1, "h2": h2, "a2": a2, "h": h1 + h2, "a": a1 + a2, "ch": ch, "ca": ca, "ch1": ch1, "ca1": ca1,
            **_leads(rng, h1, a1, h2, a2)}


def _leads(rng, h1, a1, h2, a2) -> Dict[str, np.ndarray]:
    mx, mn = _lead_path(rng, h1, a1, h2, a2)
    return {"lead1_h": mx >= 1, "lead2_h": mx >= 2, "lead1_a": mn <= -1, "lead2_a": mn <= -2}


def _lead_path(rng, x1, y1, x2, y2):
    """Diferența maximă și minimă (gazde − oaspeți) pe parcursul meciului; momentele golurilor uniform în repriză."""
    n = len(x1)
    G = MAX_G
    Ts, Ss = [], []
    for cnt, sign, off in ((x1, 1, 0.0), (y1, -1, 0.0), (x2, 1, 45.0), (y2, -1, 45.0)):
        t = rng.uniform(0, 45, (n, G)) + off
        t[np.arange(G)[None, :] >= np.minimum(cnt, G)[:, None]] = np.inf
        Ts.append(t)
        Ss.append(np.full((n, G), sign))
    T, S = np.concatenate(Ts, 1), np.concatenate(Ss, 1)
    order = np.argsort(T, 1)
    So = np.take_along_axis(S, order, 1) * np.isfinite(np.take_along_axis(T, order, 1))
    c = np.cumsum(So, 1)
    return c.max(1), c.min(1)


# ------------------------------------------------------------------ selecții (predicate pe simulare)
def _n(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.replace("ş", "s").replace("ș", "s").replace("ţ", "t").replace("ț", "t"))
    return re.sub(r"\s+", " ", "".join(c for c in s if not unicodedata.combining(c))).strip().lower()


Pred = Callable[[Dict[str, np.ndarray]], np.ndarray]


def _side(tok: str) -> Optional[str]:
    return {"home": "h", "away": "a"}.get(tok)


def parse_leg(text: str, home: str, away: str) -> Optional[Tuple[str, Pred]]:
    """Text Superbet (o selecție dintr-o combinație) → (cheie canonică, predicat). None dacă nu o putem modela."""
    t = _n(text)
    hn, an = _n(home), _n(away)
    if hn:
        t = t.replace(hn, "home")
    if an:
        t = t.replace(an, "away")
    t = t.rstrip(".")
    m = re.fullmatch(r"(peste|sub) ([\d.]+) goluri in prima repriza", t)
    if m:
        ln = float(m.group(2))
        return (f"ht_{m.group(1)}_{ln}", (lambda S, ln=ln, o=m.group(1): ((S["h1"] + S["a1"]) > ln) if o == "peste" else ((S["h1"] + S["a1"]) < ln)))
    m = re.fullmatch(r"(peste|sub) ([\d.]+) goluri", t)
    if m:
        ln = float(m.group(2))
        return (f"ft_{m.group(1)}_{ln}", (lambda S, ln=ln, o=m.group(1): ((S["h"] + S["a"]) > ln) if o == "peste" else ((S["h"] + S["a"]) < ln)))
    m = re.fullmatch(r"(peste|sub) ([\d.]+) cornere", t)
    if m:
        ln = float(m.group(2))
        return (f"corners_{m.group(1)}_{ln}", (lambda S, ln=ln, o=m.group(1): ((S["ch"] + S["ca"]) > ln) if o == "peste" else ((S["ch"] + S["ca"]) < ln)))
    m = re.fullmatch(r"(home|away) (peste|sub) ([\d.]+) goluri", t)
    if m:
        sd, ln = _side(m.group(1)), float(m.group(3))
        return (f"tt_{sd}_{m.group(2)}_{ln}", (lambda S, sd=sd, ln=ln, o=m.group(2): (S[sd] > ln) if o == "peste" else (S[sd] < ln)))
    m = re.fullmatch(r"(prima repriza - )?(home|away) castiga sau egal", t)
    if m:
        ht = bool(m.group(1))
        sd = _side(m.group(2))
        o = "a" if sd == "h" else "h"
        return (f"{'ht_' if ht else ''}dc_{sd}x", (lambda S, sd=sd, o=o, ht=ht: (S[sd + "1"] >= S[o + "1"]) if ht else (S[sd] >= S[o])))
    m = re.fullmatch(r"(prima repriza - )?egal sau (home|away) castiga", t)
    if m:
        ht = bool(m.group(1))
        sd = _side(m.group(2))
        o = "a" if sd == "h" else "h"
        return (f"{'ht_' if ht else ''}dc_x{sd}", (lambda S, sd=sd, o=o, ht=ht: (S[sd + "1"] >= S[o + "1"]) if ht else (S[sd] >= S[o])))
    m = re.fullmatch(r"(home|away) conduce oricand", t)
    if m:
        sd = _side(m.group(1))
        return (f"leads_{sd}", lambda S, sd=sd: S["lead1_" + sd])
    m = re.fullmatch(r"(home|away) castiga", t)
    if m:
        sd = _side(m.group(1))
        o = "a" if sd == "h" else "h"
        return (f"win_{sd}", lambda S, sd=sd, o=o: S[sd] > S[o])
    if t in ("ambele echipe marcheaza",):
        return ("btts_yes", lambda S: (S["h"] > 0) & (S["a"] > 0))
    m = re.fullmatch(r"(home|away) marcheaza in ambele reprize", t)
    if m:
        sd = _side(m.group(1))
        return (f"scores_both_halves_{sd}", lambda S, sd=sd: (S[sd + "1"] > 0) & (S[sd + "2"] > 0))
    m = re.fullmatch(r"(home|away) castiga oricare din reprize", t)
    if m:
        sd = _side(m.group(1))
        o = "a" if sd == "h" else "h"
        return (f"wins_a_half_{sd}", lambda S, sd=sd, o=o: (S[sd + "1"] > S[o + "1"]) | (S[sd + "2"] > S[o + "2"]))
    return None


def parse_combo(market_name: str, outcome: str, home: str, away: str) -> Optional[List[Tuple[str, Pred]]]:
    """Combinațiile Superbet cunoscute → listă de selecții. None dacă vreo selecție nu e modelabilă."""
    mn, oc = _n(market_name), _n(outcome)
    legs: List[str] = []
    res = {"1": f"{home} castiga", "x": "__draw", "2": f"{away} castiga",
           "1x": f"{home} castiga sau egal", "x2": f"egal sau {away} castiga", "12": "__12"}
    m = re.fullmatch(r"(1x2|sansa dubla) & total goluri \(([\d.]+)\)", mn)
    if m:
        a, _, b = oc.partition(" & ")
        legs = [res.get(a, ""), f"{b} goluri"]
    elif mn == "1x2 & gg":
        a, _, b = oc.partition(" & ")
        legs = [res.get(a, ""), "ambele echipe marcheaza" if b == "da" else "__nogg"]
    elif mn == "total goluri & gg":
        a, _, b = oc.partition(" & ")
        legs = [f"{a} goluri", "ambele echipe marcheaza" if b == "da" else "__nogg"]
    elif mn == "total goluri prima repriza & total goluri":
        a, _, b = oc.partition(" & ")
        legs = [f"{a} goluri in prima repriza", f"{b} goluri"]
    else:
        legs = [x.strip() for x in outcome.split(";")]
    out = []
    for lg in legs:
        if lg == "__draw":
            out.append(("draw", lambda S: S["h"] == S["a"]))
        elif lg == "__12":
            out.append(("dc_12", lambda S: S["h"] != S["a"]))
        elif lg == "__nogg":
            out.append(("btts_no", lambda S: (S["h"] == 0) | (S["a"] == 0)))
        else:
            p = parse_leg(lg, home, away) if lg else None
            if p is None:
                return None
            out.append(p)
    return out or None


def joint(S: Dict[str, np.ndarray], legs: Sequence[Tuple[str, Pred]]) -> float:
    m = np.ones(len(S["h"]), bool)
    for _, f in legs:
        m &= f(S)
    return float(m.mean())


# ------------------------------------------------------------------ piețe experimentale (din simulare)
def extra_markets(S: Dict[str, np.ndarray]) -> Dict[str, float]:
    h, a = S["h"], S["a"]
    t1, t2 = S["h1"] + S["a1"], S["h2"] + S["a2"]
    c = S["ch"] + S["ca"]
    out: Dict[str, float] = {}
    for ln in (0.5, 1.5, 2.5):
        out[f"team_total_home|{ln}|OVER"] = float((h > ln).mean())
        out[f"team_total_away|{ln}|OVER"] = float((a > ln).mean())
    for ln in (0.5, 1.5):
        out[f"ht_over_under|{ln}|OVER"] = float((t1 > ln).mean())
        out[f"h2_over_under|{ln}|OVER"] = float((t2 > ln).mean())
    out["half_most_goals|0|FIRST"] = float((t1 > t2).mean())
    out["half_most_goals|0|EQUAL"] = float((t1 == t2).mean())
    out["half_most_goals|0|SECOND"] = float((t2 > t1).mean())
    for ln in (8.5, 9.5, 10.5):
        out[f"corners_over_under|{ln}|OVER"] = float((c > ln).mean())
    for ln in (3.5, 4.5, 5.5):
        out[f"ht_corners_over_under|{ln}|OVER"] = float(((S["ch1"] + S["ca1"]) > ln).mean())
    return {k: round(v, 4) for k, v in out.items()}


def superavantaj(S: Dict[str, np.ndarray]) -> Dict[str, float]:
    """Câștigul de probabilitate al SuperAvantaj pe 1 și pe 2: P(câștigă SAU conduce oricând cu 2) − P(câștigă)."""
    h, a = S["h"], S["a"]
    wh, wa = h > a, a > h
    return {"home": round(float((wh | S["lead2_h"]).mean() - wh.mean()), 4),
            "away": round(float((wa | S["lead2_a"]).mean() - wa.mean()), 4)}
