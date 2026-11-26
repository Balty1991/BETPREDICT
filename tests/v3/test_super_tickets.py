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
    kinds = [("ss", "H1U15", 0.0), ("1x2", "AWAY", 0.0), ("1x2", "HOME", 0.0)]  # pe un bilet cel mult MAX_PER_SEL de același tip
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
    kinds = [("ss", "H1U15", 0.0), ("1x2", "AWAY", 0.0), ("1x2", "HOME", 0.0)]
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
    kinds = [("ss", "H1U15", 0.0), ("1x2", "AWAY", 0.0), ("1x2", "HOME", 0.0)]
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


def test_short_ticket_prefers_tier_a_markets(monkeypatch):
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row; DB.init_db(c)
    for i in range(1, 61):
        c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status) VALUES (?, '2026-11-25T15:00:00Z', 'h', 'a', 'notstarted')", (i,))
    pool = [_cand(i, odds=1.45 + (i % 4) * 0.04, p=0.70, market="ss", sel="H2G12" if i % 2 else "H1U15", line=0.0) for i in range(1, 61)]
    for x in pool:
        x.kickoff_utc = "2026-11-25T15:00:00Z"
    now = datetime(2026, 11, 25, 8, tzinfo=timezone.utc)
    monkeypatch.setattr(S, "LONG_ACTIVE", 0); monkeypatch.setattr(S, "LONG_MAX", 0)
    S.build(c, date(2026, 11, 25), now, pool)
    sels = [r[0] for r in c.execute("SELECT l.selection FROM ticket_leg l JOIN ticket t ON t.id=l.ticket_id WHERE t.variant='s10'")]
    assert sels and set(sels) <= {"H1U15", "H2G12"} and sels.count("H1U15") <= 3 * len({r[0] for r in c.execute("SELECT id FROM ticket WHERE variant='s10'")})


def test_build_one_lookahead_keeps_long_ticket_near_target():
    # selecțiile mari (1.65) sunt primele în listă: fără privire înainte, 20 de selecții minim ar duce biletul de 1.000
    # mult peste țintă; cu ea, după câteva mari intră cele mici (1.36) și biletul rămâne sub 1,5 × țintă
    big = [_cand(i, odds=1.65, p=0.6, sel="HOME", market="1x2", line=0.0, league=i) for i in range(1, 21)]
    small = [_cand(100 + i, odds=1.36, p=0.73, sel=("AWAY", "H1U15", "H2G13")[i % 3], market="ss", line=0.0, league=100 + i)
             for i in range(1, 31)]
    pool = big + small
    legs = S.build_one(pool, 1000.0, (20, 25), 0, {}, (), 1.5, league_cap=3)
    total = 1.0
    for c in legs:
        total *= c.odds
    assert len(legs) >= 20 and 1000.0 <= total <= 1500.0
    # când nu încape în fereastra strânsă, nu iese nimic (build încearcă apoi fereastra mai largă din LONG_SPANS)
    assert S.build_one(big, 1000.0, (20, 25), 0, {}, (), 1.5, league_cap=3) is None


def test_long_spans_try_tight_window_first_and_thousand_from_17_legs():
    assert S.LONG_SPANS[0] < S.LONG_SPANS[-1] == S.LONG_SPAN and list(S.LONG_SPANS) == sorted(S.LONG_SPANS)
    rng = {v: r for v, _t, _n, r in S.TIERS}
    assert rng["s1000"][0] == 17 and rng["s1000"][0] * 1.0 < 1000 ** (1 / 1.35)  # 17 selecții de ~1.50 ajung la ~1.000
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row; DB.init_db(c)
    for i in range(1, 201):
        c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status) VALUES (?, '2026-11-15T18:00:00Z', 'h', 'a', 'notstarted')", (i,))
    kinds = [("1x2", "AWAY", 0.0), ("1x2", "HOME", 0.0), ("ss", "H1U15", 0.0)]
    pool = [_cand(i, odds=1.40 + (i % 6) * 0.05, p=0.7, market=kinds[i % 3][0], sel=kinds[i % 3][1], line=kinds[i % 3][2], league=i % 40)
            for i in range(1, 201)]
    for x in pool:
        x.kickoff_utc = "2026-11-15T12:00:00Z"
    S.build(c, date(2026, 11, 11), datetime(2026, 11, 14, 8, tzinfo=timezone.utc), pool)
    rows = c.execute("SELECT variant, target_odds, total_odds FROM ticket WHERE kind=? AND variant!='s10'", (S.KIND,)).fetchall()
    assert rows and all(r["target_odds"] <= r["total_odds"] <= r["target_odds"] * S.LONG_SPANS[0] for r in rows)
    assert any(r["variant"] == "s1000" for r in rows)


