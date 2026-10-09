"""Bilete acumulator ~50 / ~100 / ~500+ cu variante, prin programare dinamică pe log-cote.

Obiectiv: maximizează Σ valoare_i (de ex. Σ log p_i) cu Σ log cotă_i ∈ [log 0.85T, log 1.25T],
n_min ≤ n ≤ n_max, max. 1 selecție pe meci, max. 2 pe ligă, cotă ≥ 1.15, doar piețe sănătoase.
"""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import date, datetime, timezone
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from betpredict.builder.pool import Cand, load_pool, ticket_probability
from betpredict.store import repo

RES = 0.005  # rezoluția pe log-cote (eroare max. ~n·RES/2)

# Doar selecții A/B cu EV > 0 după ajustarea spre piață; selecțiile cu probabilitate prudentă mică sunt plafonate.
TARGETS = {
    50: {"n": (4, 9), "odds": (1.15, 2.6), "min_grade": "B", "min_leg_p": 0.42},
    100: {"n": (5, 11), "odds": (1.15, 3.0), "min_grade": "B", "min_leg_p": 0.38},
    500: {"n": (7, 14), "odds": (1.15, 3.6), "min_grade": "B", "min_leg_p": 0.33},
}
# Miză sugerată (unități; 1u = 1% din bancă): Kelly fracționat (¼), plafonat pe nivel.
KELLY_FRACTION = 0.25
STAKE_CAP = {50: 0.5, 100: 0.3, 500: 0.15}
STAKE_MIN = 0.05
STAKE = STAKE_CAP  # compatibilitate


def suggested_stake(p: float, odds: float, cap: float, fraction: float = KELLY_FRACTION) -> float:
    """Kelly fracționat în unități (1u = 1% din bancă). 0 dacă EV ≤ 0."""
    if odds <= 1 or p <= 0:
        return 0.0
    ev = p * odds - 1
    if ev <= 0:
        return 0.0
    kelly = ev / (odds - 1)  # fracție din bancă
    return round(max(STAKE_MIN, min(cap, fraction * kelly * 100)), 2)
GRADE_RANK = {"A": 4, "B": 3, "C": 2, "D": 1}

VARIANTS = {
    "echilibrat": "Echilibrat",
    "valoare": "Valoare",
    "ancora_surpriza": "Ancoră + Surpriză",
    "goluri": "Goluri",
}


def knapsack(cands: Sequence[Cand], values: Sequence[float], lo: float, hi: float, n_min: int, n_max: int) -> Optional[List[int]]:
    """DP exact (discretizat) pe log-cote. Întoarce indicii aleși sau None."""
    if not cands:
        return None
    # banda se strânge cu eroarea maximă de discretizare, ca totalul real să rămână în bandă
    margin = n_max * RES / 2
    lo, hi = lo + margin, hi - margin
    if hi <= lo:
        return None
    W = int(math.ceil(hi / RES)) + 1
    weights = [max(1, int(round(c.logo / RES))) for c in cands]
    NEG = -1e18
    dp = np.full((n_max + 1, W), NEG)
    dp[0, 0] = 0.0
    take = np.zeros((len(cands), n_max + 1, W), dtype=bool)
    for i, (wi, vi) in enumerate(zip(weights, values)):
        if wi >= W:
            continue
        for k in range(min(i + 1, n_max), 0, -1):
            cand_vals = dp[k - 1, : W - wi] + vi
            cur = dp[k, wi:]
            better = cand_vals > cur
            if better.any():
                cur[better] = cand_vals[better]
                take[i, k, wi:][better] = True
    lo_w = int(math.floor(lo / RES))
    best = None
    for k in range(n_min, n_max + 1):
        seg = dp[k, lo_w:W]
        if seg.size == 0:
            continue
        j = int(np.argmax(seg))
        if seg[j] > NEG / 2 and (best is None or seg[j] > best[0]):
            best = (seg[j], k, lo_w + j)
    if not best:
        return None
    _, k, w = best
    chosen = []
    for i in range(len(cands) - 1, -1, -1):
        if k > 0 and take[i, k, w]:
            chosen.append(i)
            w -= weights[i]
            k -= 1
    return sorted(chosen) if k == 0 else None


