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
VALUE_RULES = {"legs": (2, 4), "odds": (1.30, 4.0), "min_edge": 0.02}
# Backtest (p onest, cote 1.30–4): prag 0% → ROI −19% (n=63) / −6.3% (n=114); 2% → n<30 / +2.5% ± 20 (n=40) — niciun prag
# profitabil robust out-of-sample ⇒ cel mult 1 bilet „cel mai bun” pe zi, miză Kelly mică (0 ⇒ informativ).
RISK_STAKE_U = 0.10
VALUE_MIN_TICKETS = 3  # Alin: cel puțin 3 bilete de jucat pe zi (risc asumat, EV realist afișat)
VALUE_MAX_TICKETS = 3  # Alin: mai multe bilete, risc asumat (EV realist afișat)
LOTTERY_MIN_EDGE = -0.05  # loteria: selecții cu prețul Superbet aproape de corect (EV onest ≥ −5%), informativă
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
    """Probabilitatea folosită la selecția și EV-ul biletelor = cea onestă (vezi ``Cand.p_honest``)."""
    return c.p_honest


def edge(c: Cand) -> float:
    return c.ev_honest  # −1 pentru prețuri suspecte (vezi ``Cand.price_suspect``)


def kelly_units(p: float, odds: float, fraction: float, cap: float) -> float:
    if odds <= 1 or p * odds <= 1:
        return 0.0
    return round(min(cap, fraction * (p * odds - 1) / (odds - 1) * 100), 2)


# Corecția de selecție pentru selecțiile alese pe „edge > 0” (cote 1.30–4): rata reală = 0.86 × p prudent.
# football-data walk-forward (DC lunar OOS + piața de închidere): k = 0.858 pe 21/22–23/24 (n=4,883), 0.855 pe 24/25–26/27 (n=9,488);
# jurnalul robotului 09–10.10 (cote Superbet): 0.872 (n=179). Bilete de 3/5/7/10 selecții pe test: prezis brut 10.3%/2.24%/0.49%/0.05%,
# cu corecție 6.5%/1.04%/0.17%/0.01%, real 6.1%/0.95%/0.19%/0.01%; ROI real −26…−38%.
LEG_SHRINK = 1.0  # înlocuit de p_honest (blend spre piață); păstrat pentru biletele vechi la afișare
TICKET_EV_CAP = 0.25  # EV afișat al unui bilet nu depășește +25%
LOTTERY_VALIDATED = False  # backtest-ul nu arată EV > 0 pentru loterii → informative


def p_ticket_leg(c: Cand) -> float:
    return min(0.97, LEG_SHRINK * p_prudent(c))


def ticket_stats(legs: Sequence[Cand], shrink: bool = False) -> Tuple[float, float, float]:
    total = math.prod(c.odds for c in legs)
    p = math.prod((p_ticket_leg(c) if shrink else p_prudent(c)) for c in legs)
    return total, p, min(TICKET_EV_CAP, p * total - 1)


def system_notes(legs: Sequence[Cand], stake: float, shrink: bool = False) -> List[Dict[str, Any]]:
    return system_variants([c.odds for c in legs], [(p_ticket_leg(c) if shrink else p_prudent(c)) for c in legs],
                           stake if stake > 0 else 1.0)


def _one_per_match(cands: Sequence[Cand], key) -> List[Cand]:
    best: Dict[int, Cand] = {}
    for c in cands:
        if c.match_id not in best or key(c) > key(best[c.match_id]):
            best[c.match_id] = c
    return sorted(best.values(), key=key, reverse=True)


def value_candidates(pool: Sequence[Cand]) -> List[Cand]:
    lo, hi = VALUE_RULES["odds"]
    return _one_per_match([c for c in pool if c.healthy and lo <= c.odds <= hi and edge(c) >= VALUE_RULES["min_edge"]], edge)


