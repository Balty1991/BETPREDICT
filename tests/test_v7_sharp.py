#!/usr/bin/env python3
"""Teste pentru strategiile v7 (sharp_value_engine, sharp_clv_logger, referee_ou_edge)."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))


class TestSharpValueEngine(unittest.TestCase):
    def test_sharp_fair_probs_devig(self):
        """No-vig pe Pinnacle produce probabilitati care insumeaza ~1."""
        from sharp_value_engine import _sharp_fair_probs
        outcomes = {
            "HOME": {"bookmakers": [{"bookmaker_slug": "pinnacle", "decimal_odds": 2.0}]},
            "DRAW": {"bookmakers": [{"bookmaker_slug": "pinnacle", "decimal_odds": 3.5}]},
            "AWAY": {"bookmakers": [{"bookmaker_slug": "pinnacle", "decimal_odds": 4.0}]},
        }
        res = _sharp_fair_probs("1x2", outcomes)
        self.assertIsNotNone(res)
        probs, src = res
        self.assertEqual(src, "pinnacle")
        self.assertAlmostEqual(sum(probs.values()), 1.0, places=4)
        self.assertGreater(probs["HOME"], probs["AWAY"])  # cota mai mica => prob mai mare

    def test_sharp_fair_fallback_consensus(self):
        """Fara sharp book, cade pe consensus median al book-ilor reali."""
        from sharp_value_engine import _sharp_fair_probs
        outcomes = {
            "OVER": {"bookmakers": [
                {"bookmaker_slug": "bet365", "decimal_odds": 1.9},
                {"bookmaker_slug": "betano", "decimal_odds": 1.95}]},
            "UNDER": {"bookmakers": [
                {"bookmaker_slug": "bet365", "decimal_odds": 1.95},
                {"bookmaker_slug": "betano", "decimal_odds": 1.9}]},
        }
        res = _sharp_fair_probs("over_under_25", outcomes)
        self.assertIsNotNone(res)
        _, src = res
        self.assertEqual(src, "consensus_median")

    def test_arbitrage_detection(self):
        """Cote divergente => arbitraj cu ROI pozitiv, altfel niciunul."""
        from sharp_value_engine import scan_arbitrage
        # HOME 2.1 + AWAY 2.1 => 1/2.1+1/2.1 = 0.952 < 1 => arbitraj ~5%
        best = {"results": [{
            "event_id": 1, "market": "over_under_25", "home_team": "A", "away_team": "B",
            "league_name": "L", "event_date": "2030-01-01T00:00:00Z",
            "best_odds": [
                {"outcome": "over", "decimal_odds": 2.1, "bookmaker_slug": "x", "updated_at": "2030-01-01T00:00:00Z"},
                {"outcome": "under", "decimal_odds": 2.1, "bookmaker_slug": "y", "updated_at": "2030-01-01T00:00:00Z"}],
        }]}
        arbs = scan_arbitrage(best)
        self.assertEqual(len(arbs), 1)
        self.assertGreater(arbs[0]["guaranteed_roi_pct"], 0)
        # stake-urile trebuie sa insumeze ~100%
        self.assertAlmostEqual(sum(l["stake_pct"] for l in arbs[0]["legs"]), 100.0, delta=0.5)

    def test_no_arbitrage_with_vig(self):
        """Cote normale cu marja => niciun arbitraj."""
        from sharp_value_engine import scan_arbitrage
        best = {"results": [{
            "event_id": 2, "market": "btts", "best_odds": [
                {"outcome": "yes", "decimal_odds": 1.8, "bookmaker_slug": "x", "updated_at": "2030-01-01T00:00:00Z"},
                {"outcome": "no", "decimal_odds": 1.8, "bookmaker_slug": "y", "updated_at": "2030-01-01T00:00:00Z"}],
        }]}
        self.assertEqual(len(scan_arbitrage(best)), 0)


class TestClvLogger(unittest.TestCase):
    def test_settle_1x2(self):
        from sharp_clv_logger import _settle
        self.assertEqual(_settle("1x2", "HOME", 2, 1), 1)
        self.assertEqual(_settle("1x2", "HOME", 1, 2), 0)
        self.assertEqual(_settle("1x2", "DRAW", 1, 1), 1)
        self.assertEqual(_settle("1x2", "AWAY", 0, 3), 1)

    def test_settle_over_under(self):
        from sharp_clv_logger import _settle
        self.assertEqual(_settle("over_under_25", "OVER", 2, 1), 1)   # 3 > 2.5
        self.assertEqual(_settle("over_under_25", "OVER", 1, 1), 0)   # 2 < 2.5
        self.assertEqual(_settle("over_under_25", "UNDER", 1, 1), 1)

    def test_settle_btts(self):
        from sharp_clv_logger import _settle
        self.assertEqual(_settle("btts", "YES", 1, 1), 1)
        self.assertEqual(_settle("btts", "YES", 1, 0), 0)
        self.assertEqual(_settle("btts", "NO", 2, 0), 1)


class TestRefereeEdge(unittest.TestCase):
    def test_referee_index_merges_sources(self):
        """Indexul de arbitri normalizeaza avg_goals si deriva tendinta."""
        from referee_ou_edge import _referee_index
        idx = _referee_index()
        self.assertIsInstance(idx, dict)
        # daca exista intrari, fiecare are avg_goals si flag-uri booleene
        for r in list(idx.values())[:5]:
            self.assertIn("avg_goals", r)
            self.assertIsInstance(r["is_high_goals"], bool)
            self.assertIsInstance(r["is_low_goals"], bool)


if __name__ == "__main__":
    unittest.main()


class TestSmartAccumulator(unittest.TestCase):
    def test_correlation_control(self):
        """Max 1 picior/meci si max 2/liga in orice bilet generat."""
        from smart_accumulator import build_tickets_by_period, MAX_PER_LEAGUE
        tbp = build_tickets_by_period()
        for period, tickets in tbp.items():
            for t in tickets:
                eids = [l["event_id"] for l in t["legs"]]
                self.assertEqual(len(eids), len(set(eids)), "picior duplicat pe acelasi meci")
                leagues = {}
                for l in t["legs"]:
                    leagues[l.get("league")] = leagues.get(l.get("league"), 0) + 1
                if t.get("risk_level") != "longshot":
                    self.assertLessEqual(max(leagues.values()), MAX_PER_LEAGUE)

    def test_ticket_schema_matches_frontend(self):
        """Fiecare bilet/leg are campurile cerute de ClaudeAccumulator (frontend)."""
        from smart_accumulator import build_tickets_by_period
        tbp = build_tickets_by_period()
        req_t = {"label", "risk_level", "legs", "combined_odds", "combined_probability_pct"}
        req_l = {"event_id", "home_team", "away_team", "league", "event_date",
                 "market", "market_label", "odds", "probability", "rationale"}
        for tickets in tbp.values():
            for t in tickets:
                self.assertTrue(req_t <= set(t.keys()))
                self.assertIn(t["risk_level"], ("safe", "longshot"))
                for l in t["legs"]:
                    self.assertTrue(req_l <= set(l.keys()))

    def test_probability_is_market_anchored(self):
        """Probabilitatea realista trebuie sa fie apropiata de piata, nu umflata:
        prob combinata a unui bilet nu poate depasi mult 1/cota_combinata inflatata."""
        from smart_accumulator import build_tickets_by_period
        tbp = build_tickets_by_period()
        for tickets in tbp.values():
            for t in tickets:
                implied = 1.0 / t["combined_odds"] * 100
                # prob realista nu trebuie sa fie fantezista (>2.5x implicita)
                self.assertLess(t["combined_probability_pct"], implied * 2.5 + 5)