def test_lit_adj_big_club_and_blowout_only_for_club_favourites():
    big = _cand(1, odds=1.45, market="1x2", sel="HOME"); big.home = "Arsenal"
    plain = _cand(2, odds=1.45, market="1x2", sel="HOME")
    blow = _cand(3, odds=1.45, market="1x2", sel="AWAY"); blow.extra["last_margin"] = 3
    both = _cand(4, odds=1.45, market="1x2", sel="AWAY"); both.away = "Real Madrid"; both.extra["last_margin"] = 4
    assert S.lit_adj(big) == S.LIT_BIG and S.lit_adj(plain) == 0.0 and S.lit_adj(blow) == S.LIT_BLOWOUT
    assert abs(S.lit_adj(both) - (S.LIT_BIG + S.LIT_BLOWOUT)) < 1e-12
    # doar 1X2, la cluburi, 1.25–1.70; „Rangers” e ancorat (nu Enugu Rangers International)
    away_big = _cand(5, odds=1.45, market="1x2", sel="HOME"); away_big.away = "Arsenal"
    other = _cand(6, odds=1.45, market="ss", sel="H1U15"); other.home = "Arsenal"; other.extra["last_margin"] = 5
    high = _cand(7, odds=1.9, market="1x2", sel="HOME"); high.home = "Arsenal"
    intl = _cand(8, odds=1.45, market="1x2", sel="HOME"); intl.home = "Arsenal"; intl.league = "Friendlies"
    nig = _cand(9, odds=1.45, market="1x2", sel="HOME"); nig.home = "Enugu Rangers International"
    assert all(S.lit_adj(x) == 0.0 for x in (away_big, other, high, intl, nig))
    # clasarea: la cost egal, clubul mare trece înainte, favoritul după 3+ goluri rămâne în urmă
    assert S._rank(big) < S._rank(plain) < S._rank(blow)


def test_last_margins_uses_previous_finished_match_within_window():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row; DB.init_db(c)
    rows = [(1, "2026-11-01T15:00:00Z", 10, 20, 1, 0, "finished"), (2, "2026-11-08T15:00:00Z", 30, 10, 0, 4, "finished"),
            (3, "2026-11-12T15:00:00Z", 10, 40, None, None, "postponed"), (4, "2026-09-01T15:00:00Z", 50, 60, 5, 0, "finished")]
    for i, ko, h, a, fh, fa, st in rows:
        c.execute("INSERT INTO match (id, kickoff_utc, home_id, away_id, ft_home, ft_away, status) VALUES (?, ?, ?, ?, ?, ?, ?)", (i, ko, h, a, fh, fa, st))
    m = S.last_margins(c, [(10, "2026-11-15T18:00:00Z"), (30, "2026-11-15T18:00:00Z"), (10, "2026-11-05T18:00:00Z"), (50, "2026-11-15T18:00:00Z"),
                           (None, "2026-11-15T18:00:00Z")])
    assert m[(10, "2026-11-15T18:00:00Z")] == 4 and m[(30, "2026-11-15T18:00:00Z")] == -4 and m[(10, "2026-11-05T18:00:00Z")] == 1
    assert (50, "2026-11-15T18:00:00Z") not in m  # ultimul meci e mai vechi de 30 de zile


def test_cup_detection_and_penalty_and_cap():
    from types import SimpleNamespace as N

    for name in ("Coupe de France", "FA Cup", "Copa del Rey", "Taça de Portugal", "DFB Pokal", "Ziraat Turkiye Kupasi", "Coppa Italia"):
        assert S.is_cup(N(league=name)), name
    for name in ("Copa Libertadores", "Champions League", "Europa League", "World Cup 2026", "Premier League", "Liga Portugal 2",
                 "AFC Asian Cup 2023", "Africa Cup of Nations 2023"):
        assert not S.is_cup(N(league=name)), name
    a, b = _cand(1, market="1x2", sel="HOME", odds=1.4, p=0.7), _cand(2, market="1x2", sel="HOME", odds=1.4, p=0.7)
    b.league = "Coupe de France"
    assert abs(S._rank(b) - S._rank(a) - S.CUP_PENALTY) < 1e-9
    # cel mult cup_cap selecții din cupe pe un bilet
    pool = [_cand(i, market="1x2", sel="HOME", odds=1.45, p=0.72, league=i) for i in range(1, 9)]
    for x in pool:
        x.league = "FA Cup"
    pool += [_cand(i, market="1x2", sel="HOME", odds=1.45, p=0.72, league=i) for i in range(20, 28)]
    legs = S.build_one(pool, 10.0, (6, 9), 0, {}, cup_cap=1)
    assert legs and sum(1 for x in legs if S.is_cup(x)) == 1


