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
