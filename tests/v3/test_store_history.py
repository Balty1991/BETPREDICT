import json

from betpredict.store import SCHEMA_VERSION, connect, init_db, table_counts
from betpredict.store.legacy_import import import_selection_journal, legacy_overview
from betpredict.ingest.history import import_warehouse


def test_init_db_idempotent(tmp_path):
    conn = connect(tmp_path / "x.db")
    assert init_db(conn) == SCHEMA_VERSION
    assert init_db(conn) == SCHEMA_VERSION
    assert set(table_counts(conn)) >= {"match", "odds_snapshot", "prediction", "ticket", "ticket_leg", "pyramid_run", "match_context"}


def test_legacy_import_idempotent(tmp_path):
    rows = [{"event_id": 1, "event_date": "2026-08-16T19:15:00Z", "home_team": "A", "away_team": "B", "league_id": 5,
             "market": "homeWin", "odds": 1.5, "model_probability": 0.7, "status": "settled", "result": "WIN",
             "profit_units": 0.5, "key": "k1", "strategy": "s", "home_score": 2, "away_score": 0},
            {"event_id": 2, "event_date": "2026-08-17T19:15:00Z", "market": "over25", "odds": 2.0, "status": "settled",
             "result": "LOSS", "profit_units": -1, "key": "k2", "strategy": "s"}]
    f = tmp_path / "j.json"
    f.write_text(json.dumps({"results": rows}))
    conn = connect(":memory:")
    init_db(conn)
    assert import_selection_journal(conn, f)["inserted"] == 2
    assert import_selection_journal(conn, f)["inserted"] == 0
    ov = legacy_overview(conn)
    assert ov["settled"] == 2 and ov["won"] == 1 and ov["profit_units"] == -0.5


def test_warehouse_fixes_bad_years_and_offsets(tmp_path):
    wh = tmp_path / "wh"
    wh.mkdir()
    (wh / "events_season_1.json").write_text(json.dumps([
        {"event_id": 1, "date": "2026-03-06T15:35:00+04:00", "league_id": 9, "league": "L", "home_team_id": 1, "away_team_id": 2,
         "home_score": 1, "away_score": 0},
        {"event_id": 2, "date": "2075-03-06T15:35:00+00:00", "league_id": 9, "home_team_id": 1, "away_team_id": 2,
         "home_score": 1, "away_score": 0},
        {"event_id": 3, "date": "2026-03-07T15:35:00+00:00", "league_id": 9, "home_team_id": 1, "away_team_id": 2,
         "home_score": None, "away_score": None},
    ]))
    conn = connect(":memory:")
    init_db(conn)
    st = import_warehouse(conn, wh)
    assert st["inserted"] == 1 and st["skipped_bad_date"] == 1
    assert conn.execute("SELECT kickoff_utc FROM match WHERE id=1").fetchone()[0] == "2026-03-06T11:35:00Z"
    assert import_warehouse(conn, wh).get("already_imported") == 1