def _one_per_match(cands: List[Cand], score: Callable[[Cand], float], per_league: int = 2, limit: int = 120) -> List[Cand]:
    best: Dict[int, Cand] = {}
    for c in cands:
        if c.match_id not in best or score(c) > score(best[c.match_id]):
            best[c.match_id] = c
    by_league: Dict[Optional[int], int] = {}
    out = []
    for c in sorted(best.values(), key=score, reverse=True):
        lid = c.league_id
        if lid is not None and by_league.get(lid, 0) >= per_league:
            continue
        by_league[lid] = by_league.get(lid, 0) + 1
        out.append(c)
        if len(out) >= limit:
            break
    return out


def build_variant(pool: List[Cand], target: int, variant: str, used: Dict[int, int]) -> Optional[Tuple[List[Cand], List[str]]]:
    cfg = TARGETS[target]
    n_min, n_max = cfg["n"]
    omin, omax = cfg["odds"]
    lo, hi = math.log(target * 0.85), math.log(target * 1.25)
    min_rank = GRADE_RANK[cfg["min_grade"]]
    # EV pozitiv DUPĂ ajustarea spre piață + grad A/B + plafon pe selecțiile improbabile
    base = [c for c in pool if c.healthy and omin <= c.odds <= omax and GRADE_RANK.get(c.grade, 1) >= min_rank
            and c.ev_adj > 0 and c.p_adj >= cfg["min_leg_p"]]

    def overlap_pen(c: Cand) -> float:
        return 0.35 * used.get(c.match_id, 0)

    reasons: List[str] = ["Doar selecții A/B cu EV > 0 după ajustarea probabilității spre piață (fără marjă)"]
    rec_bonus = lambda c: 0.15 if (c.p >= 0.6 and c.odds <= 2.2) else 0.0  # noqa: E731  — preferă „recomandatele”
    if variant == "echilibrat":
        sc = lambda c: c.logp_adj + 0.5 * c.ev_adj + rec_bonus(c) - overlap_pen(c)  # noqa: E731
        cands = _one_per_match(base, lambda c: c.logp_adj / max(0.05, c.logo) + 0.5 * c.ev_adj + rec_bonus(c))
        reasons.append("Probabilitate prudentă maximă la cota-țintă, cu bonus pentru valoare")
    elif variant == "valoare":
        sc = lambda c: c.logp_adj + 1.5 * c.ev_adj + rec_bonus(c) - overlap_pen(c)  # noqa: E731
        cands = _one_per_match(base, lambda c: c.ev_adj)
        reasons.append("Cele mai mari valori EV (ajustate), mai puține selecții")
    elif variant == "goluri":
        base = [c for c in base if c.market in ("over_under", "btts")]
        sc = lambda c: c.logp_adj + 0.5 * c.ev_adj + rec_bonus(c) - overlap_pen(c)  # noqa: E731
        cands = _one_per_match(base, lambda c: c.logp_adj / max(0.05, c.logo))
        reasons.append("Doar piețe de goluri (Peste/Sub, GG/NG)")
    elif variant == "ancora_surpriza":
        surprises = sorted([c for c in base if 2.3 <= c.odds <= 3.6],
                           key=lambda c: (c.ev_adj * c.p_adj) - overlap_pen(c), reverse=True)
        picked: List[Cand] = []
        for c in surprises:
            if c.match_id not in {x.match_id for x in picked}:
                picked.append(c)
            if len(picked) == (2 if target >= 100 else 1):
                break
        if not picked:
            return None
        rest_lo = lo - sum(c.logo for c in picked)
        rest_hi = hi - sum(c.logo for c in picked)
        anchors = [c for c in base if 1.15 <= c.odds <= 1.7 and c.p_adj >= 0.62 and c.match_id not in {x.match_id for x in picked}]
        cands = _one_per_match(anchors, lambda c: c.logp_adj / max(0.05, c.logo))
        idx = knapsack(cands, [c.logp_adj - overlap_pen(c) for c in cands], max(0.0, rest_lo), max(0.1, rest_hi),
                       max(1, n_min - len(picked)), max(1, n_max - len(picked)))
        if idx is None:
            return None
        legs = [cands[i] for i in idx] + picked
        return legs, reasons + ["Ancore (cote 1.15–1.70, p prudent ≥ 62%) + 1–2 selecții de valoare la cote 2.3–3.6"]
    else:
        raise ValueError(variant)
    idx = knapsack(cands, [sc(c) for c in cands], lo, hi, n_min, n_max)
    if idx is None:
        return None
    return [cands[i] for i in idx], reasons


