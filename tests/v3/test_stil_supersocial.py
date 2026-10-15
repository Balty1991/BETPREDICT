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
    # pe val (R1O15) + piețele neutre din catalog; G13 a intrat constant sub cotă (corecție sub prag), deci nu apare
    assert "R1O15" in sels and "G13" not in sels
    kept = c.execute("SELECT id FROM ticket WHERE day='2026-10-11' AND status='pending'").fetchone()[0]
    again = SS.build(c, date(2026, 10, 11), now)
    assert again.get("skipped_existing") is True or not again.get("tickets")   # nimic nou, nimic înlocuit
    assert c.execute("SELECT status FROM ticket WHERE id=?", (kept,)).fetchone()[0] == "pending"


def test_wave_change_does_not_churn_tickets():
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
    # lista pe val s-a schimbat, dar biletele bune rămân: fără refaceri din oră în oră
    assert c.execute("SELECT status FROM ticket WHERE id=?", (first,)).fetchone()[0] == "pending"




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


def test_tracks_all_priced_selections_and_learns_from_them():
    c = _db(); _seed(c)
    now = datetime(2026, 10, 11, 9, tzinfo=timezone.utc)
    rep = SS.build(c, date(2026, 10, 11), now)
    assert rep["tracked"] >= 14 * 4                      # toate selecțiile cu preț, nu doar cele de pe bilete
    n_track = c.execute("SELECT COUNT(*) FROM ss_track").fetchone()[0]
    n_legs = c.execute("SELECT COUNT(*) FROM ticket_leg").fetchone()[0]
    assert n_track > n_legs
    # 2 goluri, ambele în R2: R1O15 și R1R2 pierd, G24/G25/G13 intră
    c.execute("UPDATE match SET status='finished', ft_home=1, ft_away=1, ht_home=0, ht_away=0")
    assert SS.settle_track(c) == n_track
    res = dict(c.execute("SELECT mkey, MAX(result) FROM ss_track GROUP BY mkey").fetchall())
    assert res["G24"] == "won" and res["R1O15"] == "lost" and res["R1R2"] == "lost"
    lf = SS.key_lift(c)
    assert lf["G24"]["n"] == 14 and lf["G24"]["lift"] > 1 and lf["R1O15"]["lift"] < SS.LIFT_DROP


def test_track_price_freezes_at_kickoff():
    c = _db(); _seed(c, n=1)
    SS.track(c, [{"match_id": 1, "key": "G24", "kickoff_utc": "2026-10-11T18:00:00Z", "p": 0.6, "odds": 1.62}], datetime(2026, 10, 11, 9, tzinfo=timezone.utc))
    SS.track(c, [{"match_id": 1, "key": "G24", "kickoff_utc": "2026-10-11T18:00:00Z", "p": 0.6, "odds": 1.70}], datetime(2026, 10, 11, 17, tzinfo=timezone.utc))
    SS.track(c, [{"match_id": 1, "key": "G24", "kickoff_utc": "2026-10-11T18:00:00Z", "p": 0.6, "odds": 2.50}], datetime(2026, 10, 11, 19, tzinfo=timezone.utc))
    assert c.execute("SELECT odds FROM ss_track").fetchone()[0] == 1.70      # ultimul preț dinainte de start


def test_clv_from_first_to_last_price():
    c = _db(); _seed(c, n=1)
    k = "2026-10-11T18:00:00Z"
    SS.track(c, [{"match_id": 1, "key": "C65", "kickoff_utc": k, "p": 0.8, "odds": 1.30}], datetime(2026, 10, 10, 9, tzinfo=timezone.utc))
    SS.track(c, [{"match_id": 1, "key": "C65", "kickoff_utc": k, "p": 0.8, "odds": 1.20}], datetime(2026, 10, 11, 17, tzinfo=timezone.utc))
    lf = SS.key_lift(c)  # meciul a început (azi e după 11.10): CLV = 1.30 / 1.20 − 1
    assert lf["C65"]["clv_n"] == 1 and abs(lf["C65"]["clv"] - (1.30 / 1.20 - 1)) < 1e-3
    assert lf["C65"]["n"] == 0                                # nedecontat încă: nu intră la corecție


