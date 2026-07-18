#!/usr/bin/env python3
"""Teste pentru pyramid_assistant.py — matching cu cota reala Superbet, blocarea
pietelor prost calibrate (CRITICAL), avertisment pt. esantion mic (NO_DATA), si
calculul sansei REALE de a ajunge la fiecare pas (din win-rate istoric, nu din
o presupunere optimista)."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))


class TestRealisticCompletion(unittest.TestCase):
    def test_probability_is_win_rate_to_the_power_of_step(self):
        from pyramid_assistant import _realistic_completion
        out = _realistic_completion(50.0, 3)
        self.assertAlmostEqual(out["1"]["probability_pct"], 50.0, places=2)
        self.assertAlmostEqual(out["2"]["probability_pct"], 25.0, places=2)
        self.assertAlmostEqual(out["3"]["probability_pct"], 12.5, places=2)

    def test_ten_steps_at_realistic_win_rate_is_near_impossible(self):
        """Cu win-rate-ul real gasit in istoricul platformei (~44-47%), pasul 10
        trebuie sa iasa cu o sansa sub 1 din 1000 — nu un numar optimist."""
        from pyramid_assistant import _realistic_completion
        out = _realistic_completion(46.7, 10)
        self.assertLess(out["10"]["probability_pct"], 0.1)
        self.assertGreater(out["10"]["one_in"], 1000)

    def test_no_data_when_win_rate_missing(self):
        from pyramid_assistant import _realistic_completion
        out = _realistic_completion(None, 5)
        self.assertIn("note", out)


class TestMarketGating(unittest.TestCase):
    def _signal(self, market="btts", odds=1.4, prob=80, event_id=1,
               home="A", away="B", event_date="2026-08-01T18:00:00Z"):
        return {
            "event_id": event_id, "home_team": home, "away_team": away,
            "league": "L", "event_date": event_date, "market": market,
            "adj_prob": prob, "edge_pp": 5.0, "odds_real": True,
        }

    def _live(self, home="A", away="B", price=1.40):
        return [{
            "home_team_superbet": home, "away_team_superbet": away,
            "match_date": "2026-08-01 18:00:00",
            "markets": {"btts": {"YES": price, "NO": 2.5}},
        }]

    def test_critical_market_hard_blocked(self):
        """O piata DOVEDITA prost calibrata (CRITICAL) ramane exclusa, indiferent
        de scor — nu doar penalizata."""
        from pyramid_assistant import plan_for_step
        sig = self._signal(market="btts", odds=1.4, prob=90)
        sig["_superbet_odds"] = 1.40
        health = {"btts": {"status": "CRITICAL", "n": 20, "reason": "ECE mare"}}
        rows = plan_for_step([sig], step=1, avg_odds=1.30, ctx={}, clv={}, leagues={}, health=health)
        self.assertEqual(rows, [])

    def test_no_data_market_passes_with_warning_not_blocked(self):
        """Esantion insuficient (NO_DATA) NU mai blocheaza total — trece cu
        avertisment vizibil, ca sa nu ramana pool-ul gol doar pentru ca n e mic."""
        from pyramid_assistant import plan_for_step
        sig = self._signal(market="btts", odds=1.40, prob=90)
        sig["_superbet_odds"] = 1.40
        health = {"btts": {"status": "NO_DATA", "n": 5, "reason": "sample n=5 < 10"}}
        rows = plan_for_step([sig], step=1, avg_odds=1.30, ctx={}, clv={}, leagues={}, health=health)
        self.assertEqual(len(rows), 1)
        self.assertIn("calibration_warning", rows[0])
        self.assertIn("n=5", rows[0]["calibration_warning"])

    def test_leg_without_superbet_match_excluded(self):
        """Fara cota reala Superbet gasita, piciorul nu poate fi recomandat —
        indiferent cat de bun ar parea scorul pe cota altei case."""
        from pyramid_assistant import plan_for_step
        sig = self._signal(market="btts", odds=1.40, prob=90)
        sig["_superbet_odds"] = None
        health = {"btts": {"status": "OK", "n": 50}}
        rows = plan_for_step([sig], step=1, avg_odds=1.30, ctx={}, clv={}, leagues={}, health=health)
        self.assertEqual(rows, [])

    def test_odds_shown_are_the_real_superbet_odds(self):
        from pyramid_assistant import plan_for_step
        sig = self._signal(market="btts", odds=1.90, prob=90)  # 1.90 = cota "veche" (alta sursa)
        sig["_superbet_odds"] = 1.40  # cota reala Superbet, diferita
        health = {"btts": {"status": "OK", "n": 50}}
        rows = plan_for_step([sig], step=1, avg_odds=1.30, ctx={}, clv={}, leagues={}, health=health)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["odds"], 1.40)
        self.assertEqual(rows[0]["bookmaker"], "Superbet")


class TestSuperbetOddsResolution(unittest.TestCase):
    def test_resolves_price_for_matching_event(self):
        from pyramid_assistant import _resolve_superbet_odds
        sig = {"market": "homeWin", "home_team": "Universitatea Craiova",
               "away_team": "UTA Arad", "event_date": "2026-07-18T18:15:00Z"}
        live_matches = [{
            "home_team_superbet": "Universitatea Craiova", "away_team_superbet": "UTA Arad",
            "match_date": "2026-07-18 18:15:00",
            "markets": {"1x2": {"HOME": 1.45, "DRAW": 4.55, "AWAY": 7.3}},
        }]
        self.assertEqual(_resolve_superbet_odds(sig, live_matches), 1.45)

    def test_no_match_returns_none(self):
        from pyramid_assistant import _resolve_superbet_odds
        sig = {"market": "homeWin", "home_team": "Real Madrid",
               "away_team": "Barcelona", "event_date": "2026-07-18T18:15:00Z"}
        live_matches = [{
            "home_team_superbet": "Cu totul alt club", "away_team_superbet": "Inca unul",
            "match_date": "2026-07-18 18:15:00",
            "markets": {"1x2": {"HOME": 1.45}},
        }]
        self.assertIsNone(_resolve_superbet_odds(sig, live_matches))


if __name__ == "__main__":
    unittest.main()
