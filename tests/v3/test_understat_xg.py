import math
import sqlite3

import numpy as np

from betpredict.ingest import understat as U
from betpredict.model.xgfeat import MIN_N, xg_features


def test_parse_skips_unplayed_and_bad_rows():
    payload = {"dates": [
        {"id": "1", "isResult": True, "h": {"title": "Arsenal"}, "a": {"title": "Chelsea"}, "goals": {"h": "2", "a": "1"},
         "xG": {"h": "1.5", "a": "0.7"}, "datetime": "2024-08-17 14:00:00"},
        {"id": "2", "isResult": False, "h": {"title": "A"}, "a": {"title": "B"}, "goals": {"h": None, "a": None},
         "xG": {"h": None, "a": None}, "datetime": "2024-08-18 14:00:00"},
        {"id": "3", "isResult": True, "h": {"title": "A"}},
    ]}
    rows = U.parse(payload, "EPL", 2024)
    assert len(rows) == 1 and rows[0]["xg_h"] == 1.5 and rows[0]["day"] == "2024-08-17"


def test_current_season():
    from datetime import date
    assert U.current_season(date(2026, 10, 10)) == 2026
    assert U.current_season(date(2026, 3, 1)) == 2025


def test_xg_features_are_strictly_pre_match():
    ids = list(range(10))
    home = [1, 2] * 5
    away = [2, 1] * 5
    xg = {i: (2.0, 0.5) for i in ids}
    X, _ = xg_features(ids, home, away, xg)
    # primele MIN_N meciuri ale fiecărei echipe: NaN (fără scurgere din meciul curent)
    assert all(math.isnan(v) for v in X[0])
    assert np.isfinite(X[MIN_N]).all()
    # meciul i nu își vede propriul xG: schimbarea xG-ului ultimului meci nu schimbă feature-ul lui
    xg2 = dict(xg); xg2[9] = (9.0, 9.0)
    X2, _ = xg_features(ids, home, away, xg2)
    assert np.allclose(X[9], X2[9], equal_nan=True)


def test_xg_features_extra_rows():
    ids, home, away = [0, 1, 2, 3], [1, 2, 1, 2], [2, 1, 2, 1]
    _, Xe = xg_features(ids, home, away, {i: (1.0, 1.0) for i in ids}, extra=[(1, 2), (5, 6)])
    assert Xe.shape == (2, 5) and np.isfinite(Xe[0]).all() and math.isnan(Xe[1][0])


def test_load_xg_without_table():
    assert U.load_xg(sqlite3.connect(":memory:")) == {}