def test_track_table_migrates_old_schema():
    c = _db()
    c.execute("CREATE TABLE ss_track (match_id INTEGER NOT NULL, mkey TEXT NOT NULL, kickoff_utc TEXT NOT NULL, p REAL NOT NULL, "
              "odds REAL NOT NULL, updated_at TEXT NOT NULL, result TEXT, PRIMARY KEY (match_id, mkey))")
    SS.key_lift(c)
    assert "odds_first" in {r[1] for r in c.execute("PRAGMA table_info(ss_track)")}


def test_ticket_chance_is_realistic_not_model():
    c = _db(); _seed(c)
    rep = SS.build(c, date(2026, 10, 11), datetime(2026, 10, 11, 9, tzinfo=timezone.utc))
    for t in c.execute("SELECT total_odds, p_ticket, ev, notes FROM ticket WHERE variant=?", (SS.VARIANT,)).fetchall():
        # fără istoric: șansa = Π (1/cotă)/1.05 = (1/cotă totală)/1.05^n, deci EV negativ (marja), nu „EV model”
        assert t["p_ticket"] < 1 / t["total_odds"] and t["ev"] < 0
        assert "Modelul singur" in json.loads(t["notes"])["reasons"][2]
    assert all(x["ev"] < 0 for x in rep["tickets"])


def test_realistic_p_uses_learned_lift():
    c = {"key": "R1O15", "odds": 1.5}
    plain = SS.realistic_p(c, {})
    assert abs(plain - (1 / 1.5) / SS.MARGIN) < 1e-9
    assert SS.realistic_p(c, {"R1O15": {"n": 40, "lift": 1.14}}) > plain
    assert SS.realistic_p(c, {"R1O15": {"n": 3, "lift": 1.14}}) == plain   # prea puține rezultate


def test_realistic_p_is_prudent_on_learned_upside():
    c = {"key": "R1O15", "odds": 1.30}
    lf = {"R1O15": {"n": 45, "lift": 1.114, "se": 0.088}}
    p = SS.realistic_p(c, lf)
    assert p < (1 / 1.30) / SS.MARGIN * 1.114 / SS.LIFT_PRIOR      # nu ia corecția plină
    # 11 selecții la cota totală ~21: șansa nu mai sare la 16%
    total = 1.30 ** 11
    assert SS.realistic_p(c, lf) ** 11 * total - 1 < 0.6
    weak = SS.realistic_p({"key": "G13", "odds": 1.5}, {"G13": {"n": 40, "lift": 0.86, "se": 0.08}})
    assert abs(weak - (1 / 1.5) / SS.MARGIN * 0.86 / SS.LIFT_PRIOR) < 1e-9   # sub 1: corecția întreagă, fără îndulcire


def test_pending_tickets_get_current_realistic_chance():
    c = _db(); _seed(c)
    now = datetime(2026, 10, 11, 9, tzinfo=timezone.utc)
    SS.build(c, date(2026, 10, 11), now)
    c.execute("UPDATE ticket SET p_ticket=0.16, ev=2.37 WHERE variant=?", (SS.VARIANT,))   # ca biletul vechi „EV +237%”
    legs_before = c.execute("SELECT ticket_id, match_id, selection, odds FROM ticket_leg ORDER BY 1,2,3").fetchall()
    assert SS.refresh_pending(c, {}) >= 1
    for t in c.execute("SELECT total_odds, p_ticket, ev FROM ticket WHERE variant=?", (SS.VARIANT,)).fetchall():
        assert t["p_ticket"] < 1 / t["total_odds"] and t["ev"] < 0
    assert c.execute("SELECT ticket_id, match_id, selection, odds FROM ticket_leg ORDER BY 1,2,3").fetchall() == legs_before


