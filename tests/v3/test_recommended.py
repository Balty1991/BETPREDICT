from betpredict.robot import is_recommended


def test_recommended_thresholds():
    assert is_recommended(0.65, 1.70, 0.105, "A")
    assert not is_recommended(0.58, 1.90, 0.10, "A")      # p sub 60%
    assert not is_recommended(0.62, 2.40, 0.49, "B")      # cotă peste 2.20
    assert not is_recommended(0.80, 1.20, -0.04, "A")     # EV negativ
    assert not is_recommended(0.70, 1.60, 0.12, "C")      # grad C
    assert not is_recommended(0.70, 1.10, 0.01, "A")      # cotă sub 1.15
    assert not is_recommended(0.70, 1.60, 0.12, "A", healthy=False)
