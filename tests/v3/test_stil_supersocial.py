import json
import sqlite3
from datetime import date, datetime, timezone

from betpredict.store import db as DB
from betpredict.experimental import supersocial as SS
from betpredict.settle import settle_tickets


def _db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    DB.init_db(c)
    return c


def _seed(c, n=14):
    for i in range(1, n + 1):
        c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status) VALUES (?,?,?,?,?)",
                  (i, "2026-10-11T18:00:00Z", f"Home{i}", f"Away{i}", "scheduled"))
        c.execute("INSERT INTO match_model (match_id, model_version, lambda_home, lambda_away) VALUES (?,?,?,?)", (i, "robot-v1", 1.5, 1.2))
        for (mn, out), price in {("Interval goluri", "2-4"): 1.62, ("Interval goluri", "2-5"): 1.42, ("Interval goluri", "1-3"): 1.70,
                                 ("Gol marcat în ambele reprize", "Da"): 1.60,
                                 ("Total goluri prima repriză & Total goluri", "Peste 0.5 & Peste 1.5"): 1.45}.items():
            c.execute("INSERT INTO sb_offer (match_id, market_name, outcome, price, observed_at) VALUES (?,?,?,?,?)",
                      (i, mn, out, price, "2026-10-11T08:00:00Z"))


def test_build_tickets_overlap_and_snapshot():
    c = _db(); _seed(c)
    now = datetime(2026, 10, 11, 9, tzinfo=timezone.utc)
    rep = SS.build(c, date(2026, 10, 11), now)
    assert rep["snapshot_rows"] == 70 and len(rep["tickets"]) >= 2
    t = c.execute("SELECT * FROM ticket WHERE variant=?", (SS.VARIANT,)).fetchall()
    assert all(4 <= len(c.execute("SELECT * FROM ticket_leg WHERE ticket_id=?", (x["id"],)).fetchall()) <= SS.MAX_LEGS for x in t)
    assert all(SS.ODDS_LO <= x["total_odds"] <= SS.ODDS_HI_HARD for x in t)
    per_match = c.execute("SELECT match_id, COUNT(*) n FROM ticket_leg GROUP BY match_id").fetchall()
    assert max(r["n"] for r in per_match) <= SS.MAX_TICKETS_PER_MATCH
    dup = c.execute("SELECT COUNT(*) FROM (SELECT match_id, selection FROM ticket_leg GROUP BY 1,2 HAVING COUNT(*)>1)").fetchone()[0]
    assert dup == 0
    gol = next(x for x in t if json.loads(x["notes"])["stil"] == "Goluri 2–4 / 2–5")
    first = c.execute("SELECT selection FROM ticket_leg WHERE ticket_id=?", (gol["id"],)).fetchall()
    assert {r["selection"] for r in first} <= {"G24", "G25"}
    assert json.loads(t[0]["notes"])["paper"] is True
    again = SS.build(c, date(2026, 10, 11), now)
    assert again.get("skipped_existing") or not again.get("tickets")  # biletele existente nu se dublează


def test_real_settlement_with_halftime():
    c = _db(); _seed(c)
    SS.build(c, date(2026, 10, 11), datetime(2026, 10, 11, 9, tzinfo=timezone.utc))
    c.execute("UPDATE match SET status='finished', ft_home=2, ft_away=1, ht_home=1, ht_away=0")
    settle_tickets(c)
    legs = c.execute("SELECT selection, result FROM ticket_leg").fetchall()
    assert all(l["result"] == "won" for l in legs)  # 3 goluri, gol în ambele reprize → toate tiparele intră
    assert c.execute("SELECT COUNT(*) FROM ticket WHERE variant=? AND status='won'", (SS.VARIANT,)).fetchone()[0] >= 2
    c.execute("UPDATE ticket_leg SET result=NULL"); c.execute("UPDATE ticket SET status='pending'")
    c.execute("UPDATE match SET ft_home=1, ft_away=0, ht_home=1, ht_away=0")
    settle_tickets(c)
    res = {(l["selection"], l["result"]) for l in c.execute("SELECT selection, result FROM ticket_leg")}
    assert ("G24", "lost") in res or ("G25", "lost") in res
    assert SS.live_stats(c)["legs"]


