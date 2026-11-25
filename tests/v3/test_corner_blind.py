import json
import sqlite3
from datetime import datetime, timezone

from betpredict.builder import corner_tickets as C
from betpredict.ingest import corners as CO
from betpredict.store import db as DB

NOW = datetime(2026, 11, 25, 8, tzinfo=timezone.utc)


def _db():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row; DB.init_db(c); CO.ensure(c)
    # liga 1: BSD dă cornere; liga 2: niciodată (citirea s-a încercat)
    for i in range(1, 21):
        lg = 1 if i <= 10 else 2
        corners = (5, 4) if lg == 1 else (None, None)
        c.execute("INSERT INTO match (id, league_id, kickoff_utc, home_name, away_name, status, ft_home, ft_away, corners_home, corners_away) "
                  "VALUES (?, ?, '2026-11-20T18:00:00Z', 'h', 'a', 'finished', 1, 0, ?, ?)", (i, lg, *corners))
        c.execute("INSERT INTO corner_fetch VALUES (?, '2026-11-21T00:00:00Z', ?)", (i, 1 if lg == 1 else 0))
    return c


def test_blind_leagues_only_where_bsd_has_no_corners():
    c = _db()
    assert CO.blind_leagues(c, NOW) == {2}
    assert CO.blind_leagues(c, NOW, min_n=11) == set()  # prea puține meciuri: nu decidem


def test_corner_pool_skips_leagues_without_corner_data():
    c = _db()
    for mid, lg in ((101, 1), (102, 2)):
        c.execute("INSERT INTO match (id, league_id, kickoff_utc, home_name, away_name, status) VALUES (?, ?, '2026-11-26T18:00:00Z', 'h', 'a', 'notstarted')", (mid, lg))
        c.execute("INSERT INTO bb_suggestion (match_id, day, legs_json, label, p_joint, fair_odds, min_odds, sb_price, source, created_at) VALUES (?,?,?,?,?,1.43,1.43,?,?,?)",
                  (mid, "2026-11-26", json.dumps({"superbet": {"market": "Peste 0.5 goluri; Peste 7.5 cornere", "outcome": "Peste 0.5 goluri; Peste 7.5 cornere"}}),
                   "Peste 0.5 goluri; Peste 7.5 cornere", 0.7, 1.5, "superbet", "2026-11-25T00:00:00Z"))
    pool = C._pool(c, "2026-11-25T08:00:00", 1.9, "2026-11-30T00:00:00Z")
    assert [p["match_id"] for p in pool] == [101]


def test_corner_leg_on_lost_ticket_is_still_settled():
    c = _db()
    sel = "Peste 0.5 goluri; Peste 7.5 cornere|Peste 0.5 goluri; Peste 7.5 cornere"
    c.execute("INSERT INTO ticket (id, kind, variant, created_by, total_odds, status, created_at) "
              "VALUES (1, 'acca_corners', '500', 'robot', 500, 'lost', '2026-11-19T10:00:00Z')")
    c.execute("INSERT INTO ticket_leg (ticket_id, match_id, market, selection, odds) VALUES (1, 1, 'bb', ?, 1.5)", (sel,))
    c.execute("UPDATE match SET corners_home=3, corners_away=3 WHERE id=1")  # 6 cornere: pierdut
    C.settle_legs(c)
    assert c.execute("SELECT result FROM ticket_leg WHERE ticket_id=1").fetchone()[0] == "lost"
