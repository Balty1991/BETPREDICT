"""Audit 17.10.2026: praguri CLV, biletele Stil 3–6 din piețe pozitive, cartonașe calibrate, EV suspect."""
import math
import sqlite3

from betpredict.experimental import supersocial as ss
from betpredict.learn import adaptive_thresholds
from betpredict.robot.params import threshold_ok


def test_nozone_uses_clv():
    rows = [{"market": "btts", "line": 0.0, "odds_shown": 1.9, "ev": 0.03, "profit_1u": -1.0 if i % 2 else 0.8,
             "league_id": 1, "clv": 0.02} for i in range(100)]
    th = adaptive_thresholds(rows)["btts"]
    assert th["source"] == "live_clv" and th["min_ev"] == 0.0


def test_legacy_015_capped():
    p = {"thresholds": {"btts": {"min_ev": 0.15, "roi_shrunk": None, "source": "live"}}}
    assert threshold_ok(p, "btts", 1, 0.07)
    assert not threshold_ok(p, "btts", 1, 0.03)


def _db():
    c = sqlite3.connect(":memory:")
    ss._ensure_track(c)
    rows = []
    for i in range(50):
        rows.append((i, "H2G13", "2026-10-10T12:00:00Z", 0.8, 1.40, "x", "won" if i % 10 < 8 else "lost"))   # ROI +12%
        rows.append((i, "H1C56", "2026-10-10T12:00:00Z", 0.3, 4.0, "x", "won" if i % 10 < 4 else "lost"))   # pozitiv, dar interzis
        rows.append((i, "C75", "2026-10-10T12:00:00Z", 0.7, 1.30, "x", "won" if i % 10 < 6 else "lost"))    # negativ
        rows.append((i, "YCU55", "2026-10-10T12:00:00Z", 0.95, 1.20, "x", "won" if i % 10 < 8 else "lost"))
    c.executemany("INSERT INTO ss_track (match_id, mkey, kickoff_utc, p, odds, updated_at, result) VALUES (?,?,?,?,?,?,?)", rows)
    return c


def test_positive_keys_and_specs():
    c = _db()
    keys = ss.positive_keys(c)
    assert "H1C56" not in keys and "C75" not in keys
    specs = ss.stil_specs(ss.TICKETS, keys)
    assert specs and all(lo == 3 and hi == 6 for _, _, lo, hi, _, _ in specs)
    assert all(not (set(k) & ss.STIL_BANNED) for _, k, *_ in specs)


def test_cards_calibrated_and_suspect():
    c = _db()
    cal = ss.card_calibration(c)
    assert 0.8 < cal["YCU55"] < 0.95
    cands = ss.calibrate_cards([{"key": "YCU55", "p": 0.97, "odds": 1.75}], cal)
    assert cands[0]["p"] < 0.97
    assert ss.suspect({"key": "YCU55", "edge": 0.4}) and ss.suspect({"key": "C65", "edge": 0.3})
    assert not ss.suspect({"key": "GG", "edge": 0.1})


def test_tiers_defined_and_banded():
    assert [n for n, *_ in ss.STIL_TIERS] == ["Stil 100+", "Stil 500+", "Stil 1000+"]
    assert ss._odds_band("Stil 1000+")[0] == 1000.0 and ss._odds_band("1–3 în fiecare repriză") == ss.STIL_ODDS
    assert all(hi >= ss.SYSTEM_MIN_LEGS for *_, hi in ss.STIL_TIERS)  # sistem N−1 posibil


def test_market_gate_and_beats_market():
    from betpredict.builder import v4tickets as V
    from betpredict.builder.pool import Cand

    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE prediction (market TEXT, line REAL, odds_shown REAL, profit_1u REAL, result TEXT, day TEXT)")
    rows = [("btts", 0.0, 2.2, 1.2 if i % 2 else -1.0, "won" if i % 2 else "lost", "2026-10-12") for i in range(100)]
    rows += [("1x2", 0.0, 1.6, 0.6 if i % 3 == 0 else -1.0, "won" if i % 3 == 0 else "lost", "2026-10-12") for i in range(100)]
    c.executemany("INSERT INTO prediction VALUES (?,?,?,?,?,?)", rows)
    ok = V.positive_markets(c)
    assert ("btts", "hi") in ok and ("1x2", "mid") not in ok
    mk = lambda o, pm: Cand(1, 1, 1, "L", "2026-10-18T12:00:00Z", "a", "b", "btts", 0.0, "yes", o, 0.5, 0.0, "B", 60, p_market=pm)
    assert V.beats_market(mk(2.0, 0.5)) and not V.beats_market(mk(1.80, 0.5)) and not V.beats_market(mk(2.0, None))
    assert len(V.gate_pool(c, [mk(2.3, 0.45), mk(1.5, 0.6)])) == 1


