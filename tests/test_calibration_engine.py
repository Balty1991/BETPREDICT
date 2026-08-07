#!/usr/bin/env python3
"""Teste pentru calibration_engine.py — in special pentru bug-ul de evaluare
in-sample (audit 21.07.2026): evaluate_state() antrena si evalua calibratorul
PE ACELASI set, ceea ce da mereu ECE post ~0 pentru isotonic, indiferent daca
calibratorul generalizeaza sau nu (certifica fals piete cu bias real ca "HEALTHY").
evaluate_out_of_fold() trebuie sa fie onesta: k-fold CV, nu fit+evaluate pe acelasi
set."""
import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))


def _biased_samples(n, predicted=0.80, actual_rate=0.60, seed=0):
    """Simuleaza o piata sistematic supra-increzatoare: modelul zice `predicted`
    mereu, dar rata reala de castig e `actual_rate` (bias mare si constant)."""
    rnd = random.Random(seed)
    return [(predicted, 1 if rnd.random() < actual_rate else 0) for _ in range(n)]


class TestOutOfFoldEvaluation(unittest.TestCase):
    def test_out_of_fold_does_not_collapse_to_near_zero_like_in_sample(self):
        """Pe date real biasate, evaluate_state() (in-sample) da ECE post ~0
        (modelul isi descrie propriile date de antrenare) — evaluate_out_of_fold()
        trebuie sa ramana onest: eroarea reziduala nu poate disparea complet doar
        pentru ca am evaluat pe date nevazute de calibrator."""
        from calibration_engine import fit_calibrator_state, evaluate_state, evaluate_out_of_fold
        samples = _biased_samples(200, predicted=0.80, actual_rate=0.55)
        state = fit_calibrator_state(samples)
        in_sample = evaluate_state(state, samples)
        oof = evaluate_out_of_fold(samples)

        # In-sample e suspect de bun (asta e chiar bug-ul original) —
        # verificam ca out-of-fold NU e la fel de optimist.
        self.assertIsNotNone(oof["post"]["ece"])
        self.assertGreaterEqual(oof["post"]["ece"], in_sample["post"]["ece"] - 1e-9)

    def test_insufficient_samples_reports_none_instead_of_fake_perfect_score(self):
        """Sub MIN_SAMPLES_FOR_CV, raportam onest ca evaluarea nu e disponibila —
        NU inventam un ECE fals (asta ar retrograda la exact bug-ul vechi)."""
        from calibration_engine import evaluate_out_of_fold, MIN_SAMPLES_FOR_CV
        samples = _biased_samples(MIN_SAMPLES_FOR_CV - 1)
        oof = evaluate_out_of_fold(samples)
        self.assertIsNone(oof["post"]["ece"])
        self.assertIsNone(oof["post"]["brier"])
        self.assertIn("insuficient", oof["eval_method"])

    def test_well_calibrated_market_scores_well_out_of_fold_too(self):
        """Control: o piata FARA bias (predicted == actual rate) trebuie sa
        ramana cu ECE mic si in evaluarea out-of-fold, nu doar in-sample."""
        from calibration_engine import fit_calibrator_state, evaluate_out_of_fold
        samples = _biased_samples(200, predicted=0.70, actual_rate=0.70, seed=1)
        state = fit_calibrator_state(samples)
        oof = evaluate_out_of_fold(samples)
        self.assertIsNotNone(oof["post"]["ece"])
        self.assertLess(oof["post"]["ece"], 0.15)


class TestCalibrationHealthBiasField(unittest.TestCase):
    def test_bias_pp_field_is_actually_populated(self):
        """Bug corectat: calibration_health.py citea 'bias_pp' dintr-un dict care
        avea doar 'bias' (fractie) — cheia gresita insemna ca verificarea
        |bias|>15pp nu se declansa NICIODATA. Un market cu bias real +19pp trebuie
        sa iasa CRITICAL, nu HEALTHY."""
        from calibration_health import classify
        rec = {
            "type": "isotonic", "n_samples": 150,
            "pre": {"bias": 0.19, "ece": 0.19},
            "post": {"ece": 0.0001, "brier": 0.0},  # in-sample style, artificial de bun
        }
        result = classify(rec)
        self.assertEqual(result["status"], "CRITICAL")
        self.assertAlmostEqual(result["bias_pp"], 19.0, places=3)

    def test_healthy_when_bias_and_ece_both_small(self):
        from calibration_health import classify
        rec = {
            "type": "isotonic", "n_samples": 150,
            "pre": {"bias": 0.02, "ece": 0.02},
            "post": {"ece": 0.02, "brier": 0.1},
        }
        result = classify(rec)
        self.assertEqual(result["status"], "HEALTHY")


if __name__ == "__main__":
    unittest.main()
