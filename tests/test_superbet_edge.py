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


class TestLiveOddsMatching(unittest.TestCase):
    def _compare_fixture(self, event_id=1, event_date=None, home="A", away="B"):
        if event_date is None:
            from datetime import datetime, timedelta, timezone
            event_date = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat().replace("+00:00", "Z")
        return {"results": [{
            "event_id": event_id, "home_team": home, "away_team": away,
            "league": "L", "event_date": event_date,
            "markets": {"1x2": {"outcomes": {
                "HOME": {"bookmakers": [{"bookmaker_slug": "pinnacle", "decimal_odds": 1.60}]},
                "DRAW": {"bookmakers": [{"bookmaker_slug": "pinnacle", "decimal_odds": 4.0}]},
                "AWAY": {"bookmakers": [{"bookmaker_slug": "pinnacle", "decimal_odds": 5.0}]},
            }}},
        }], "_event_date": event_date}

    def _live_odds_fixture(self, event_date_str, home="A", away="B", home_price=1.60):
        match_date = event_date_str[:10] + " 18:00:00"
        return {"matches": [{
            "superbet_event_id": 999,
            "home_team_superbet": home, "away_team_superbet": away,
            "match_date": match_date,
            "markets": {"1x2": {"HOME": home_price, "DRAW": 3.9, "AWAY": 4.8}},
        }]}

    def test_live_price_used_when_edge_confirmed(self):
        """Daca live_odds confirma un edge real (cota mai mare decat pragul calibrat),
        threshold_odds si expected_superbet_odds devin cota REALA, nu estimarea."""
        from superbet_edge_engine import build_watchlist
        fixture = self._compare_fixture()
        live = self._live_odds_fixture(fixture["_event_date"], home_price=1.90)  # edge mare, real
        dc_idx = {"1": {"tier": "COMPLETE"}}
        rows = build_watchlist(0.90, 0.05, compare=fixture, dc_idx=dc_idx, live_odds=live)
        home = next(r for r in rows if r["outcome"] == "HOME")
        self.assertEqual(home["odds_source"], "live")
        self.assertEqual(home["actual_superbet_odds"], 1.90)
        self.assertEqual(home["threshold_odds"], 1.90)

    def test_leg_excluded_when_live_price_confirms_no_edge(self):
        """Daca stim SIGUR (din live_odds) ca nu e edge, nu mai aratam piciorul deloc —
        nu mai avem nevoie sa cerem utilizatorului sa verifice manual o estimare."""
        from superbet_edge_engine import build_watchlist
        fixture = self._compare_fixture()
        # fair_odds HOME ~1.60 devigat; cota reala Superbet 1.55 nu are edge de 5% peste el
        live = self._live_odds_fixture(fixture["_event_date"], home_price=1.55)
        dc_idx = {"1": {"tier": "COMPLETE"}}
        rows = build_watchlist(0.90, 0.05, compare=fixture, dc_idx=dc_idx, live_odds=live)
        home_rows = [r for r in rows if r["outcome"] == "HOME"]
        self.assertEqual(home_rows, [])

    def test_no_live_match_falls_back_to_estimate(self):
        """Cand echipele din live_odds nu se potrivesc deloc, ramanem pe estimarea calibrata
        (comportamentul vechi), nu esuam si nu potrivim gresit."""
        from superbet_edge_engine import build_watchlist
        fixture = self._compare_fixture(home="Real Madrid", away="Barcelona")
        live = self._live_odds_fixture(fixture["_event_date"], home="Total Alt Meci", away="Alta Echipa")
        dc_idx = {"1": {"tier": "COMPLETE"}}
        rows = build_watchlist(0.90, 0.05, compare=fixture, dc_idx=dc_idx, live_odds=live)
        home = next(r for r in rows if r["outcome"] == "HOME")
        self.assertEqual(home["odds_source"], "estimare_calibrata")
        self.assertIsNone(home["actual_superbet_odds"])

    def test_different_date_does_not_match(self):
        """Acelasi nume de echipe, dar data diferita -> NU potrivim (ar putea fi confuzie
        intre doua meciuri diferite, sau date stale)."""
        from superbet_edge_engine import build_watchlist
        fixture = self._compare_fixture()
        live = self._live_odds_fixture("2099-01-01T00:00:00Z", home_price=1.90)
        dc_idx = {"1": {"tier": "COMPLETE"}}
        rows = build_watchlist(0.90, 0.05, compare=fixture, dc_idx=dc_idx, live_odds=live)
        home = next(r for r in rows if r["outcome"] == "HOME")
        self.assertEqual(home["odds_source"], "estimare_calibrata")

    def test_team_name_fuzzy_matching(self):
        from superbet_live_odds import normalize_team_name, team_match_score
        self.assertEqual(normalize_team_name("FCV Farul Constanța"), normalize_team_name("FCV Farul Constanta"))
        self.assertGreater(team_match_score("Otelul Galati", "SC Oțelul Galați"), 0.9)
        self.assertGreater(team_match_score("Universitatea Craiova", "Universitatea Craiova"), 0.99)
        # "FF" (prefix comun la cluburi nordice, ex. finlandeze) — gasit ca fals-negativ
        # real in productie (FF Jaro vs Jaro), la fel ca celelalte prefixe de club deja in lista.
        self.assertGreater(team_match_score("FF Jaro", "Jaro"), 0.9)
        # Nume diferite care doar impart un cuvant comun ("Real") NU trebuie sa treaca
        # de LIVE_MATCH_MIN_SCORE (0.6) — ar insemna sa potrivim gresit doua cluburi diferite.
        from superbet_edge_engine import LIVE_MATCH_MIN_SCORE
        self.assertLess(team_match_score("Real Madrid", "Real Sociedad"), LIVE_MATCH_MIN_SCORE)

    def test_market_extraction_from_raw_superbet_payload(self):
        """Payload brut (asa cum vine de la API-ul real, gasit prin recon) e parsat corect
        in cele 3 piete (1x2/btts/over_under_25)."""
        from superbet_live_odds import build_live_odds
        raw_events = [{
            "eventId": 1, "matchName": "Universitatea Craiova·UTA Arad",
            "matchDate": "2026-07-18 18:15:00", "tournamentId": 631,
            "odds": [
                {"marketId": 547, "name": "1", "price": 1.45},
                {"marketId": 547, "name": "X", "price": 4.55},
                {"marketId": 547, "name": "2", "price": 7.3},
                {"marketId": 539, "name": "Da", "price": 2.12},
                {"marketId": 539, "name": "Nu", "price": 1.73},
                {"marketId": 200734, "name": "Peste 2.5", "price": 1.87},
                {"marketId": 200734, "name": "Sub 2.5", "price": 1.95},
            ],
        }]
        out = build_live_odds(events=raw_events)
        self.assertEqual(out["n_matches_with_markets"], 1)
        m = out["matches"][0]
        self.assertEqual(m["home_team_superbet"], "Universitatea Craiova")
        self.assertEqual(m["away_team_superbet"], "UTA Arad")
        self.assertEqual(m["markets"]["1x2"], {"HOME": 1.45, "DRAW": 4.55, "AWAY": 7.3})
        self.assertEqual(m["markets"]["btts"], {"YES": 2.12, "NO": 1.73})
        self.assertEqual(m["markets"]["over_under_25"], {"OVER": 1.87, "UNDER": 1.95})


