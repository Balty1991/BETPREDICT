"""v4: reguli de bilete (docs/research v4 §4).

* **Bilete de valoare** (``acca_value``): 2–4 selecții, fiecare cu edge ≥ 4% (p prudent · cotă − 1), cote 1.50–2.50,
  piață sănătoasă; p prudent = 0.7·p_model + 0.3·p_piață; miză Kelly 1/8 plafonată la 1u (1% bancă) pe bilet și
  5u expunere totală pe zi.
* **Dublu de valoare** (``acca_double``): 2 selecții, cotă totală 1.60–1.80, EV > 0 — înlocuiește „biletul sigur”
  ca bilet de joc (cel sigur rămâne doar informativ, miză 0).
* **Loterie** (``acca_<T>``, variant ``loterie``, T ∈ 50/100/500/1000/2000): doar selecții cu edge pozitiv la cote
  Superbet, max. 3 selecții sub 1.35, bilete cât mai scurte, miză fixă 0.10–0.25u; pentru fiecare: variante sistem.
* Pentru ORICE bilet: variante sistem Superbet (n−1/n, n−2/n, n−3/n) cu tabel de câștig la 0/1/2 ratări și EV.
"""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import date
from itertools import combinations
from typing import Any, Dict, List, Optional, Sequence, Tuple

from betpredict.builder.pool import Cand
from betpredict.builder.system import system_variants

VALUE_KIND, DOUBLE_KIND = "acca_value", "acca_double"
LOTTERY_VARIANT = "loterie"
VALUE_RULES = {"legs": (2, 4), "odds": (1.50, 2.50), "min_edge": 0.04}
KELLY_TICKET, KELLY_SINGLE = 1 / 8, 1 / 4
TICKET_CAP_U, DAY_CAP_U = 1.0, 5.0
DOUBLE_BAND = (1.60, 1.80)
LOTTERY = {  # țintă: (n_min, n_max, cote/selecție, miză fixă u)
    50: (3, 6, (1.30, 4.0), 0.25),
    100: (4, 7, (1.30, 4.0), 0.25),
    500: (5, 9, (1.30, 4.0), 0.20),
    1000: (6, 10, (1.30, 4.0), 0.15),
    2000: (6, 11, (1.30, 4.0), 0.10),
}
LOW_ODDS, MAX_LOW_LEGS = 1.35, 3


def p_prudent(c: Cand) -> float:
    pm = c.p_market if (c.p_market is not None and 0 < c.p_market < 1) else min(0.97, (1 / c.odds) / 1.05)
    return 0.7 * c.p + 0.3 * pm


def edge(c: Cand) -> float:
    return p_prudent(c) * c.odds - 1


def kelly_units(p: float, odds: float, fraction: float, cap: float) -> float:
    if odds <= 1 or p * odds <= 1:
        return 0.0
    return round(min(cap, fraction * (p * odds - 1) / (odds - 1) * 100), 2)


def ticket_stats(legs: Sequence[Cand]) -> Tuple[float, float, float]:
    total = math.prod(c.odds for c in legs)
    p = math.prod(p_prudent(c) for c in legs)
    return total, p, p * total - 1


def system_notes(legs: Sequence[Cand], stake: float) -> List[Dict[str, Any]]:
    return system_variants([c.odds for c in legs], [p_prudent(c) for c in legs], stake if stake > 0 else 1.0)


def _one_per_match(cands: Sequence[Cand], key) -> List[Cand]:
    best: Dict[int, Cand] = {}
    for c in cands:
        if c.match_id not in best or key(c) > key(best[c.match_id]):
            best[c.match_id] = c
    return sorted(best.values(), key=key, reverse=True)


def value_candidates(pool: Sequence[Cand]) -> List[Cand]:
    lo, hi = VALUE_RULES["odds"]
    return _one_per_match([c for c in pool if c.healthy and lo <= c.odds <= hi and edge(c) >= VALUE_RULES["min_edge"]], edge)


