import sqlite3

from betpredict.ingest.multibook import rows_from_comparison
from betpredict.robot.engine import blend_pinnacle
from betpredict.clv import pinnacle_fair_close
from betpredict.store import db as DB, repo

CMP = {"event_id": 7, "markets": {
    "1x2": {"HOME": {"outcome": "HOME", "bookmakers": {"pinnacle": {"decimal_odds": 2.0}, "bet365": {"decimal_odds": 1.9}, "bwin": {"decimal_odds": 2.1}}},
            "DRAW": {"outcome": "DRAW", "bookmakers": {"pinnacle": {"decimal_odds": 3.5}, "bet365": {"decimal_odds": 3.4}}},
            "AWAY": {"outcome": "AWAY", "bookmakers": {"bet365": {"decimal_odds": 4.0}}}},
    "over_under_25": {"over": {"outcome": "over", "bookmakers": {"a": {"decimal_odds": 1.8}, "b": {"decimal_odds": 1.9}}}},
    "asian_handicap": {"x": {"outcome": "HOME", "bookmakers": {"a": {"decimal_odds": 1.9}}}}}}


def test_rows_from_comparison():
    rows = rows_from_comparison(CMP, "2026-10-11T08:00:00Z", {(7, "1x2", 0.0, "HOME"): 2.2})
    by = {(r["source"], r["market"], r["outcome"]): r for r in rows}
    assert by[("bsd_consensus", "1x2", "HOME")]["decimal"] == 2.0 and by[("bsd_consensus", "1x2", "HOME")]["opening_decimal"] == 2.2
    assert by[("bsd:pinnacle", "1x2", "HOME")]["decimal"] == 2.0 and by[("bsd_best", "1x2", "HOME")]["decimal"] == 2.1
    assert ("bsd_consensus", "1x2", "AWAY") not in by  # o singură casă → fără consens
    assert by[("bsd_consensus", "over_under", "OVER")]["line"] == 2.5
    assert not any(r["market"] == "asian_handicap" for r in rows)


def test_blend_pinnacle():
    m = {("1x2", 0.0, "HOME"): 0.50, ("btts", 0.0, "YES"): 0.55}
    out = blend_pinnacle(m, {("1x2", 0.0, "HOME"): 0.60})
    assert 0.57 < out[("1x2", 0.0, "HOME")] < 0.60 and out[("btts", 0.0, "YES")] == 0.55
    assert blend_pinnacle(m, {}) is m


def test_pinnacle_fair_close():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row; DB.init_db(c)
    rows = [{"match_id": 1, "market": "1x2", "line": 0.0, "period": "FT", "outcome": o, "decimal": d, "source": "bsd:pinnacle",
             "observed_at": "2026-10-11T17:00:00Z"} for o, d in (("HOME", 2.0), ("DRAW", 3.5), ("AWAY", 4.0))]
    repo.insert_odds(c, rows)
    f = pinnacle_fair_close(c, 1, "1x2", 0.0, "HOME", "2026-10-11T18:00:00Z")
    s = 1 / 2.0 + 1 / 3.5 + 1 / 4.0
    assert abs(f - 2.0 * s) < 1e-3
    assert pinnacle_fair_close(c, 1, "1x2", 0.0, "HOME", "2026-10-11T16:00:00Z") is None