def build_value_tickets(pool: Sequence[Cand], sel_used: Dict[int, int], max_uses: int = 2, max_tickets: int = VALUE_MAX_TICKETS) -> List[List[Cand]]:
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


def _fallback_value(pool: Sequence[Cand], sel_used: Dict[int, int], have: List[List[Cand]], need: int) -> List[List[Cand]]:
    """Cele mai bune bilete disponibile (2–4 selecții, ligi diferite), chiar dacă edge-ul e ușor negativ.
    Întâi doar prețuri Superbet cu EV onest > −5%, apoi orice cotă sănătoasă (consensul pieței)."""
    seen = {frozenset(c.prediction_id for c in legs) for legs in have}
    used: Dict[int, int] = {}
    for legs in have:
        for c in legs:
            used[c.prediction_id] = used.get(c.prediction_id, 0) + 1
    out: List[List[Cand]] = []
    tiers = [
        [c for c in pool if c.healthy and c.odds_source == "superbet" and 1.30 <= c.odds <= 4.0 and edge(c) > LOTTERY_MIN_EDGE],
        [c for c in pool if c.healthy and 1.30 <= c.odds <= 4.0 and edge(c) > -0.10],
    ]
    for tier in tiers:
        cands = [c for c in _one_per_match(tier, edge) if sel_used.get(c.prediction_id, 0) < 2]
        for n in (2, 3, 4, 2, 3):
            if len(out) >= need:
                return out
            legs: List[Cand] = []
            for c in cands:
                if used.get(c.prediction_id, 0) >= 2 or any(x.league_id == c.league_id or x.match_id == c.match_id for x in legs):
                    continue
                legs.append(c)
                if len(legs) == n:
                    break
            key = frozenset(c.prediction_id for c in legs)
            if len(legs) == n and key not in seen:
                seen.add(key)
                out.append(legs)
                for c in legs:
                    used[c.prediction_id] = used.get(c.prediction_id, 0) + 1
    return out


DAY_PICK_ODDS, DAY_PICK_LEGS, DAY_PICK_LEG_P, DAY_PICK_MIN_EDGE = (4.0, 6.5), (4, 6), 0.70, -0.02


from betpredict.selflearn import tuned as _tuned  # noqa: E402  (auto-tuning zilnic)


def build_balanced(pool: Sequence[Cand], sel_used: Dict[int, int], have: List[List[Cand]]) -> Optional[List[Cand]]:
    """Trepte: EV/selecție ≥ −2% (expunere ≤2) → ≥ −5% (marja casei) → ≥ −5% cu expunere ≤3. EV afișat onest, miză mică."""
    for thr, cap in ((DAY_PICK_MIN_EDGE, 2), (-0.05, 2), (-0.05, 3)):
        r = _build_balanced(pool, sel_used, have, thr, cap)
        if r:
            return r
    return None