def test_old_tracked_rows_get_first_price():
    c = _db(); _seed(c, n=1)
    k = "2026-10-11T18:00:00Z"
    SS.track(c, [{"match_id": 1, "key": "C65", "kickoff_utc": k, "p": 0.8, "odds": 1.30}], datetime(2026, 10, 10, 9, tzinfo=timezone.utc))
    c.execute("UPDATE ss_track SET odds_first=NULL")   # rând urmărit înainte de coloana nouă
    SS.track(c, [{"match_id": 1, "key": "C65", "kickoff_utc": k, "p": 0.8, "odds": 1.25}], datetime(2026, 10, 11, 9, tzinfo=timezone.utc))
    SS.track(c, [{"match_id": 1, "key": "C65", "kickoff_utc": k, "p": 0.8, "odds": 1.20}], datetime(2026, 10, 11, 17, tzinfo=timezone.utc))
    assert c.execute("SELECT odds_first, odds FROM ss_track").fetchone()[:] == (1.25, 1.20)


def test_history_doc_by_day():
    c = _db(); _seed(c, n=3)
    SS.track(c, [{"match_id": i, "key": k, "kickoff_utc": "2026-10-11T18:00:00Z", "p": p, "odds": o}
                 for i in (1, 2, 3) for k, p, o in (("R1O15", 0.7, 1.45), ("G24", 0.6, 1.62))], datetime(2026, 10, 11, 9, tzinfo=timezone.utc))
    c.execute("UPDATE match SET status='finished', ft_home=1, ft_away=1, ht_home=0, ht_away=0")   # 2 goluri, ambele în R2
    SS.settle_track(c)
    doc = SS.history_doc(c, now=datetime(2026, 10, 12, 9, tzinfo=timezone.utc))
    d = doc["days"][0]
    assert d["date"] == "2026-10-11" and d["n"] == 6 and d["won"] == 3 and d["lost"] == 3
    mk = {m["key"]: m for m in d["markets"]}
    assert mk["G24"]["win_rate"] == 1.0 and mk["R1O15"]["win_rate"] == 0.0
    assert abs(mk["G24"]["roi"] - 0.62) < 1e-9 and d["top"][0]["key"] == "R1O15" and d["top"][0]["score"] == "1-1"


def test_r1o25_combo_probability_and_settlement():
    import math
    from betpredict.lab.patterns import _probs
    p = _probs(1.5, 1.2, 0.45, None)
    # brut: R1 ~ Poisson(t·share), R2 ~ Poisson(t·(1−share)), independente
    t, sh = 2.7, 0.45
    pois = lambda lam, k: math.exp(-lam) * lam ** k / math.factorial(k)
    brute = sum(pois(t * sh, a) * pois(t * (1 - sh), b) for a in range(1, 15) for b in range(15) if a + b >= 3)
    assert abs(p["R1O25"] - brute) < 1e-6 and p["R1O25"] < p["R1O15"]
    r = {"fthg": 2, "ftag": 0, "hthg": 1, "htag": 0, "hc": None, "ac": None}
    assert not SS.won("R1O25", r) and SS.won("R1O15", r)
    assert SS.won("R1O25", {**r, "ftag": 1})
    assert not SS.won("R1O25", {"fthg": 3, "ftag": 0, "hthg": 0, "htag": 0, "hc": None, "ac": None})
    assert SS.MARKETS[("Total goluri prima repriză & Total goluri", "Peste 0.5 & Peste 2.5")] == "R1O25"
    assert SS.GROUP["R1O25"] == "combo" and "R1O25" in SS.model_p(1.5, 1.2)