def test_second_division_corner_combo_ranked_first():
    a = _cand(1, market="bb", sel="Peste 0.5 goluri; Peste 7.5 cornere|x", odds=1.5, p=0.66, league=6)
    b = _cand(2, market="bb", sel="Peste 0.5 goluri; Peste 7.5 cornere|x", odds=1.5, p=0.66, league=12)  # Championship
    h = _cand(3, market="1x2", sel="HOME", odds=1.5, p=0.66, league=12)  # doar combinația cu cornere are preferința
    assert S.is_corner_2nd(b) and not S.is_corner_2nd(a) and not S.is_corner_2nd(h)
    assert abs(S._rank(a) - S._rank(b) - S.CORNER_2ND_BONUS) < 1e-9
    assert b.p == a.p  # șansa afișată nu se schimbă
    assert any("ligă secundă" in r.lower() for r in S.leg_reasons(b))


def test_corner_combo_penalized_midweek_only():
    combo = "Peste 0.5 goluri; Peste 7.5 cornere|Da"
    tue = _cand(1, odds=1.5, p=0.68, market="bb", sel=combo); tue.kickoff_utc = "2026-11-24T18:00:00Z"   # marți
    sat = _cand(2, odds=1.5, p=0.68, market="bb", sel=combo); sat.kickoff_utc = "2026-11-21T18:00:00Z"   # sâmbătă
    late_mon = _cand(3, odds=1.5, p=0.68, market="bb", sel=combo); late_mon.kickoff_utc = "2026-11-23T22:30:00Z"  # marți 00:30 RO
    fav = _cand(4, odds=1.5, p=0.68, market="1x2", sel="HOME"); fav.kickoff_utc = "2026-11-24T18:00:00Z"
    fav_sat = _cand(5, odds=1.5, p=0.68, market="1x2", sel="HOME"); fav_sat.kickoff_utc = "2026-11-21T18:00:00Z"
    assert S.is_midweek(tue) and S.is_midweek(late_mon) and not S.is_midweek(sat)
    assert abs(S._rank(tue) - S._rank(sat) - S.MIDWEEK_COMBO_PENALTY) < 1e-9
    assert S._rank(fav) == S._rank(fav_sat)  # doar combinația cu cornere
    assert [c.match_id for c in S.candidates([tue, sat], datetime(2026, 11, 20, tzinfo=timezone.utc), hours=24 * 7)] == [2, 1]


def test_rules_off_disable_rank_adjustments():
    a, b = _cand(1, market="1x2", sel="HOME", odds=1.4, p=0.7), _cand(2, market="1x2", sel="HOME", odds=1.4, p=0.7)
    b.league = "Coupe de France"
    assert S._rank(b) > S._rank(a)
    S.RULES_OFF.add("cup")
    try:
        assert abs(S._rank(b) - S._rank(a)) < 1e-9
    finally:
        S.RULES_OFF.discard("cup")


def test_rule_check_weekly_update_runs_once_per_week():
    from betpredict.builder import rule_check as R
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row; DB.init_db(c)
    now = datetime(2026, 12, 1, 8, tzinfo=timezone.utc)
    first = R.weekly_update(c, now)
    assert first and first["off"] == [] and all(r["status"] == "proba" for r in first["rules"])
    assert R.weekly_update(c, now) is None and R.off_rules(c) == set()
    assert R.doc(c, now)["checked_week"] == first["week"]


def test_superavantaj_favourite_ranked_first():
    a, b = _cand(1, market="1x2", sel="HOME", odds=1.45, p=0.66), _cand(2, market="1x2", sel="HOME", odds=1.45, p=0.66)
    b.extra["sa"] = True
    assert S.lit_adj(b) == S.SA_ADJ and S._rank(b) < S._rank(a)
    assert any("SuperAvantaj" in r for r in S.leg_reasons(b))
