"""Bilete Manus: selecție separată, filtrată, pentru acumulatoare 100+.

Nu modifică biletele existente. Este un singur bilet experimental pe zi, construit
numai din cote Superbet verificabile, fără cote lungite, fără selecții suspecte și
cu diversificare pe meci, ligă și familie de piață. Poate combina predicții
clasice cu selecții Supersocial; șansa totală rămâne produsul probabilităților,
nu o promisiune de profit.
"""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence

from betpredict.builder.high_odds import lengthened, load_extra, near_fair, p_prudent
from betpredict.builder.pool import Cand
from betpredict.builder.v4tickets import insert_ticket, ticket_stats

KIND = "acca_manus"
VARIANT = "manus_100_filtered"
TARGET = 100.0
MIN_LEG_ODDS = 1.28
MAX_LEG_ODDS = 1.75
MIN_LEG_P = 0.70
MIN_LEGS = 10
MAX_LEGS = 18
MAX_PER_LEAGUE = 2
MAX_PER_FAMILY = 0.50

# Piețe cu istoric slab sau cu risc de interpretare; Manus nu le folosește implicit.
AVOID_CLASSIC = frozenset({"btts", "away_win", "awaywin", "under35", "under_35", "under25", "under_25"})


def _family(c: Cand) -> str:
    if c.market == "ss":
        return "supersocial"
    if c.market in {"1x2", "double_chance", "draw_no_bet"}:
        return "rezultat"
    if c.market in {"over_under", "goals", "over15", "over25"}:
        return "goluri"
    return str(c.market or "clasic")


def eligible(c: Cand) -> bool:
    """Filtru de intrare; lipsa oricărei condiții exclude piciorul."""
    if not c.healthy or c.price_suspect or lengthened(c):
        return False
    if c.odds_source != "superbet" or not (MIN_LEG_ODDS <= c.odds <= MAX_LEG_ODDS):
        return False
    if p_prudent(c) < MIN_LEG_P:
        return False
    if c.market == "ss":
        return near_fair(c.selection)
    return str(c.market or "").lower() not in AVOID_CLASSIC


def _rank(c: Cand) -> float:
    # Eficiență probabilitate / creștere de cotă: favorizează cât mai puține
    # picioare și probabilitatea totală cea mai mare pentru pragul 100+.
    p = max(1e-6, min(0.995, p_prudent(c)))
    return math.log(p) / math.log(max(1.001, c.odds))


def choose_legs(pool: Sequence[Cand]) -> Optional[List[Cand]]:
    candidates = [c for c in pool if eligible(c)]
    best_by_match: Dict[int, Cand] = {}
    for c in candidates:
        old = best_by_match.get(c.match_id)
        if old is None or (_rank(c), p_prudent(c), -c.odds) > (_rank(old), p_prudent(old), -old.odds):
            best_by_match[c.match_id] = c

    ordered = sorted(best_by_match.values(), key=lambda c: (_rank(c), p_prudent(c), -c.odds), reverse=True)
    legs: List[Cand] = []
    leagues: Dict[str, int] = {}
    families: Dict[str, int] = {}
    total = 1.0
    for c in ordered:
        league = str(c.league or "?")
        family = _family(c)
        if leagues.get(league, 0) >= MAX_PER_LEAGUE:
            continue
        if len(legs) >= 4 and (families.get(family, 0) + 1) / (len(legs) + 1) > MAX_PER_FAMILY:
            continue
        legs.append(c)
        total *= c.odds
        leagues[league] = leagues.get(league, 0) + 1
        families[family] = families.get(family, 0) + 1
        if len(legs) >= MIN_LEGS and total >= TARGET:
            break
        if len(legs) >= MAX_LEGS:
            break

    if len(legs) < MIN_LEGS or total < TARGET:
        return None
    return legs


def build_day(conn, day: date, pool: Sequence[Cand], created: str, sel_used: Dict[int, int]) -> Dict[str, Any]:
    """Construiește cel mult un bilet Manus pentru ziua cerută."""
    existing = conn.execute(
        "SELECT 1 FROM ticket WHERE day=? AND kind=? AND status!='replaced' LIMIT 1",
        (day.isoformat(), KIND),
    ).fetchone()
    if existing:
        return {"skipped_existing": True}

    try:
        wide = list(pool) + load_extra(conn, day)
        legs = choose_legs(wide)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    if not legs:
        return {"made": 0, "reason": "Nu există suficiente selecții 70%+ eligibile pentru 100+."}

    total, p, ev = ticket_stats(legs, shrink=True)
    if total < TARGET:
        return {"made": 0, "reason": "Pragul real 100+ nu a fost atins."}
    families = sorted({_family(c) for c in legs})
    ss_n = sum(1 for c in legs if c.market == "ss")
    classic_n = len(legs) - ss_n
    reasons = [
        f"Bilete Manus · 100+ filtrat: {len(legs)} selecții, cotă reală {total:.2f}.",
        f"Mix analiză: {classic_n} predicții clasice + {ss_n} Supersocial; familii: {', '.join(families)}.",
        f"Probabilitate prudentă estimată: {p:.3%} (aprox. 1 din {round(1 / p) if p else '—'}); EV estimat: {ev:+.1%}.",
        "Filtre: cotă Superbet verificată, 1 meci o dată, max. 2 selecții/ligă, fără cote lungite sau piețe evitate.",
        "Manus este experimental/paper-only: cota 100+ implică volatilitate foarte mare; nu reprezintă garanție de câștig.",
    ]
    extra: Dict[str, Any] = {
        "label": "Bilete Manus · 100+ · analiză filtrată",
        "manus": True,
        "lottery": True,
        "paper": True,
        "informational": True,
        "experimental": True,
        "recommended": True,
        "risk_acknowledged": True,
        "tier": "manus",
        "source_mix": {"classic": classic_n, "supersocial": ss_n},
        "families": families,
        "filter_version": "manus-v1",
        "p_ticket_prudent": round(p, 6),
    }
    insert_ticket(conn, KIND, VARIANT, TARGET, legs, 0.0025, reasons, day, created, sel_used, extra)
    return {"made": 1, "legs": len(legs), "total_odds": round(total, 2), "p_ticket": round(p, 6), "ev": round(ev, 4)}