def test_week_offer_and_stops_for_green():
    import math
    assert SS.HORIZON_H == 24 * 7
    pool = [{"match_id": i, "league_id": None, "key": "C65", "p": 0.82, "odds": 1.30, "edge": 0.04} for i in range(1, 23)]
    legs = SS._assemble(pool, 10, 22, None)
    assert legs is not None and len(legs) == 17  # 1.30^16 < 80, 1.30^17 ≈ 86; nu umflă până la 22
    assert SS.ODDS_LO <= math.prod(c["odds"] for c in legs) <= SS.ODDS_HI
    c = _db()
    kick = "2026-10-16T18:00:00Z"  # peste 5 zile, în afara ferestrei vechi de 60h
    for i in range(1, 13):
        c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status) VALUES (?,?,?,?,?)",
                  (i, kick, f"Home{i}", f"Away{i}", "scheduled"))
        c.execute("INSERT INTO match_model (match_id, model_version, lambda_home, lambda_away) VALUES (?,?,?,?)", (i, "robot-v1", 1.5, 1.2))
        c.execute("INSERT INTO sb_offer (match_id, market_name, outcome, price, observed_at) VALUES (?,?,?,?,?)",
                  (i, "Interval goluri", "1-3", 1.55, "2026-10-11T08:00:00Z"))
    now = datetime(2026, 10, 11, 9, tzinfo=timezone.utc)
    far = SS.candidates(c, now, 60)
    week = SS.candidates(c, now, SS.HORIZON_H)
    assert not any(x["odds"] for x in far if x["key"] == "G13")
    assert any(x["key"] == "G13" and x["odds"] == 1.55 for x in week)
    rep = SS.build(c, date(2026, 10, 11), now)
    assert any(t["name"] == "Goluri 1–3" and SS.ODDS_LO <= t["odds"] <= SS.ODDS_HI_HARD for t in rep["tickets"])
    c.execute("UPDATE ticket SET total_odds=900 WHERE variant=?", (SS.VARIANT,))
    rep2 = SS.build(c, date(2026, 10, 11), now)
    assert c.execute("SELECT COUNT(*) FROM ticket WHERE status='replaced'").fetchone()[0] >= 1
    assert rep2["tickets"] and all(SS.ODDS_LO <= t["odds"] <= SS.ODDS_HI_HARD for t in rep2["tickets"])


def test_labels():
    from betpredict.robot.markets import label_ro
    assert label_ro("ss", 0.0, "G24") == "Interval goluri 2-4"


def test_mix_key_cap():
    c = _db(); _seed(c, 20)
    SS.build(c, date(2026, 10, 11), datetime(2026, 10, 11, 9, tzinfo=timezone.utc))
    for t in c.execute("SELECT id, notes FROM ticket").fetchall():
        n = c.execute("SELECT selection, COUNT(*) k FROM ticket_leg WHERE ticket_id=? GROUP BY 1", (t["id"],)).fetchall()
        if len(n) > 2:
            assert max(r["k"] for r in n) <= SS.MAX_PER_KEY


def test_markets_all_labelled_and_grouped():
    from betpredict.experimental import supersocial as ss
    p = ss.model_p(1.5, 1.1)
    for k in ("H13x2", "R1R2", "R1O15", "G13", "G24", "G25"):
        assert 0 < p[k] < 1 and k in ss.LABELS and k in ss.GROUP
    assert ss.won("BB_H1C25_U65", {"hc1": 2, "ac1": 2}) and not ss.won("BB_H1C25_U65", {"hc1": 5, "ac1": 2})
    assert ss.won("R1O15", {"fthg": 1, "ftag": 1, "hthg": 1, "htag": 0, "hc": None, "ac": None})
    assert not ss.won("R1R2", {"fthg": 2, "ftag": 0, "hthg": 2, "htag": 0, "hc": None, "ac": None})
    assert ss.won("H13x2", {"fthg": 2, "ftag": 1, "hthg": 1, "htag": 0, "hc": None, "ac": None})
    assert "interval 3-6" in ss.LABELS["BB_H1C25_U65"]


def test_wave_keeps_only_positive_markets():
    c = _db(); _seed(c, 36)
    cur = c.execute(
        "INSERT INTO ticket (kind, variant, created_by, stake, status, created_at, day, notes) VALUES (?,?,?,?,?,?,?,?)",
        ("acca_stil", "stil_supersocial", "robot", 0.05, "lost", "x", "2026-10-01", "{}"))
    tid = cur.lastrowid
    for i in range(1, 31):
        c.execute("INSERT INTO ticket_leg (ticket_id, match_id, market, selection, odds, result) VALUES (?,?,?,?,?,?)",
                  (tid, i, "ss|0", "R1O15", 1.48, "won"))
        c.execute("INSERT INTO ticket_leg (ticket_id, match_id, market, selection, odds, result) VALUES (?,?,?,?,?,?)",
                  (tid, i, "ss|0", "G13", 1.70, "lost"))
    c.execute("UPDATE sb_offer SET price=1.60 WHERE outcome='Peste 0.5 & Peste 1.5'")
    wave = SS.live_stats(c)["wave"]
    assert [w["key"] for w in wave] == ["R1O15"]
    now = datetime(2026, 10, 11, 9, tzinfo=timezone.utc)
    rep = SS.build(c, date(2026, 10, 11), now)
    assert rep["wave"] == ["R1O15"]
    sels = {r[0] for r in c.execute(
        "SELECT DISTINCT tl.selection FROM ticket_leg tl JOIN ticket t ON t.id=tl.ticket_id WHERE t.day='2026-10-11' AND t.status!='replaced'")}
    assert sels == {"R1O15"}
    kept = c.execute("SELECT id FROM ticket WHERE day='2026-10-11' AND status='pending'").fetchone()[0]
    again = SS.build(c, date(2026, 10, 11), now)
    assert again.get("skipped_existing") is True
    assert c.execute("SELECT status FROM ticket WHERE id=?", (kept,)).fetchone()[0] == "pending"


