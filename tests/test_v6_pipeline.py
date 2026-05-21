#!/usr/bin/env python3
"""
tests/test_v6_pipeline.py
=========================
BetPredict Pro v6.0 — Regression Tests

Test-uri care valideaza ca toate componentele v6 functioneaza corect.
Foloseste unittest (built-in), zero dependencies suplimentare.

Rulare:
    python -m unittest tests.test_v6_pipeline -v

Sau direct:
    python tests/test_v6_pipeline.py

Suite-uri:
  1. TestAnalyticsCoreV6 — functii noi din analytics_core.py
  2. TestCalibrationEngine — calibratoare + apply_calibration
  3. TestAdaptiveThresholds — load + lookup
  4. TestDataOutputs — fisiere JSON exista si au schema corecta
  5. TestMLPredictions — output ml_ensemble valid
  6. TestSignalsV6Augmentation — semnale au campuri v6
  7. TestEndToEnd — schema cross-layer integration
"""

from __future__ import annotations
import json
import os
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = ROOT_DIR / "data"
MODELS_DIR = ROOT_DIR / "models"
SRC_DIR = ROOT_DIR / "src"

# Permite import din root si src/
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(SRC_DIR))


def load_json_or_none(path):
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ============================================================
# 1. ANALYTICS CORE V6
# ============================================================

class TestAnalyticsCoreV6(unittest.TestCase):
    """Verifica functiile noi din analytics_core.py v6."""

    def test_import_existing_functions_still_work(self):
        """Backward compat: functiile v5 sunt inca exportate."""
        from analytics_core import (
            safe_float, clamp, decimal_to_implied_probability,
            normalize_no_vig, expected_value_decimal, kelly_fraction,
            poisson_market_probabilities, quality_grade,
        )
        self.assertEqual(safe_float("1.5"), 1.5)
        self.assertEqual(clamp(5, 0, 3), 3)
        self.assertEqual(quality_grade(85), "A")
        self.assertIsNotNone(expected_value_decimal(0.7, 1.5))

    def test_blend_3way_balanced(self):
        from analytics_core import blend_3way
        # Cu greutati default 40/40/20
        result = blend_3way(0.70, 0.65, 0.68)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 0.676, places=2)

    def test_blend_3way_missing_source(self):
        """Daca BSD lipseste, greutatea redistribuita."""
        from analytics_core import blend_3way
        result = blend_3way(None, 0.50, 0.70)
        self.assertIsNotNone(result)
        # ML weight 40 + Poisson weight 20 = 60 total
        expected = (0.50 * 40 + 0.70 * 20) / 60
        self.assertAlmostEqual(result, expected, places=2)

    def test_blend_3way_all_none(self):
        from analytics_core import blend_3way
        self.assertIsNone(blend_3way(None, None, None))

    def test_consensus_agreement_perfect(self):
        from analytics_core import consensus_agreement
        ag = consensus_agreement([0.70, 0.70, 0.70])
        self.assertAlmostEqual(ag, 1.0, places=2)

    def test_consensus_agreement_divergent(self):
        from analytics_core import consensus_agreement
        ag = consensus_agreement([0.85, 0.30, 0.20])
        self.assertLess(ag, 0.5)

    def test_consensus_agreement_single_source(self):
        """Un singur sample = 1.0 (nu putem masura disacord)."""
        from analytics_core import consensus_agreement
        self.assertEqual(consensus_agreement([0.70]), 1.0)

    def test_apply_calibration_identity(self):
        from analytics_core import apply_calibration_state
        self.assertAlmostEqual(
            apply_calibration_state(0.75, {"type": "identity"}),
            0.75, places=2
        )

    def test_apply_calibration_shift(self):
        from analytics_core import apply_calibration_state
        result = apply_calibration_state(0.80, {"type": "shift", "shift": -0.30})
        self.assertAlmostEqual(result, 0.50, places=2)

    def test_apply_calibration_none_state(self):
        """State None = identity (clip)."""
        from analytics_core import apply_calibration_state
        self.assertAlmostEqual(apply_calibration_state(0.75, None), 0.75, places=2)

    def test_ev_calibrated(self):
        from analytics_core import ev_calibrated
        # Prob 0.75 * cota 1.5 - 1 = 0.125
        ev = ev_calibrated(0.75, 1.5, None)
        self.assertAlmostEqual(ev, 0.125, places=2)

    def test_smartbet_v6_consensus_total(self):
        from analytics_core import smartbet_score_v6
        # Consens total + prob mare = scor mare
        s = smartbet_score_v6(0.80, 0.78, 0.79, consensus_ag=0.95)
        self.assertGreater(s, 60)
        self.assertLessEqual(s, 100)

    def test_smartbet_v6_divergent(self):
        from analytics_core import smartbet_score_v6
        # Divergenta puternica = scor mai mic
        s_div = smartbet_score_v6(0.90, 0.40, 0.30, consensus_ag=0.10)
        s_con = smartbet_score_v6(0.90, 0.85, 0.88, consensus_ag=0.95)
        self.assertLess(s_div, s_con)

    def test_quality_grade_v6_levels(self):
        from analytics_core import quality_grade_v6
        self.assertEqual(quality_grade_v6(90, 0.90), "A+")
        self.assertEqual(quality_grade_v6(90, 0.50), "A")  # consens prea mic
        self.assertEqual(quality_grade_v6(75, 0.95), "B")
        self.assertEqual(quality_grade_v6(55, 0.95), "C")
        self.assertEqual(quality_grade_v6(20, 0.95), "E")