def build_tickets(conn: sqlite3.Connection, day: date, now: Optional[datetime] = None,
                  targets=(50, 100, 500), replace: bool = False) -> Dict[str, int]:
    existing = conn.execute("SELECT COUNT(*) FROM ticket WHERE day=? AND kind LIKE 'acca_%' AND created_by='robot'",
                            (day.isoformat(),)).fetchone()[0]
    if existing and not replace:
        return {"skipped_existing": existing}
    if replace:
        with conn:
            ids = [r[0] for r in conn.execute("SELECT id FROM ticket WHERE day=? AND kind LIKE 'acca_%' AND created_by='robot' AND status='pending'", (day.isoformat(),))]
            for i in ids:
                # biletele vechi rămân în jurnal, marcate ca înlocuite (nu se șterg)
                conn.execute("UPDATE ticket SET status='replaced' WHERE id=?", (i,))
    pool = load_pool(conn, day, now)
    used: Dict[int, int] = {}
    made = 0
    skipped: List[str] = []
    created = repo.now_iso()
    with conn:
        for target in targets:
            for variant, vlabel in VARIANTS.items():
                res = build_variant(pool, target, variant, used)
                if not res:
                    continue
                legs, reasons = res
                legs.sort(key=lambda c: c.kickoff_utc)
                total = math.prod(c.odds for c in legs)
                p_t = ticket_probability(legs, adjusted=True)  # probabilitate prudentă (spre piață)
                ev_t = p_t * total - 1
                if ev_t <= 0:
                    skipped.append(f"{target}/{variant}")  # mai bine fără bilet decât unul cu EV negativ
                    continue
                stake = suggested_stake(p_t, total, STAKE_CAP.get(target, 0.15))
                leagues = len({c.league_id for c in legs})
                reasons = reasons + [f"{len(legs)} selecții din {leagues} ligi",
                                     f"Șansă prudentă ~{p_t * 100:.2f}% · EV {ev_t * 100:+.1f}% · miză sugerată {stake:g}u (¼ Kelly)"]
                cur = conn.execute(
                    """INSERT INTO ticket (kind, variant, created_by, target_odds, total_odds, p_ticket, ev, stake,
                       status, created_at, notes, day) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (f"acca_{target}", variant, "robot", target, round(total, 2), round(p_t, 6),
                     round(ev_t, 4), stake, "pending", created, json.dumps({"reasons": reasons}, ensure_ascii=False),
                     day.isoformat()),
                )
                tid = cur.lastrowid
                for c in legs:
                    conn.execute(
                        "INSERT INTO ticket_leg (ticket_id, prediction_id, match_id, market, selection, odds) VALUES (?,?,?,?,?,?)",
                        (tid, c.prediction_id, c.match_id, f"{c.market}|{c.line:g}", c.selection, c.odds),
                    )
                    used[c.match_id] = used.get(c.match_id, 0) + 1
                made += 1
    return {"tickets": made, "pool": len(pool), "positive_ev_pool": sum(1 for c in pool if c.ev_adj > 0), "skipped_negative_ev": skipped}
