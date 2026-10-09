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

from betpredict.builder import optimizer
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
    "sigur": "Bilet sigur",
}

# „Bilet sigur”: favoriți clari (cote 1.20–1.40, la nevoie 1.15–1.40), grad A/B, probabilitate maximă.
# Se publică mereu (dacă există selecții), chiar și cu EV ușor negativ — marcat clar în aplicație.
SAFE_KIND = "acca_safe"
SAFE_TARGETS = {
    2: {"n": (2, 5), "band": (0.9, 1.15)},
    3: {"n": (3, 7), "band": (0.9, 1.15)},
    5: {"n": (5, 10), "band": (0.9, 1.15)},
}
# (cote min, cote max, grad minim, p calibrat minim) — în ordinea preferinței
SAFE_LEVELS = ((1.20, 1.40, "B", 0.0), (1.15, 1.40, "B", 0.0), (1.15, 1.40, "C", 0.72))
SAFE_STAKE_CAP = 1.0
SAFE_STAKE_INFO = 0.1  # miză minimă de urmărire când EV ≤ 0 (doar informativ)


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


PER_SLOT = 3  # max. selecții care încep în aceeași oră (corelație de „slot”)


def _one_per_match(cands: List[Cand], score: Callable[[Cand], float], per_league: int = 2, limit: int = 120,
                   per_slot: int = PER_SLOT) -> List[Cand]:
    best: Dict[int, Cand] = {}
    for c in cands:
        if c.match_id not in best or score(c) > score(best[c.match_id]):
            best[c.match_id] = c
    by_league: Dict[Optional[int], int] = {}
    by_slot: Dict[str, int] = {}
    out = []
    for c in sorted(best.values(), key=score, reverse=True):
        lid = c.league_id
        if lid is not None and by_league.get(lid, 0) >= per_league:
            continue
        slot = (c.kickoff_utc or "")[:13]
        if slot and by_slot.get(slot, 0) >= per_slot:
            continue
        by_league[lid] = by_league.get(lid, 0) + 1
        by_slot[slot] = by_slot.get(slot, 0) + 1
        out.append(c)
        if len(out) >= limit:
            break
    return out


def build_variant(pool: List[Cand], target: int, variant: str, used: Dict[int, int],
                  sel_used: Optional[Dict[int, int]] = None) -> Optional[Tuple[List[Cand], List[str]]]:
    cfg = TARGETS[target]
    n_min, n_max = cfg["n"]
    omin, omax = cfg["odds"]
    lo, hi = math.log(target * 0.85), math.log(target * 1.25)
    min_rank = GRADE_RANK[cfg["min_grade"]]
    # EV pozitiv DUPĂ ajustarea spre piață + grad A/B + plafon pe selecțiile improbabile
    base = [c for c in pool if c.healthy and omin <= c.odds <= omax and GRADE_RANK.get(c.grade, 1) >= min_rank
            and c.ev_adj > 0 and c.p_adj >= cfg["min_leg_p"] and optimizer.leg_ok(c, target)]

    def overlap_pen(c: Cand) -> float:
        # meci deja folosit în alt bilet al zilei + aceeași selecție deja în bilete active − bonus cotă reală
        return 0.35 * used.get(c.match_id, 0) + optimizer.reuse_penalty(c, sel_used) - optimizer.leg_bonus(c)

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


def build_safe_variant(pool: List[Cand], target: int, used: Dict[int, int],
                       excluded: Sequence[str] = ()) -> Optional[Tuple[List[Cand], List[str]]]:
    """Cele mai probabile selecții la cote mici, cu total ≈ ``target``.

    Nu cere „piață sănătoasă” (aceea include pragul de EV minim) — doar piețe neexcluse la calibrare.
    Preferă grad A/B; dacă nu ajung, acceptă și C cu probabilitate calibrată ≥ 72% (marcat în motive)."""
    from betpredict.robot.markets import market_key

    cfg = SAFE_TARGETS[target]
    n_min, n_max = cfg["n"]
    lo, hi = math.log(target * cfg["band"][0]), math.log(target * cfg["band"][1])
    for omin, omax, min_grade, min_p in SAFE_LEVELS:
        base = [c for c in pool if omin <= c.odds <= omax and GRADE_RANK.get(c.grade, 1) >= GRADE_RANK[min_grade]
                and c.p >= min_p and market_key(c.market, c.line) not in excluded]
        cands = _one_per_match(base, lambda c: c.p, limit=80)
        if len(cands) < n_min:
            continue
        idx = knapsack(cands, [c.logp - 0.2 * used.get(c.match_id, 0) for c in cands], lo, hi, n_min, n_max)
        if idx is None:
            continue
        conf = "încredere mare/bună (A/B)" if min_grade == "B" else "încredere A/B/C cu șansă calibrată ≥ 72%"
        return [cands[i] for i in idx], [
            f"Favoriți clari: cote {omin:.2f}–{omax:.2f}, {conf}",
            "Se aleg selecțiile cu cea mai mare probabilitate calibrată (o selecție pe meci, max. 2 pe ligă)",
        ]
    return None


