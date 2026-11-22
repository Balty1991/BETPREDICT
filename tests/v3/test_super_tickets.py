import sqlite3
from datetime import date, datetime, timezone

from betpredict.builder import super_tickets as S
from betpredict.builder.pool import Cand
from betpredict.store import db as DB


def _cand(i, odds=1.6, p=0.62, market="over_under", sel="OVER", line=2.5, league=None):
    c = Cand(prediction_id=i, match_id=i, league_id=league if league is not None else i % 9, league="L", kickoff_utc="2026-11-14T18:00:00Z",
             home=f"H{i}", away=f"A{i}", market=market, line=line, selection=sel, odds=odds, p=p, ev=p * odds - 1, grade="B",
             confidence=60, p_market=p, odds_source="superbet")
    return c


def test_many_tickets_per_tier_with_limited_reuse_and_stats(monkeypatch):
    monkeypatch.setattr(S, "LONG_MAX", S.LONG_ACTIVE)
    monkeypatch.setattr(S, "SEL_CAP", {"YES": 4})  # bazinul de test are doar 3 tipuri de selecții  # fără bilete în plus de zi bogată: a doua rulare nu adaugă nimic
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row; DB.init_db(c)
    for i in range(1, 161):
        c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status) VALUES (?, '2026-11-14T18:00:00Z', 'h', 'a', 'notstarted')", (i,))
    kinds = [("over_under", "OVER", 2.5), ("1x2", "AWAY", 0.0), ("1x2", "HOME", 0.0)]  # pe un bilet cel mult MAX_PER_SEL de același tip
    pool = [_cand(i, odds=1.36 + (i % 7) * 0.03, p=0.74, market=kinds[i % 3][0], sel=kinds[i % 3][1], line=kinds[i % 3][2]) for i in range(1, 161)]
    pool += [_cand(100 + i, market="btts", sel="NO", odds=1.9, p=0.6) for i in range(5)]  # NG nu intră
    now = datetime(2026, 11, 14, 8, tzinfo=timezone.utc)
    rep = S.build(c, date(2026, 11, 14), now, pool)
    # un meci apare o singură dată (selecțiile de aici nu sunt „foarte sigure”): 120 de meciuri ajung pentru câteva bilete,
    # fiecare țintă are măcar unul
    assert rep["tickets"] >= 3 and {m["variant"] for m in rep["made"]} == {"s10", "s100", "s500", "s1000", "s5000", "s10000"}
    for t in c.execute("SELECT id, variant, target_odds, total_odds FROM ticket WHERE kind=?", (S.KIND,)):
        assert t["target_odds"] <= t["total_odds"] <= t["target_odds"] * (S.SPAN if t["variant"] in S.SHORT else S.LONG_SPAN)
        legs = c.execute("SELECT match_id, market, selection FROM ticket_leg WHERE ticket_id=?", (t["id"],)).fetchall()
        assert len({l["match_id"] for l in legs}) == len(legs)
        assert not any(l["market"] == "btts|0" and l["selection"] == "NO" for l in legs)
    # pe fiecare familie (bilete de ~10 / bilete lungi) un meci apare o singură dată
    for fam in ("t.variant='s10'", "t.variant!='s10'"):
        use = [r[0] for r in c.execute(f"SELECT COUNT(*) FROM ticket_leg l JOIN ticket t ON t.id=l.ticket_id WHERE {fam} GROUP BY l.match_id")]
        assert max(use) == 1
    assert S.build(c, date(2026, 11, 14), now, pool).get("tickets", 0) == 0  # a doua rulare nu mai adaugă nimic
    c.execute("UPDATE ticket SET status='won' WHERE id=(SELECT MIN(id) FROM ticket)")
    s = S.stats_doc(c, now)
    t1 = next(x for x in s["tiers"] if x["variant"] == c.execute("SELECT variant FROM ticket WHERE status='won'").fetchone()[0])
    assert t1["n"] == 1 and t1["won"] == 1 and t1["best"] >= t1["target"]


