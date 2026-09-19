#!/usr/bin/env python3
"""Unit tests for accumulator_engine — fixture-driven, no live API."""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))


def _dt(days=1):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat().replace("+00:00", "Z")


def _sig(eid, market, odds, grade="A+", consensus="TOTAL", cal=0.72, ev=0.03, league="L1"):
    return {
        "event_id": eid,
        "home_team": f"Home{eid}",
        "away_team": f"Away{eid}",
        "league": league,
        "event_date": _dt(eid),
        "market": market,
        "market_label": market,
        "odds": odds,
        "quality_grade_v6": grade,
        "consensus_tier": consensus,
        "consensus_score": 0.9 if consensus == "TOTAL" else 0.78,
        "calibrated_prob": cal,
        "ev_calibrated": ev,
        "publication_eligible": True,
        "adaptive_verdict": "PASS",
        "adj_prob": cal * 100,
    }


class TestAccumulatorEngine(unittest.TestCase):
    def test_build_leg_candidates_prefers_grades(self):
        from accumulator_engine import build_leg_candidates
        sigs = [
            _sig(1, "over15", 1.85, grade="A+", cal=0.70),
            _sig(2, "over15", 1.90, grade="C", cal=0.70),
            _sig(3, "under35", 1.40, grade="A+", cal=0.80),
        ]
        pool = build_leg_candidates(signals=sigs, live_odds={}, allow_best_odds_fallback=True, multi_mode=True)
        markets = {p["market"] for p in pool}
        self.assertIn("over15", markets)
        self.assertNotIn("under35", markets)
        grades = {p["quality_grade_v6"] for p in pool}
        self.assertNotIn("C", grades)

    def test_band_50_builds_or_stays_empty_honestly(self):
        from accumulator_engine import BANDS, _pick_band, make_ticket
        legs_src = []
        markets = ["over15", "btts", "homeWin", "awayWin", "over15", "btts", "homeWin", "awayWin"]
        for i in range(1, 9):
            mk = markets[i - 1]
            legs_src.append({
                "event_id": i, "home_team": f"H{i}", "away_team": f"A{i}", "league": f"Lg{i}",
                "event_date": _dt(i), "market": mk, "market_label": mk,
                "odds": 1.85, "probability": 58.0, "calibrated_prob": 0.58, "ev_calibrated": 0.01,
                "quality_grade_v6": "A", "consensus_tier": "TOTAL", "executable": True,
                "green_badge": True, "bookmaker": "Superbet", "odds_source": "superbet",
                "rationale": "test", "_score": 90 - i, "_edge_pp": 1.0,
            })
        band = next(b for b in BANDS if b["id"] == "band_50")
        picked = _pick_band(legs_src, band, require_executable=True)
        self.assertTrue(len(picked) >= band["min_legs"])
        ticket = make_ticket(band, picked)
        self.assertIsNotNone(ticket)
        self.assertTrue(ticket["paper_only"])
        self.assertGreaterEqual(ticket["combined_odds"], 40)

    def test_longshot_requires_diverse_leagues(self):
        from accumulator_engine import BANDS, _pick_band
        legs_src = []
        for i in range(1, 8):
            legs_src.append({
                "event_id": i, "league": "SAME", "market": "btts", "odds": 1.90,
                "probability": 55.0, "executable": True, "_score": 80,
                "home_team": "H", "away_team": "A", "event_date": _dt(), "market_label": "BTTS",
                "rationale": "t", "green_badge": True, "bookmaker": "Superbet", "odds_source": "superbet",
                "calibrated_prob": 0.55, "ev_calibrated": 0.0, "quality_grade_v6": "A",
                "consensus_tier": "TOTAL", "_edge_pp": 0,
            })
        band = next(b for b in BANDS if b["id"] == "band_50")
        picked = _pick_band(legs_src, band, require_executable=True)
        self.assertEqual(picked, [])


class TestPyramidStaking(unittest.TestCase):
    def test_staircase_2_5_10(self):
        from pyramid_staking import build_staircase_plan
        cands = [
            {"event_id": 1, "home_team": "A", "away_team": "B", "market": "over15",
             "market_label": "O1.5", "odds": 1.35, "calibrated_prob": 0.78,
             "quality_grade_v6": "A+", "consensus_tier": "TOTAL", "green_badge": True,
             "ev_calibrated": 0.02, "pyramid_ready_score": 90},
            {"event_id": 2, "home_team": "C", "away_team": "D", "market": "over15",
             "market_label": "O1.5", "odds": 1.40, "calibrated_prob": 0.74,
             "quality_grade_v6": "A", "consensus_tier": "TOTAL", "green_badge": True,
             "ev_calibrated": 0.01, "pyramid_ready_score": 85},
            {"event_id": 3, "home_team": "E", "away_team": "F", "market": "homeWin",
             "market_label": "1", "odds": 1.45, "calibrated_prob": 0.70,
             "quality_grade_v6": "A", "consensus_tier": "PARTIAL", "green_badge": True,
             "ev_calibrated": 0.0, "pyramid_ready_score": 80},
        ]
        plan = build_staircase_plan(cands, units=(2, 5, 10), bankroll_units=100, unit_value_lei=10)
        self.assertEqual(plan["units"], [2, 5, 10])
        self.assertEqual(len(plan["steps"]), 3)
        self.assertEqual(plan["steps"][0]["stake_intended_units"], 2)
        self.assertEqual(plan["steps"][2]["stake_intended_units"], 10)
        self.assertEqual(plan["execution_status"], "PAPER_ONLY")
        self.assertLess(plan["series_survival_probability"], 0.78)
        self.assertIn("REINVESTEȘTE", plan["disclaimer"])

    def test_select_rejects_low_grade(self):
        from pyramid_staking import select_step_candidates
        sigs = [
            _sig(1, "over15", 1.40, grade="C", cal=0.80),
            _sig(2, "over15", 1.40, grade="A+", cal=0.72, consensus="TOTAL"),
        ]
        rows = select_step_candidates(sigs)
        self.assertTrue(all(r["quality_grade_v6"] in ("A+", "A") for r in rows))


if __name__ == "__main__":
    unittest.main()
