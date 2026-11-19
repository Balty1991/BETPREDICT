"""Decontare: scor live la 2 h, meciuri dublate, rezultate corectate; monitorul pieței recomandate; arhiva cotelor."""
import json
import sqlite3
from datetime import datetime, timezone

from betpredict import settle as S
from betpredict.builder import rec_monitor as RM
from betpredict.ingest import superbet as SB
from betpredict.store import db as DB

NOW = datetime(2026, 11, 19, 8, 0, tzinfo=timezone.utc)


def _db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    DB.init_db(c)
    from betpredict.ingest.corners import ensure

    ensure(c)
    return c


def _match(c, mid, ko, status, fh=None, fa=None, hh=None, ha=None, home="Kuwait", away="Honduras", hid=10, aid=20, league=None):
    c.execute("INSERT INTO match (id, kickoff_utc, home_id, away_id, home_name, away_name, status, ft_home, ft_away, ht_home, ht_away, "
              "raw_json, league_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,'{}',?)", (mid, ko, hid, aid, home, away, status, fh, fa, hh, ha, league))


def _ticket(c, tid, kind="acca_super", status="pending", stake=1.0, payout=None):
    c.execute("INSERT INTO ticket (id, kind, created_at, stake, status, payout, total_odds) VALUES (?,?,?,?,?,?,2.0)",
              (tid, kind, "2026-11-10T00:00:00Z", stake, status, payout))


def _leg(c, tid, mid, market, sel, odds, result=None):
    c.execute("INSERT INTO ticket_leg (ticket_id, match_id, market, selection, odds, result) VALUES (?,?,?,?,?,?)",
              (tid, mid, market, sel, odds, result))


def test_score_without_final_status_waits_six_hours():
    assert not S.looks_final("notstarted", 1, 2, "2026-11-19T05:30:00Z", NOW)  # 2,5 h: poate fi încă în prelungiri
    assert S.looks_final("notstarted", 1, 2, "2026-11-19T01:30:00Z", NOW)
    assert S.looks_final("finished", 1, 2, "2026-11-19T07:00:00Z", NOW)
    assert not S.looks_final("postponed", 1, 2, "2026-11-10T01:30:00Z", NOW)
    row = {"status": "notstarted", "ft_home": 0, "ft_away": 1, "kickoff_utc": "2026-11-19T05:30:00Z", "raw_json": "{}"}
    assert S.leg_result_from_match("1x2|0", "AWAY", row, NOW) is None


def test_duplicate_fixture_settles_from_finished_twin():
    c = _db()
    _match(c, 1, "2026-11-17T16:30:00Z", "finished", 0, 2, 0, 1)
    _match(c, 2, "2026-11-17T17:30:00Z", "notstarted")  # copia rămasă „notstarted”, altă oră
    _match(c, 3, "2026-11-17T16:30:00Z", "notstarted", home="Other", away="Team", hid=30, aid=40)  # fără geamăn
    _ticket(c, 1)
    _leg(c, 1, 2, "1x2|0", "AWAY", 1.5)
    _leg(c, 1, 3, "1x2|0", "HOME", 1.5)
    assert S.twin_match(c, c.execute("SELECT * FROM match WHERE id=2").fetchone(), NOW)["id"] == 1
    assert S.twin_match(c, c.execute("SELECT * FROM match WHERE id=3").fetchone(), NOW) is None
    assert S.settle_orphan_legs(c, NOW) == 1
    assert c.execute("SELECT result FROM ticket_leg WHERE match_id=2").fetchone()[0] == "won"
    assert c.execute("SELECT result FROM ticket_leg WHERE match_id=3").fetchone()[0] is None


def test_twin_by_normalized_names_when_ids_differ():
    c = _db()
    _match(c, 1, "2026-11-13T22:00:00Z", "finished", 2, 1, 1, 0, home="Colo-Colo", away="Racing Club", hid=1, aid=2)
    _match(c, 2, "2026-11-13T23:00:00Z", "notstarted", home="Colo Colo", away="Racing Club", hid=None, aid=None)
    assert S.twin_match(c, c.execute("SELECT * FROM match WHERE id=2").fetchone(), NOW)["id"] == 1