def test_pyramid_mici_pauses_after_two_losses():
    from betpredict.builder import pyramid as P

    assert P.RULES_MICI["pause_after_losses"] == 2


def test_chain_steps_are_sequential_and_reach_100():
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 10, 18, 8, tzinfo=timezone.utc)
    pool = []
    for i in range(24):
        ko = (now + timedelta(hours=2 + i // 3 * 2.5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        pool.append({"match_id": i, "key": "H13x2", "p": 0.55, "p_rank": 0.55, "odds": 1.85, "edge": 0.02, "kickoff_utc": ko, "league_id": i})
    steps = ss.build_chain(pool, now)
    assert steps and 3 <= len(steps) <= 4
    assert math.prod(ss._prod(s) for s in steps) >= 100
    for a, b in zip(steps, steps[1:]):
        assert min(c["kickoff_utc"] for c in b) >= max(c["kickoff_utc"] for c in a)


def test_signal_filter_lineups_and_drift(monkeypatch):
    cands = [{"match_id": 1, "key": "HO05", "p_rank": 0.7}, {"match_id": 1, "key": "GG", "p_rank": 0.6},
             {"match_id": 2, "key": "GG", "p_rank": 0.6}, {"match_id": 3, "key": "GG", "p_rank": 0.6}]
    monkeypatch.setattr(ss, "lineup_info", lambda conn, ids: {1: (2, 0)})
    monkeypatch.setattr(ss, "pinnacle_drift", lambda conn, ids: {2: 0.06, 3: -0.05})
    out, st = ss.signal_filter(None, cands)
    keys = {(c["match_id"], c["key"]) for c in out}
    assert (1, "HO05") not in keys and (1, "GG") in keys and (2, "GG") not in keys
    assert st == {"lineup": 1, "drift": 1, "shortened": 1}
    assert next(c for c in out if c["match_id"] == 3)["p_rank"] > 0.6


def test_lineup_counts_only_key_starters():
    import json as _j
    import sqlite3 as _s
    c = _s.connect(":memory:")
    c.execute("CREATE TABLE match_context (match_id INTEGER PRIMARY KEY, context_json TEXT, updated_at TEXT)")
    un = {"home": [{"id": 1, "imp": 0.9}, {"id": 2, "imp": 0.2}, {"id": 3}], "away": [{"id": 4, "imp": 0.6}]}
    c.execute("INSERT INTO match_context VALUES (7, ?, '')", (_j.dumps({"lineups": {"status": "confirmed", "unavailable": un}}),))
    assert ss.lineup_info(c, [7]) == {7: (1, 1)}


def test_player_importance():
    from datetime import datetime, timezone
    from betpredict.ingest.multibook import player_importance

    class C:
        def __init__(self, rows): self.rows = rows
        def get(self, url, cache_ttl=0): return {"results": self.rows}
    now = datetime(2026, 10, 17, tzinfo=timezone.utc)
    starter = [{"date": f"2026-09-{d:02d}", "minutes": 85, "goals": 0, "assists": 0} for d in range(1, 11)]
    bench = [{"date": f"2026-09-{d:02d}", "minutes": 15} for d in range(1, 5)]
    scorer = [{"date": f"2026-09-{d:02d}", "minutes": 30, "goals": 1} for d in range(1, 5)]
    assert player_importance(C(starter), 1, now) >= 0.6
    assert player_importance(C(bench), 1, now) < 0.6
    assert player_importance(C(scorer), 1, now) >= 0.6


def test_absence_edge_key_players_only():
    from betpredict.robot.engine import absence_edge
    ctx = {"lineups": {"unavailable": {"home": [{"status": "injured", "imp": 0.9}, {"status": "injured", "imp": 0.1}, {"status": "suspended", "imp": 0.7}],
                                       "away": [{"status": "injured", "imp": 0.2}]}}}
    assert absence_edge(ctx) == 2
    old = {"lineups": {"unavailable": {"home": [{"status": "injured"}, {"status": "injured"}], "away": []}}}
    assert absence_edge(old) == 2


def test_apifootball_suspended_stops():
    from datetime import datetime, timezone
    from betpredict.ingest import apifootball as af
    from betpredict.store.db import connect, init_db

    c = connect(":memory:"); init_db(c)

    class Fake:
        suspended = "Your account is suspended"
        left = 0
        def get(self, path): return None
        def can(self): return False
        def used(self): return 0
    now = datetime(2026, 10, 18, tzinfo=timezone.utc)
    st = af.collect(c, key="x", now=now, client=Fake())
    assert st.get("suspended")
    st2 = af.collect(c, key="x", now=now, client=Fake())
    assert "suspendat" in st2.get("skipped", "")
