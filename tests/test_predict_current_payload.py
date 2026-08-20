import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from predict_current import normalize_prediction_map, prediction_rows


class TestPredictionPayloadNormalization(unittest.TestCase):
    def test_extracts_rows_from_published_results_container(self):
        payload = {
            "updated_at": "2026-08-20T00:00:00Z",
            "results": [
                {"event": {"id": 101}, "markets": {}},
                {"event": {"id": 202}, "markets": {}},
            ],
        }

        rows = prediction_rows(payload)
        index = normalize_prediction_map(rows)

        self.assertEqual(len(rows), 2)
        self.assertEqual(set(index), {"101", "202"})

    def test_accepts_already_normalized_list_and_discards_invalid_rows(self):
        rows = prediction_rows([{"event": {"id": 303}}, "invalid", None])

        self.assertEqual(rows, [{"event": {"id": 303}}])
        self.assertEqual(set(normalize_prediction_map(rows)), {"303"})


if __name__ == "__main__":
    unittest.main()