def test_contradictory_first_half_corners_are_not_learned():
    c = _db(); _seed(c, n=2)
    old = "2026-10-01T18:00:00Z"   # mai vechi de 4 zile: devine anulat, nu așteaptă
    SS.track(c, [{"match_id": i, "key": k, "kickoff_utc": old, "p": 0.7, "odds": 1.4}
                 for i in (1, 2) for k in ("H1C25", "C65")], datetime(2026, 10, 1, 9, tzinfo=timezone.utc))
    from betpredict.ingest.corners import ensure
    ensure(c)
    c.execute("UPDATE match SET kickoff_utc=?, status='finished', ft_home=1, ft_away=1, ht_home=0, ht_away=0, "
              "corners_home=4, corners_away=3, corners_ht_home=2, corners_ht_away=2", (old,))
    c.execute("UPDATE match SET corners_ht_home=6 WHERE id=2")   # R1: 6 cornere, meci: 4 → date greșite
    SS.settle_track(c)
    res = {(m, k): r for m, k, r in c.execute("SELECT match_id, mkey, result FROM ss_track")}
    assert res[(1, "H1C25")] == "won" and res[(2, "H1C25")] == "void"
    assert res[(2, "C65")] == "won"                               # totalul pe meci rămâne valid
    # un rezultat trecut deja din date greșite e refăcut
    c.execute("UPDATE ss_track SET result='won' WHERE match_id=2 AND mkey='H1C25'")
    SS.settle_track(c)
    assert c.execute("SELECT result FROM ss_track WHERE match_id=2 AND mkey='H1C25'").fetchone()[0] == "void"
    assert SS.key_lift(c)["H1C25"]["n"] == 1


def _odds(c, mid, h, d, a, o, u, source="bsd_consensus"):
    for mk, line, out, v in (("1x2", 0, "HOME", h), ("1x2", 0, "DRAW", d), ("1x2", 0, "AWAY", a),
                             ("over_under", 2.5, "OVER", o), ("over_under", 2.5, "UNDER", u)):
        c.execute("INSERT INTO odds_snapshot (match_id, market, line, outcome, decimal, source, observed_at) VALUES (?,?,?,?,?,?,?)",
                  (mid, mk, line, out, v, source, "2026-10-11T08:00:00Z"))


def test_goal_lambdas_lean_on_the_market():
    c = _db(); _seed(c, 2)
    _odds(c, 1, 1.50, 4.20, 6.50, 1.55, 2.45)
    _odds(c, 1, 1.48, 4.40, 7.00, 1.52, 2.55, source="bsd:pinnacle")
    lam = SS.market_lambdas(c, [1, 2])
    assert set(lam) == {1}  # meciul fără cote rămâne doar pe robot
    lh, la = lam[1]
    assert lh > la and 2.6 < lh + la < 3.6  # favorit clar, meci cu goluri
    blh, bla, src = SS.goal_lambdas(1.5, 1.2, lam[1])
    assert abs(blh - (SS.MKT_W * lh + (1 - SS.MKT_W) * 1.5)) < 1e-9 and src == "goluri (piață + robot)"
    assert SS.goal_lambdas(1.5, 1.2, None) == (1.5, 1.2, "goluri (λ robot)")
    assert SS.goal_lambdas(None, None, lam[1])[2] == "goluri (piață)"
    cands = SS.candidates(c, datetime(2026, 10, 11, 9, tzinfo=timezone.utc), 24)
    assert {x["src"] for x in cands if x["match_id"] == 1 and x["key"] in ("G24", "R1R2")} == {"goluri (piață + robot)"}


def test_rank_blends_model_and_price_and_drops_suspect_edges():
    lift = {}
    a = {"key": "G24", "p": 0.70, "odds": 1.60, "edge": 0.12}
    b = {"key": "G24", "p": 0.70, "odds": 1.30, "edge": -0.09}
    assert SS.rank_p(b, lift) > SS.rank_p(a, lift)  # aceeași șansă de model, dar casa o vede mai probabilă pe b
    assert SS.realistic_p(a, lift) < SS.rank_p(a, lift) < a["p"]
    assert SS.suspect({"key": "GG", "edge": 0.40}) and not SS.suspect({"key": "C85", "edge": 0.40})
    pool = SS._priced_pool([{**a, "match_id": 1}, {"key": "GG", "p": 0.9, "odds": 1.8, "edge": 0.62, "match_id": 2}], ("*",), (1.15, 2.2))
    assert [x["match_id"] for x in pool] == [1]


