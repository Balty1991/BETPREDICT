from betpredict.ingest.superavantaj import led_by_two


def _inc(goals, final=True):
    inc = [{"type": "goal", "home_score": h, "away_score": a} for h, a in goals]
    if final:
        inc.insert(0, {"type": "period", "text": "FT"})
    return {"incidents": inc}


def test_led_by_two_any_time():
    js = _inc([(1, 0), (2, 0), (2, 1), (2, 2)])  # gazdele au condus 2-0, s-a terminat 2-2
    assert led_by_two(js, True) is True and led_by_two(js, False) is False
    assert led_by_two(_inc([(0, 1), (0, 2), (1, 2)]), False) is True
    assert led_by_two(_inc([(1, 0), (1, 1)]), True) is False
    assert led_by_two(_inc([(2, 0)], final=False), True) is None  # fără final: nu decidem
    assert led_by_two({"incidents": []}, True) is None
