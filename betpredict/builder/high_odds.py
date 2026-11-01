"""Bilete 50+/100+, Lung 20-30 și SuperBonus (hârtie).

Șansa și EV-ul sunt ale pieței fără marjă, plus SuperBonus pe profit. Modelul nu ordonează biletele.
O selecție pe meci. Cotele lungite față de deschidere nu intră.
"""

from __future__ import annotations

import hashlib
import math
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from betpredict.builder.pool import Cand
from betpredict.builder.v4tickets import p_prudent

# (n istoric, ROI) — micșorat spre −5%. Pragul de intrare este −2.5%.
PRIORS: Dict[str, Tuple[float, float]] = {
    "BB": (1373, 0.024),
    "R1R2": (400, 0.021),
    "H2G13": (400, 0.009),
    "H13x2": (400, -0.008),
    "R1O15": (400, -0.009),
    "GGO25": (400, -0.012),
    "YCU45": (250, -0.005),
    "YCU55": (250, -0.005),
}
AVOID = frozenset({"AO15", "H1O15", "H1C56", "H1C7P"})
PRIOR_N, PRIOR_ROI, MIN_SHRUNK = 80.0, -0.05, -0.025
DRIFT_MAX = 0.0  # cota s-a lungit față de deschidere


def shrunk_roi(roi: float, n: float, prior_n: float = PRIOR_N, prior_roi: float = PRIOR_ROI) -> float:
    return (roi * n + prior_roi * prior_n) / (n + prior_n)


def near_fair(key: str, live_n: Optional[float] = None, live_roi: Optional[float] = None) -> bool:
    """Piața e aproape de corect după micșorarea spre −5%. Piețele evitate nu intră niciodată."""
    if not key or key in AVOID or key.startswith(("HTFT", "CS")):
        return False
    prior = PRIORS.get("BB" if key.startswith("BB_") else key)
    if live_n is None or live_roi is None:
        if prior is None:
            return False
        n, roi = prior
    else:
        n, roi = float(live_n), float(live_roi)
    return shrunk_roi(roi, n) >= MIN_SHRUNK - 1e-12


def lengthened(c: Cand) -> bool:
    return c.drift is not None and c.drift > DRIFT_MAX


def leg_p(c: Cand) -> float:
    return p_prudent(c)


def _one(cands: Sequence[Cand]) -> List[Cand]:
    best: Dict[int, Cand] = {}
    for c in cands:
        cur = best.get(c.match_id)
        if cur is None or (leg_p(c), -c.odds) > (leg_p(cur), -cur.odds):
            best[c.match_id] = c
    return list(best.values())


def _window(target: float, short: bool) -> Tuple[float, float]:
    if target <= 50:
        return 50.0, 99.999
    if target <= 100:
        return 100.0, 180.0
    return float(target), float(target) * (1.45 if short else 2.5)


def build_short(pool: Sequence[Cand], target: int) -> Optional[List[Cand]]:
    """4–5 selecții pentru 50+, 4–6 pentru 100+, cote 2.00–2.90 (niciodată peste 3.50)."""
    n_min, n_max = (4, 5) if target <= 50 else (4, 6)
    lo, hi = _window(target, True)
    primary = _one([c for c in pool if c.healthy and not c.price_suspect and not lengthened(c)
                    and c.odds_source == "superbet" and 2.0 <= c.odds <= 2.9])
    extra = []
    if len(primary) < n_min:
        have = {c.match_id for c in primary}
        extra = _one([c for c in pool if c.match_id not in have and c.healthy and not lengthened(c)
                      and c.odds_source == "superbet" and 1.70 <= c.odds < 2.0])[:2]
    cands = sorted(primary + extra, key=leg_p, reverse=True)[:14]
    cands.sort(key=lambda c: c.prediction_id)
    if len(cands) < n_min:
        return None
    best: Optional[Tuple[float, int, float, List[Cand]]] = None
    from itertools import combinations
    for n in range(n_min, min(n_max, len(cands)) + 1):
        for combo in combinations(cands, n):
            if len({c.match_id for c in combo}) != n:
                continue
            if sum(1 for c in combo if c.odds < 2.0) > 2:
                continue
            odds = math.prod(c.odds for c in combo)
            if not lo <= odds <= hi or any(c.odds > 3.5 for c in combo):
                continue
            p = math.prod(leg_p(c) for c in combo)
            key = (p, -n, -abs(math.log(odds / target)))
            if best is None or key > best[:3]:
                best = (*key, list(combo))
    return None if best is None else best[3]


