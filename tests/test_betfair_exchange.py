import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from betfair_exchange import canonical_outcome, normalize_snapshot


class TestBetfairExchange(unittest.TestCase):
    def test_canonical_outcomes(self):
        self.assertEqual(canonical_outcome("1x2", "Home"), "HOME")
        self.assertEqual(canonical_outcome("1x2", "Draw"), "DRAW")
        self.assertEqual(canonical_outcome("over_under_25", "Over 2.5"), "OVER")
        self.assertEqual(canonical_outcome("btts", "No"), "NO")
        self.assertIsNone(canonical_outcome("1x2", "Unknown"))

    def test_normalize_snapshot_filters_low_volume_and_spread(self):
        catalogue = [{
            "marketId": "m1",
            "marketType": "OVER_UNDER_25",
            "marketStartTime": "2030-01-01T12:00:00Z",
            "event": {"id": "e1", "name": "A v B", "openDate": "2030-01-01T12:00:00Z"},
            "runners": [
                {"selectionId": 1, "runnerName": "Over 2.5"},
                {"selectionId": 2, "runnerName": "Under 2.5"},
            ],
        }]
        books = [{
            "marketId": "m1",
            "status": "OPEN",
            "runners": [
                {"selectionId": 1, "ex": {"availableToBack": [{"price": 2.0, "size": 200}], "availableToLay": [{"price": 2.02, "size": 200}], "tradedVolume": [{"price": 2.0, "size": 250}]}},
                {"selectionId": 2, "ex": {"availableToBack": [{"price": 1.9, "size": 200}], "availableToLay": [{"price": 1.91, "size": 200}], "tradedVolume": [{"price": 1.9, "size": 50}]}},
            ],
        }]
        out = normalize_snapshot(catalogue, books, "2030-01-01T11:00:00Z")
        self.assertEqual(out["count"], 1)
        row = out["rows"][0]
        self.assertEqual(row["event_id"], "e1")
        self.assertEqual(row["market_type"], "over_under_25")
        self.assertEqual(row["outcome"], "OVER")
        self.assertEqual(row["source"], "betfair_exchange")


if __name__ == "__main__":
    unittest.main()
