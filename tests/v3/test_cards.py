import sqlite3

from betpredict.store import db as DB
from betpredict.ingest import cards as IC
from betpredict.experimental.cards import CardModel
from betpredict.experimental import supersocial as SS


def _db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    DB.init_db(c)
    IC.ensure(c)
    return c


def test_parse_incidents_counts_points_like_superbet_only_after_full_time():
    inc = [{"type": "card", "is_home": True, "card_type": "yellow"}, {"type": "card", "is_home": False, "card_type": "yellow"},
           {"type": "card", "is_home": False, "card_type": "red"}, {"type": "goal", "is_home": True}]
    # roșu = 2 (Superbet): galben gazde 1; galben + roșu oaspeți = 3
    assert IC.parse({"incidents": inc + [{"type": "period", "text": "FT"}]}) == (1, 3)
    assert IC.parse({"results": inc + [{"type": "period", "text": "FT"}]}) == (1, 3)
    second = [{"type": "card", "is_home": True, "card_type": "yellowRed"}, {"type": "period", "text": "FT"}]
    assert IC.parse({"incidents": second}) == (2, 0)
    assert IC.parse({"incidents": inc + [{"type": "period", "text": "HT"}]}) is None   # meci neterminat
    assert IC.parse({"incidents": []}) is None


def test_collect_stores_cards():
    c = _db()
    c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status) VALUES (1, '2026-10-14T18:00:00Z', 'A', 'B', 'finished')")

    class Client:
        def get(self, path):
            assert path == "events/1/incidents/"
            return {"incidents": [{"type": "card", "is_home": True}, {"type": "period", "text": "FT"}]}
    from datetime import datetime, timezone
    st = IC.collect(c, Client(), now=datetime(2026, 10, 15, 9, tzinfo=timezone.utc))
    assert st["ok"] == 1 and tuple(c.execute("SELECT cards_home, cards_away FROM match").fetchone()) == (1, 0)


def test_card_model_uses_league_and_teams():
    c = _db()
    for i in range(30):
        h, a = (1, 2) if i % 2 else (2, 1)
        c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status, league_id, home_id, away_id, cards_home, cards_away) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?)", (i + 1, f"2026-09-{i % 28 + 1:02d}T18:00:00Z", "H", "A", "finished", 7, h, a, 1, 3))
    m = CardModel(c)
    mh, ma, src = m.means(7, 1, 2)
    assert src == "liga+echipe" and 0.9 < mh < 2.2 and 1.8 < ma < 3.2
    assert m.means(99, 50, 51)[0] is None                   # ligă necunoscută, echipe necunoscute: nimic
    p = CardModel.probs(2.0, 2.4)
    assert 0 < p["BOTH15"] < p["YC35"] < 1 and abs(p["YC45"] + p["YCU45"] - 1) < 1e-9


def test_card_markets_settle():
    assert SS.MARKETS[("Total cartonașe", "Peste 3.5")] == "YC35"
    assert SS.MARKETS[("Fiecare echipă va primi peste X cartonașe", "Peste 1.5 - Da")] == "BOTH15"
    base = {"status": "finished", "ft_home": 1, "ft_away": 0, "ht_home": 0, "ht_away": 0, "corners_home": None, "corners_away": None,
            "corners_ht_home": None, "corners_ht_away": None, "kickoff_utc": "2026-10-14T18:00:00Z"}
    old = "2026-10-11T00:00:00Z"
    assert SS._settle_result("YC35", {**base, "cards_home": 2, "cards_away": 2}, old) == "won"
    assert SS._settle_result("BOTH15", {**base, "cards_home": 3, "cards_away": 1}, old) == "lost"
    assert SS._settle_result("YCU45", {**base, "cards_home": None, "cards_away": None}, old) is None   # așteaptă cartonașele


