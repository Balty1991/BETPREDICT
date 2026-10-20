import sqlite3
from datetime import datetime, timezone

from betpredict.ingest import apifootball as AF
from betpredict.store import db as DB

NOW = datetime(2026, 10, 15, 15, tzinfo=timezone.utc)


def _db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    DB.init_db(c)
    AF.ensure(c)
    return c


class Fake:
    def __init__(self, c, pages):
        self.pages, self.calls, self.c = pages, [], c

    def can(self):
        return True

    def used(self):
        return len(self.calls)

    def get(self, path):
        self.calls.append(path)
        for k, v in self.pages.items():
            if path.startswith(k):
                return v
        return None


def _fx(fid, home, away, when="2026-10-14T23:30:00+00:00", hid=1, aid=2):
    return {"fixture": {"id": fid, "date": when}, "teams": {"home": {"id": hid, "name": home}, "away": {"id": aid, "name": away}}}


def _stats(ch, ca, yh, ya, rh=None, ra=None):
    t = lambda c, y, r: {"statistics": [{"type": "Corner Kicks", "value": c}, {"type": "Yellow Cards", "value": y},  # noqa: E731
                                         {"type": "Red Cards", "value": r}]}
    return {"response": [t(ch, yh, rh), t(ca, ya, ra)], "errors": []}


def test_parse_stats_counts_reds_and_null_as_zero():
    assert AF.parse_stats(_stats(6, 3, 2, None, 1, None)) == (6, 3, 4, 0)  # roșu = 2
    assert AF.parse_stats({"response": []}) is None


def test_collect_links_and_fills_missing_corners_and_cards():
    c = _db()
    c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status, ft_home, ft_away) VALUES (1,?,?,?,?,1,1)",
              ("2026-10-14T23:30:00Z", "Inter Miami CF", "New York City FC", "finished"))
    c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status) VALUES (2,?,?,?,?)",
              ("2026-10-14T23:30:00Z", "LA Galaxy", "Portland Timbers", "finished"))
    fake = Fake(c, {"fixtures?date=": {"response": [_fx(77, "Inter Miami", "New York City FC")], "errors": []},
                    "fixtures/statistics?fixture=77": _stats(5, 4, 2, 3)})
    st = AF.collect(c, now=NOW, client=fake)
    assert st["linked"] >= 1 and st["stats"] == 1
    m = c.execute("SELECT corners_home, corners_away, cards_home, cards_away FROM match WHERE id=1").fetchone()
    assert tuple(m) == (5, 4, 2, 3)
    assert c.execute("SELECT COUNT(*) FROM af_fixture WHERE match_id=2").fetchone()[0] == 0  # alt meci: nelegat
    again = AF.collect(c, now=NOW, client=fake)
    assert again["stats"] == 0 and not any(p.startswith("fixtures?date=") for p in fake.calls[len(fake.calls) - 0:])


def test_without_key_does_nothing(monkeypatch):
    monkeypatch.delenv("APIFOOTBALL_KEY", raising=False)
    assert AF.collect(_db(), now=NOW) == {"skipped": "fără APIFOOTBALL_KEY"}


def test_daily_cap(monkeypatch):
    c = _db()
    c.execute("INSERT INTO af_usage VALUES (?, ?)", ("2026-10-15", AF.DAILY_CAP))
    assert not AF.Client("k", c, NOW.date()).can()
