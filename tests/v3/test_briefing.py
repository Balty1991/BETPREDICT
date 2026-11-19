import json
import sqlite3
from datetime import datetime, timezone

from betpredict.builder.pyramid import ensure_track_tables
from betpredict.publish import briefing as B
from betpredict.store import db as DB

NOW = datetime(2026, 11, 19, 7, 45, tzinfo=timezone.utc)


def _db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    DB.init_db(c)
    ensure_track_tables(c, "pyramid120")
    c.execute("CREATE TABLE IF NOT EXISTS sb_offer_close (match_id INTEGER, market_name TEXT, outcome TEXT, line TEXT, price REAL, observed_at TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS sb_offer (match_id INTEGER, market_name TEXT, outcome TEXT, line TEXT, price REAL, observed_at TEXT)")
    c.execute("INSERT INTO league (id, name) VALUES (1, 'Serie A'), (2, 'International Friendly Games')")
    return c


def _match(c, mid, ko, league=1, ft=None, ht=None):
    c.execute("INSERT INTO match (id, league_id, kickoff_utc, home_name, away_name, status, ft_home, ft_away, ht_home, ht_away) "
              "VALUES (?,?,?,?,?,?,?,?,?,?)", (mid, league, ko, f"H{mid}", f"A{mid}", "finished" if ft else "scheduled",
                                               *(ft or (None, None)), *(ht or (None, None))))


def test_thin_day_warnings_and_small_stake():
    c = _db()
    _match(c, 1, "2026-11-19T15:00:00Z")           # 17:00 RO, club
    _match(c, 2, "2026-11-19T01:00:00Z")           # noaptea
    for i in range(3, 9):
        _match(c, i, "2026-11-19T17:00:00Z", league=2)  # amicale
    d = B.brief_doc(c, NOW)
    q = d["quality"]
    assert (q["club_day"], q["night"], q["intl"], q["level"]) == (1, 1, 6, "slaba")
    assert q["intl_break"] and d["tone"] == "warn" and d["weekday"] == "joi"
    assert any("noaptea" in w for w in d["warnings"]) and any("internaționale" in w for w in d["warnings"])
    short = next(b for b in d["bankroll"] if b["key"] == "short")
    assert short["pct"] == 0.01  # zi slabă: spre minim
    assert d["tickets"]["short"] == [] and d["tickets"]["short_note"]
    assert d["pyramid"]["step"] == 1 and d["pyramid"]["stake"] == 50.0  # repornire: jumătate din 100


def test_short_ticket_pyramid_and_yesterday(tmp_path):
    c = _db()
    _match(c, 10, "2026-11-19T16:00:00Z")
    _match(c, 11, "2026-11-19T18:00:00Z")
    _match(c, 20, "2026-11-18T17:00:00Z", ft=(2, 1), ht=(1, 0))  # ieri: R2 1 gol
    c.execute("INSERT INTO sb_offer_close VALUES (20, 'A doua repriză - Interval goluri', '1-3', NULL, 1.33, '2026-11-18T16:59:00Z')")
    c.execute("INSERT INTO ticket (id, kind, variant, total_odds, p_ticket, ev, stake, status, created_at, notes, day) VALUES "
              "(1, 'acca_super', 's10', 11.2, 0.09, -0.05, 0.02, 'pending', '2026-11-19T07:00:00Z', ?, '2026-11-19')",
              (json.dumps({"payout_bonus": 11.7, "superbonus": 0.06}),))
    for mid in (10, 11):
        c.execute("INSERT INTO ticket_leg (ticket_id, match_id, market, selection, odds) VALUES (1, ?, 'ss|0', 'H2G13', 1.35)", (mid,))
    c.execute("INSERT INTO ticket (id, kind, variant, total_odds, p_ticket, stake, status, created_at, day) VALUES "
              "(2, 'acca_super', 's10', 12.0, 0.08, 0.02, 'lost', '2026-11-18T07:00:00Z', '2026-11-18')")
    c.execute("INSERT INTO ticket_leg (ticket_id, match_id, market, selection, odds, result) VALUES (2, 20, 'ss|0', 'H2G13', 1.33, 'lost')")
    c.execute("INSERT INTO ticket (id, kind, variant, total_odds, p_ticket, stake, status, created_at, day) VALUES "
              "(3, 'pyramid', 'p120', 1.96, 0.5, 60, 'pending', '2026-11-19T07:00:00Z', '2026-11-19')")
    c.execute("INSERT INTO ticket_leg (ticket_id, match_id, market, selection, odds) VALUES (3, 10, '1x2|0', 'HOME', 1.4)")
    c.execute("INSERT INTO pyramid120_run (start_date, start_bank, status, current_step, current_bank) VALUES ('2026-11-17', 100, 'active', 1, 120)")
    c.execute("INSERT INTO ingest_state (key, value) VALUES ('pyramid120.day.2026-11-19', ?)", (json.dumps({"status": "pick", "main": 3}),))
    p = B.publish_brief(c, tmp_path, NOW)
    d = json.loads(p.read_text(encoding="utf-8"))
    assert p == tmp_path / "api" / "brief" / "today.json"
    t = d["tickets"]["short"][0]
    assert t["n_legs"] == 2 and "Repriza 2: 1–3 goluri" in t["why"][0]
    assert d["pyramid"]["step"] == 2 and d["pyramid"]["stake"] == 60.0 and d["pyramid"]["ticket"]["odds"] == 1.96
    y = d["yesterday"]
    assert y["date"] == "2026-11-18" and y["tickets"]["~10"]["lost"] == 1
    assert y["markets"] == [{"label": "Repriza 2: 1–3 goluri", "n": 1, "won": 1}]
    assert d["short_loss_streak"] == 1


def test_market_states():
    c = _db()
    for i in range(1, 41):  # GG la 1.80 intră 40% → rece
        _match(c, 100 + i, "2026-11-10T18:00:00Z", ft=(1, 1 if i % 5 < 2 else 0), ht=(0, 0))
        c.execute("INSERT INTO sb_offer_close VALUES (?, 'Ambele echipe marchează (GG)', 'Da', NULL, 1.8, 'x')", (100 + i,))
    rows = B.market_board(c, NOW)["rows"]
    gg = next(r for r in rows if r["label"].startswith("Ambele"))
    assert gg["n"] == 40 and gg["state"] == "cold"
    assert any("reci" in w for w in B.risk_warnings(B.day_quality(c, NOW.date(), NOW), {"rows": rows}, {"short": []}, {}, 0))