# ============================================================
# 2. CALIBRATION ENGINE
# ============================================================

class TestCalibrationEngine(unittest.TestCase):
    """Verifica calibration_engine.py."""

    def test_import_module(self):
        try:
            from calibration_engine import (
                apply_calibration, load_calibrators, normalize_market,
                get_market_bias,
            )
        except ImportError as e:
            self.fail(f"calibration_engine import: {e}")

    def test_normalize_market(self):
        from calibration_engine import normalize_market
        self.assertEqual(normalize_market("1"), "homeWin")
        self.assertEqual(normalize_market("homeWin"), "homeWin")
        self.assertEqual(normalize_market("X"), "draw")
        self.assertEqual(normalize_market("under35"), "under35")
        self.assertEqual(normalize_market("Over 2.5"), "over25")  # cleaned normalization
        self.assertEqual(normalize_market("over_25"), "over25")
        self.assertEqual(normalize_market(None), None)
        self.assertEqual(normalize_market(""), None)
        self.assertEqual(normalize_market("unknown_market_xyz"), None)

    def test_apply_calibration_no_calibrators(self):
        """Cu dict gol, returneaza prob clipped."""
        from calibration_engine import apply_calibration
        result = apply_calibration("homeWin", 0.90, {})
        self.assertAlmostEqual(result, 0.90, places=2)

    def test_apply_calibration_with_real_calibrators(self):
        """Cu calibratorii reali din models/, homeWin trebuie redus."""
        from calibration_engine import apply_calibration, load_calibrators
        cals = load_calibrators()
        if not cals:
            self.skipTest("models/calibrators_v6.pkl nu exista — ruleaza calibration_engine.py")
        homewin_cal = cals.get("homeWin")
        if not homewin_cal:
            self.skipTest("Calibrator homeWin nu exista — date insuficiente")
        # homeWin are bias +43pp, deci 0.90 ar trebui redus mult
        result = apply_calibration("homeWin", 0.90, cals)
        self.assertLess(result, 0.75)

    def test_get_market_bias_returns_float_or_none(self):
        from calibration_engine import get_market_bias, load_calibrators
        cals = load_calibrators()
        # Daca exista, e float; daca nu, e None
        bias = get_market_bias("homeWin", cals)
        self.assertTrue(bias is None or isinstance(bias, float))


# ============================================================
# 3. ADAPTIVE THRESHOLDS
# ============================================================

