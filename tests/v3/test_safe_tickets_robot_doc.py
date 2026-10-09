import math
from datetime import datetime, timezone

from betpredict.builder.tickets import SAFE_TARGETS, build_safe_variant
from betpredict.publish.robot import backtest_summary, model_label, next_retrain, thresholds
from tests.v3.test_positive_ev_tickets import cand


def test_safe_ticket_low_odds_highest_probability():
    pool = [cand(i, 1.20 + 0.01 * (i % 20), 0.80 - 0.002 * i, p_market=0.76) for i in range(40)]
    pool += [cand(100 + i, 1.30, 0.60, grade="C") for i in range(5)]  # grad C cu p mic — exclus
    pool += [cand(200 + i, 1.80, 0.70) for i in range(10)]  # cote prea mari — excluse
    for target in SAFE_TARGETS:
        res = build_safe_variant(pool, target, {})
        assert res, target
        legs, reasons = res
        total = math.prod(c.odds for c in legs)
        assert target * 0.85 <= total <= target * 1.2
        assert all(1.15 <= c.odds <= 1.40 and c.grade in ("A", "B") for c in legs)
        assert "A/B)" in reasons[0]
        assert len({c.match_id for c in legs}) == len(legs)


def test_safe_ticket_published_even_with_negative_ev():
    # piața e mai sigură decât modelul → EV ajustat negativ, dar biletul sigur se construiește oricum
    pool = [cand(i, 1.25, 0.74, p_market=0.78) for i in range(30)]
    res = build_safe_variant(pool, 2, {})
    assert res and all(c.ev_adj < 0 for c in res[0])


def test_safe_ticket_falls_back_to_1_15():
    pool = [cand(i, 1.17, 0.86) for i in range(30)]
    res = build_safe_variant(pool, 2, {})
    assert res and "1.15" in res[1][0]


def test_robot_doc_parts():
    assert model_label("robot-v1") == "robot-v2" and model_label(None) == "robot-v2"
    assert model_label("robot-v3") == "robot-v3"
    nr = next_retrain(datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc))
    assert nr.weekday() == 0 and nr.isoformat().startswith("2026-10-12T03:45")
    nr2 = next_retrain(datetime(2026, 10, 12, 4, 0, tzinfo=timezone.utc))
    assert nr2.isoformat().startswith("2026-10-19")
    th = {t["key"]: t for t in thresholds({"thresholds": {"1x2": {"min_ev": 0.08, "source": "learned", "n": 120}}})}
    assert th["1x2"]["min_ev"] == 0.08 and th["1x2"]["source"] == "learned" and th["btts"]["source"] == "backtest"
    bt = backtest_summary()
    assert bt and bt["markets"] and any(m["v2"] for m in bt["markets"])


def test_safe_ticket_grade_c_fallback_and_excluded_markets():
    pool = [cand(i, 1.28, 0.80, grade="C") for i in range(20)]
    res = build_safe_variant(pool, 3, {})
    assert res and "72%" in res[1][0]
    assert build_safe_variant(pool, 3, {}, excluded=["1x2"]) is None


def test_exposure_cap_filters_overused_selections():
    from betpredict.builder.tickets import MAX_TICKETS_PER_SELECTION, _available

    pool = [cand(i, 1.3, 0.8) for i in range(5)]
    used = {0: MAX_TICKETS_PER_SELECTION, 1: 1}
    ids = [c.prediction_id for c in _available(pool, used)]
    assert 0 not in ids and 1 in ids and len(ids) == 4


def test_exposure_report_counts_overlap():
    from betpredict.publish.outputs import exposure_report

    def leg(pid):
        return {"prediction_id": pid, "match_id": pid, "market": "1x2", "selection": "HOME", "label": "1", "home": "H", "away": "A",
                "kickoff_utc": "2026-10-10T12:00:00Z"}
    ts = [{"id": 1, "status": "pending", "stake_units": 0.5, "legs": [leg(1), leg(2)]},
          {"id": 2, "status": "pending", "stake_units": 0.3, "legs": [leg(2), leg(3)]},
          {"id": 3, "status": "pending", "stake_units": 0.1, "legs": [leg(4)]}]
    r = exposure_report(ts)
    assert r["max_tickets_on_one_selection"] == 2 and r["shared_pairs"] == 1 and r["independent_tickets"] == 1
    assert r["top"][0]["prediction_id"] == 2 and r["top"][0]["stake_units"] == 0.8
    assert [t["overlap"] for t in ts] == [1, 1, 0]


def test_safety_score_needs_both_high():
    from betpredict.publish.safety import is_high_safety, safety_score

    assert safety_score(0.95, 50) == 56
    assert safety_score(0.70, 80) == 71
    assert safety_score(0.95, 50) < safety_score(0.70, 80)
    assert safety_score(0.6, None, "A") > safety_score(0.6, None, "D")
    assert safety_score(None, 80) is None
    assert is_high_safety(0.62, "B") and not is_high_safety(0.9, "C") and not is_high_safety(0.55, "A") and not is_high_safety(0.8, "A", None)