def test_best_ticket_mixes_markets():
    c = _db(); _seed(c, 30)
    c.execute("UPDATE sb_offer SET price=1.80 WHERE outcome='2-4'")  # G24 și R1R2 cu avantaj, ca G13
    c.execute("UPDATE sb_offer SET price=2.00 WHERE outcome='Da'")
    SS.build(c, date(2026, 10, 11), datetime(2026, 10, 11, 9, tzinfo=timezone.utc))
    best = [t for t in c.execute("SELECT id, notes FROM ticket").fetchall() if json.loads(t["notes"])["stil"] == SS.BEST_NAME]
    assert len(best) == 1
    keys = [r["selection"] for r in c.execute("SELECT selection FROM ticket_leg WHERE ticket_id=?", (best[0]["id"],))]
    assert len(set(keys)) >= 2 and max(keys.count(k) for k in keys) <= SS.BEST_PER_KEY


def test_tickets_that_turned_bad_before_kickoff_are_rebuilt():
    c = _db(); _seed(c, 30)
    now = datetime(2026, 10, 11, 9, tzinfo=timezone.utc)
    SS.build(c, date(2026, 10, 11), now)
    gol = [t["id"] for t in c.execute("SELECT id, notes FROM ticket WHERE status='pending'") if json.loads(t["notes"])["stil"] == "Goluri 1–3"]
    assert gol
    c.execute("UPDATE sb_offer SET price=1.30 WHERE outcome='1-3'")  # cota a scăzut mult: G13 nu mai are valoare
    rep = SS.build(c, date(2026, 10, 11), now)
    assert rep.get("stale_replaced", 0) >= 1
    assert c.execute("SELECT status FROM ticket WHERE id=?", (gol[0],)).fetchone()[0] == "replaced"
    # un bilet cu un meci început nu se atinge
    assert SS._stale_tickets(c, date(2026, 10, 11), [], datetime(2026, 10, 11, 19, tzinfo=timezone.utc)) == []


def test_safe_best_ticket_stays_in_its_band():
    c = _db(); _seed(c, 30)
    c.execute("UPDATE sb_offer SET price=1.80 WHERE outcome='2-4'")
    c.execute("UPDATE sb_offer SET price=2.00 WHERE outcome='Da'")
    now = datetime(2026, 10, 11, 9, tzinfo=timezone.utc)
    SS.build(c, date(2026, 10, 11), now)
    safe = [t for t in c.execute("SELECT * FROM ticket").fetchall() if json.loads(t["notes"])["stil"] == SS.BEST_SAFE_NAME]
    assert len(safe) == 1 and 20 <= safe[0]["total_odds"] <= 40 * 1.04
    assert not SS._odds_outside(c, date(2026, 10, 11))  # banda 20–40 nu forțează refacerea la fiecare rulare


def test_family_cap_in_assemble():
    pool = [{"match_id": i, "key": k, "odds": 1.6, "p": 0.9 - i * 0.001, "league_id": None}
            for i, k in enumerate(["C65", "C75", "C85", "C95", "H1C25", "H1C35"] * 3 + ["G13", "GG", "R1R2", "YC35"] * 2)]
    legs = SS._assemble(pool, 4, 16, 3, 80, 200, 4, SS.BEST_PER_FAMILY)
    assert legs and sum(SS.family(c["key"]) == "cornere" for c in legs) <= SS.BEST_PER_FAMILY
    assert len({SS.family(c["key"]) for c in legs}) >= 2