class TestAdaptiveThresholds(unittest.TestCase):
    """Verifica adaptive_thresholds.py."""

    def test_import_module(self):
        try:
            from adaptive_thresholds import (
                load_thresholds, get_market_threshold,
                is_market_blacklisted, apply_to_strategies,
                normalize_market,
            )
        except ImportError as e:
            self.fail(f"adaptive_thresholds import: {e}")

    def test_load_thresholds_returns_dict(self):
        from adaptive_thresholds import load_thresholds
        data = load_thresholds()
        self.assertIsInstance(data, dict)

    def test_apply_to_strategies_preserves_structure(self):
        """apply_to_strategies returneaza dict cu aceleasi chei."""
        from adaptive_thresholds import apply_to_strategies
        defaults = {
            "test_strategy": {
                "markets": ["homeWin", "over15"],
                "min_adj": 70.0,
                "min_edge": 8.0,
                "odd_min": 1.20,
                "odd_max": 2.00,
            }
        }
        result = apply_to_strategies(defaults)
        self.assertIn("test_strategy", result)
        self.assertIn("markets", result["test_strategy"])
        self.assertIn("min_edge", result["test_strategy"])

    def test_get_market_threshold_returns_value_or_default(self):
        from adaptive_thresholds import get_market_threshold
        val = get_market_threshold("under35", "min_edge_pp", default=5.0)
        self.assertIsInstance(val, (int, float))


# ============================================================
# 4. DATA OUTPUTS — schema valida
# ============================================================

class TestDataOutputs(unittest.TestCase):
    """Verifica ca fisierele JSON v6 exista si au schema corecta."""

    def test_predictions_json_exists(self):
        path = DATA_DIR / "predictions.json"
        self.assertTrue(path.exists(), f"{path} lipseste")

    def test_signals_json_exists(self):
        path = DATA_DIR / "signals.json"
        self.assertTrue(path.exists(), f"{path} lipseste")

    def test_ml_predictions_schema(self):
        data = load_json_or_none(DATA_DIR / "ml_predictions.json")
        if data is None:
            self.skipTest("ml_predictions.json nu exista")
        self.assertIn("updated_at", data)
        self.assertIn("model_version", data)
        self.assertIn("results", data)
        self.assertIn("markets", data)

    def test_calibration_report_schema(self):
        data = load_json_or_none(DATA_DIR / "calibration_report.json")
        if data is None:
            self.skipTest("calibration_report.json nu exista")
        self.assertIn("updated_at", data)
        self.assertIn("markets", data)
        self.assertIn("overall", data)

    def test_adaptive_thresholds_schema(self):
        data = load_json_or_none(DATA_DIR / "adaptive_thresholds.json")
        if data is None:
            self.skipTest("adaptive_thresholds.json nu exista")
        self.assertIn("updated_at", data)
        self.assertIn("by_market", data)

    def test_consensus_schema(self):
        data = load_json_or_none(DATA_DIR / "consensus.json")
        if data is None:
            self.skipTest("consensus.json nu exista")
        self.assertIn("updated_at", data)
        self.assertIn("results", data)
        self.assertIn("summary", data)

    def test_signals_v6_schema(self):
        data = load_json_or_none(DATA_DIR / "signals_v6.json")
        if data is None:
            self.skipTest("signals_v6.json nu exista")
        self.assertIn("updated_at", data)
        self.assertIn("signals", data)
        self.assertIn("summary", data)
        summary = data["summary"]
        for key in ("upgraded", "downgraded", "quality_aplus"):
            self.assertIn(key, summary)


# ============================================================
# 5. ML PREDICTIONS — validitate per match
# ============================================================