# ── Controlul expunerii: aceeași selecție (meci + pariu) apare în cel mult N bilete ale Robotului ──
MAX_TICKETS_PER_SELECTION = 2
MULTI_VARIANT = "multi_zi"
MULTI_VARIANTS = ("echilibrat", "valoare")


def exposure(conn: sqlite3.Connection) -> Dict[int, int]:
    """prediction_id → în câte bilete active (pending) ale Robotului apare deja."""
    out: Dict[int, int] = {}
    for r in conn.execute(
        """SELECT tl.prediction_id, COUNT(DISTINCT t.id) FROM ticket_leg tl JOIN ticket t ON t.id = tl.ticket_id
           WHERE t.status = 'pending' AND t.kind LIKE 'acca_%' AND t.created_by = 'robot' AND tl.prediction_id IS NOT NULL
           GROUP BY tl.prediction_id"""
    ):
        out[r[0]] = r[1]
    return out


def _available(pool: List[Cand], sel_used: Dict[int, int], cap: Optional[int] = None) -> List[Cand]:
    cap = cap or min(MAX_TICKETS_PER_SELECTION, int(optimizer.strategy().get("max_uses_per_selection", MAX_TICKETS_PER_SELECTION)))
    return [c for c in pool if sel_used.get(c.prediction_id, 0) < cap]