def build_value_tickets(pool: Sequence[Cand], sel_used: Dict[int, int], max_uses: int = 2, max_tickets: int = 3) -> List[List[Cand]]:
    """Bilete 4 → 3 → 2 selecții din cele mai bune edge-uri (Superbet preferat), ligi diferite, fără reutilizare excesivă."""
    cands = [c for c in value_candidates(pool) if sel_used.get(c.prediction_id, 0) < max_uses]
    cands.sort(key=lambda c: (c.odds_source == "superbet", edge(c)), reverse=True)
    out: List[List[Cand]] = []
    used = dict(sel_used)
    for n in (2, 3, 4):
        avail = [c for c in cands if used.get(c.prediction_id, 0) < max_uses]
        legs: List[Cand] = []
        leagues: Dict[Any, int] = {}
        for c in avail:
            if leagues.get(c.league_id, 0) >= 1:
                continue
            legs.append(c)
            leagues[c.league_id] = leagues.get(c.league_id, 0) + 1
            if len(legs) == n:
                break
        if len(legs) == n:
            out.append(legs)
            for c in legs:
                used[c.prediction_id] = used.get(c.prediction_id, 0) + 1
        if len(out) >= max_tickets:
            break
    return out


def build_value_double(pool: Sequence[Cand], sel_used: Dict[int, int], max_uses: int = 2) -> Optional[List[Cand]]:
    cands = _one_per_match([c for c in pool if c.healthy and 1.15 <= c.odds <= 1.6 and sel_used.get(c.prediction_id, 0) < max_uses
                            and edge(c) > 0], p_prudent)[:40]
    best, best_s = None, -1e9
    for a, b in combinations(cands, 2):
        if a.match_id == b.match_id:
            continue
        tot = a.odds * b.odds
        if not (DOUBLE_BAND[0] <= tot <= DOUBLE_BAND[1]):
            continue
        p = p_prudent(a) * p_prudent(b)
        ev = p * tot - 1
        if ev <= 0:
            continue
        s = math.log(p) + 2 * ev
        if s > best_s:
            best, best_s = [a, b], s
    return best


def build_lottery(pool: Sequence[Cand], target: int, sel_used: Dict[int, int], max_uses: int = 2) -> Optional[List[Cand]]:
    """Cele mai scurte bilete cu total ∈ [0.8T, 1.35T]: selecții cu edge > 0 la cote Superbet (jucabile),
    max. 3 selecții sub 1.35, max. 2 pe ligă; scor = Σ log p prudent + 2·Σ edge (bonus pentru mai puține selecții)."""
    n_min, n_max, (omin, omax), _ = LOTTERY[target]
    cands = _one_per_match([c for c in pool if c.healthy and c.odds_source == "superbet" and omin <= c.odds <= omax
                            and edge(c) > 0 and sel_used.get(c.prediction_id, 0) < max_uses], edge)[:60]
    lo, hi = math.log(target * 0.8), math.log(target * 1.35)
    best, best_s = None, -1e9
    # căutare în fascicul (beam) pe selecții sortate după log-cotă: rapidă și suficientă pentru ≤ 60 candidați
    beam: List[Tuple[float, float, List[Cand]]] = [(0.0, 0.0, [])]
    for _ in range(n_max):
        nxt = []
        for sc, lo_sum, legs in beam:
            ids = {c.match_id for c in legs}
            low = sum(1 for c in legs if c.odds < LOW_ODDS)
            lg: Dict[Any, int] = {}
            for c in legs:
                lg[c.league_id] = lg.get(c.league_id, 0) + 1
            for c in cands:
                if c.match_id in ids or (c.odds < LOW_ODDS and low >= MAX_LOW_LEGS) or lg.get(c.league_id, 0) >= 2:
                    continue
                if legs and c.prediction_id <= legs[-1].prediction_id:
                    continue  # combinații, nu permutări
                s2, l2 = sc + math.log(p_prudent(c)) + 2 * edge(c), lo_sum + math.log(c.odds)
                if l2 > hi:
                    continue
                nxt.append((s2, l2, legs + [c]))
        if not nxt:
            break
        for s2, l2, legs in nxt:
            if lo <= l2 <= hi and len(legs) >= n_min:
                adj = s2 - 0.15 * len(legs)  # preferă biletele mai scurte
                if adj > best_s:
                    best, best_s = legs, adj
        nxt.sort(key=lambda x: x[0] + 0.6 * x[1], reverse=True)
        beam = nxt[:300]
    return best


