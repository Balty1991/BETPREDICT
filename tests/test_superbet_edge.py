#!/usr/bin/env python3
"""Teste pentru superbet_edge_engine.py si superbet_edge_logger.py (motorul de praguri
pentru un singur bookmaker + jurnalul de monitorizare)."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))


class TestCalibration(unittest.TestCase):
    def test_fallback_on_insufficient_samples(self):
        from superbet_edge_engine import _calibration, DEFAULT_MARGIN_FACTOR, DEFAULT_EDGE_REQUIRED
        margin, edge, meta = _calibration({"observations": [{"gap_pct": -5.0}]})
        self.assertEqual(margin, DEFAULT_MARGIN_FACTOR)
        self.assertEqual(edge, DEFAULT_EDGE_REQUIRED)
        self.assertEqual(meta["source"], "default")

    def test_fallback_on_empty_calibration(self):
        from superbet_edge_engine import _calibration, DEFAULT_MARGIN_FACTOR
        margin, edge, meta = _calibration({})
        self.assertEqual(margin, DEFAULT_MARGIN_FACTOR)
        self.assertEqual(meta["n_observations"], 0)

    def test_margin_factor_from_real_observations(self):
        """Marja medie -10% => margin_factor ~0.90 (Superbet ofera de obicei 90% din pretul corect)."""
        from superbet_edge_engine import _calibration
        obs = [{"gap_pct": -10.0}, {"gap_pct": -10.0}, {"gap_pct": -10.0}]
        margin, edge, meta = _calibration({"observations": obs})
        self.assertAlmostEqual(margin, 0.90, places=2)
        self.assertEqual(meta["source"], "calibrat_din_observatii")
        self.assertEqual(meta["n_positive_gap"], 0)

    def test_margin_factor_clamped_on_extreme_average(self):
        """Un outlier extrem (-50%) nu trebuie sa produca un margin_factor absurd — clamp activ."""
        from superbet_edge_engine import _calibration, MARGIN_FACTOR_FLOOR
        obs = [{"gap_pct": -50.0}, {"gap_pct": -50.0}, {"gap_pct": -50.0}]
        margin, edge, meta = _calibration({"observations": obs})
        self.assertEqual(margin, MARGIN_FACTOR_FLOOR)
        self.assertTrue(meta["clamped"])

    def test_stale_calibration_adds_extra_cushion(self):
        """Un jurnal vechi (>7 zile) trebuie marcat stale si sa ceara edge suplimentar."""
        from superbet_edge_engine import _calibration, CALIBRATION_EDGE_REQUIRED
        old_cal = {
            "updated_at": "2020-01-01T00:00:00+00:00",
            "observations": [{"gap_pct": -5.0}, {"gap_pct": -5.0}, {"gap_pct": -5.0}],
        }
        margin, edge, meta = _calibration(old_cal)
        self.assertTrue(meta["stale"])
        self.assertGreater(edge, CALIBRATION_EDGE_REQUIRED)

    def test_fresh_calibration_not_stale(self):
        from datetime import datetime, timezone
        from superbet_edge_engine import _calibration
        fresh_cal = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "observations": [{"gap_pct": -5.0}, {"gap_pct": -5.0}, {"gap_pct": -5.0}],
        }
        _, _, meta = _calibration(fresh_cal)
        self.assertFalse(meta["stale"])


class TestWatchlistFiltering(unittest.TestCase):
    def _compare_fixture(self, event_id=1, event_date=None):
        if event_date is None:
            from datetime import datetime, timedelta, timezone
            event_date = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat().replace("+00:00", "Z")
        return {"results": [{
            "event_id": event_id, "home_team": "A", "away_team": "B",
            "league": "L", "event_date": event_date,
            "markets": {"1x2": {"outcomes": {
                "HOME": {"bookmakers": [{"bookmaker_slug": "pinnacle", "decimal_odds": 1.60}]},
                "DRAW": {"bookmakers": [{"bookmaker_slug": "pinnacle", "decimal_odds": 4.0}]},
                "AWAY": {"bookmakers": [{"bookmaker_slug": "pinnacle", "decimal_odds": 5.0}]},
            }}},
        }]}

    def test_missing_data_confidence_is_excluded(self):
        """Un eveniment ABSENT din data_confidence.json trebuie tratat conservator (exclus),
        nu implicit acceptat."""
        from superbet_edge_engine import build_watchlist
        rows = build_watchlist(1.0, 0.05, compare=self._compare_fixture(), dc_idx={})
        self.assertEqual(rows, [])

    def test_insuficient_tier_is_excluded(self):
        from superbet_edge_engine import build_watchlist
        dc_idx = {"1": {"tier": "INSUFICIENT"}}
        rows = build_watchlist(1.0, 0.05, compare=self._compare_fixture(), dc_idx=dc_idx)
        self.assertEqual(rows, [])

    def test_complete_tier_passes_through(self):
        from superbet_edge_engine import build_watchlist
        dc_idx = {"1": {"tier": "COMPLETE"}}
        rows = build_watchlist(1.0, 0.05, compare=self._compare_fixture(), dc_idx=dc_idx)
        self.assertGreater(len(rows), 0)

    def test_threshold_formula_uses_margin_and_edge_not_raw_pinnacle(self):
        """threshold = fair_odds * margin_factor * (1+edge_required) — NU fair_odds * (1+edge_required)
        (bug-ul original corectat: reperul e cota tipica Superbet, nu pretul brut Pinnacle).
        fair_odds nu e identic cu cota bruta introdusa (se de-vig-uieste impotriva DRAW/AWAY),
        deci verificam relatia dintre campuri, nu o valoare fixa hardcodata."""
        from superbet_edge_engine import build_watchlist
        dc_idx = {"1": {"tier": "COMPLETE"}}
        rows = build_watchlist(0.90, 0.05, compare=self._compare_fixture(), dc_idx=dc_idx)
        home = next(r for r in rows if r["outcome"] == "HOME")
        self.assertAlmostEqual(home["expected_superbet_odds"], round(home["fair_odds"] * 0.90, 2), places=2)
        self.assertAlmostEqual(home["threshold_odds"], round(home["expected_superbet_odds"] * 1.05, 2), places=2)

    def test_out_of_range_odds_excluded(self):
        """THRESH_MIN/THRESH_MAX filtreaza pe fair_odds (dupa de-vig) — un favorit foarte scurt
        nu apare in watchlist."""
        from superbet_edge_engine import build_watchlist, THRESH_MIN
        fixture = self._compare_fixture()
        outcomes = fixture["results"][0]["markets"]["1x2"]["outcomes"]
        outcomes["HOME"]["bookmakers"][0]["decimal_odds"] = 1.01
        outcomes["DRAW"]["bookmakers"][0]["decimal_odds"] = 50.0
        outcomes["AWAY"]["bookmakers"][0]["decimal_odds"] = 50.0
        dc_idx = {"1": {"tier": "COMPLETE"}}
        rows = build_watchlist(1.0, 0.05, compare=fixture, dc_idx=dc_idx)
        home_rows = [r for r in rows if r["outcome"] == "HOME"]
        self.assertEqual(home_rows, [])
        if home_rows:
            self.assertGreaterEqual(home_rows[0]["fair_odds"], THRESH_MIN)

    def test_recommended_flag_marks_best_leg_per_event(self):
        """Exact un picior per meci trebuie marcat 'recommended'."""
        from superbet_edge_engine import build_watchlist
        dc_idx = {"1": {"tier": "COMPLETE"}}
        rows = build_watchlist(1.0, 0.05, compare=self._compare_fixture(), dc_idx=dc_idx)
        recommended = [r for r in rows if r["recommended"]]
        self.assertEqual(len(recommended), 1)
        # HOME are cea mai mare probabilitate (cota 1.60) -> ar trebui sa fie recomandat
        self.assertEqual(recommended[0]["outcome"], "HOME")


class TestExposureCap(unittest.TestCase):
    def test_no_scaling_under_cap(self):
        from superbet_edge_engine import _apply_exposure_cap
        tickets = [{"stake_pct_of_bankroll": 2.0, "stake_amount_lei": 10.0, "instructions": ""}]
        info = _apply_exposure_cap(tickets, {"ml_circuit_breaker_active": False})
        self.assertEqual(info["scale_applied"], 1.0)
        self.assertEqual(tickets[0]["stake_pct_of_bankroll"], 2.0)

    def test_scales_down_when_over_cap(self):
        from superbet_edge_engine import _apply_exposure_cap, SELF_MAX_DAILY_EXPOSURE_PCT
        tickets = [{"stake_pct_of_bankroll": 4.0, "stake_amount_lei": 20.0, "instructions": ""},
                   {"stake_pct_of_bankroll": 4.0, "stake_amount_lei": 20.0, "instructions": ""}]
        info = _apply_exposure_cap(tickets, {"ml_circuit_breaker_active": False})
        self.assertLess(info["scale_applied"], 1.0)
        total_after = sum(t["stake_pct_of_bankroll"] for t in tickets)
        self.assertLessEqual(round(total_after, 2), SELF_MAX_DAILY_EXPOSURE_PCT)

    def test_circuit_breaker_halves_cap(self):
        """Cand circuit breaker-ul din sistemul ML e activ, plafonul Superbet Edge se injumatateste."""
        from superbet_edge_engine import _apply_exposure_cap
        tickets = [{"stake_pct_of_bankroll": 4.0, "stake_amount_lei": 20.0, "instructions": ""}]
        info = _apply_exposure_cap(tickets, {"ml_circuit_breaker_active": True})
        self.assertEqual(info["cap_pct"], 2.5)
        self.assertLess(tickets[0]["stake_pct_of_bankroll"], 4.0)


class TestHealthCheck(unittest.TestCase):
    def test_green_on_healthy_state(self):
        from superbet_edge_engine import _health_check
        h = _health_check(
            watchlist=[{"x": 1}] * 20, tickets=[{"x": 1}],
            cal_meta={"n_observations": 15, "stale": False, "clamped": False},
            exposure={"scale_applied": 1.0})
        self.assertEqual(h["status"], "GREEN")
        self.assertEqual(h["issues"], [])

    def test_red_on_empty_watchlist(self):
        from superbet_edge_engine import _health_check
        h = _health_check(watchlist=[], tickets=[],
                          cal_meta={"n_observations": 0, "stale": False, "clamped": False},
                          exposure={"scale_applied": 1.0})
        self.assertEqual(h["status"], "RED")

    def test_yellow_on_stale_calibration(self):
        from superbet_edge_engine import _health_check
        h = _health_check(
            watchlist=[{"x": 1}] * 20, tickets=[{"x": 1}],
            cal_meta={"n_observations": 15, "stale": True, "days_old": 30, "clamped": False},
            exposure={"scale_applied": 1.0})
        self.assertEqual(h["status"], "YELLOW")
        self.assertTrue(any("veche" in i for i in h["issues"]))


class TestLoggerKeys(unittest.TestCase):
    def test_leg_key_stable(self):
        from superbet_edge_logger import _leg_key
        self.assertEqual(_leg_key(1, "1x2", "HOME"), _leg_key(1, "1x2", "HOME"))
        self.assertNotEqual(_leg_key(1, "1x2", "HOME"), _leg_key(1, "1x2", "AWAY"))

    def test_ticket_key_order_independent(self):
        """Cheia unui bilet nu trebuie sa depinda de ordinea picioarelor — acelasi set
        de picioare, indiferent de ordine, trebuie sa mapeze la aceeasi cheie (evita
        duplicarea in jurnal la fiecare rulare)."""
        from superbet_edge_logger import _ticket_key
        legs_a = [{"event_id": 1, "market": "1x2", "outcome": "HOME"},
                  {"event_id": 2, "market": "btts", "outcome": "YES"}]
        legs_b = list(reversed(legs_a))
        self.assertEqual(_ticket_key("Sigur", legs_a), _ticket_key("Sigur", legs_b))

    def test_register_leg_does_not_overwrite_existing(self):
        from superbet_edge_logger import _register_leg
        ledger = {}
        leg = {"event_id": 1, "market": "1x2", "outcome": "HOME", "fair_prob_pct": 60.0}
        _register_leg(ledger, leg, "t1")
        ledger["1:1x2:HOME"]["result"] = "WIN"  # simuleaza o decontare
        _register_leg(ledger, leg, "t2")  # nu trebuie sa resteze rezultatul
        self.assertEqual(ledger["1:1x2:HOME"]["result"], "WIN")
        self.assertEqual(ledger["1:1x2:HOME"]["logged_at"], "t1")


class TestSettlement(unittest.TestCase):
    def test_settle_leg_win(self):
        from superbet_edge_logger import _settle_leg
        row = {"event_id": 1, "market": "1x2", "outcome": "HOME", "result": None}
        res_idx = {1: {"home_score": 2, "away_score": 1}}
        _settle_leg(row, res_idx, "now")
        self.assertEqual(row["result"], "WIN")
        self.assertTrue(row["win"])

    def test_settle_leg_loss(self):
        from superbet_edge_logger import _settle_leg
        row = {"event_id": 1, "market": "1x2", "outcome": "HOME", "result": None}
        res_idx = {1: {"home_score": 0, "away_score": 1}}
        _settle_leg(row, res_idx, "now")
        self.assertEqual(row["result"], "LOSS")

    def test_settle_leg_pending_without_result(self):
        from superbet_edge_logger import _settle_leg
        row = {"event_id": 1, "market": "1x2", "outcome": "HOME", "result": None}
        _settle_leg(row, {}, "now")  # meciul nu apare inca in rezultate
        self.assertIsNone(row["result"])

    def test_ticket_win_requires_all_legs_win(self):
        from superbet_edge_logger import _settle_ticket
        legs_ledger = {"1:1x2:HOME": {"result": "WIN"}, "2:btts:YES": {"result": "WIN"}}
        t = {"leg_keys": ["1:1x2:HOME", "2:btts:YES"], "result": None, "combined_threshold_odds": 3.0}
        _settle_ticket(t, legs_ledger, "now")
        self.assertEqual(t["result"], "WIN")
        self.assertAlmostEqual(t["profit_units_proxy"], 2.0)

    def test_ticket_loses_as_soon_as_one_leg_loses(self):
        from superbet_edge_logger import _settle_ticket
        legs_ledger = {"1:1x2:HOME": {"result": "WIN"}, "2:btts:YES": {"result": "LOSS"}}
        t = {"leg_keys": ["1:1x2:HOME", "2:btts:YES"], "result": None, "combined_threshold_odds": 3.0}
        _settle_ticket(t, legs_ledger, "now")
        self.assertEqual(t["result"], "LOSS")
        self.assertEqual(t["profit_units_proxy"], -1.0)

    def test_ticket_pending_while_legs_unsettled(self):
        from superbet_edge_logger import _settle_ticket
        legs_ledger = {"1:1x2:HOME": {"result": "WIN"}, "2:btts:YES": {"result": None}}
        t = {"leg_keys": ["1:1x2:HOME", "2:btts:YES"], "result": None, "combined_threshold_odds": 3.0}
        _settle_ticket(t, legs_ledger, "now")
        self.assertIsNone(t["result"])


if __name__ == "__main__":
    unittest.main()