def build_lung(pool: Sequence[Cand], target: int) -> Optional[List[Cand]]:
    """20–30 dintre cele mai sigure selecții aproape corecte. Cota totală cel puțin ținta."""
    lo, hi = (50.0, 99.999) if target <= 50 else (float(target), float(target) * 4)
    cands = _one([c for c in pool if c.healthy and not lengthened(c) and c.odds_source == "superbet"
                  and 1.15 <= c.odds <= 1.70 and _near(c)])
    cands.sort(key=leg_p, reverse=True)
    if len(cands) < 20:
        return None
    best = None
    best_key = None
    for n in range(20, min(30, len(cands)) + 1):
        legs = cands[:n]
        odds = math.prod(c.odds for c in legs)
        if odds < lo:
            continue
        if target <= 50 and odds >= 100:
            continue
        if odds > hi:
            continue
        p = math.prod(leg_p(c) for c in legs)
        key = (round(p, 8), -n)
        if best_key is None or key > best_key:
            best, best_key = legs, key
    return best


def build_superbonus(pool: Sequence[Cand], target: int) -> Optional[List[Cand]]:
    """10–25 selecții aproape corecte, cotă pe selecție de preferință 1.35–1.60. Hârtie."""
    lo, hi = _window(target, False)
    if target >= 200:
        lo, hi = 200.0, 500.0
    cands = _one([c for c in pool if c.healthy and not lengthened(c) and c.odds_source == "superbet"
                  and 1.35 <= c.odds <= 1.60 and _near(c) and not _super_cota(c)])
    cands.sort(key=leg_p, reverse=True)
    cands = cands[:25]
    if len(cands) < 8:
        return None
    best = None
    best_key = None
    from itertools import combinations
    # prefixele cele mai sigure: nu căutăm toate combinațiile de 25
    for n in range(8, min(25, len(cands)) + 1):
        legs = cands[:n]
        odds = math.prod(c.odds for c in legs)
        if not lo <= odds <= hi:
            continue
        p = math.prod(leg_p(c) for c in legs)
        bonus = superbonus_pct(legs)
        ev = market_ev(p, odds, bonus)
        key = (ev, p, -n)
        if best_key is None or key > best_key:
            best, best_key = legs, key
    if best:
        return best
    # dacă prefixul nu nimerește banda, încearcă combinații scurte din primele 12
    top = cands[:12]
    for n in range(8, min(12, len(top)) + 1):
        for combo in combinations(top, n):
            odds = math.prod(c.odds for c in combo)
            if not lo <= odds <= hi:
                continue
            p = math.prod(leg_p(c) for c in combo)
            ev = market_ev(p, odds, superbonus_pct(combo))
            key = (ev, p, -n)
            if best_key is None or key > best_key:
                best, best_key = list(combo), key
    return best


def _near(c: Cand) -> bool:
    key = c.selection if c.market == "ss" else ""
    if c.market == "ss":
        return near_fair(key)
    # predicțiile normale: 1X2 / șansă dublă / goluri, nu piețele evitate
    if c.market in {"corners", "cards"}:
        return False
    return c.market in {"1x2", "double_chance", "draw_no_bet", "btts", "over_under"}


def _super_cota(c: Cand) -> bool:
    return c.market == "boost" and str(c.selection).startswith("Super Cota")