def test_recheck_fixes_legs_and_tickets_after_score_correction_and_only_flags_pyramid():
    c = _db()
    _match(c, 1, "2026-11-14T17:30:00Z", "finished", 1, 1, 0, 1)  # scorul corectat: 1-1 (decontat pe 1-2)
    _match(c, 2, "2026-11-14T17:30:00Z", "finished", 2, 0, 1, 0, home="A", away="B", hid=3, aid=4)
    _ticket(c, 1, status="lost", payout=0.0)
    _leg(c, 1, 1, "double_chance|0", "1X", 1.5, "lost")
    _leg(c, 1, 2, "1x2|0", "HOME", 1.4, "won")
    _ticket(c, 2, kind="pyramid", status="lost", payout=0.0)
    _leg(c, 2, 1, "ss|0", "H2G13", 1.3, "lost")  # repriza a doua: 1 gol → câștigat
    out = S.recheck_settled(c, NOW)
    assert out["legs"] == 2 and out["tickets"] == 1 and out["flagged"] == 1
    t = c.execute("SELECT status, payout, notes FROM ticket WHERE id=1").fetchone()
    assert t["status"] == "won" and abs(t["payout"] - 2.1) < 1e-6
    assert json.loads(t["notes"])["corrected"]["was"] == "lost"
    p = c.execute("SELECT status, notes FROM ticket WHERE id=2").fetchone()
    assert p["status"] == "lost" and json.loads(p["notes"])["result_mismatch"]["now"] == "won"
    assert S.recheck_settled(c, NOW)["legs"] == 0  # idempotent


def test_ticket_outcome_matches_accumulator_rules():
    legs = [{"odds": 2.0, "result": "won"}, {"odds": 1.5, "result": "void"}]
    assert S.ticket_outcome(legs, 1.0, None) == ("won", 2.0)
    assert S.ticket_outcome([{"odds": 2.0, "result": None}], 1.0, None) is None
    assert S.ticket_outcome([{"odds": 2.0, "result": "lost"}, {"odds": 2.0, "result": None}], 1.0, None) == ("lost", 0.0)


# ----------------------------------------------------------------------------------------------- monitor
REC = {("Final", "2"): ("1x2", "AWAY", 1.3, 1.6, 0.01)}


def _close(c, mid, mn, oc, price):
    c.execute("CREATE TABLE IF NOT EXISTS sb_offer_close (match_id INTEGER, market_name TEXT, outcome TEXT, line TEXT, price REAL, "
              "observed_at TEXT, PRIMARY KEY (match_id, market_name, outcome))")
    c.execute("INSERT INTO sb_offer_close VALUES (?,?,?,NULL,?,NULL)", (mid, mn, oc, price))


def test_wilson_interval():
    lo, hi = RM.wilson(50, 100)
    assert 0.40 < lo < 0.41 and 0.59 < hi < 0.60
    assert RM.wilson(0, 0) == (None, None)


