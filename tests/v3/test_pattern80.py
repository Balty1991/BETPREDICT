import json
import sqlite3
from datetime import datetime, timezone

from betpredict.builder import pattern80 as P
from betpredict.store import db as DB


def _db():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row; DB.init_db(c)
    return c


def _pred(c, mid, market, line, sel, p, sb, ko="2026-10-17T15:00:00Z", result=None):
    c.execute("INSERT OR IGNORE INTO match (id, kickoff_utc, home_name, away_name, status, league_id) VALUES (?,?,?,?,?,?)",
              (mid, ko, f"H{mid}", f"A{mid}", "scheduled", mid))
    c.execute("""INSERT INTO prediction (match_id, model_version, market, line, selection, p_calibrated, p_model, period, result, reasons_json, created_at)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (mid, "t", market, line, sel, p, p, "FT", result,
                 json.dumps({"odds_alt": {"superbet": sb}}), "2026-10-17T05:00:00Z"))


def test_pattern_tickets_only_good_markets_and_distinct_matches():
    c = _db()
    for i in range(1, 61):
        _pred(c, i, "over_under", 1.5, "OVER", 0.86, 1.20)
    for i in range(61, 65):
        _pred(c, i, "over_under", 4.5, "UNDER", 0.95, 1.20)  # piață scoasă din tipar
    rep = P.build(c, datetime(2026, 10, 17, 6, tzinfo=timezone.utc).date(), datetime(2026, 10, 17, 6, tzinfo=timezone.utc))
    assert len(rep["tickets"]) == 2
    legs = c.execute("SELECT match_id, selection, prediction_id FROM ticket_leg").fetchall()
    assert all(l["selection"] == "OVER" and l["prediction_id"] for l in legs)
    assert len({l["match_id"] for l in legs}) == len(legs)
    assert P.build(c, datetime(2026, 10, 17, 6, tzinfo=timezone.utc).date(), datetime(2026, 10, 17, 6, tzinfo=timezone.utc)).get("skipped_existing")


def test_pattern_doc_splits_good_and_rest():
    c = _db()
    _pred(c, 1, "over_under", 1.5, "OVER", 0.85, 1.25, ko="2026-10-15T15:00:00Z", result="won")
    _pred(c, 2, "over_under", 4.5, "UNDER", 0.9, 1.20, ko="2026-10-15T15:00:00Z", result="lost")
    d = P.pattern_doc(c, datetime(2026, 10, 17, tzinfo=timezone.utc))
    good, rest = d["groups"][0]["all"], d["groups"][1]["all"]
    assert (good["n"], good["roi"]) == (1, 0.25) and (rest["n"], rest["roi"]) == (1, -1.0)
