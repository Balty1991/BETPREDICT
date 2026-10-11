from betpredict.lab import patterns as P


def test_pattern_probs_sane():
    p = P._probs(1.5, 1.1, 0.446, 9.5)
    assert 0.5 < p["R1R2"] < 0.75 and 0 < p["H13x2"] < p["G13"] < 1 and p["O25"] < p["GGO25"] and p["C85"] < p["C75"]


def test_pattern_settlement():
    r = {"fthg": 2, "ftag": 1, "hthg": 1, "htag": 0, "hc": 5, "ac": 4}
    assert P._won("R1R2", r) and P._won("G13", r) and P._won("H13x2", r) and P._won("C85", r) and P._won("GGO25", r)
    r2 = {"fthg": 1, "ftag": 0, "hthg": 1, "htag": 0, "hc": 3, "ac": 4}
    assert not P._won("R1R2", r2) and not P._won("C75", r2) and not P._won("GGO25", r2)
