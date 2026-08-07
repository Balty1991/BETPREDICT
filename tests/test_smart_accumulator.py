#!/usr/bin/env python3
"""Teste pentru smart_accumulator.py — in special pt. integrarea cu cotele reale
Superbet (build_leg_pool trebuie sa arate DOAR picioare pe care userul le poate
paria efectiv la casa lui, nu la orice casa avea cea mai buna cota in BSD API)."""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))


def _event_date():
    return (datetime.now(timezone.utc) + timedelta(days=2)).isoformat().replace("+00:00", "Z")


def _sig(event_id=1, market="homeWin", odds=2.0, home="A", away="B",
        event_date=None, grade="A"):
    return {
        "event_id": event_id, "home_team": home, "away_team": away, "league": "L",
        "event_date": event_date or _event_date(), "market": market, "market_label": market,
        # ev_calibrated=0.05: peste MIN_EV_CAL (+0.02, audit 21.07.2026 — cerem edge
        # real pozitiv, nu doar "nu prea negativ"). Aceste teste verifica rezolvarea
        # cotei Superbet, nu poarta de EV, deci fixture-ul trebuie doar sa o treaca.
        "odds": odds, "quality_grade_v6": grade, "ev_calibrated": 0.05,
        "calibrated_prob": round(1 / odds, 4), "bookmaker": "bet365",
    }


def _live(event_date_str, home="A", away="B", home_price=2.3):
    match_date = event_date_str[:10] + " 18:00:00"
    return {"matches": [{
        "home_team_superbet": home, "away_team_superbet": away,
        "match_date": match_date,
        "markets": {"1x2": {"HOME": home_price, "DRAW": 3.5, "AWAY": 3.0}},
    }]}


class TestBuildLegPoolSuperbetOnly(unittest.TestCase):
    def test_leg_dropped_without_superbet_match(self):
        """Fara date live (sau fara potrivire), piciorul e scos — nu aratam cote
        de la case unde userul nu are cont."""
        from smart_accumulator import build_leg_pool
        sig = _sig()
        pool = build_leg_pool(sigs={"signals": [sig]}, dc_idx={}, live_odds={}, sharp=set())
        self.assertEqual(pool, [])

    def test_leg_uses_real_superbet_odds_when_matched(self):
        """Cand gasim meciul cu siguranta la Superbet, cota aratata e cea REALA
        Superbet, nu cea mai buna cota cross-book din signals_v6.json."""
        from smart_accumulator import build_leg_pool
        ev_date = _event_date()
        sig = _sig(odds=2.0, event_date=ev_date)
        live = _live(ev_date, home_price=2.55)
        pool = build_leg_pool(sigs={"signals": [sig]}, dc_idx={}, live_odds=live, sharp=set())
        self.assertEqual(len(pool), 1)
        self.assertEqual(pool[0]["odds"], 2.55)
        self.assertEqual(pool[0]["bookmaker"], "Superbet")

    def test_probability_based_on_sharp_market_not_superbet_price(self):
        """Probabilitatea/edge-ul raman ancorate pe piata eficienta (cea mai buna
        cota cross-book), NU pe cota (mai proasta, cu marja retail) a Superbet —
        altfel am confunda 'marja tipica Superbet' cu semnal de valoare."""
        from smart_accumulator import build_leg_pool
        ev_date = _event_date()
        sig = _sig(odds=2.0, event_date=ev_date)
        pool_a = build_leg_pool(sigs={"signals": [sig]}, dc_idx={},
                                 live_odds=_live(ev_date, home_price=2.55), sharp=set())
        pool_b = build_leg_pool(sigs={"signals": [sig]}, dc_idx={},
                                 live_odds=_live(ev_date, home_price=1.90), sharp=set())
        self.assertEqual(pool_a[0]["probability"], pool_b[0]["probability"])
        self.assertNotEqual(pool_a[0]["odds"], pool_b[0]["odds"])

    def test_mismatched_team_names_dropped(self):
        """Nume de echipe complet diferite in live_odds -> nicio potrivire -> picior scos."""
        from smart_accumulator import build_leg_pool
        ev_date = _event_date()
        sig = _sig(home="Real Madrid", away="Barcelona", event_date=ev_date)
        live = _live(ev_date, home="Alt Club Total Diferit", away="Inca Unul")
        pool = build_leg_pool(sigs={"signals": [sig]}, dc_idx={}, live_odds=live, sharp=set())
        self.assertEqual(pool, [])


if __name__ == "__main__":
    unittest.main()
