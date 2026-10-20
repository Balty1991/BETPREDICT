import sqlite3

from betpredict.builder import pyramid_risk as R
from betpredict.builder.pool import Cand


def _c(i, odds, p, market="over_under", lg=None):
    return Cand(i, i, lg if lg is not None else i, None, "2026-10-18T12:00:00Z", None, None, market, 2.5, "OVER", odds, p, p * odds - 1, "A", 80,
                p_market=min(0.97, p))


def test_pick_targets_band_and_ev():
    # selecțiile cu cotă mare (3.0) nu mai intră: ~5 se face din 3–5 cote mici
    pool = [_c(1, 1.75, 0.6), _c(2, 1.7, 0.62), _c(3, 1.8, 0.58), _c(4, 3.0, 0.4), _c(5, 1.65, 0.63)]
    st = {"losses": 0, "target": 5.0, "band": [4.25, 6.0], "avoid": [], "paused": []}
    r = R.pick(pool, R.RULES_R5, {"market": {}, "league": {}}, st)
    assert r["status"] == "pick"
    legs, p = r["main"]
    import math
    o = math.prod(c.odds for c in legs)
    assert 4.25 <= o <= 6.0 and 3 <= len(legs) <= 5 and p * o - 1 >= 0 and all(c.odds <= 1.9 for c in legs)


def test_avoid_family_and_bad_score():
    pool = [_c(1, 1.7, 0.6), _c(2, 1.7, 0.6), _c(3, 1.7, 0.6)]
    st = {"losses": 1, "target": 4.5, "band": [4.0, 5.4], "avoid": ["over_under"], "paused": []}
    assert R.pick(pool, R.RULES_R5, {"market": {}, "league": {}}, st)["status"] == "no_bet"
    st["avoid"] = []
    r = R.pick([_c(1, 1.7, 0.56), _c(2, 1.7, 0.56), _c(3, 1.7, 0.56)], R.RULES_R5, {"market": {"over_under": -0.2}, "league": {}}, st)
    assert r["status"] == "pick" and r["tier"] == "p"  # fallback: cea mai mare șansă, marcată


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
