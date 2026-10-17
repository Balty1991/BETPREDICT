"""Audit 17.10.2026: praguri CLV, biletele Stil 3–6 din piețe pozitive, cartonașe calibrate, EV suspect."""
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