def superbonus_pct(legs: Sequence[Cand]) -> float:
    from betpredict.builder.calea100 import superbonus

    n = sum(1 for c in legs if c.odds >= 1.35 and not _super_cota(c))
    return superbonus(n)


def market_ev(p: float, total: float, bonus: float) -> float:
    from betpredict.builder.calea100 import ev_with_bonus

    return ev_with_bonus(p, total, bonus)


def weakest(legs: Sequence[Cand]) -> Cand:
    return min(legs, key=lambda c: (leg_p(c), -c.odds))


def safer_swap(legs: Sequence[Cand], pool: Sequence[Cand]) -> Optional[Dict[str, Any]]:
    """O selecție pe același meci cu șansă de piață mai mare, dacă biletul rămâne în joc."""
    weak = weakest(legs)
    others = [c for c in pool if c.match_id == weak.match_id and c.selection != weak.selection
              and not lengthened(c) and leg_p(c) > leg_p(weak) + 1e-6]
    if not others:
        return None
    alt = max(others, key=leg_p)
    return {"match_id": alt.match_id, "market": alt.market, "selection": alt.selection,
            "odds": alt.odds, "p": round(leg_p(alt), 4),
            "instead_of": weak.selection}


def ticket_view(legs: Sequence[Cand], pool: Sequence[Cand] = ()) -> Dict[str, Any]:
    total = math.prod(c.odds for c in legs)
    p = math.prod(leg_p(c) for c in legs)
    bonus = superbonus_pct(legs)
    ev = market_ev(p, total, bonus)
    weak = weakest(legs)
    breakeven = (1 / (1 + bonus) - 1) if bonus < 1 else None
    # ROI pe selecție care face biletul egal cu 0 după bonus: (1+b) * Π(1+r) = 1 aproximat prin r identic
    per_leg = (1 / (p * (1 + bonus))) ** (1 / len(legs)) - 1 if p > 0 and legs else None
    return {
        "total": round(total, 2), "p_market": round(p, 6), "ev": round(ev, 4), "superbonus": bonus,
        "one_in_n": int(round(1 / p)) if p > 0 else None,
        "breakeven_leg_roi": None if per_leg is None else round(per_leg, 4),
        "weakest": {"match_id": weak.match_id, "market": weak.market, "selection": weak.selection, "p": round(leg_p(weak), 4)},
        "safer_swap": safer_swap(legs, pool),
        "steam": [c.selection for c in legs if c.drift is not None and c.drift <= -0.02],
    }


def synth_id(match_id: int, key: str) -> int:
    h = int(hashlib.sha1(f"{match_id}|{key}".encode()).hexdigest()[:8], 16)
    return -1 - (h % 1_000_000_000)


def rows_to_cands(rows: Iterable[Dict[str, Any]]) -> List[Cand]:
    out = []
    for row in rows:
        odds = row.get("odds")
        if not odds or float(odds) <= 1 or row.get("est") and not str(row.get("key", "")).startswith("BB_"):
            continue
        key = str(row.get("key") or "")
        if not near_fair(key) and not row.get("allow"):
            continue
        if key in AVOID:
            continue
        odds_f = float(odds)
        p_m = min(0.97, (1.0 / odds_f) / 1.05)
        out.append(Cand(
            synth_id(int(row["match_id"]), key), int(row["match_id"]), row.get("league_id"), row.get("league"),
            row.get("kickoff_utc") or "", row.get("home"), row.get("away"), "ss", 0.0, key, odds_f,
            float(row.get("p") or p_m), float(row.get("p") or p_m) * odds_f - 1, "B", 50, True,
            p_market=p_m, odds_source="superbet",
            extra={"bb": key.startswith("BB_"), "source": "betbuilder" if key.startswith("BB_") else "supersocial"},
        ))
    return out