def _insert(conn: sqlite3.Connection, kind: str, variant: str, target: float, legs: List[Cand], p_t: float, ev_t: float,
            stake: float, notes: Dict[str, object], day: date, created: str, sel_used: Dict[int, int],
            used: Optional[Dict[int, int]] = None) -> int:
    cur = conn.execute(
        """INSERT INTO ticket (kind, variant, created_by, target_odds, total_odds, p_ticket, ev, stake,
           status, created_at, notes, day) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (kind, variant, "robot", target, round(math.prod(c.odds for c in legs), 2), round(p_t, 6), round(ev_t, 4), stake,
         "pending", created, json.dumps(notes, ensure_ascii=False), day.isoformat()),
    )
    tid = cur.lastrowid
    for c in legs:
        conn.execute(
            "INSERT INTO ticket_leg (ticket_id, prediction_id, match_id, market, selection, odds) VALUES (?,?,?,?,?,?)",
            (tid, c.prediction_id, c.match_id, f"{c.market}|{c.line:g}", c.selection, c.odds),
        )
        sel_used[c.prediction_id] = sel_used.get(c.prediction_id, 0) + 1
        if used is not None:
            used[c.match_id] = used.get(c.match_id, 0) + 1
    return tid


def build_safe_tickets(conn: sqlite3.Connection, day: date, pool: List[Cand], created: str,
                       sel_used: Optional[Dict[int, int]] = None) -> Dict[str, object]:
    from betpredict.robot.params import load_params  # doar citire (piețe excluse la calibrare)

    excluded = list(load_params(conn).get("excluded_markets") or [])
    sel_used = exposure(conn) if sel_used is None else sel_used
    used: Dict[int, int] = {}
    made, negative = 0, []
    for target in SAFE_TARGETS:
        res = build_safe_variant(_available(pool, sel_used), target, used, excluded)
        if not res:
            continue
        legs, reasons = res
        legs.sort(key=lambda c: c.kickoff_utc)
        total = math.prod(c.odds for c in legs)
        p_t = ticket_probability(legs, adjusted=True)
        ev_t = p_t * total - 1
        if ev_t > 0:
            stake = suggested_stake(p_t, total, SAFE_STAKE_CAP)
            reasons.append(f"Șansă prudentă ~{p_t * 100:.1f}% · EV {ev_t * 100:+.1f}% · miză sugerată {stake:g}u (¼ Kelly)")
        else:
            stake = SAFE_STAKE_INFO
            negative.append(target)
            reasons.append(f"Șansă prudentă ~{p_t * 100:.1f}% · EV {ev_t * 100:+.1f}% (negativ) — informativ, miză minimă {stake:g}u")
        reasons.append(f"{len(legs)} selecții din {len({c.league_id for c in legs})} ligi · fiecare selecție în max. {MAX_TICKETS_PER_SELECTION} bilete")
        _insert(conn, SAFE_KIND, "sigur", target, legs, p_t, ev_t, stake, {"reasons": reasons, "safe": True}, day, created, sel_used, used)
        made += 1
    return {"safe_tickets": made, "safe_negative_ev": negative}


MAX_MATCH_STAKE = 0.8  # miza totală (u) a biletelor de valoare ale unei rulări pe același meci


def _value_tickets(conn: sqlite3.Connection, pool: List[Cand], day: date, created: str, targets, variants,
                   sel_used: Dict[int, int], variant_name: Optional[str] = None, extra_reason: Optional[str] = None) -> Tuple[int, List[str]]:
    """Bilete de valoare (EV > 0) pe nivelurile cerute.

    1. fiecare nivel × variantă (în ordinea ponderilor învățate) se construiește cu filtrele învățate
       (``optimizer.leg_ok``) și penalizare pentru selecțiile deja folosite;
    2. probabilitatea/EV/varianța biletului vin din Monte Carlo cu corelație pe ligă și oră;
    3. portofoliul final e ales după EV/abatere, cu plafon de expunere pe selecție și pe meci."""
    used: Dict[int, int] = {}
    tmp_used = dict(sel_used)
    cands: List[Dict[str, object]] = []
    skipped: List[str] = []
    strat = optimizer.strategy()
    for target in targets:
        for variant in optimizer.variant_order(target, variants, strat):
            res = build_variant(_available(pool, tmp_used), target, variant, used, tmp_used)
            if not res:
                continue
            legs, reasons = res
            legs.sort(key=lambda c: c.kickoff_utc)
            e = optimizer.ticket_eval(legs, n_sims=6000, s=strat)
            p_t, ev_t, total = e["p"], e["ev"], e["odds"]
            if ev_t <= 0:
                skipped.append(f"{target}/{variant}")  # mai bine fără bilet decât unul cu EV negativ
                continue
            for c in legs:
                tmp_used[c.prediction_id] = tmp_used.get(c.prediction_id, 0) + 1
                used[c.match_id] = used.get(c.match_id, 0) + 1
            stake = suggested_stake(p_t, total, STAKE_CAP.get(target, 0.15))
            cands.append({"target": target, "variant": variant, "legs": legs, "reasons": reasons, "p": p_t, "ev": ev_t,
                          "sd": e["sd"], "stake": stake, "eval": e})
    chosen = optimizer.portfolio_select(cands, max_uses=_cap(), max_match_stake=MAX_MATCH_STAKE, s=strat)
    used = {}
    chosen_ids = {id(t) for t in chosen}
    for t in cands:
        if id(t) not in chosen_ids:
            skipped.append(f"{t['target']}/{t['variant']} (expunere)")
            continue
        legs, e, stake, target = t["legs"], t["eval"], t["stake"], t["target"]
        p_t, ev_t = e["p"], e["ev"]
        leagues = len({c.league_id for c in legs})
        days = sorted({c.kickoff_utc[:10] for c in legs})
        real = sum(1 for c in legs if optimizer.is_real_odds(c))
        reasons = list(t["reasons"]) + ([extra_reason] if extra_reason else []) + [
            f"{len(legs)} selecții din {leagues} ligi" + (f", {len(days)} zile" if len(days) > 1 else "")
            + (f" · {real}/{len(legs)} cu cote reale" if real < len(legs) else " · toate cu cote reale"),
            f"Șansă prudentă ~{p_t * 100:.2f}% (interval {e['p_lo'] * 100:.2f}–{e['p_hi'] * 100:.2f}%, corelații ligă/oră incluse)"
            f" · EV {ev_t * 100:+.1f}% · miză sugerată {stake:g}u (¼ Kelly)",
            f"Expunere: fiecare selecție apare în cel mult {_cap()} bilete; max. {MAX_MATCH_STAKE:g}u pe un meci"]
        notes: Dict[str, object] = {"reasons": reasons, "p_naive": round(e["p_naive"], 6), "p_lo": round(e["p_lo"], 6),
                                    "p_hi": round(e["p_hi"], 6), "sd": round(e["sd"], 3),
                                    "strategy_version": strat.get("version", 1),
                                    "legs_safety": [optimizer.safety(c.p, c.confidence, c.grade)["score"] for c in legs]}
        if variant_name:
            notes["strategy"] = t["variant"]
        _insert(conn, f"acca_{target}", variant_name or str(t["variant"]), target, legs, p_t, ev_t, stake, notes, day, created,
                sel_used, used)
    return len(chosen), skipped


def _cap() -> int:
    return min(MAX_TICKETS_PER_SELECTION, int(optimizer.strategy().get("max_uses_per_selection", MAX_TICKETS_PER_SELECTION)))


def _count(conn: sqlite3.Connection, day: date, where: str, args=()) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM ticket WHERE day=? AND kind LIKE 'acca_%' AND created_by='robot' AND {where}",
                        (day.isoformat(), *args)).fetchone()[0]


def _replace(conn: sqlite3.Connection, day: date, where: str = "1=1", args=()) -> int:
    ids = [r[0] for r in conn.execute(
        f"SELECT id FROM ticket WHERE day=? AND kind LIKE 'acca_%' AND created_by='robot' AND status='pending' AND {where}",
        (day.isoformat(), *args))]
    for i in ids:
        # biletele vechi rămân în jurnal, marcate ca înlocuite (nu se șterg)
        conn.execute("UPDATE ticket SET status='replaced' WHERE id=?", (i,))
    return len(ids)


def build_tickets(conn: sqlite3.Connection, day: date, now: Optional[datetime] = None,
                  targets=(50, 100, 500), replace: bool = False, sel_used: Optional[Dict[int, int]] = None) -> Dict[str, object]:
    """Biletele unei zile (o singură zi): „Bilet sigur” ~2/3/5 + bilete de valoare ~50/100/500."""
    main_where, main_args = "kind != ? AND COALESCE(variant,'') != ?", (SAFE_KIND, MULTI_VARIANT)
    existing, existing_safe = _count(conn, day, main_where, main_args), _count(conn, day, "kind = ?", (SAFE_KIND,))
    do_main = replace or not existing
    do_safe = replace or not existing_safe
    if not do_main and not do_safe:
        return {"skipped_existing": existing + existing_safe}
    with conn:
        if replace:
            _replace(conn, day, main_where, main_args)
            _replace(conn, day, "kind = ?", (SAFE_KIND,))
    sel_used = exposure(conn) if sel_used is None else sel_used
    pool = load_pool(conn, day, now)
    created = repo.now_iso()
    out: Dict[str, object] = {}
    made, skipped = 0, []
    with conn:
        if do_main:
            made, skipped = _value_tickets(conn, pool, day, created, targets, [v for v in VARIANTS if v != "sigur"], sel_used)
        if do_safe:
            out.update(build_safe_tickets(conn, day, pool, created, sel_used))
    if not do_main:
        out["skipped_existing"] = existing
    return {**out, "tickets": made, "pool": len(pool), "positive_ev_pool": sum(1 for c in pool if c.ev_adj > 0), "skipped_negative_ev": skipped}


def build_multi_day(conn: sqlite3.Connection, today: date, days: Sequence[date], now: Optional[datetime] = None,
                    replace: bool = False, sel_used: Optional[Dict[int, int]] = None, targets=(50, 100, 500)) -> Dict[str, object]:
    """Bilete de cotă mare pe tot orizontul (meciuri din mai multe zile), salvate pe ziua de azi."""
    where, args = "COALESCE(variant,'') = ?", (MULTI_VARIANT,)
    if _count(conn, today, where, args) and not replace:
        return {"skipped_existing": True}
    with conn:
        _replace(conn, today, where, args)
    sel_used = exposure(conn) if sel_used is None else sel_used
    pool: List[Cand] = []
    for d in days:
        pool.extend(load_pool(conn, d, now))
    span = f"{days[0].strftime('%d.%m')}–{days[-1].strftime('%d.%m')}" if days else ""
    with conn:
        made, skipped = _value_tickets(conn, pool, today, repo.now_iso(), targets, MULTI_VARIANTS, sel_used,
                                       variant_name=MULTI_VARIANT, extra_reason=f"Multi-zi: meciuri din {span}")
    return {"tickets": made, "pool": len(pool), "positive_ev_pool": sum(1 for c in pool if c.ev_adj > 0), "skipped_negative_ev": skipped}


def build_horizon(conn: sqlite3.Connection, today: date, days_ahead: int, now: Optional[datetime] = None,
                  rebuild_today: bool = False, refresh_future: bool = False) -> Dict[str, object]:
    """Azi (o dată pe zi), apoi fiecare zi viitoare din orizont, apoi biletele multi-zi.

    Expunerea e comună: o selecție apare în cel mult ``MAX_TICKETS_PER_SELECTION`` bilete active."""
    from datetime import timedelta

    future = [today + timedelta(days=i) for i in range(1, days_ahead + 1)]
    if refresh_future:  # biletele viitoare se refac la rularea zilnică (cote mai noi); cele de azi rămân
        with conn:
            for d in future:
                _replace(conn, d)
            _replace(conn, today, "COALESCE(variant,'') = ?", (MULTI_VARIANT,))
    report: Dict[str, object] = {"today": build_tickets(conn, today, now, replace=rebuild_today)}
    sel_used = exposure(conn)
    report["future"] = {d.isoformat(): build_tickets(conn, d, now, sel_used=sel_used) for d in future}
    report["multi_day"] = build_multi_day(conn, today, [today] + future, now, replace=rebuild_today, sel_used=sel_used)
    report["max_tickets_per_selection"] = MAX_TICKETS_PER_SELECTION
    return report