def _build_balanced(pool: Sequence[Cand], sel_used: Dict[int, int], have: List[List[Cand]], min_edge: float, cap: int = 2) -> Optional[List[Cand]]:
    """„Biletul zilei ~5”: 4–6 selecții, fiecare cu șansă realistă ≥ 70% și EV realist ≥ −2%, ligi/meciuri diferite,
    cotă totală 4–6.5 (țintă 5, șansă totală ~20%). Fiecare selecție în max. 2 bilete active."""
    seen = {frozenset(c.prediction_id for c in legs) for legs in have}
    cands = [c for c in _one_per_match([c for c in pool if c.healthy and 1.15 <= c.odds <= 1.60 and p_prudent(c) >= _tuned("biletul_zilei", "leg_p", DAY_PICK_LEG_P)
                                        and edge(c) >= min_edge and sel_used.get(c.prediction_id, 0) < cap], edge)]
    cands.sort(key=lambda c: (c.odds_source == "superbet", edge(c), p_prudent(c)), reverse=True)
    import itertools
    top = list({c.prediction_id: c for c in cands[:12] + sorted(cands, key=lambda c: c.odds, reverse=True)[:10]}.values())  # cele mai bune 18 după EV: căutăm combinația 4–6 cu cota totală în fereastra ~5
    best, best_score = None, -9.0
    for n in range(DAY_PICK_LEGS[0], DAY_PICK_LEGS[1] + 1):
        for legs in itertools.combinations(top, n):
            tot = math.prod(c.odds for c in legs)
            if not (DAY_PICK_ODDS[0] <= tot <= DAY_PICK_ODDS[1]) or len({c.league_id for c in legs}) < n:
                continue
            if frozenset(c.prediction_id for c in legs) in seen:
                continue
            total, p, ev = ticket_stats(list(legs))
            score = ev - abs(total - 5.0) * 0.01
            if score > best_score:
                best, best_score = sorted(legs, key=lambda c: c.kickoff_utc), score
    return best


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
    max. 3 selecții sub 1.35, o singură ligă o dată; scor = Σ log p prudent + 2·Σ edge (bonus pentru mai puține selecții)."""
    n_min, n_max, (omin, omax), _ = LOTTERY[target]
    cands = _one_per_match([c for c in pool if c.healthy and c.odds_source == "superbet" and omin <= c.odds <= omax
                            and edge(c) > LOTTERY_MIN_EDGE and sel_used.get(c.prediction_id, 0) < max_uses], edge)[:60]
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
                if c.match_id in ids or (c.odds < LOW_ODDS and low >= MAX_LOW_LEGS) or lg.get(c.league_id, 0) >= 1:
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
    lot = bool((extra or {}).get("lottery"))
    total, p, ev = ticket_stats(legs, shrink=lot)
    notes = {"reasons": reasons, "systems": system_notes(legs, stake, shrink=lot), "rules": "v4", **(extra or {})}
    notes["p_raw"] = round(math.prod(c.p for c in legs), 6)  # model brut (doar informativ)
    if lot:
        notes.update(informational=not LOTTERY_VALIDATED, label="Loterie · miză mică")
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


def ensure_day_pick(conn: sqlite3.Connection, day: date, pool: List[Cand], created: str, sel_used: Dict[int, int]) -> int:
    """Adaugă „Biletul zilei ~5” unei zile deja construite (fără să refacă celelalte bilete). Doar meciuri neîncepute (pool)."""
    if conn.execute("SELECT 1 FROM ticket WHERE day=? AND kind=? AND variant LIKE 'biletul_zilei%' AND status!='replaced'",
                    (day.isoformat(), VALUE_KIND)).fetchone():
        return 0
    legs = build_balanced(pool, sel_used, [])
    if not legs:
        return 0
    total, p, ev = ticket_stats(legs)
    stake = kelly_units(p, total, KELLY_TICKET, TICKET_CAP_U)
    info = stake <= 0
    if info:
        stake = RISK_STAKE_U
    insert_ticket(conn, VALUE_KIND, "biletul_zilei", round(total, 2), legs, stake,
                  [f"Biletul zilei ~5: {len(legs)} selecții, fiecare cu șansă realistă ≥ 70%, ligi diferite",
                   f"Șansă realistă {p:.1%} · EV realist {ev:+.1%} · miză {stake:g}u" + (" — EV ≤ 0, risc asumat" if info else "")],
                  day, created, sel_used, {"honest": True, "risk_acknowledged": True})
    return 1


PONT_KIND, PONT_VARIANT, PONT_ODDS = "acca_pont", "pontul_zilei", (1.40, 2.00)

# Poarta pe piață (audit 17.10.2026): o piață a robotului principal intră pe bilete (valoare, dublu, loterie, pont) doar
# dacă are ROI pozitiv pe predicțiile decontate cu cotă, pe banda ei de cotă, micșorat bayesian spre marja casei.
GATE_MIN_N, GATE_PRIOR_N, GATE_PRIOR_ROI = 40, 40.0, -0.05
MARKET_AVG_MARGIN = 1.05  # cota medie din piață ≈ 1 / (șansa fără marjă × 1.05)


def odds_band(o: float) -> str:
    return "lo" if o < 1.40 else ("mid" if o <= 2.00 else "hi")


def positive_markets(conn: sqlite3.Connection, since: Optional[str] = None) -> Dict[Tuple[str, str], Dict[str, float]]:
    from betpredict.robot import STATS_SINCE
    from betpredict.robot.markets import market_key

    agg: Dict[Tuple[str, str], List[float]] = {}
    for m, line, o, pr in conn.execute(
            """SELECT market, line, odds_shown, profit_1u FROM prediction WHERE result IN ('won','lost')
               AND profit_1u IS NOT NULL AND odds_shown IS NOT NULL AND day >= ?""", (since or STATS_SINCE,)):
        a = agg.setdefault((market_key(m, line or 0.0), odds_band(o)), [0, 0.0])
        a[0] += 1
        a[1] += pr
    out = {}
    for k, (n, s) in agg.items():
        shr = (s + GATE_PRIOR_N * GATE_PRIOR_ROI) / (n + GATE_PRIOR_N)
        if n >= GATE_MIN_N and shr > 0:
            out[k] = {"n": n, "roi": round(s / n, 4), "roi_shrunk": round(shr, 4)}
    return out


def gate_pool(conn: sqlite3.Connection, pool: Sequence[Cand]) -> List[Cand]:
    from betpredict.robot.markets import market_key

    ok = positive_markets(conn)
    return [c for c in pool if (market_key(c.market, c.line or 0.0), odds_band(c.odds)) in ok]


def beats_market(c: Cand) -> bool:
    """Prețul Superbet cel puțin cât media pieței (din șansa fără marjă). Fără date de piață: nu."""
    return c.p_market is not None and 0 < c.p_market < 1 and c.odds * c.p_market * MARKET_AVG_MARGIN >= 1.0


def build_pont(pool: Sequence[Cand], sel_used: Dict[int, int]) -> Optional[List[Cand]]:
    """Pontul zilei: 1 selecție cotă 1.40–2.00 SAU un dublu (2 ligi diferite) cu cota totală 1.40–2.00 — ce are șansa
    realistă mai mare, cu EV ≥ 0. Dacă nimic nu are EV ≥ 0, relaxăm la EV ≥ −3% (afișat onest)."""
    for min_ev in (0.0, -0.03, -0.05):
        ok = [c for c in pool if c.healthy and edge(c) >= min_ev and sel_used.get(c.prediction_id, 0) < 3 and beats_market(c)]
        cands: List[List[Cand]] = [[c] for c in ok if PONT_ODDS[0] <= c.odds <= PONT_ODDS[1]]
        low = sorted([c for c in _one_per_match(ok, edge) if 1.15 <= c.odds <= 1.45], key=p_prudent, reverse=True)[:25]
        for i, a in enumerate(low):
            for b in low[i + 1:]:
                if a.league_id != b.league_id and a.match_id != b.match_id and PONT_ODDS[0] <= a.odds * b.odds <= PONT_ODDS[1]:
                    cands.append([a, b])
        best, key = None, None
        for legs in cands:
            total, p, ev = ticket_stats(legs)
            if ev < min_ev:
                continue
            k = (round(p, 3), -len(legs), ev)  # șansa realistă decide; la egalitate preferăm simplul
            if key is None or k > key:
                best, key = legs, k
        if best:
            return sorted(best, key=lambda c: c.kickoff_utc)
    return None


def ensure_pont(conn: sqlite3.Connection, day: date, pool: List[Cand], created: str, sel_used: Dict[int, int]) -> int:
    """Un singur „Pontul zilei” pe zi (urmărit și decontat ca orice bilet; card separat în Statistici)."""
    if conn.execute("SELECT 1 FROM ticket WHERE day=? AND kind=? AND status!='replaced'", (day.isoformat(), PONT_KIND)).fetchone():
        return 0
    legs = build_pont(gate_pool(conn, pool), sel_used)
    if not legs:
        # nicio piață a robotului principal nu e pe plus: pontul vine din piețele Stil cu ROI pozitiv
        from betpredict.experimental.supersocial import ensure_pont_stil

        return ensure_pont_stil(conn, day, PONT_KIND, PONT_VARIANT, PONT_ODDS)
    total, p, ev = ticket_stats(legs)
    stake = 1.0 if ev >= 0 else RISK_STAKE_U
    insert_ticket(conn, PONT_KIND, PONT_VARIANT, round(total, 2), legs, stake,
                  [f"Pontul zilei: {'o selecție' if len(legs) == 1 else 'dublu, 2 ligi diferite'} · cotă {total:.2f}",
                   f"Șansă realistă {p:.1%} · EV realist {ev:+.1%} · miză {stake:g}u" + ("" if ev >= 0 else " — EV < 0, risc asumat")],
                  day, created, sel_used, {"honest": True, "pont": True})
    return 1


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
    best = build_value_tickets(pool, sel_used)
    bal = build_balanced(pool, sel_used, best)
    if bal:  # „Biletul zilei ~5”: 4–6 selecții sigure (≥70% fiecare), șansă totală ~20%
        best = [bal] + best
    if len(best) < VALUE_MIN_TICKETS:  # Alin: minim 3 bilete/zi — completăm cu cele mai bune selecții disponibile, etichetat onest
        best = best + _fallback_value(pool, sel_used, best, VALUE_MIN_TICKETS - len(best))
    for legs in best[:max(VALUE_MAX_TICKETS, VALUE_MIN_TICKETS) + (1 if bal else 0)]:
        total, p, ev = ticket_stats(legs)
        stake = min(budget, kelly_units(p, total, KELLY_TICKET, TICKET_CAP_U))
        info = stake <= 0
        if info:
            stake = RISK_STAKE_U  # risc asumat (Alin): miză minimă fixă chiar dacă Kelly = 0
        vname = "biletul_zilei" if bal is not None and legs is bal else ("cel_mai_bun" if not rep["value"] else f"{len(legs)}_selectii")
        insert_ticket(conn, VALUE_KIND, vname + variant_suffix, round(total, 2), legs, stake,
                      [f"Bilet de valoare: {len(legs)} selecții, ligi diferite, prețuri Superbet vs. piața fără marjă",
                       f"Șansă realistă {p:.1%} · EV realist {ev:+.1%} · miză Kelly 1/8 = {stake:g}u"
                       + (f" — EV realist ≤ 0: miză minimă {RISK_STAKE_U:g}u, risc asumat" if info else ""),
                       "Backtest: niciun prag de edge nu a fost profitabil robust out-of-sample — miză mică"],
                      day, created, sel_used, {"honest": True, "risk_acknowledged": True})
        budget -= stake
        rep["value"] += 1
        rep["stake_value_u"] += stake
    for target in lottery_targets:
        legs = build_lottery(pool, target, sel_used)
        if not legs:
            continue
        total, p, ev = ticket_stats(legs, shrink=True)
        stake = LOTTERY[target][3]
        insert_ticket(conn, f"acca_{target}", LOTTERY_VARIANT + variant_suffix, target, legs, stake,
                      [f"Loterie ~{target}: {len(legs)} selecții cu edge pozitiv la cote Superbet, miză fixă {stake:g}u",
                       f"Șansă realistă {p:.3%} (probabilități trase 90% spre piața fără marjă) · EV realist {ev:+.0%} — INFORMATIV, doar miză mică",
                       "Variantele sistem de mai jos plătesc și cu 1–2 ratări (miza se împarte pe combinații)"],
                      day, created, sel_used, {"lottery": True})
        rep["lottery"] += 1
    rep["stake_value_u"] = round(rep["stake_value_u"], 2)
    return rep
