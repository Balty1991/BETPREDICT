from datetime import datetime, timezone

from betpredict.builder import discovery as D


def _rows(key, n, hit_every, price, start_day=1):
    out = []
    for i in range(n):
        ko = f"2026-11-{start_day + i // 40:02d}T15:{i % 40:02d}:00Z"
        out.append((key, ko, price, i % hit_every != 0))
    return out


def test_candidate_needs_size_roi_and_both_halves():
    # 1.40, intră 5 din 6 (83%) → ROI +17%, pe ambele jumătăți
    good = _rows("H1O05", 200, 6, 1.40)
    small = _rows("H2O05", 60, 6, 1.40)          # prea puține
    bad = _rows("G23", 200, 2, 1.50)            # intră 50% la 1.50 → −25%
    st = {s["key"]: s for s in D.scan(None, datetime(2026, 11, 20, tzinfo=timezone.utc), good + small + bad)}
    assert D._is_candidate(st["H1O05"]) and not D._is_candidate(st["H2O05"]) and not D._is_candidate(st["G23"])


def test_probation_then_active_then_dropped():
    import sqlite3

    c = sqlite3.connect(":memory:")
    now = datetime(2026, 11, 20, tzinfo=timezone.utc)
    hist = _rows("H1O05", 200, 6, 1.40)
    assert D.update(c, now, hist)["proba"] == ["H1O05@1.25"]
    assert not D.active_specs(c)
    # după găsire: 100 de selecții noi, tot pe plus → activă
    later = datetime(2026, 12, 10, tzinfo=timezone.utc)
    fwd = [(k, ko.replace("2026-11-", "2026-12-"), p, w) for k, ko, p, w in _rows("H1O05", 100, 6, 1.40)]
    assert D.update(c, later, hist + fwd)["activ"] == ["H1O05@1.25"]
    assert any(v[1] == "H1O05" for v in D.active_specs(c).values())
    # apoi pierde clar pe meciurile noi → scoasă
    worse = [(k, ko.replace("2026-11-", "2026-12-"), p, i % 2 == 0) for i, (k, ko, p, _) in enumerate(_rows("H1O05", 100, 6, 1.40))]
    assert D.update(c, later, hist + worse)["scos"] == ["H1O05@1.25"]