class TestEnrichFullMarkets(unittest.TestCase):
    """Bulk-ul (events/by-date) intoarce DOAR piata preselectata (1X2) — confirmat
    empiric (0/494 meciuri aveau btts/over_under in productie, desi Superbet chiar
    le ofera, verificat manual de utilizator in aplicatie). enrich_with_full_markets
    face un request individual DOAR pt. meciurile relevante (compare_odds_cache.json),
    ca sa completeze BTTS/Over-Under reale fara sa bata API-ul cu ~500 request-uri."""

    def test_enrich_merges_extra_markets_into_matched_event(self):
        from unittest.mock import patch
        from datetime import datetime, timezone
        from superbet_live_odds import enrich_with_full_markets
        matches = [{
            "superbet_event_id": 999, "home_team_superbet": "Universitatea Craiova",
            "away_team_superbet": "UTA Arad", "match_date": "2026-07-18 18:15:00",
            "markets": {"1x2": {"HOME": 1.45, "DRAW": 4.55, "AWAY": 7.3}},
        }]
        targets = [("Universitatea Craiova", "UTA Arad", datetime(2026, 7, 18, 18, 15, tzinfo=timezone.utc))]
        with patch("superbet_live_odds._load_compare_targets", return_value=targets), \
             patch("superbet_live_odds.fetch_match_detail_markets", return_value={"btts": {"YES": 2.12, "NO": 1.73}}):
            n = enrich_with_full_markets(matches)
        self.assertEqual(n, 1)
        self.assertEqual(matches[0]["markets"]["btts"], {"YES": 2.12, "NO": 1.73})
        self.assertEqual(matches[0]["markets"]["1x2"], {"HOME": 1.45, "DRAW": 4.55, "AWAY": 7.3})

    def test_enrich_skips_when_no_confident_match(self):
        from unittest.mock import patch
        from datetime import datetime, timezone
        from superbet_live_odds import enrich_with_full_markets
        matches = [{
            "superbet_event_id": 999, "home_team_superbet": "Cu totul alt club",
            "away_team_superbet": "Inca unul", "match_date": "2026-07-18 18:15:00",
            "markets": {"1x2": {"HOME": 1.45}},
        }]
        targets = [("Universitatea Craiova", "UTA Arad", datetime(2026, 7, 18, 18, 15, tzinfo=timezone.utc))]
        with patch("superbet_live_odds._load_compare_targets", return_value=targets):
            n = enrich_with_full_markets(matches)
        self.assertEqual(n, 0)
        self.assertEqual(matches[0]["markets"], {"1x2": {"HOME": 1.45}})

    def test_enrich_continues_after_individual_failure(self):
        from unittest.mock import patch
        from datetime import datetime, timezone
        from superbet_live_odds import enrich_with_full_markets
        matches = [{
            "superbet_event_id": 999, "home_team_superbet": "A", "away_team_superbet": "B",
            "match_date": "2026-07-18 18:15:00", "markets": {"1x2": {"HOME": 1.5}},
        }]
        targets = [("A", "B", datetime(2026, 7, 18, 18, 15, tzinfo=timezone.utc))]
        with patch("superbet_live_odds._load_compare_targets", return_value=targets), \
             patch("superbet_live_odds.fetch_match_detail_markets", side_effect=Exception("boom")):
            n = enrich_with_full_markets(matches)
        self.assertEqual(n, 0)
        self.assertEqual(matches[0]["markets"], {"1x2": {"HOME": 1.5}})


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

    def test_aggregate_win_rate_by_market(self):
        from superbet_edge_logger import _aggregate_win_rate_by
        rows = [
            {"market": "1x2", "market_label": "Rezultat final", "win": True},
            {"market": "1x2", "market_label": "Rezultat final", "win": False},
            {"market": "btts", "market_label": "Ambele echipe marchează", "win": True},
        ]
        out = _aggregate_win_rate_by(rows, "market", "necunoscut", label_key="market_label")
        self.assertEqual(out["1x2"]["n_settled"], 2)
        self.assertEqual(out["1x2"]["win_rate_pct"], 50.0)
        self.assertEqual(out["1x2"]["label"], "Rezultat final")
        self.assertEqual(out["btts"]["win_rate_pct"], 100.0)

    def test_aggregate_win_rate_by_sorts_by_sample_size_and_respects_top_n(self):
        from superbet_edge_logger import _aggregate_win_rate_by
        rows = ([{"league": "A", "win": True}] * 5 + [{"league": "B", "win": False}] * 2
                + [{"league": "C", "win": True}] * 1)
        out = _aggregate_win_rate_by(rows, "league", "necunoscuta", top_n=2)
        self.assertEqual(list(out.keys()), ["A", "B"])  # C exclus, top_n=2, sortat desc dupa n_settled

    def test_aggregate_win_rate_by_missing_key_uses_default(self):
        from superbet_edge_logger import _aggregate_win_rate_by
        rows = [{"win": True}]  # fara camp 'market'
        out = _aggregate_win_rate_by(rows, "market", "necunoscut")
        self.assertIn("necunoscut", out)


class TestSettlement(unittest.TestCase):
    def test_settle_leg_win(self):
        from superbet_edge_logger import _settle_leg
        row = {"event_id": 1, "market": "1x2", "outcome": "HOME", "result": None}
        res_idx = {1: {"home_score": 2, "away_score": 1}}
        _settle_leg(row, res_idx, "now")
        self.assertEqual(row["result"], "WIN")
        self.assertTrue(row["win"])
        self.assertEqual(row["final_score"], "2-1")

    def test_settle_leg_loss(self):
        from superbet_edge_logger import _settle_leg
        row = {"event_id": 1, "market": "1x2", "outcome": "HOME", "result": None}
        res_idx = {1: {"home_score": 0, "away_score": 1}}
        _settle_leg(row, res_idx, "now")
        self.assertEqual(row["result"], "LOSS")
        self.assertEqual(row["final_score"], "0-1")

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