def _robot_pred(c, mid, market, line, sel, p, sb, healthy=True, created="2026-10-11T08:00:00Z"):
    c.execute("""INSERT INTO prediction (match_id, market, line, period, selection, p_model, p_calibrated, reasons_json,
                 model_version, created_at, shown_on_page) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
              (mid, market, line, "FT", sel, p, p, json.dumps({"healthy": healthy, "odds_alt": {"superbet": sb}}), "v", created, "predictii"))


def test_main_robot_predictions_join_the_mixed_ticket():
    c = _db(); _seed(c, 30)
    for i in range(1, 31):
        _robot_pred(c, i, "double_chance", 0, "X2", 0.62, 1.75)
        _robot_pred(c, i, "1x2", 0, "HOME", 0.50, 2.20, healthy=False)  # nesănătoasă: nu intră
    now = datetime(2026, 10, 11, 9, tzinfo=timezone.utc)
    rc = SS.robot_candidates(c, now, SS.HORIZON_H)
    assert {x["key"] for x in rc} == {"R:double_chance:0:X2"} and len(rc) == 30
    assert SS.label("R:double_chance:0:X2") == "Șansă dublă X2" and SS.label("R:over_under:2.5:OVER") == "Total goluri Peste 2.5"
    assert SS.family("R:double_chance:0:X2") == "rezultat" and SS.family("R:btts:0:YES") == "goluri"
    SS.build(c, date(2026, 10, 11), now)
    best = [t for t in c.execute("SELECT id, notes FROM ticket").fetchall() if json.loads(t["notes"])["stil"].startswith(SS.BEST_NAME)]
    assert best  # 3 G13 + 3 X2 ajung la cota 20–40
    keys = [r[0] for r in c.execute("SELECT selection FROM ticket_leg WHERE ticket_id=?", (best[0]["id"],))]
    assert "R:double_chance:0:X2" in keys and "G13" in keys  # amestec: robotul principal + piețele Stil


def test_robot_keys_settle_including_dnb_void():
    m = {"status": "finished", "ft_home": 1, "ft_away": 1, "ht_home": 0, "ht_away": 1, "kickoff_utc": "2026-10-11T18:00:00Z",
         "corners_home": None, "corners_away": None, "corners_ht_home": None, "corners_ht_away": None, "cards_home": None, "cards_away": None}
    assert SS._settle_result("R:double_chance:0:X2", m, "2026-10-01") == "won"
    assert SS._settle_result("R:1x2:0:HOME", m, "2026-10-01") == "lost"
    assert SS._settle_result("R:draw_no_bet:0:HOME", m, "2026-10-01") == "void"
    assert SS._settle_result("R:over_under:1.5:OVER", m, "2026-10-01") == "won"


def test_efficient_assembly_reaches_target_odds_with_short_and_long_prices():
    # 40 de cote mici foarte sigure și câteva cote medii: doar cu cele mici nu se ajunge la 80 în 16 selecții
    pool = [{"match_id": i, "key": f"K{i % 6}", "odds": 1.15, "p": 0.85, "edge": 0.0, "league_id": None} for i in range(40)]
    pool += [{"match_id": 100 + i, "key": f"M{i % 6}", "odds": 1.6, "p": 0.64, "edge": 0.02, "league_id": None} for i in range(20)]
    g = SS._by_green(pool)
    assert SS._assemble(g, 4, 16, 3, 80, 200, 4) is None
    legs = SS._assemble(g, 4, 16, 3, 80, 200, 4, efficient=True)
    assert legs and 80 <= SS._prod(legs) <= SS.ODDS_HI_HARD


def test_replace_keeps_tickets_already_in_play():
    c = _db(); _seed(c, 30)
    SS.build(c, date(2026, 10, 11), datetime(2026, 10, 11, 9, tzinfo=timezone.utc))
    n = c.execute("SELECT COUNT(*) FROM ticket WHERE status='pending'").fetchone()[0]
    assert n
    # toate meciurile au început la 18:00: o refacere forțată nu atinge biletele aflate în joc
    SS.build(c, date(2026, 10, 11), datetime(2026, 10, 11, 18, 30, tzinfo=timezone.utc), replace=True)
    assert c.execute("SELECT COUNT(*) FROM ticket WHERE status='replaced'").fetchone()[0] == 0