def test_team_named_markets():
    assert SS.team_market("Total goluri Paris Saint-Germain", "Peste 1.5", "Olympique Marseille", "Paris Saint-Germain") == "AO15"
    assert SS.team_market("Total cartonașe Liverpool", "Peste 1.5", "Liverpool", "Manchester City") == "HY15"
    assert SS.team_market("Total goluri prima repriză & Total goluri", "Peste 0.5 & Peste 1.5", "A", "B") is None
    assert SS.team_market("Total goluri & GG", "Peste 2.5 & Da", "A", "B") is None
    assert SS.team_market("Total goluri Chelsea", "Peste 0.5", "Liverpool", "Arsenal") is None   # altă echipă
    p = SS.team_p(1.5, 1.0, 2.0, 2.5)
    assert p["HO05"] > p["HO15"] and p["AY15"] > p["HY15"] and p["AY25"] < p["AY15"]
    r = {"fthg": 2, "ftag": 0, "yh": 2, "ya": 1}
    assert SS.won("HO15", r) and not SS.won("AO05", r) and SS.won("HY15", r) and not SS.won("AY15", r)


def test_fill_match_stats_backfills_cards_for_already_linked_matches():
    import sqlite3 as _sq
    from betpredict.ingest import footballdata as FD
    from betpredict.store import db as _DB

    c = _sq.connect(":memory:")
    c.row_factory = _sq.Row
    _DB.init_db(c)
    c.executescript(FD.SCHEMA)
    c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status) VALUES (1, '2026-09-01T18:00:00Z', 'A', 'B', 'finished')")
    c.execute("INSERT INTO fd_match (div, season, day, home, away, match_id, hy, ay, hc, ac) VALUES ('E0','2526','2026-09-01','A','B',1,3,2,6,4)")
    assert FD.link_matches(c) == 0  # niciun meci nou de legat, dar coloanele lipsă se completează
    m = c.execute("SELECT cards_home, cards_away, corners_home, corners_away FROM match WHERE id=1").fetchone()
    assert tuple(m) == (3, 2, 6, 4)


def test_recount_fixes_old_count_and_reopens_card_tickets():
    """Meci numărat cu roșu = 1 (Sub 5.5 câștigat greșit): renumărat, selecția și biletul se decontează din nou."""
    from datetime import datetime, timezone
    c = _db()
    SS._ensure_track(c)
    c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status, cards_home, cards_away) "
              "VALUES (1, '2026-10-17T23:00:00Z', 'Santos', 'Queretaro', 'finished', 2, 3)")
    c.execute("INSERT INTO card_fetch (match_id, fetched_at, ok) VALUES (1, '2026-10-18T05:00:00Z', 1)")
    c.execute("INSERT INTO ticket (id, kind, variant, created_by, status, created_at, day, payout) "
              "VALUES (9, 'ss', 'x', 'robot', 'won', '2026-10-17T00:00:00Z', '2026-10-17', 5)")
    c.execute("INSERT INTO ticket_leg (ticket_id, match_id, market, selection, odds, result) VALUES (9, 1, 'ss|0', 'YCU55', 2.25, 'won')")
    c.execute("INSERT INTO ss_track (match_id, mkey, odds, p, updated_at, result, kickoff_utc) VALUES (1, 'YCU55', 2.25, 0.6, 'x', 'won', '2026-10-17T23:00:00Z')")
    inc = [{"type": "card", "is_home": True, "card_type": "yellow"}] * 2 + [{"type": "card", "is_home": False, "card_type": "yellow"}] * 2 \
        + [{"type": "card", "is_home": False, "card_type": "red"}, {"type": "period", "text": "FT"}]

    class Client:
        def get(self, path):
            return {"incidents": inc}
    st = IC.collect(c, Client(), now=datetime(2026, 10, 20, 9, tzinfo=timezone.utc))
    assert st["recount"] == 1 and st["changed"] == 1
    assert tuple(c.execute("SELECT cards_home, cards_away FROM match").fetchone()) == (2, 4)
    assert c.execute("SELECT result FROM ticket_leg").fetchone()[0] is None
    assert c.execute("SELECT status FROM ticket WHERE id=9").fetchone()[0] == "pending"
    assert c.execute("SELECT result FROM ss_track").fetchone()[0] is None
    assert IC.collect(c, Client(), now=datetime(2026, 10, 20, 10, tzinfo=timezone.utc))["recount"] == 0   # o singură dată