def test_long_tickets_are_kept_at_five_and_replaced_when_lost(monkeypatch):
    monkeypatch.setattr(S, "RICH_MATCHES", 10**6)  # zi obișnuită (miercuri, ofertă normală): exact 5
    monkeypatch.setattr(S, "SEL_CAP", {"YES": 4})  # bazinul de test are doar 3 tipuri de selecții
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row; DB.init_db(c)
    for i in range(1, 201):
        c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status) VALUES (?, '2026-11-15T18:00:00Z', 'h', 'a', 'notstarted')", (i,))
    kinds = [("over_under", "OVER", 2.5), ("1x2", "AWAY", 0.0), ("1x2", "HOME", 0.0)]
    pool = [_cand(i, odds=1.36 + (i % 7) * 0.02, p=0.74, market=kinds[i % 3][0], sel=kinds[i % 3][1], line=kinds[i % 3][2]) for i in range(1, 201)]
    for x in pool:
        x.kickoff_utc = "2026-11-15T18:00:00Z"
    now = datetime(2026, 11, 14, 8, tzinfo=timezone.utc)
    S.build(c, date(2026, 11, 11), now, pool)
    q = "SELECT COUNT(*) FROM ticket WHERE kind=? AND status='pending' AND variant!='s10'"
    assert c.execute(q, (S.KIND,)).fetchone()[0] == S.LONG_ACTIVE
    assert S.build(c, date(2026, 11, 11), now, pool)["tickets"] == 0
    c.execute("UPDATE ticket SET status='lost' WHERE id=(SELECT MIN(id) FROM ticket WHERE variant!='s10')")
    rep = S.build(c, date(2026, 11, 11), now, pool)
    assert rep["tickets"] == 1 and c.execute(q, (S.KIND,)).fetchone()[0] == S.LONG_ACTIVE
    # meciurile biletelor lungi în joc nu se repetă
    use = [r[0] for r in c.execute("SELECT COUNT(*) FROM ticket_leg l JOIN ticket t ON t.id=l.ticket_id WHERE t.status='pending' AND t.variant!='s10' GROUP BY l.match_id")]
    assert max(use) == 1


def _close_db(n_won, n_lost, price=1.35, league="Premier League", ko="2026-11-10T15:00:00Z"):
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row; DB.init_db(c)
    c.execute("INSERT INTO league (id, name) VALUES (1, ?)", (league,))
    c.execute("CREATE TABLE IF NOT EXISTS sb_offer_close (match_id INTEGER, market_name TEXT, outcome TEXT, line TEXT, price REAL, observed_at TEXT)")
    for i in range(n_won + n_lost):
        won = i < n_won  # R2 1-3: câștigă la 1 gol în repriza a doua, pierde la 0
        c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status, league_id, ft_home, ft_away, ht_home, ht_away) "
                  "VALUES (?, ?, 'h', 'a', 'finished', 1, ?, 0, 0, 0)", (i + 1, ko, 1 if won else 0))
        for oc, pr in (("1-3", price), ("1-2", 1.5)):
            c.execute("INSERT INTO sb_offer_close (match_id, market_name, outcome, price) VALUES (?, 'A doua repriză - Interval goluri', ?, ?)",
                      (i + 1, oc, pr))
    return c


def test_leg_calibration_shrinks_toward_price_and_learns_losses():
    key = ("A doua repriză - Interval goluri", "1-3")
    now = datetime(2026, 11, 19, 8, tzinfo=timezone.utc)
    empty = S.leg_calibration(_close_db(0, 0), now)
    assert empty["selections"] == 0 and empty["q"][(key, "club_day")] == S.CAL_Q0
    # 100 de selecții la 1.35, doar 50% intrate (prețul spune 74%): șansa coboară clar, dar nu până la 50% (micșorare)
    bad = S.leg_calibration(_close_db(50, 50), now)
    q = bad["q"][(key, "club_day")]
    assert 0.5 * 1.35 < q < 0.95 and bad["n"][(key, "club_day")] == (100, 50)
    # foarte bine pe puține zile: plafonat la CAL_Q_MAX, nu promitem avantaj mare
    assert S.leg_calibration(_close_db(100, 0), now)["q"][(key, "club_day")] == S.CAL_Q_MAX
    # meciurile care încă nu s-au jucat (după acum − 3 h) nu intră: fără privit în viitor
    assert S.leg_calibration(_close_db(50, 50, ko="2026-11-19T07:00:00Z"), now)["selections"] == 0


def test_overround_and_segment():
    pr = {("Final", "1"): 1.5, ("Final", "X"): 4.0, ("Final", "2"): 6.0}
    assert abs(S.overround(pr, ("Final", "1")) - (1 / 1.5 + 1 / 4 + 1 / 6)) < 1e-9
    assert S.overround({("Final", "1"): 1.5}, ("Final", "1")) is None
    assert S.segment("World Cup Qualification", "2026-11-14T18:00:00Z") == "intl_day"
    assert S.segment("Premier League", "2026-11-14T02:00:00Z") == "club_night"


