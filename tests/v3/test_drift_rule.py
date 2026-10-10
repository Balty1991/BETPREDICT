from betpredict.robot import engine


def test_drift_rule_constant_and_reason():
    assert engine.DRIFT_BLOCK == 0.05
    src = open(engine.__file__, encoding="utf-8").read()
    assert "drift > DRIFT_BLOCK" in src
