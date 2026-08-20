import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import market_performance_guard as guard


class TestMarketPerformanceGuard(unittest.TestCase):
    def test_blocks_severe_loss_with_sufficient_sample(self):
        payload = {
            "by_market": {
                "awayWin": {"stats": {"n": 34, "roi_pct": -25.5}},
            },
        }
        with patch.object(guard, "_load", return_value=payload):
            result = guard.market_guard()

        self.assertTrue(result["awayWin"]["blocked"])
        self.assertEqual(result["awayWin"]["mult"], 0.0)
        self.assertIn("pierderi severe", result["awayWin"]["reason"])

    def test_does_not_block_small_sample(self):
        payload = {
            "by_market": {
                "btts": {"stats": {"n": 10, "roi_pct": -45.0}},
            },
        }
        with patch.object(guard, "_load", return_value=payload):
            result = guard.market_guard()

        self.assertNotIn("btts", result)

    def test_blocks_persistent_negative_market(self):
        payload = {
            "by_market": {
                "under35": {"stats": {"n": 99, "roi_pct": -16.6}},
            },
        }
        with patch.object(guard, "_load", return_value=payload):
            result = guard.market_guard()

        self.assertTrue(result["under35"]["blocked"])


if __name__ == "__main__":
    unittest.main()
