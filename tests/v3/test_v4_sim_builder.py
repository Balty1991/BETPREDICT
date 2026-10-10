"""v4: simularea comună, parserul de selecții Superbet, SuperAvantaj, Bet Builder."""
import numpy as np

from betpredict.model import sim as SIM


def test_sim_consistency():
    S = SIM.simulate(1.6, 1.1, n=40000, seed=1)
    assert abs(S["h"].mean() - 1.6) < 0.05 and abs((S["h1"] + S["a1"]).mean() - 2.7 * SIM.HALF_SHARE) < 0.05
    assert np.all(S["lead2_h"] <= S["lead1_h"])  # cine conduce cu 2 a condus și cu 1
    assert np.all(S["lead2_h"][(S["h"] - S["a"]) >= 2])  # final +2 ⇒ a condus cu 2
    sa = SIM.superavantaj(S)
    assert 0 < sa["home"] < 0.06 and 0 < sa["away"] < 0.06
    ex = SIM.extra_markets(S)
    assert ex["team_total_home|0.5|OVER"] > ex["team_total_home|1.5|OVER"]
    assert abs(ex["half_most_goals|0|FIRST"] + ex["half_most_goals|0|EQUAL"] + ex["half_most_goals|0|SECOND"] - 1) < 1e-3


def test_nb_fit_roundtrip():
    pts = [(ln, SIM.nb_over(10.2, 9.0, ln)) for ln in (8.5, 9.5, 10.5)]
    mu, k = SIM.fit_corners(pts)
    assert abs(mu - 10.2) < 0.3


def test_parse_legs_and_combos():
    H, A = "Beerschot VA", "RFC Liege"
    S = {"h": np.array([2]), "a": np.array([1]), "h1": np.array([1]), "a1": np.array([0]), "h2": np.array([1]), "a2": np.array([1]),
         "ch": np.array([6]), "ca": np.array([3]), "ch1": np.array([3]), "ca1": np.array([1]),
         "lead1_h": np.array([True]), "lead1_a": np.array([False]), "lead2_h": np.array([False]), "lead2_a": np.array([False])}
    cases = {
        ("x", "Beerschot VA câştigă sau egal; RFC Liege sub 2.5 goluri; Beerschot VA peste 1.5 goluri"): 1.0,
        ("x", "Sub 3.5 goluri; Sub 10.5 cornere"): 1.0,
        ("x", "Sub 5.5 goluri; Peste 0.5 goluri; Sub 2.5 goluri în prima repriză; Peste 5.5 cornere"): 1.0,
        ("1X2 & Total goluri (2.5)", "1 & Peste 2.5"): 1.0,
        ("1X2 & GG", "X & Da"): 0.0,
        ("Total goluri prima repriză & Total goluri", "Sub 0.5 & Peste 1.5"): 0.0,
        ("x", "Beerschot VA conduce oricând; Beerschot VA câştigă sau egal"): 1.0,
        ("x", "Beerschot VA câștigă oricare din reprize; Beerschot VA marchează în ambele reprize"): 1.0,
    }
    for (mn, oc), want in cases.items():
        legs = SIM.parse_combo(mn, oc, H, A)
        assert legs, oc
        assert SIM.joint(S, legs) == want, oc
    assert SIM.parse_combo("x", "Beerschot VA câștigă după ce a fost condusă; Peste 1.5 goluri", H, A) is None


def test_anchored_lambdas_follow_market():
    from betpredict.builder.betbuilder import _grid_probs
    A = np.array([1.5]); B = np.array([1.0])
    h, d, o = _grid_probs(A, B)
    assert 0.4 < h[0, 0] < 0.5 and 0.2 < d[0, 0] < 0.3 and 0.4 < o[0, 0] < 0.5
