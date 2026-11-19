import json
import sqlite3
from datetime import datetime, timezone

from betpredict.builder.pyramid import ensure_track_tables
from betpredict.publish import bankroll as B
from betpredict.store import db as DB

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)


def _db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    DB.init_db(c)
    ensure_track_tables(c, "pyramid120")
    return c


def _ticket(c, kind, variant, status, odds, p, day, legs, pay=None, created=None):
    notes = {"payout_bonus": pay} if pay else {}
    cur = c.execute("INSERT INTO ticket (kind, variant, total_odds, p_ticket, stake, status, created_at, settled_at, notes, day) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)", (kind, variant, odds, p, 0.02, status, created or f"{day}T08:00:00+00:00",
                                                    f"{day}T22:00:00+00:00" if status in ("won", "lost") else None, json.dumps(notes), day))
    tid = cur.lastrowid
    for i, (o, res, close) in enumerate(legs):
        c.execute("INSERT INTO ticket_leg (ticket_id, match_id, market, selection, odds, result, closing_odds) VALUES (?,?,?,?,?,?,?)",
                  (tid, tid * 100 + i, "ss|0", "H2G13", o, res, close))
    return tid


def test_helpers():
    assert B.max_drawdown([1, 3, -2, 0, 4, 1]) == 5
    assert B.max_drawdown([-1, -2]) == 2
    st = B._streaks([True, True, False, True, True, True, False, False])
    assert st == {"win": 3, "loss": 2, "current": -2}
    cal = B.calibration([{"p": 0.55, "result": "won"}, {"p": 0.58, "result": "lost"}, {"p": 0.85, "result": "won"}, {"p": 0.9, "result": None}])
    assert cal["n"] == 3 and [b["n"] for b in cal["buckets"]] == [2, 1]
    assert cal["buckets"][0]["hit"] == 0.5
    clv = B.clv_stats([{"odds": 1.5, "close": 1.4}, {"odds": 1.4, "close": 1.5}, {"odds": 1.4, "close": None}])
    assert clv["n"] == 2 and clv["beat"] == 0.5


def test_doc_products_roi_bonus_and_reset_filter(tmp_path):
    c = _db()
    # înainte de noul început: nu intră
    _ticket(c, "acca_super", "s10", "won", 10.0, 0.09, "2026-11-18", [(1.5, "won", 1.5)] * 1, pay=11.0, created="2026-11-18T08:00:00+00:00")
    _ticket(c, "acca_super", "s10", "won", 10.0, 0.09, "2026-11-20", [(1.4, "won", 1.35), (1.5, "won", 1.5)], pay=11.0)
    _ticket(c, "acca_super", "s10", "lost", 10.0, 0.09, "2026-11-21", [(1.4, "lost", 1.45), (1.5, "won", 1.5)], pay=11.0)
    _ticket(c, "acca_super", "s10", "replaced", 10.0, 0.09, "2026-11-21", [(1.4, None, None)])
    _ticket(c, "acca_super", "s1000", "lost", 2000.0, 0.0005, "2026-11-21", [(1.4, "lost", None)] * 1, pay=3600.0)
    _ticket(c, "acca_super", "s5000", "pending", 6000.0, 0.0002, "2026-11-25", [(1.4, None, None)], pay=10000.0)
    _ticket(c, "pyramid", "p120", "won", 2.0, 0.5, "2026-11-20", [(1.4, "won", 1.38), (1.43, "won", 1.43)])
    _ticket(c, "pyramid", "p120", "lost", 2.0, 0.5, "2026-11-21", [(1.4, "lost", 1.38), (1.43, "won", 1.43)])
    c.execute("INSERT INTO pyramid120_run (start_date, start_bank, status, current_step, current_bank) VALUES ('2026-11-20', 100, 'lost', 1, 50)")
    c.execute("INSERT INTO pyramid120_step (run_id, step_no, date, result) VALUES (1, 1, '2026-11-20', 'won'), (1, 2, '2026-11-21', 'lost')")
    d = B.bankroll_doc(c, NOW, paths=300)
    assert d["since"] == B.TICKETS_RESET_AT
    s10, lng, pyr = d["products"]
    assert (s10["bets"], s10["won"], s10["lost"]) == (2, 1, 1)
    assert s10["roi"] == round((10.0 - 1) / 2, 4) and s10["roi_no_bonus"] == 4.0  # cu SuperBonus 11 vs 10 fără
    assert s10["expected_hit"] == 0.09 and s10["max_drawdown"] == 1.0
    assert [x["cum"] for x in s10["by_day"]] == [10.0, 9.0]
    assert s10["clv"]["n"] == 4 and s10["calibration"]["n"] == 4
    assert lng["bets"] == 1 and lng["pending"] == 1 and lng["profit"] == -1.0
    assert pyr["series"]["best"] == 1 and pyr["series"]["runs"] == 1
    sim = d["sim"]
    assert {p["plan"] for p in sim["plans"]} == {"prudent", "fara_lungi", "activ"}
    for p in sim["plans"]:
        assert p["p5"] <= p["p25"] <= p["p50"] <= p["p75"] <= p["p95"] and len(p["fan"]) == sim["horizon_days"]
    for v in sim["inputs"].values():
        assert 0 < v["p_mean"] < 1 and v["alpha"] > 0 and v["beta"] > 0
    out = B.publish_bankroll(c, tmp_path, NOW)
    assert out == tmp_path / "api" / "stats" / "bankroll.json" and json.loads(out.read_text())["products"][0]["id"] == "s10"


def test_empty_db_uses_honest_fallbacks():
    d = B.bankroll_doc(_db(), NOW, paths=200)
    assert all(p["bets"] == 0 and p["roi"] is None for p in d["products"])
    inp = d["sim"]["inputs"]
    # fără date nu apare niciun avantaj: EV negativ pe toate produsele
    assert all(v["ev"] < 0 for v in inp.values())
    assert d["sim"]["sample_small"] is True


def test_negative_ev_bleeds_bank_on_average():
    inputs = {"s10": {"alpha": 85.0, "beta": 915.0, "payout": 10.0, "per_day": 2.0, "ev": -0.15}}
    r = B.simulate(inputs, {"id": "x", "label": "x", "s10": 0.02, "long": 0, "pyr2": 0}, days=60, paths=3000)
    assert r["mean"] < 100 and r["p50"] < 100