def test_monitor_segments_and_reenable_rule():
    c = _db()
    c.execute("INSERT INTO league (id, name) VALUES (1, 'Serie A'), (2, 'International Friendly Games')")
    mid = 0
    # 160 selecții vechi (11–20 zile): intră 50% la 1.50 → ROI −25%; ultimele 10 zile: 60 la 1.50, intră 70% → +5%
    for i in range(160):
        mid += 1
        won = i % 2 == 0
        _match(c, mid, f"2026-11-{1 + i % 8:02d}T15:00:00Z", "finished", 0, 1 if won else 0, 0, 0, home=f"h{mid}", away=f"a{mid}",
               hid=None, aid=None, league=1 if i % 4 else 2)
        _close(c, mid, "Final", "2", 1.5)
    for i in range(60):
        mid += 1
        won = i % 10 < 7
        _match(c, mid, "2026-11-15T15:30:00Z" if i % 3 else "2026-11-15T02:00:00Z", "finished", 0, 1 if won else 0, 0, 0,
               home=f"h{mid}", away=f"a{mid}", hid=None, aid=None, league=1)
        _close(c, mid, "Final", "2", 1.5)
    st = RM.market_stats(c, REC, (1.4, 1.6), NOW)[("Final", "2")]
    assert st["n"] == 220 and st["roi"] < RM.DROP_ROI
    assert st["segments"]["recent"]["n"] == 60 and st["segments"]["recent"]["roi"] > 0
    assert st["status"] == "reenabled" and not st["off"]
    assert st["segments"]["intl"]["n"] == 40 and st["segments"]["club"]["n"] == 180
    assert st["segments"]["night"]["n"] == 20  # 02:00 UTC = 04:00 ora României
    assert st["roi_ci"][0] < st["roi"] < st["roi_ci"][1]
    assert 0 <= st["p_profit"] <= 1
    doc = RM.monitor_doc(c, NOW, rec=REC)
    json.dumps(doc)
    assert doc["markets"][0]["status"] == "reenabled" and doc["off"] == []
    assert doc["markets"][-1]["key"] == RM.COMBO and doc["markets"][-1]["n"] == 0


def test_decide_off_without_recovery():
    assert RM.decide({"n": 200, "roi": -0.10}, {"n": 20, "roi": 0.2})[0] == "off"
    assert RM.decide({"n": 100, "roi": -0.30}, {})[0] == "on"
    assert RM.decide({"n": 200, "roi": -0.03}, {})[0] == "on"


# ----------------------------------------------------------------------------------------------- arhiva
def test_archive_keeps_detail_price_and_fills_from_bulk_snapshot():
    c = _db()
    _match(c, 1, "2026-11-18T18:00:00Z", "finished", 1, 0)
    _match(c, 2, "2026-11-18T18:00:00Z", "finished", 1, 0, home="A", away="B", hid=3, aid=4)
    c.execute("CREATE TABLE IF NOT EXISTS sb_offer (match_id INTEGER, market_id INTEGER, market_name TEXT, outcome TEXT, line TEXT, "
              "price REAL, observed_at TEXT, ref TEXT, PRIMARY KEY (match_id, market_name, outcome))")
    c.execute("INSERT OR REPLACE INTO sb_offer (match_id, market_name, outcome, line, price, observed_at) "
              "VALUES (1, 'Final', '1', '', 1.80, '2026-11-18T17:55:00Z')")
    for mid, out, price, seen in ((1, "HOME", 1.70, "2026-11-18T12:00:00Z"), (2, "HOME", 1.40, "2026-11-18T12:00:00Z"),
                                  (2, "HOME", 1.45, "2026-11-18T17:00:00Z"), (2, "HOME", 1.10, "2026-11-18T18:30:00Z")):
        c.execute("INSERT INTO odds_snapshot (match_id, market, line, period, outcome, decimal, source, observed_at) "
                  "VALUES (?, '1x2', 0, 'FT', ?, ?, 'superbet', ?)", (mid, out, price, seen))
    c.execute("INSERT INTO odds_snapshot (match_id, market, line, period, outcome, decimal, source, observed_at) "
              "VALUES (2, 'over_under', 1.5, 'FT', 'OVER', 1.30, 'superbet', '2026-11-18T17:00:00Z')")
    SB._archive_offers(c, "2026-11-19T02:00:00Z")
    rows = {(r[0], r[1], r[2]): r[3] for r in c.execute("SELECT match_id, market_name, outcome, price FROM sb_offer_close")}
    assert rows[(1, "Final", "1")] == 1.80          # prețul din detalii are întâietate
    assert rows[(2, "Final", "1")] == 1.45          # ultimul preț bulk de dinaintea startului (nu cel live)
    assert rows[(2, "Total goluri", "Peste 1.5")] == 1.30
    SB._archive_offers(c, "2026-11-19T02:00:00Z")
    assert c.execute("SELECT COUNT(*) FROM sb_offer_close").fetchone()[0] == len(rows)
    h = SB.archive_health(c, NOW)
    assert h["archived_finished"] == 2 and h["markets"]["Final"] == 2
