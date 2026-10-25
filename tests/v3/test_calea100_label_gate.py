"""25.10.2026: poarta de etichetă (100+/500+/1000+) și Calea 100+ (reguli înghețate)."""
import sqlite3
from datetime import date

import pytest

from betpredict.builder import calea100 as c
from betpredict.builder.label_gate import below_label, label_min


def test_label_gate():
    assert label_min("acca_100") == 100 and label_min("acca_1000") == 1000
    assert label_min("acca_stil", "Stil 500+ · cornere") == 500
    assert label_min("acca_value", "Bilet 2 selecții") is None
    assert below_label("acca_100", 92.4) and not below_label("acca_100", 100.0)
    assert below_label("acca_stil", 480, "Stil 500+") and not below_label("acca_value", 3.0)


def test_superbonus_grid():
    assert c.superbonus(2) == 0 and c.superbonus(3) == 0.03 and c.superbonus(8) == 0.15
    assert c.superbonus(10) == 0.25 and c.superbonus(12) == pytest.approx(0.35) and c.superbonus(40) == 1.0


def test_honest_chance_and_ev():
    p = c.honest_chance([1.8] * 8)  # cota 110
    assert p == pytest.approx(0.97 ** 8 / 1.8 ** 8)
    assert 0.006 < p < 0.0075
    assert c.ev_with_bonus(p, 1.8 ** 8, 0.0) < 0  # fără avantaj, EV negativ
    assert c.ev_with_bonus(p, 1.8 ** 8, 0.15) > c.ev_with_bonus(p, 1.8 ** 8, 0.0)


def _leg(i, odds, league=None, tier=1, key=None):
    return {"match_id": i, "league_id": league if league is not None else i, "odds": odds, "p": 1 / odds, "tier": tier,
            "cost": 1.0, "selection": key or f"K{i % 9}"}


def test_pick_fewest_legs_to_100():
    assert c.pick([_leg(i, 1.9) for i in range(4)]) is None  # 4 selecții nu ajung
    legs = c.pick([_leg(i, 1.9) for i in range(20)])
    assert legs and len(legs) == 8  # 1.9^8 = 169, cât mai puține
    assert c.pick([_leg(i, 1.36) for i in range(20)]) is None  # 1.36^12 = 40 < 100 (max 12)
    assert c.pick([_leg(i, 1.9, league=1) for i in range(20)]) is None  # max 3 pe ligă
    assert c.pick([_leg(i, 1.9, key="C75") for i in range(20)]) is None  # max 4 pe piață


def test_tiers_fall_back():
    pool = [_leg(i, 1.9, tier=3) for i in range(12)] + [_leg(100 + i, 1.9, tier=1) for i in range(3)]
    ch = c.choose(pool)
    assert ch["tier"] == 3 and sum(l["tier"] == 1 for l in ch["legs"]) == 3  # treptele sigure intră primele
    ch = c.choose([_leg(i, 2.0, tier=0) for i in range(9)])
    assert ch["tier"] == 0


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE ticket (id INTEGER PRIMARY KEY, kind TEXT, variant TEXT, day TEXT, status TEXT, total_odds REAL, p_ticket REAL, stake REAL, notes TEXT)")
    return conn


def test_build_waits_for_start():
    assert c.build(_db(), date(2026, 10, 24), rows=[]) == {"skipped": "before_start"}


def test_rolling_state():
    conn = _db()
    for d, s, o in [("2026-10-20", "won", 1.5), ("2026-10-25", "won", 1.5), ("2026-10-27", "won", 1.4), ("2026-10-28", "pending", 1.45)]:
        conn.execute("INSERT INTO ticket (kind, variant, day, status, total_odds) VALUES ('acca_pont','pontul_zilei',?,?,?)", (d, s, o))
    st = c.rolling_state(conn, date(2026, 10, 28))
    a = st["active"]
    assert a["step"] == 3 and a["odds"] == pytest.approx(2.1) and a["stake_lei"] == pytest.approx(4.2)
    assert a["today"]["odds"] == 1.45 and a["p_reach_lo"] < a["p_reach_hi"] < 0.1
    conn.execute("INSERT INTO ticket (kind, variant, day, status, total_odds) VALUES ('acca_pont','pontul_zilei','2026-10-29','lost',1.4)")
    conn.execute("UPDATE ticket SET status='lost' WHERE day='2026-10-28'")
    st = c.rolling_state(conn, date(2026, 10, 30))
    assert st["active"]["step"] == 1 and st["active"]["stake_lei"] == 2.0 and st["record"]["chains"] >= 1
