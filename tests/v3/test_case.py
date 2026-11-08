"""Cazul pe meci: o selecție fără fapte care o susțin nu intră pe bilet."""

from betpredict.builder.case import support_lines

AWAY = {
    "form": {"home": {"ppm": 1.1}, "away": {"ppm": 1.8}},
    "standings": {"home": {"position": 12}, "away": {"position": 4}},
    "h2h": {"total": 6, "home_wins": 1, "draws": 1, "away_wins": 4, "avg_goals": 2.1, "btts_rate": 0.33},
}
HOME = {
    "form": {"home": {"ppm": 2.1}, "away": {"ppm": 0.9}},
    "standings": {"home": {"position": 2}, "away": {"position": 14}},
}


def test_away_under_is_kept_when_the_match_says_so():
    lines = support_lines("bb", "1X2 & Total goluri (2.5)|2 & Sub 2.5", AWAY, 0.9, 1.3)
    assert lines
    assert any("Formă" in x or "Clasament" in x for x in lines)
    assert any("sub 2.5" in x for x in lines)


def test_away_is_rejected_when_the_home_side_is_stronger():
    assert support_lines("bb", "1X2 & Total goluri (2.5)|2 & Sub 2.5", HOME, 1.8, 0.8) is None


def test_under_is_rejected_when_expected_goals_are_high():
    assert support_lines("bb", "Șansă dublă & Total goluri (2.5)|12 & Sub 2.5", AWAY, 1.8, 1.6) is None


def test_btts_no_needs_a_low_scoring_side():
    assert support_lines("btts", "NO", {}, 0.7, 1.4)
    assert support_lines("btts", "NO", {}, 1.4, 1.5) is None


def test_home_pick_is_rejected_when_the_away_side_leads():
    ctx = {"form": {"home": {"ppm": 0.60}, "away": {"ppm": 0.90}},
           "standings": {"home": {"position": 13}, "away": {"position": 9}}}
    assert support_lines("bb", "1X2 & Interval goluri|1 & 3-6", ctx, 1.6, 1.2) is None


def test_away_pick_is_rejected_when_the_table_favors_home():
    ctx = {"standings": {"home": {"position": 3}, "away": {"position": 17}}}
    assert support_lines("bb", "1X2 & Total goluri (4.5)|2 & Sub 4.5", ctx, 1.50, 1.20) is None


def test_shown_lines_do_not_argue_the_other_side():
    lines = support_lines("bb", "1X2 & Total goluri (2.5)|2 & Sub 2.5", AWAY, 0.9, 1.3)
    assert lines
    assert all(not x.startswith("Clasament: gazde") for x in lines)
    assert any(x.startswith("Formă: oaspeți") or x.startswith("Clasament: oaspeți") for x in lines)
