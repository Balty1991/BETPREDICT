import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from compute_signals_v6 import augment_signal


class TestSignalPerformanceGuard(unittest.TestCase):
    @staticmethod
    def base_signal(market="awayWin"):
        return {
            "event_id": 123,
            "home_team": "Home",
            "away_team": "Away",
            "market": market,
            "adj_prob": 72.0,
            "odds": 1.55,
            "edge_pp": 7.5,
            "ev": 0.116,
            "smartbet_score": 75,
        }

    def test_blocked_market_is_not_publication_eligible(self):
        result = augment_signal(
            self.base_signal(), {}, {}, {}, gates={},
            performance_guards={
                "awayWin": {
                    "blocked": True,
                    "roi_pct": -25.5,
                    "n": 34,
                    "reason": "pierderi severe: ROI real -25.5% pe 34 pariuri decontate",
                }
            },
        )

        self.assertFalse(result["publication_eligible"])
        self.assertEqual(result["performance_verdict"], "BLOCKED")
        self.assertIn("ROI real", result["publication_reason"])
        self.assertLess(result["display_score"], -900)

    def test_penalized_market_remains_auditable(self):
        result = augment_signal(
            self.base_signal("homeWin"), {}, {}, {}, gates={},
            performance_guards={
                "homeWin": {
                    "blocked": False,
                    "mult": 0.55,
                    "roi_pct": -2.0,
                    "n": 40,
                    "reason": "ROI real -2.0% pe 40 pariuri — penalizat la selectie",
                }
            },
        )

        self.assertTrue(result["publication_eligible"])
        self.assertEqual(result["performance_verdict"], "PENALIZED")
        self.assertIn("penalizat", result["publication_reason"])


if __name__ == "__main__":
    unittest.main()