def test_load_recommended_uses_calibrated_p_and_match_overround():
    c = _close_db(50, 50)  # R2 1-3 a intrat doar 50% la 1.35 în ultimele zile
    c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status, league_id) VALUES (999, '2026-11-19T15:00:00Z', 'H', 'A', 'notstarted', 1)")
    for mn, oc, pr in (("A doua repriză - Interval goluri", "1-3", 1.35), ("A doua repriză - Total goluri", "Sub 0.5", 4.0),
                       ("A doua repriză - Total goluri", "Peste 3.5", 15.0)):
        c.execute("INSERT INTO sb_offer (match_id, market_name, outcome, price, observed_at) VALUES (999, ?, ?, ?, '2026-11-19T07:00:00Z')", (mn, oc, pr))
    x = next(x for x in S.load_recommended(c, datetime(2026, 11, 19, 8, tzinfo=timezone.utc)) if x.selection == "H2G13")
    assert x.p_honest < 1 / 1.35 and x.p_honest < (1 + 0.03 / 2) / 1.35  # mai mic decât prețul și decât vechea formulă
    assert abs(x.extra["ovr"] - (1 / 1.35 + 1 / 4 + 1 / 15)) < 1e-9 and x.extra["cal_n"] == (100, 50)


def test_legs_diversified_and_explained_in_romanian():
    import json

    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row; DB.init_db(c)
    pool = []
    for i in range(1, 41):
        ko = f"2026-11-14T{10 + i % 10:02d}:00:00Z"
        c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status) VALUES (?, ?, 'h', 'a', 'notstarted')", (i, ko))
        x = _cand(i, odds=1.40 + (i % 5) * 0.04, p=0.70, market="ss", sel=["H2G13", "H1U15", "H2G12"][i % 3], line=0.0, league=i % 8)
        x.kickoff_utc = ko
        x.extra.update({"seg": "club_day", "ovr": 1.06 + (i % 4) * 0.01, "ovr_typ": 1.08, "cal_n": (80, 60), "cal_days": 45})
        pool.append(x)
    S.build(c, date(2026, 11, 14), datetime(2026, 11, 14, 8, tzinfo=timezone.utc), pool)
    t = c.execute("SELECT id, notes FROM ticket WHERE variant='s10'").fetchone()
    assert t is not None
    notes = json.loads(t["notes"])
    assert notes["rules"] == S.RULES_V and len(notes["leg_reasons"]) == len(notes["leg_p"])
    text = " ".join(" ".join(r["r"]) for r in notes["leg_reasons"])
    assert "șansă estimată" in text and "Marja Superbet" in text and "60 din 80 intrate" in text
    mids = [r[0] for r in c.execute("SELECT match_id FROM ticket_leg WHERE ticket_id=?", (t["id"],))]
    lg = [m % 8 for m in mids]
    assert max(lg.count(x) for x in lg) <= 2  # pe biletul de ~10, cel mult 2 meciuri din aceeași ligă când oferta permite
    slots = [S.slot(next(x for x in pool if x.match_id == m)) for m in mids]
    assert max(slots.count(s) for s in slots) <= 3


def test_rich_day_adds_long_tickets_up_to_ten():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row; DB.init_db(c)
    for i in range(1, 301):
        c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status) VALUES (?, '2026-11-15T18:00:00Z', 'h', 'a', 'notstarted')", (i,))
    kinds = [("over_under", "OVER", 2.5), ("1x2", "AWAY", 0.0), ("1x2", "HOME", 0.0)]
    pool = [_cand(i, odds=1.36 + (i % 7) * 0.03, p=0.74, market=kinds[i % 3][0], sel=kinds[i % 3][1], line=kinds[i % 3][2], league=i % 40)
            for i in range(1, 301)]
    for x in pool:
        x.kickoff_utc = "2026-11-15T18:00:00Z"
    now = datetime(2026, 11, 14, 8, tzinfo=timezone.utc)
    S.build(c, date(2026, 11, 14), now, pool)  # sâmbătă, 300 de meciuri: zi bogată
    n = c.execute("SELECT COUNT(*) FROM ticket WHERE kind=? AND status='pending' AND variant!='s10'", (S.KIND,)).fetchone()[0]
    assert S.LONG_ACTIVE < n <= S.LONG_MAX
    use = [r[0] for r in c.execute("SELECT COUNT(*) FROM ticket_leg l JOIN ticket t ON t.id=l.ticket_id WHERE t.variant!='s10' GROUP BY l.match_id")]
    assert max(use) == 1
