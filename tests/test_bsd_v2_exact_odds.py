import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import bsd_v2_exact as bsd


class FakeResponse:
    def __init__(self, status_code, headers=None, payload=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload or {}

    def json(self):
        return self._payload


class TestBestOddsCollection(unittest.TestCase):
    def setUp(self):
        self.original_data_dir = bsd.DATA_DIR
        self.original_markets = bsd.ODDS_MARKETS
        self.original_get = bsd.get
        self.original_exhausted = bsd.QUOTA_EXHAUSTED
        bsd.QUOTA_EXHAUSTED = False
        bsd.QUOTA_STATE.clear()
        bsd.QUOTA_STATE.update({"status": "unknown", "remaining": None, "reset_seconds": None})

    def tearDown(self):
        bsd.DATA_DIR = self.original_data_dir
        bsd.ODDS_MARKETS = self.original_markets
        bsd.get = self.original_get
        bsd.QUOTA_EXHAUSTED = self.original_exhausted

    def test_normalizes_1x2_best_odds_for_veyra(self):
        row = {
            "event_id": 42,
            "event_date": "2026-08-21T18:00:00Z",
            "market": "1x2",
            "home_team": "Home",
            "away_team": "Away",
            "best_odds": [
                {"outcome": "HOME", "decimal_odds": 1.8},
                {"outcome": "DRAW", "decimal_odds": 3.6},
                {"outcome": "AWAY", "decimal_odds": 4.2},
            ],
        }

        normalized = bsd.normalize_best_odds_row(row, "1x2")

        self.assertEqual(normalized["home_odds"], 1.8)
        self.assertEqual(normalized["draw_odds"], 3.6)
        self.assertEqual(normalized["away_odds"], 4.2)
        self.assertEqual(normalized["market"], "1x2")

    def test_build_best_odds_persists_current_rows(self):
        def fake_get(url, params=None, label=""):
            self.assertIn("odds/best", url)
            self.assertEqual(params["market"], "1x2")
            return {"results": [{
                "event_id": 77,
                "event_date": "2026-08-21T18:00:00Z",
                "market": "1x2",
                "best_odds": [{"outcome": "HOME", "decimal_odds": 1.9}],
            }]}

        with tempfile.TemporaryDirectory() as tmp:
            bsd.DATA_DIR = Path(tmp)
            bsd.ODDS_MARKETS = ("1x2",)
            bsd.get = fake_get

            bsd.build_best_odds()

            payload = json.loads((Path(tmp) / "best_odds.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["count"], 1)
            self.assertEqual(payload["results"][0]["home_odds"], 1.9)
            self.assertEqual(payload["market_counts"], {"1x2": 1})

    def test_marks_daily_quota_exhaustion(self):
        response = FakeResponse(
            429,
            headers={"Retry-After": "3600", "RateLimit": '"football";r=0;t=3600'},
            payload={"code": "taster_exhausted"},
        )

        bsd._record_quota(response)

        self.assertTrue(bsd.QUOTA_EXHAUSTED)
        self.assertEqual(bsd.QUOTA_STATE["status"], "exhausted")
        self.assertEqual(bsd.QUOTA_STATE["remaining"], 0)
        self.assertEqual(bsd.QUOTA_STATE["reset_seconds"], 3600)


if __name__ == "__main__":
    unittest.main()