def test_wave_rebuilds_when_the_set_changes():
    c = _db(); _seed(c, 36)
    cur = c.execute(
        "INSERT INTO ticket (kind, variant, created_by, stake, status, created_at, day, notes) VALUES (?,?,?,?,?,?,?,?)",
        ("acca_stil", "stil_supersocial", "robot", 0.05, "lost", "x", "2026-10-01", "{}"))
    tid = cur.lastrowid
    for i in range(1, 31):
        c.execute("INSERT INTO ticket_leg (ticket_id, match_id, market, selection, odds, result) VALUES (?,?,?,?,?,?)",
                  (tid, i, "ss|0", "R1O15", 1.48, "won"))
    c.execute("UPDATE sb_offer SET price=1.60 WHERE outcome='Peste 0.5 & Peste 1.5'")
    now = datetime(2026, 10, 11, 9, tzinfo=timezone.utc)
    SS.build(c, date(2026, 10, 11), now)
    first = c.execute("SELECT id FROM ticket WHERE day='2026-10-11' AND status='pending'").fetchone()[0]
    for i in range(1, 31):
        c.execute("INSERT INTO ticket_leg (ticket_id, match_id, market, selection, odds, result) VALUES (?,?,?,?,?,?)",
                  (tid, i, "ss|0", "R1R2", 1.70, "won"))
    SS.build(c, date(2026, 10, 11), now)
    assert c.execute("SELECT status FROM ticket WHERE id=?", (first,)).fetchone()[0] == "replaced"
    notes = json.loads(c.execute("SELECT notes FROM ticket WHERE day='2026-10-11' AND status='pending' LIMIT 1").fetchone()[0])
    assert notes["wave_keys"] == ["R1R2", "R1O15"]




def _legs(c, key, n, won, odds, tickets_per_leg=1):
    """n rezultate pe piață; fiecare selecție poate sta pe mai multe bilete (trebuie numărată o dată)."""
    for i in range(n):
        mid = 10_000 + hash(key) % 1000 * 100 + i
        c.execute("INSERT OR IGNORE INTO match (id, kickoff_utc, home_name, away_name, status) VALUES (?,?,?,?,?)",
                  (mid, "2026-10-10T18:00:00Z", "H", "A", "finished"))
        for _ in range(tickets_per_leg):
            cur = c.execute("INSERT INTO ticket (kind, variant, created_by, total_odds, stake, status, created_at, day) VALUES (?,?,?,?,?,?,?,?)",
                            (SS.KIND, SS.VARIANT, "robot", 100.0, 0.05, "lost", "2026-10-10T08:00:00Z", "2026-10-10"))
            c.execute("INSERT INTO ticket_leg (ticket_id, match_id, market, selection, odds, odds_source, result) VALUES (?,?,?,?,?,?,?)",
                      (cur.lastrowid, mid, "ss|0", key, odds, "superbet", "won" if i < won else "lost"))


def test_lift_counts_each_selection_once_and_shrinks():
    c = _db()
    _legs(c, "R1O15", 20, 18, 1.50, tickets_per_leg=3)   # 90% intră, cota promite 67%
    _legs(c, "G25", 20, 11, 1.40)                         # 55% intră, cota promite 71%
    lf = SS.key_lift(c)
    assert lf["R1O15"]["n"] == 20                         # nu 60: o selecție pe 3 bilete e un singur rezultat
    assert 1.05 < lf["R1O15"]["lift"] < 0.9 / (1 / 1.5)   # peste 1, dar micșorat față de raportul brut 1.35
    assert lf["G25"]["lift"] < SS.LIFT_DROP
    assert SS.live_stats(c)["legs"]["R1O15"]["n"] == 20


def test_apply_lift_drops_weak_markets_and_reweights():
    lift = {"G25": {"n": 20, "lift": 0.85}, "R1O15": {"n": 20, "lift": 1.10}, "C65": {"n": 3, "lift": 0.5}}
    cands = [{"key": "G25", "p": 0.7, "odds": 1.4}, {"key": "R1O15", "p": 0.7, "odds": 1.5}, {"key": "C65", "p": 0.8, "odds": 1.2}]
    out = {c["key"]: c for c in SS.apply_lift(cands, lift)}
    assert "G25" not in out                               # intră constant sub cotă: iese
    assert abs(out["R1O15"]["p"] - 0.77) < 1e-9 and out["R1O15"]["p_model"] == 0.7
    assert out["C65"]["p"] == 0.8                         # sub LIFT_MIN_N rezultate: neatins
