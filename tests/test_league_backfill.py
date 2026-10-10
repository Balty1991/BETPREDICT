from betpredict.pipeline.daily import backfill_league_names, parse_league_detail
from betpredict.store import db


class FakeClient:
    def __init__(self, data):
        self.data, self.calls = data, []

    def get(self, path, **kw):
        self.calls.append(path)
        lid = int(path.strip("/").split("/")[1])
        if lid not in self.data:
            raise RuntimeError("404")
        return self.data[lid]


def test_parse_variants():
    assert parse_league_detail({"name": "Chance Liga", "country": "Czech Republic"}) == {"name": "Chance Liga", "country": "Czech Republic"}
    assert parse_league_detail({"league": {"name": "X", "country": {"name": "Y"}}}) == {"name": "X", "country": "Y"}
    assert parse_league_detail(None) == {}


def test_backfill(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.init_db(conn)
    conn.execute("INSERT INTO match (id, league_id, kickoff_utc, home_name, away_name) VALUES (1, 99, '2026-10-11T12:00:00Z', 'Bohemians', 'Banik')")
    conn.execute("INSERT INTO match (id, league_id, kickoff_utc, home_name, away_name) VALUES (2, 98, '2026-10-11T12:00:00Z', 'A', 'B')")
    c = FakeClient({99: {"name": "Czech First League", "country": "Czech Republic"}})
    assert backfill_league_names(conn, c) == 1
    assert tuple(conn.execute("SELECT name, country FROM league WHERE id=99").fetchone()) == ("Czech First League", "Czech Republic")