class TestMLPredictions(unittest.TestCase):
    """Verifica calitatea output-ului ml_ensemble."""

    @classmethod
    def setUpClass(cls):
        cls.data = load_json_or_none(DATA_DIR / "ml_predictions.json")

    def test_data_loaded(self):
        if self.data is None:
            self.skipTest("ml_predictions.json lipseste")
        self.assertIsInstance(self.data.get("results", []), list)

    def test_probabilities_in_range(self):
        if self.data is None:
            self.skipTest("ml_predictions.json lipseste")
        for r in self.data.get("results", [])[:50]:
            probs = r.get("ml_probabilities", {})
            for m, p in probs.items():
                if p is None:
                    continue
                self.assertGreaterEqual(p, 0.0, f"Prob negativa pe {m}")
                self.assertLessEqual(p, 1.0, f"Prob > 1 pe {m}")

    def test_1x2_sums_close_to_1(self):
        """homeWin + draw + awayWin trebuie sa fie aprox 1."""
        if self.data is None:
            self.skipTest("ml_predictions.json lipseste")
        for r in self.data.get("results", [])[:30]:
            probs = r.get("ml_probabilities", {})
            h = probs.get("homeWin")
            d = probs.get("draw")
            a = probs.get("awayWin")
            if None in (h, d, a):
                continue
            total = h + d + a
            self.assertAlmostEqual(total, 1.0, delta=0.10,
                                   msg=f"1X2 nu suma la 1: {total} ({r.get('home_team')})")


# ============================================================
# 6. SIGNALS V6 AUGMENTATION
# ============================================================

class TestSignalsV6Augmentation(unittest.TestCase):
    """Verifica ca semnalele din signals.json au campuri v6."""

    @classmethod
    def setUpClass(cls):
        cls.data = load_json_or_none(DATA_DIR / "signals.json")

    def test_signals_marked_v6(self):
        if self.data is None:
            self.skipTest("signals.json lipseste")
        self.assertTrue(
            self.data.get("_v6_enhanced", False),
            "signals.json nu e marcat _v6_enhanced — ruleaza compute_signals_v6.py"
        )

    def test_signals_have_v6_fields(self):
        if self.data is None:
            self.skipTest("signals.json lipseste")
        signals = self.data.get("signals", [])
        if not signals:
            self.skipTest("Niciun semnal")

        v6_fields = [
            "smartbet_score_v6", "quality_grade_v6", "_v6_status",
            "calibrated_prob", "consensus_tier", "ev_calibrated",
        ]
        sample = signals[0]
        for field in v6_fields:
            self.assertIn(field, sample,
                          f"Semnal lipseste {field}: {sample.get('event_id')}")

    def test_v6_statuses_valid(self):
        if self.data is None:
            self.skipTest("signals.json lipseste")
        valid_statuses = {"UPGRADED", "DOWNGRADED", "ADJUSTED", "UNCHANGED", "NEW_ML"}
        for sig in self.data.get("signals", []):
            status = sig.get("_v6_status")
            if status:
                self.assertIn(status, valid_statuses,
                              f"Status invalid: {status}")

    def test_consensus_tiers_valid(self):
        if self.data is None:
            self.skipTest("signals.json lipseste")
        valid_tiers = {"TOTAL", "PARTIAL", "DIVERGENT", "CONTRADICTORIU", None}
        for sig in self.data.get("signals", []):
            tier = sig.get("consensus_tier")
            self.assertIn(tier, valid_tiers, f"Tier invalid: {tier}")


# ============================================================
# 7. END-TO-END INTEGRATION
# ============================================================

class TestEndToEndIntegration(unittest.TestCase):
    """Verifica integrarea cross-layer."""

    def test_v6_health_status_exists(self):
        data = load_json_or_none(DATA_DIR / "v6_health.json")
        if data is None:
            self.skipTest("v6_health.json lipseste — ruleaza v6_healthcheck.py")
        self.assertIn("overall", data)
        self.assertIn(data["overall"]["status"], ("GREEN", "YELLOW", "RED"))

    def test_all_layers_reported(self):
        data = load_json_or_none(DATA_DIR / "v6_health.json")
        if data is None:
            self.skipTest("v6_health.json lipseste")
        layers = data.get("layers", {})
        for layer_name in ("ml_ensemble", "calibration", "adaptive_thresholds",
                           "consensus", "signals_v6"):
            self.assertIn(layer_name, layers)

    def test_models_directory(self):
        if not MODELS_DIR.exists():
            self.skipTest("models/ nu exista — pipeline-ul nu a rulat")
        # Verifica ca exista cel putin un .pkl
        pkls = list(MODELS_DIR.glob("*.pkl"))
        self.assertGreater(len(pkls), 0, "Niciun model .pkl in models/")


if __name__ == "__main__":
    unittest.main(verbosity=2)