def load_extra(conn, day: date, now: Optional[datetime] = None) -> List[Cand]:
    """Supersocial + Bet Builder pentru ziua dată. Gol dacă tabelele lipsesc."""
    now = now or datetime.now(timezone.utc)
    try:
        from betpredict.experimental.supersocial import BB_KEYS, candidates
        from betpredict.timeutil import ro_day_bounds_utc

        lo, hi = ro_day_bounds_utc(day)
        rows = []
        for row in candidates(conn, now, horizon_h=36):
            kick = row.get("kickoff_utc") or ""
            if not (lo <= kick < hi):
                continue
            key = row.get("key") or ""
            row = dict(row)
            row["allow"] = key in BB_KEYS or near_fair(key)
            if row.get("est") and key not in BB_KEYS:
                continue
            rows.append(row)
        return rows_to_cands(rows)
    except Exception:  # noqa: BLE001
        return []


def notes_for(kind_label: str, legs: List[Cand], pool: Sequence[Cand], *, paper: bool, tier: str, recommended: bool) -> Dict[str, Any]:
    view = ticket_view(legs, pool)
    return {
        "lottery": tier != "superbonus", "paper": paper, "experimental": paper, "tier": tier,
        "recommended": recommended, "label": kind_label, "lung": tier == "lung",
        "superbonus_tier": tier == "superbonus", "market_ev": view["ev"], "superbonus": view["superbonus"],
        "one_in_n": view["one_in_n"], "p_market": view["p_market"], "breakeven_leg_roi": view["breakeven_leg_roi"],
        "weakest": view["weakest"], "safer_swap": view["safer_swap"], "steam": view["steam"],
        "leg_p": {f"{c.match_id}|{c.selection}": round(leg_p(c), 4) for c in legs},
        "reasons": [
            f"{kind_label}: șansă fără marjă {view['p_market']:.2%} (1 din {view['one_in_n']}).",
            f"EV de piață {view['ev']:+.1%} · SuperBonus {view['superbonus']:.0%}.",
            "Cel mai slab picior e marcat. Cotele lungite față de deschidere nu intră.",
        ],
    }


def build_day(conn, day: date, pool: Sequence[Cand], created: str, sel_used: Dict[int, int]) -> Dict[str, Any]:
    from betpredict.builder.v4tickets import insert_ticket

    wide = list(pool) + load_extra(conn, day)
    wide = [c for c in wide if not lengthened(c)]
    report: Dict[str, Any] = {}
    specs = [
        (50, "short", f"acca_50", "scurt", "Loterie 50+ · scurt", False, True, 0.25),
        (100, "short", f"acca_100", "scurt", "Loterie 100+ · scurt", False, True, 0.20),
        (50, "lung", f"acca_50", "lung_20_30", "Lung 20-30 · 50+", True, False, 0.10),
        (100, "lung", f"acca_100", "lung_20_30", "Lung 20-30 · 100+", True, False, 0.10),
        (50, "superbonus", "acca_superbonus", "superbonus", "SuperBonus · 50×", True, False, 0.10),
        (100, "superbonus", "acca_superbonus", "superbonus", "SuperBonus · 100×", True, False, 0.10),
        (200, "superbonus", "acca_superbonus", "superbonus", "SuperBonus · 200×", True, False, 0.05),
    ]
    for target, tier, kind, variant, label, paper, recommended, stake in specs:
        if tier == "short":
            legs = build_short(wide, target)
        elif tier == "lung":
            legs = build_lung([c for c in wide if _near(c) or (c.market == "ss" and near_fair(c.selection))], target)
        else:
            legs = build_superbonus(wide, target)
        report[f"{tier}_{target}"] = 0 if not legs else len(legs)
        if not legs:
            continue
        extra = notes_for(label, legs, wide, paper=paper, tier=tier, recommended=recommended)
        if tier == "superbonus":
            extra["lottery"] = False
            extra["stil"] = False
        insert_ticket(conn, kind, variant, target, legs, stake,
                      extra["reasons"], day, created, sel_used, extra)
    return report
