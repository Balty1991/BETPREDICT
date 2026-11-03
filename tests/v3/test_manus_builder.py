import math
import sqlite3
from collections import Counter
from datetime import date

from betpredict.builder import manus, v4tickets
from betpredict.builder.pool import Cand


def _candidate(index, selection, league_index, odds=1.5, p=0.60):
    return Cand(
        prediction_id=index,
        match_id=10_000 + index,
        league_id=league_index,
        league=f"League {league_index}",
        kickoff_utc=f"2026-11-03T{12 + index:02d}:00:00Z",
        home=f"Home {index}",
        away=f"Away {index}",
        market="ss",
        line=0.0,
        selection=selection,
        odds=odds,
        p=p,
        ev=p * odds - 1,
        grade="B",
        confidence=70,
        healthy=True,
        p_market=0.75,
        odds_source="superbet",
    )


def _diversified_pool():
    pool = []
    keys = ("H2G13", "BB_C65_U145", "YCU45")
    for family_index, key in enumerate(keys, start=1):
        for offset in range(4):
            index = (family_index - 1) * 4 + offset + 1
            pool.append(_candidate(index, key, family_index))
    return pool


def test_supersocial_keys_are_classified_by_market_not_by_source():
    assert manus._family(_candidate(1, "H2G13", 1)) == "goluri"
    assert manus._family(_candidate(2, "BB_C65_U145", 1)) == "cornere"
    assert manus._family(_candidate(3, "YCU45", 1)) == "cartonașe"


def test_fallback_can_build_a_diversified_100x_ticket_when_strict_tier_cannot(monkeypatch):
    # Isolate recipe behavior from optimizer calibration; 60% legs intentionally fail the strict 70% tier.
    monkeypatch.setattr(manus, "p_prudent", lambda c: c.p)
    pool = _diversified_pool()

    assert manus.choose_legs(pool) is None

    legs = manus.choose_legs(
        pool,
        min_leg_p=manus.FALLBACK_MIN_LEG_P,
        max_per_league=manus.FALLBACK_MAX_PER_LEAGUE,
    )
    assert legs is not None
    assert len(legs) == 12
    assert math.prod(c.odds for c in legs) >= manus.TARGET
    assert set(manus._family(c) for c in legs) == {"goluri", "cornere", "cartonașe"}
    assert max(Counter(manus._family(c) for c in legs).values()) <= len(legs) * manus.MAX_PER_FAMILY
    assert max(Counter(c.league for c in legs).values()) <= manus.FALLBACK_MAX_PER_LEAGUE


def test_build_day_marks_fallback_paper_only_and_not_recommended(monkeypatch):
    monkeypatch.setattr(manus, "p_prudent", lambda c: c.p)
    monkeypatch.setattr(manus, "load_extra", lambda conn, day: [])
    monkeypatch.setattr(
        manus,
        "ticket_stats",
        lambda legs, shrink: (math.prod(c.odds for c in legs), 0.0049, -0.42),
    )
    stored = {}
    monkeypatch.setattr(manus, "insert_ticket", lambda conn, *args: stored.update(extra=args[-1], reasons=args[5]))
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ticket (day TEXT, kind TEXT, status TEXT)")

    result = manus.build_day(conn, date(2026, 11, 3), _diversified_pool(), "created", {})

    assert result["made"] == 1
    assert result["filter_mode"] == "experimental_fallback_60"
    assert stored["extra"]["paper"] is True
    assert stored["extra"]["experimental"] is True
    assert stored["extra"]["recommended"] is False
    assert stored["extra"]["filter_version"] == "manus-v2-fallback-60"
    assert any("fallback experimental" in reason.lower() for reason in stored["reasons"])
    assert any("sub 1%" in reason.lower() for reason in stored["reasons"])


def test_insert_ticket_nulls_nonexistent_synthetic_prediction_ids(monkeypatch):
    monkeypatch.setattr(v4tickets, "ticket_stats", lambda legs, shrink: (120.0, 0.01, 0.20))
    monkeypatch.setattr(v4tickets, "system_notes", lambda legs, stake, shrink: [])
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE prediction (id INTEGER PRIMARY KEY);
        CREATE TABLE ticket (
            id INTEGER PRIMARY KEY, kind TEXT, variant TEXT, created_by TEXT,
            target_odds REAL, total_odds REAL, p_ticket REAL, ev REAL, stake REAL,
            status TEXT, created_at TEXT, notes TEXT, day TEXT
        );
        CREATE TABLE ticket_leg (
            id INTEGER PRIMARY KEY, ticket_id INTEGER REFERENCES ticket(id) ON DELETE CASCADE,
            prediction_id INTEGER REFERENCES prediction(id), match_id INTEGER,
            market TEXT, selection TEXT, odds REAL, odds_source TEXT
        );
        INSERT INTO prediction(id) VALUES (123);
    """)
    day = date(2026, 11, 3)
    synthetic = _candidate(1, "H2G13", 1)
    synthetic.prediction_id = -123
    sel_used = {}

    first = v4tickets.insert_ticket(conn, "acca_manus", "fallback", 100, [synthetic], 0.0025, [], day,
                                    "created", sel_used, {"paper": True, "lottery": True})
    stored_synthetic = conn.execute("SELECT prediction_id FROM ticket_leg WHERE ticket_id=?", (first,)).fetchone()[0]
    assert stored_synthetic is None
    assert sel_used[-123] == 1

    real = _candidate(2, "R1R2", 1)
    real.prediction_id = 123
    second = v4tickets.insert_ticket(conn, "acca_manus", "strict", 100, [real], 0.0025, [], day,
                                     "created", sel_used, {"paper": True, "lottery": True})
    stored_real = conn.execute("SELECT prediction_id FROM ticket_leg WHERE ticket_id=?", (second,)).fetchone()[0]
    assert stored_real == 123
