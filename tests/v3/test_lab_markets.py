import math
import random
from datetime import date, timedelta

import numpy as np

from betpredict.lab import markets as LM


def _rows(n=2400, seed=7):
    """Meciuri sintetice: rezultate Poisson din λ adevărați, cote corecte cu marjă → piața e „cinstită”."""
    rng = random.Random(seed)
    nprng = np.random.default_rng(seed)
    out = []
    d0 = date(2021, 8, 1)
    teams = [f"T{i}" for i in range(20)]
    for i in range(n):
        lh, la = rng.uniform(0.8, 2.0), rng.uniform(0.6, 1.6)
        g = np.arange(11)
        ph = np.exp(-lh) * lh ** g / np.array([math.factorial(int(x)) for x in g])
        pa = np.exp(-la) * la ** g / np.array([math.factorial(int(x)) for x in g])
        M = ph[:, None] * pa[None, :]
        H, D, A = np.tril(M, -1).sum(), np.trace(M), np.triu(M, 1).sum()
        po = 1 - sum(M[a, b] for a in range(11) for b in range(11) if a + b <= 2)
        o = {"avg_h": 1 / (1.05 * H), "avg_d": 1 / (1.05 * D), "avg_a": 1 / (1.05 * A), "avg_o25": 1 / (1.05 * po), "avg_u25": 1 / (1.05 * (1 - po))}
        hh, ha = nprng.poisson(lh * 0.45), nprng.poisson(la * 0.45)
        h, a = hh + nprng.poisson(lh * 0.55), ha + nprng.poisson(la * 0.55)
        day = d0 + timedelta(days=i // 8)
        season = f"{day.year % 100:02d}{(day.year + 1) % 100:02d}" if day.month >= 7 else f"{(day.year - 1) % 100:02d}{day.year % 100:02d}"
        home, away = rng.sample(teams, 2)
        out.append({"div": "E2" if i % 2 else "E0", "season": season, "day": day.isoformat(), "home": home, "away": away,
                    **o, **{k.replace("avg_", "avgc_"): v for k, v in o.items()},
                    "fthg": h, "ftag": a, "hthg": hh, "htag": ha, "hc": int(nprng.poisson(5.4)), "ac": int(nprng.poisson(4.6))})
    return out


def test_probabilities_match_rules_on_simple_case():
    p = LM.probs(np.array([1.5]), np.array([1.1]), 0.45)
    assert abs(p["H"][0] + p["DCX2"][0] - 1) < 1e-5 and abs(p["GG"][0] + p["NG"][0] - 1) < 1e-5
    assert p["R1O25"][0] < p["R1O15"][0] < p["H1O05"][0] and p["H13x2"][0] < p["H2G13"][0]
    r = {"fthg": 2, "ftag": 1, "hthg": 0, "htag": 1, "hc": 6, "ac": 3}
    assert LM.won("HWEH", r) and LM.won("AWEH", r) and LM.won("H2MORE", r) and LM.won("R1O25", r) and not LM.won("R1O25", {**r, "ftag": 0, "htag": 0, "hthg": 1, "fthg": 2})
    assert LM.won("C85", r) and not LM.won("HC45", {**r, "hc": 4})


def test_fair_market_has_no_lift_and_few_robust_strategies():
    doc = LM.run(_rows(), log=lambda *_: None)
    assert doc["matches"] == 2400 and doc["configs_tested"] > 0
    m = {x["key"]: x for x in doc["markets"]}
    # piață reală, cote corecte: intră cam cât promite prețul
    assert 0.9 < m["O25"]["test"]["lift"] < 1.1
    assert doc["significant_both"] <= 3
