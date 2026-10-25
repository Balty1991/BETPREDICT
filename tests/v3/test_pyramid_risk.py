import sqlite3

from betpredict.builder import pyramid_risk as R
from betpredict.builder.pool import Cand


def _c(i, odds, p, market="over_under", lg=None):
    return Cand(i, i, lg if lg is not None else i, None, "2026-10-18T12:00:00Z", None, None, market, 2.5, "OVER", odds, p, p * odds - 1, "A", 80,
                p_market=min(0.97, p))


def test_pick_targets_band_and_ev():
    """Combinațiile (pentru reguli fără acumulare) rămân în bandă, cu EV ≥ 0."""
    rules = {**R.RULES_R5, "min_legs": 3, "max_legs": 5, "leg_odds": [1.2, 1.9], "leg_min_p": 0.55, "greedy": False}
    pool = [_c(1, 1.75, 0.6), _c(2, 1.7, 0.62), _c(3, 1.8, 0.58), _c(4, 3.0, 0.4), _c(5, 1.65, 0.63)]
    st = {"losses": 0, "target": 5.0, "band": [4.25, 6.0], "avoid": [], "paused": []}
    r = R.pick(pool, rules, {"market": {}, "league": {}}, st)
    assert r["status"] == "pick"
    legs, p = r["main"]
    import math
    o = math.prod(c.odds for c in legs)
    assert 4.25 <= o <= 6.0 and 3 <= len(legs) <= 5 and p * o - 1 >= 0 and all(c.odds <= 1.9 for c in legs)


GREEDY = {**R.BASE, "target_odds": 5.0, "band": [4.0, 6.5], "max_steps": 5, "variant": "pr5", "min_legs": 5, "max_legs": 9,
          "leg_odds": [1.15, 1.40], "leg_min_p": 0.72, "greedy": True}
GREEDY10 = {**GREEDY, "target_odds": 10.0, "band": [8.0, 13.0], "min_legs": 8, "max_legs": 12}


def test_r5_r10_rules_25oct():
    """25.10 (Alin): 2–4 selecții, cota ≥ 1.40 pe selecție, EV ≥ −3%, fără start 00:00–07:00 ora României."""
    import math
    for rules in (R.RULES_R5, R.RULES_R10):
        assert rules["min_legs"] == 2 and rules["max_legs"] == 4 and rules["leg_odds"][0] == 1.40 and not rules.get("greedy")
    pool = [_c(i, 2.3, 0.45) for i in range(1, 8)] + [_c(50, 1.25, 0.95)]
    st = {"losses": 0, "target": 5.0, "band": [4.0, 6.5], "avoid": [], "paused": []}
    r = R.pick(pool, R.RULES_R5, {"market": {}, "league": {}}, st)
    legs, p = r["main"]
    assert r["status"] == "pick" and 2 <= len(legs) <= 4 and all(c.odds >= 1.40 for c in legs)
    assert p * math.prod(c.odds for c in legs) - 1 >= -0.03
    # EV sub −3% → nimic publicat (fără treapta „cea mai mare șansă”)
    bad = [_c(i, 2.3, 0.38) for i in range(1, 8)]
    assert R.pick(bad, R.RULES_R5, {"market": {}, "league": {}}, st)["status"] == "no_bet"


def test_night_kickoffs_excluded():
    assert R.night_kickoff("2026-10-25T23:30:00Z")      # 01:30 ora României (iarnă, UTC+2)
    assert R.night_kickoff("2026-10-26T04:59:00Z")      # 06:59
    assert not R.night_kickoff("2026-10-26T05:00:00Z")  # 07:00
    assert not R.night_kickoff("2026-10-25T21:59:00Z")  # 23:59
    assert R.night_kickoff("2026-07-01T21:30:00Z")      # 00:30 vara (UTC+3)
    night = [Cand(i, i, i, None, "2026-10-26T01:00:00Z", None, None, "over_under", 2.5, "OVER", 2.3, 0.5, 0.15, "A", 80, p_market=0.5)
             for i in range(1, 6)]
    st = {"losses": 0, "target": 5.0, "band": [4.0, 6.5], "avoid": [], "paused": []}
    assert R.pick(night, R.RULES_R5, {"market": {}, "league": {}}, st)["status"] == "no_bet"


def test_greedy_accumulates_many_safe_low_odds():
    """~5 și ~10: multe selecții sigure (cota 1.15–1.40), una pe meci și pe ligă, până la cota țintă."""
    import math
    pool = [_c(i, 1.22 + (i % 5) * 0.02, 0.86 - i * 0.004) for i in range(1, 30)] + [_c(99, 2.5, 0.9), _c(98, 1.3, 0.6)]
    st = {"losses": 0, "target": 5.0, "band": [4.25, 6.0], "avoid": [], "paused": []}
    r = R.pick_greedy(pool, GREEDY, st)
    legs, p = r["main"]
    o = math.prod(c.odds for c in legs)
    assert r["status"] == "pick" and 4.25 <= o <= 6.0 and 5 <= len(legs) <= 9
    assert all(1.15 <= c.odds <= 1.40 and c.p_honest >= 0.72 for c in legs)
    assert len({c.match_id for c in legs}) == len(legs) and len({c.league_id for c in legs}) == len(legs)
    st10 = {"losses": 0, "target": 10.0, "band": [8.0, 13.0], "avoid": [], "paused": []}
    r10 = R.pick_greedy(pool, GREEDY10, st10)
    assert r10["status"] == "pick" and 8 <= len(r10["main"][0]) <= 12


def test_avoid_family_and_bad_score():
    pool = [_c(i, 1.25, 0.85) for i in range(1, 12)]
    st = {"losses": 1, "target": 4.5, "band": [4.0, 5.4], "avoid": ["over_under"], "paused": []}
    assert R.pick_greedy(pool, GREEDY, st)["status"] == "no_bet"   # familia biletului pierdut e evitată
    st["avoid"] = []
    assert R.pick_greedy(pool, GREEDY, st)["status"] == "pick"


def test_adapt_lowers_target_after_losses_and_never_raises_stake():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ticket (id INTEGER PRIMARY KEY, kind TEXT, variant TEXT, status TEXT, day TEXT)")
    conn.execute("CREATE TABLE ticket_leg (ticket_id INTEGER, market TEXT, selection TEXT)")
    for i, s in enumerate(["lost", "lost"], 1):
        conn.execute("INSERT INTO ticket VALUES (?, 'pyramid', 'pr5', ?, ?)", (i, s, f"2026-10-0{i}"))
        conn.execute("INSERT INTO ticket_leg VALUES (?, 'btts|0', 'YES')", (i,))
    a = R.adapt(conn, R.RULES_R5, __import__("datetime").date(2026, 10, 5))
    assert a["losses"] == 2 and a["target"] < 5.0 and a["avoid"] == ["btts"]
    assert R.RULES_R5["start_bank"] <= 2 and R.RULES_R10["start_bank"] <= 2
