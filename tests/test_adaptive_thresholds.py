#!/usr/bin/env python3
"""Teste pentru adaptive_thresholds.py — audit 21.07.2026: recommend_thresholds()
putea produce min_edge_pp NEGATIV (ex. -100 pentru over15, n=222) cand un cos cu
esantion minuscul (n>=3) "castiga" prin zgomot, dezactivand efectiv filtrul de
edge pentru piata cu cel mai mare volum din pipeline."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))


def _bucket(lo, hi, n, roi_pct):
    return {"range_lo": lo, "range_hi": hi, "n": n, "roi_pct": roi_pct,
            "wins": 0, "losses": 0, "win_rate_pct": None, "avg_odds": None}


class TestRecommendThresholdsNeverGoesNegative(unittest.TestCase):
    def test_tiny_noisy_bucket_cannot_disable_edge_filter(self):
        """Reproducere directa a bug-ului din audit: cosul (-100,0) are n=3 si ROI
        pozitiv prin noroc pur -> inainte de fix, min_edge_pp ar fi devenit -100.
        Acum cosurile sub MIN_BUCKET_N (15) sunt ignorate, iar rezultatul final
        nu poate fi negativ oricum (plasa de siguranta)."""
        from adaptive_thresholds import recommend_thresholds
        edge_buckets = [
            _bucket(-100, 0, 3, 40.0),     # zgomot: n mic, ROI mare intamplator
            _bucket(0, 2, 250, -8.0),
            _bucket(2, 5, 180, -4.0),
            _bucket(5, 10, 90, 6.0),
        ]
        odds_buckets = [_bucket(1.0, 1.2, 300, -5.0), _bucket(1.2, 1.4, 200, 3.0)]
        prob_buckets = [_bucket(60, 70, 200, -6.0), _bucket(70, 80, 300, 2.0)]
        stats = {"n": 522, "roi_pct": -6.1, "wins": 200, "losses": 322}
        rec = recommend_thresholds("over15", stats, edge_buckets, odds_buckets, prob_buckets, trust=0.9)
        self.assertGreaterEqual(rec["min_edge_pp"], 0.0)
        self.assertGreaterEqual(rec["min_prob_pct"], 50.0)

    def test_profitable_bucket_needs_real_sample_size(self):
        """Un cos cu n=10 (sub MIN_BUCKET_N=15) nu trebuie sa fundamenteze singur
        recomandarea, chiar daca ROI-ul lui arata bine."""
        from adaptive_thresholds import recommend_thresholds, MIN_BUCKET_N
        self.assertEqual(MIN_BUCKET_N, 15)
        edge_buckets = [_bucket(0, 2, 10, 50.0), _bucket(2, 5, 100, -2.0)]
        odds_buckets = [_bucket(1.2, 1.4, 100, -2.0)]
        prob_buckets = [_bucket(60, 70, 100, -2.0)]
        stats = {"n": 110, "roi_pct": -2.0, "wins": 40, "losses": 70}
        rec = recommend_thresholds("btts", stats, edge_buckets, odds_buckets, prob_buckets, trust=0.7)
        # cosul de n=10 nu conteaza -> nu exista cos edge profitabil valid ->
        # ramane pe default-uri stricte pentru piata cu ROI negativ.
        self.assertGreaterEqual(rec["min_edge_pp"], 5.0)

    def test_blacklist_threshold_catches_real_bad_markets(self):
        """BLACKLIST_ROI_THRESHOLD era -50% (nu bloca niciodata piete reale ca
        -11.5%/-9.3% vazute in productie). Acum -15% cu n>=20 trebuie sa
        blacklisteze o piata cu ROI -20% pe n=93."""
        from adaptive_thresholds import recommend_thresholds
        stats = {"n": 93, "roi_pct": -20.0, "wins": 30, "losses": 63}
        rec = recommend_thresholds("under35", stats, [], [], [], trust=0.85)
        self.assertTrue(rec["blacklisted"])


if __name__ == "__main__":
    unittest.main()
