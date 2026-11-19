import sqlite3

import numpy as np
import pytest

from betpredict.model import halves as hv


def _db():
    c = sqlite3.connect(":memory:")
    c.executescript("""
        CREATE TABLE match (id INTEGER PRIMARY KEY, league_id INTEGER, kickoff_utc TEXT, home_id INTEGER, away_id INTEGER,
            status TEXT, ft_home INTEGER, ft_away INTEGER, ht_home INTEGER, ht_away INTEGER);
        CREATE TABLE sb_offer (match_id INTEGER, market_id INTEGER, market_name TEXT, outcome TEXT, line TEXT, price REAL,
            observed_at TEXT, ref TEXT, PRIMARY KEY (match_id, market_name, outcome));
        CREATE TABLE sb_offer_close (match_id INTEGER, market_name TEXT, outcome TEXT, line TEXT, price REAL, observed_at TEXT,
            PRIMARY KEY (match_id, market_name, outcome));
    """)
    return c


def _offer(c, table, mid, lh, la, margin=1.06):
    """Prețuri Superbet sintetice generate dintr-un model cunoscut (cu marjă proporțională)."""
    c.execute("INSERT OR IGNORE INTO match VALUES (?,?,?,?,?,?,?,?,?,?)", (mid, 7, "2026-11-20T18:00:00Z", 1, 2, "notstarted",
                                                                        None, None, None, None))
    p = hv.raw_probs(np.array([lh]), np.array([la]), np.array([hv.H1_SHARE]))
    rows = [("Final", "1", "", p["HOME"][0]), ("Final", "X", "", p["DRAW"][0]), ("Final", "2", "", p["AWAY"][0])]
    fp = hv.ft_probs(np.array([lh]), np.array([la]))[0]
    for j, ln in enumerate(hv.LINES):
        rows += [("Total goluri", f"Peste {ln}", str(ln), fp[2 + j]), ("Total goluri", f"Sub {ln}", str(ln), 1 - fp[2 + j])]
    rows += [("A doua repriză - Interval goluri", "1-3", "", p["H2G13"][0]), ("A doua repriză - Interval goluri", "1-2", "", p["H2G12"][0]),
             ("Prima repriză - Total goluri", "Sub 1.5", "1.5", p["H1U15"][0]), ("Prima repriză - Total goluri", "Peste 1.5", "1.5", 1 - p["H1U15"][0])]
    for mk, oc, ln, q in rows:
        price = round(1 / (q * margin), 3)
        if table == "sb_offer":
            c.execute("INSERT INTO sb_offer VALUES (?,?,?,?,?,?,?,?)", (mid, 1, mk, oc, ln, price, "2026-11-19T10:00:00Z", None))
        else:
            c.execute("INSERT INTO sb_offer_close VALUES (?,?,?,?,?,?)", (mid, mk, oc, ln, price, "2026-11-19T10:00:00Z"))


def test_demargin_power_sums_to_one_and_keeps_order():
    p = hv.demargin([1.5, 4.2, 6.5])
    assert abs(sum(p) - 1) < 1e-9
    assert p[0] > p[1] > p[2]
    # marja cade mai mult pe cota mare decât la metoda proporțională
    prop = [1 / 6.5 / sum(1 / o for o in (1.5, 4.2, 6.5))]
    assert p[2] < prop[0]


def test_fit_lambdas_recovers_known_goal_rates():
    lh, la = np.array([1.7, 0.9, 1.2]), np.array([0.8, 1.6, 1.2])
    t = hv.ft_probs(lh, la)
    t[1, 2:4] = np.nan  # linii lipsă
    fh, fa = hv.fit_lambdas(t)
    assert np.allclose(fh, lh, atol=0.03) and np.allclose(fa, la, atol=0.03)


def test_raw_probs_consistency():
    r = hv.raw_probs(np.array([1.4]), np.array([1.1]), np.array([0.45]))
    assert abs(r["HOME"][0] + r["AWAY"][0] + r["DRAW"][0] - 1) < 1e-9
    assert r["H2G13"][0] > r["H2G12"][0]
    assert 0.5 < r["O15"][0] < 0.95 and 0.5 < r["H1U15"][0] < 0.9


def test_fit_calib_identity_on_calibrated_data():
    rng = np.random.default_rng(1)
    p = rng.uniform(0.2, 0.8, 20000)
    y = rng.uniform(size=p.size) < p
    a, b = hv.fit_calib(p, y)
    assert abs(a) < 0.08 and abs(b - 1) < 0.08


def test_outcomes_from_scores():
    o = hv.outcomes([2, 0], [1, 0], [0, 0], [1, 0])
    assert list(o["H2G13"]) == [True, False] and list(o["H2G12"]) == [True, False]
    assert list(o["H1U15"]) == [True, True] and list(o["O15"]) == [True, False]
    assert list(o["HOME"]) == [True, False] and list(o["DRAW"]) == [False, True]


def test_batch_and_prob_from_superbet_prices():
    c = _db()
    _offer(c, "sb_offer", 10, 1.6, 0.9)
    _offer(c, "sb_offer_close", 11, 1.0, 1.5)  # doar cote de închidere → completare
    res = hv.batch(c, [10, 11, 12])
    assert set(res) == {10, 11}
    r = res[10]
    assert abs(r["lh"] - 1.6) < 0.1 and abs(r["la"] - 0.9) < 0.1
    for k in hv.KEYS:
        assert 0.0 < r["p"][k] < 1.0
        if k in r["implied"]:
            assert abs(r["p"][k] - r["implied"][k]) < 0.06, k
    assert r["ev"]["H2G13"] == pytest.approx(r["p"]["H2G13"] * r["price"]["H2G13"] - 1)
    assert res[11]["p"]["AWAY"] > res[11]["p"]["HOME"]
    assert hv.prob(c, 10, "OVER") == pytest.approx(r["p"]["O15"])
    assert hv.prob(c, 10, "1") == pytest.approx(r["p"]["HOME"])
    assert hv.prob(c, 12, "H2G13") is None
    with pytest.raises(KeyError):
        hv.prob(c, 10, "NOPE")


def test_implied_needs_both_sides():
    pr = {"1x2": {"1": 2.0, "X": 3.4}, "ft": {1.5: {"Peste": 1.3}}, "h1": {}, "h2": {0.5: {"Peste": 1.3, "Sub": 3.4}}, "sel": {}}
    assert hv.implied(pr) == {}
