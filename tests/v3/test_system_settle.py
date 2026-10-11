import itertools
import json
import math
import sqlite3

from betpredict.settle import system_multiplier, ticket_system
from betpredict.ingest import opening as O


def test_system_multiplier_bruteforce():
    f = [2.0, 1.5, 0.0, 1.0, 1.3]  # câștig, câștig, pierdut, void, câștig
    for k in (1, 2, 3):
        m = len(f) - k
        brute = sum(math.prod(c) for c in itertools.combinations(f, m)) / math.comb(len(f), m)
        assert abs(system_multiplier(f, k) - brute) < 1e-12
    assert system_multiplier([2.0, 0.0, 0.0], 1) == 0.0


def test_ticket_system_from_notes():
    assert ticket_system(json.dumps({"backtest": {"system": 3}})) == 3
    assert ticket_system("{}") == 0 and ticket_system("bad") == 0


def test_openings_first_seen_and_drift():
    c = sqlite3.connect(":memory:")
    c.execute("""CREATE TABLE odds_snapshot (match_id INT, market TEXT, line REAL, period TEXT, outcome TEXT, decimal REAL,
                 opening_decimal REAL, previous_decimal REAL, movement TEXT, source TEXT, observed_at TEXT)""")
    ins = "INSERT INTO odds_snapshot VALUES (?,?,?,?,?,?,?,?,?,?,?)"
    c.execute(ins, (1, "1x2", 0, "FT", "HOME", 1.50, None, None, None, "superbet", "2026-10-10T08:00:00Z"))
    c.execute(ins, (1, "1x2", 0, "FT", "HOME", 1.60, None, None, None, "superbet", "2026-10-11T08:00:00Z"))
    c.execute(ins, (1, "1x2", 0, "FT", "HOME", 1.58, 1.45, None, None, "bsd_consensus", "2026-10-11T08:00:00Z"))
    assert O.record_openings(c) == 2
    c.execute(ins, (1, "1x2", 0, "FT", "HOME", 1.70, None, None, None, "superbet", "2026-10-11T09:00:00Z"))
    O.record_openings(c)
    m = O.opening_map(c, [1])
    assert m[(1, "1x2", 0.0, "HOME", "superbet")] == 1.50 and m[(1, "1x2", 0.0, "HOME", "bsd_consensus")] == 1.45
    assert abs(O.drift_of(m, 1, "1x2", 0, "HOME", 1.65, "superbet") - 0.10) < 1e-9
    assert O.drift_of(m, 2, "1x2", 0, "HOME", 1.65, "superbet") is None
