#!/usr/bin/env python3
"""Teste pentru pyramid_tracker.py — inregistrare, decontare WIN/LOSS, regula
de retragere partiala formala, si reset la pierdere."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))


def _pool(step, event_id=1, odds=1.40, market="homeWin", home="A", away="B"):
    return {str(step): [{
        "event_id": event_id, "home_team": home, "away_team": away, "league": "L",
        "event_date": "2026-08-01T18:00:00Z", "market": market, "market_label": "1X2",
        "odds": odds, "bookmaker": "Superbet", "pyramid_ready_score": 90,
        "calibration_status": "OK",
    }]}


class TestRegisterNext(unittest.TestCase):
    def test_registers_top_candidate_for_next_step(self):
        from pyramid_tracker import _fresh_track, _register_next
        track = _fresh_track("test")
        pyramid_data = {"current_step_pool": _pool(1), "pools_by_target": {"t2_50": {}}}
        _register_next(track, "current_step_pool", 10, pyramid_data, "now")
        self.assertIsNotNone(track["pending"])
        self.assertEqual(track["pending"]["step"], 1)
        self.assertEqual(track["pending"]["stake_lei"], track["bankroll_lei"])

    def test_does_not_overwrite_existing_pending(self):
        from pyramid_tracker import _fresh_track, _register_next
        track = _fresh_track("test")
        pyramid_data = {"current_step_pool": _pool(1, event_id=1), "pools_by_target": {"t2_50": {}}}
        _register_next(track, "current_step_pool", 10, pyramid_data, "now")
        first_pending = track["pending"]
        pyramid_data2 = {"current_step_pool": _pool(1, event_id=2), "pools_by_target": {"t2_50": {}}}
        _register_next(track, "current_step_pool", 10, pyramid_data2, "later")
        self.assertEqual(track["pending"], first_pending)

    def test_no_candidates_leaves_pending_empty(self):
        from pyramid_tracker import _fresh_track, _register_next
        track = _fresh_track("test")
        pyramid_data = {"current_step_pool": {"1": []}, "pools_by_target": {"t2_50": {}}}
        _register_next(track, "current_step_pool", 10, pyramid_data, "now")
        self.assertIsNone(track["pending"])


class TestSettlePending(unittest.TestCase):
    def _track_with_pending(self, odds=1.40, step_target=1, bankroll=10.0):
        from pyramid_tracker import _fresh_track
        track = _fresh_track("test")
        track["bankroll_lei"] = bankroll
        track["step"] = step_target - 1
        track["pending"] = {
            "step": step_target, "event_id": 1, "home_team": "A", "away_team": "B",
            "league": "L", "event_date": "2026-08-01T18:00:00Z", "market": "homeWin",
            "market_label": "1X2", "odds": odds, "bookmaker": "Superbet",
            "stake_lei": bankroll, "registered_at": "now",
        }
        return track

    def test_win_compounds_bankroll_and_advances_step(self):
        from pyramid_tracker import _settle_pending
        track = self._track_with_pending(odds=1.40, step_target=1, bankroll=10.0)
        res_idx = {1: {"home_score": 2, "away_score": 0}}  # HOME wins
        _settle_pending(track, res_idx, "later")
        self.assertIsNone(track["pending"])
        self.assertEqual(track["step"], 1)
        self.assertAlmostEqual(track["bankroll_lei"], 14.0, places=2)
        self.assertEqual(track["history"][-1]["result"], "WIN")

    def test_loss_resets_step_and_bankroll(self):
        from pyramid_tracker import _settle_pending
        track = self._track_with_pending(odds=1.40, step_target=4, bankroll=27.44)
        res_idx = {1: {"home_score": 0, "away_score": 1}}  # AWAY wins -> homeWin pierde
        _settle_pending(track, res_idx, "later")
        self.assertIsNone(track["pending"])
        self.assertEqual(track["step"], 0)
        self.assertEqual(track["bankroll_lei"], track["initial_stake_lei"])
        self.assertEqual(track["n_resets"], 1)
        self.assertEqual(track["history"][-1]["result"], "LOSS")

    def test_unfinished_match_leaves_pending_untouched(self):
        from pyramid_tracker import _settle_pending
        track = self._track_with_pending()
        _settle_pending(track, {}, "later")  # niciun rezultat disponibil inca
        self.assertIsNotNone(track["pending"])
        self.assertEqual(track["history"], [])


class TestWithdrawalRule(unittest.TestCase):
    def test_no_withdrawal_below_threshold_step(self):
        from pyramid_tracker import _apply_withdrawal, WITHDRAW_FROM_STEP
        bankroll, withdrawn = _apply_withdrawal(WITHDRAW_FROM_STEP - 1, 100.0, 10.0)
        self.assertEqual(withdrawn, 0.0)
        self.assertEqual(bankroll, 100.0)

    def test_withdraws_half_of_profit_at_threshold_step(self):
        from pyramid_tracker import _apply_withdrawal, WITHDRAW_FROM_STEP, WITHDRAW_PCT
        bankroll, withdrawn = _apply_withdrawal(WITHDRAW_FROM_STEP, 100.0, 10.0)
        expected_withdrawn = round((100.0 - 10.0) * WITHDRAW_PCT, 2)
        self.assertEqual(withdrawn, expected_withdrawn)
        self.assertEqual(bankroll, round(100.0 - expected_withdrawn, 2))

    def test_full_cycle_five_wins_triggers_withdrawal(self):
        """Simulare completa: 5 castiguri consecutive la cota 1.40 -> retragerea
        automata trebuie sa se activeze exact la pasul WITHDRAW_FROM_STEP."""
        from pyramid_tracker import _fresh_track, _register_next, _settle_pending, WITHDRAW_FROM_STEP
        track = _fresh_track("test")
        for i in range(WITHDRAW_FROM_STEP):
            pyramid_data = {"current_step_pool": _pool(track["step"] + 1, event_id=100 + i),
                             "pools_by_target": {"t2_50": {}}}
            _register_next(track, "current_step_pool", 10, pyramid_data, "now")
            _settle_pending(track, {100 + i: {"home_score": 1, "away_score": 0}}, "later")
        self.assertEqual(track["step"], WITHDRAW_FROM_STEP)
        self.assertGreater(track["total_withdrawn_lei"], 0.0)


if __name__ == "__main__":
    unittest.main()