def insert_ticket(conn: sqlite3.Connection, kind: str, variant: str, target: float, legs: List[Cand], stake: float,
                  reasons: List[str], day: date, created: str, sel_used: Dict[int, int], extra: Optional[Dict[str, Any]] = None) -> int:
    total, p, ev = ticket_stats(legs)
    notes = {"reasons": reasons, "systems": system_notes(legs, stake), "rules": "v4", **(extra or {})}
    cur = conn.execute(
        """INSERT INTO ticket (kind, variant, created_by, target_odds, total_odds, p_ticket, ev, stake, status, created_at, notes, day)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (kind, variant, "robot", target, round(total, 2), round(p, 6), round(ev, 4), stake, "pending", created,
         json.dumps(notes, ensure_ascii=False), day.isoformat()))
    tid = cur.lastrowid
    for c in sorted(legs, key=lambda c: c.kickoff_utc):
        conn.execute("INSERT INTO ticket_leg (ticket_id, prediction_id, match_id, market, selection, odds, odds_source) VALUES (?,?,?,?,?,?,?)",
                     (tid, c.prediction_id, c.match_id, f"{c.market}|{c.line:g}", c.selection, c.odds, c.odds_source))
        sel_used[c.prediction_id] = sel_used.get(c.prediction_id, 0) + 1
    return tid


def build_v4_day(conn: sqlite3.Connection, day: date, pool: List[Cand], created: str, sel_used: Dict[int, int],
                 lottery_targets: Sequence[int] = tuple(LOTTERY), variant_suffix: str = "") -> Dict[str, Any]:
    rep: Dict[str, Any] = {"value": 0, "double": 0, "lottery": 0, "stake_value_u": 0.0}
    budget = DAY_CAP_U
    dbl = build_value_double(pool, sel_used)
    if dbl:
        total, p, ev = ticket_stats(dbl)
        stake = min(budget, kelly_units(p, total, KELLY_TICKET, TICKET_CAP_U))
        if stake > 0:
            insert_ticket(conn, DOUBLE_KIND, "dublu" + variant_suffix, round(total, 2), dbl, stake,
                          [f"Dublu de valoare: cotă {total:.2f}, șansă prudentă {p:.0%}, EV {ev:+.1%}",
                           f"Miză Kelly 1/8: {stake:g}u (plafon 1u/bilet, 5u/zi)"], day, created, sel_used)
            budget -= stake
            rep["double"] += 1
            rep["stake_value_u"] += stake
    for legs in build_value_tickets(pool, sel_used):
        total, p, ev = ticket_stats(legs)
        stake = min(budget, kelly_units(p, total, KELLY_TICKET, TICKET_CAP_U))
        if stake <= 0:
            continue
        insert_ticket(conn, VALUE_KIND, f"{len(legs)}_selectii" + variant_suffix, round(total, 2), legs, stake,
                      [f"{len(legs)} selecții de valoare (edge ≥ 4%, cote 1.50–2.50, ligi diferite)",
                       f"Șansă prudentă {p:.1%} · EV {ev:+.1%} · miză Kelly 1/8 = {stake:g}u"], day, created, sel_used)
        budget -= stake
        rep["value"] += 1
        rep["stake_value_u"] += stake
        if budget <= 0.05:
            break
    for target in lottery_targets:
        legs = build_lottery(pool, target, sel_used)
        if not legs:
            continue
        total, p, ev = ticket_stats(legs)
        stake = LOTTERY[target][3]
        insert_ticket(conn, f"acca_{target}", LOTTERY_VARIANT + variant_suffix, target, legs, stake,
                      [f"Loterie ~{target}: {len(legs)} selecții cu edge pozitiv la cote Superbet, miză fixă {stake:g}u",
                       f"Șansă estimată {p:.3%} · EV {ev:+.0%} (varianță uriașă — doar miză mică)",
                       "Variantele sistem de mai jos plătesc și cu 1–2 ratări (miza se împarte pe combinații)"],
                      day, created, sel_used, {"lottery": True})
        rep["lottery"] += 1
    rep["stake_value_u"] = round(rep["stake_value_u"], 2)
    return rep
