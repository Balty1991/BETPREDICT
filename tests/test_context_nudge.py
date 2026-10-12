from betpredict.robot.engine import absence_edge, context_nudge


def test_no_context_leaves_probability():
    p, note = context_nudge(0.62, ("1x2", 0.0, "HOME"), {})
    assert p == 0.62 and note is None


def test_doubtful_does_not_count():
    ctx = {"absences": {"home": [{"status": "doubtful"}, {"status": "doubtful"}], "away": []}}
    assert absence_edge(ctx) == 0
    p, note = context_nudge(0.62, ("1x2", 0.0, "HOME"), ctx)
    assert p == 0.62 and note is None


def test_home_absences_cut_home_and_lift_away():
    ctx = {"absences": {"home": [{"status": "injured"}, {"status": "suspended"}, {"status": "injured"}], "away": []}}
    p_h, note = context_nudge(0.62, ("1x2", 0.0, "HOME"), ctx)
    p_a, _ = context_nudge(0.22, ("1x2", 0.0, "AWAY"), ctx)
    assert p_h == 0.605
    assert p_a == 0.235
    assert note and "Gazdele" in note


def test_nudge_is_capped():
    ctx = {"absences": {"home": [{"status": "injured"}] * 8, "away": []}}
    p, _ = context_nudge(0.70, ("1x2", 0.0, "HOME"), ctx)
    assert p == 0.685


def test_confirmed_lineup_overrides_squad():
    ctx = {
        "absences": {"home": [{"status": "injured"}] * 5, "away": []},
        "lineups": {"unavailable": {"home": [], "away": [{"status": "suspended"}, {"status": "out"}]}},
    }
    assert absence_edge(ctx) == -2
    p, note = context_nudge(0.40, ("1x2", 0.0, "AWAY"), ctx)
    assert p == 0.39
    assert note and "Oaspeții" in note


def test_goals_markets_move_less():
    ctx = {"absences": {"away": [{"status": "injured"}, {"status": "injured"}], "home": []}}
    p_over, _ = context_nudge(0.55, ("over_under", 2.5, "OVER"), ctx)
    p_under, _ = context_nudge(0.45, ("over_under", 2.5, "UNDER"), ctx)
    assert p_over == 0.542
    assert p_under == 0.458
