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


def test_many_tickets_per_tier_with_limited_reuse_and_stats():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row; DB.init_db(c)
    for i in range(1, 121):
        c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status) VALUES (?, '2026-11-14T18:00:00Z', 'h', 'a', 'notstarted')", (i,))
    pool = [_cand(i, odds=1.5 + (i % 7) * 0.08, p=0.62) for i in range(1, 121)]
    pool += [_cand(100 + i, market="btts", sel="NO", odds=1.9, p=0.6) for i in range(5)]  # NG nu intră
    now = datetime(2026, 11, 14, 8, tzinfo=timezone.utc)
    rep = S.build(c, date(2026, 11, 14), now, pool)
    # un meci apare o singură dată (selecțiile de aici nu sunt „foarte sigure”): 120 de meciuri ajung pentru câteva bilete,
    # fiecare țintă are măcar unul
    assert rep["tickets"] >= 3 and {m["variant"] for m in rep["made"]} == {"s1000", "s5000", "s10000"}
    for t in c.execute("SELECT id, variant, target_odds, total_odds FROM ticket WHERE kind=?", (S.KIND,)):
        assert t["target_odds"] <= t["total_odds"] <= t["target_odds"] * S.SPAN
        legs = c.execute("SELECT match_id, market, selection FROM ticket_leg WHERE ticket_id=?", (t["id"],)).fetchall()
        assert len({l["match_id"] for l in legs}) == len(legs)
        assert not any(l["market"] == "btts|0" and l["selection"] == "NO" for l in legs)
    use = [r[0] for r in c.execute("SELECT COUNT(*) FROM ticket_leg GROUP BY match_id")]
    assert max(use) == 1
    assert S.build(c, date(2026, 11, 14), now, pool) == {"skipped_existing": rep["tickets"]}
    c.execute("UPDATE ticket SET status='won' WHERE id=(SELECT MIN(id) FROM ticket)")
    s = S.stats_doc(c, now)
    t1 = s["tiers"][0]
    assert t1["n"] == 1 and t1["won"] == 1 and t1["best"] >= 1000
