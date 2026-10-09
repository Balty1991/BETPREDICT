"""Piețe, etichete RO și decontare pe scor (sursă unică pentru robot, bilete și settle)."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

OU_LINES = (0.5, 1.5, 2.5, 3.5, 4.5)

# (market, line, selection)
Selection = Tuple[str, float, str]


def all_selections() -> List[Selection]:
    out: List[Selection] = [("1x2", 0.0, s) for s in ("HOME", "DRAW", "AWAY")]
    out += [("double_chance", 0.0, s) for s in ("1X", "12", "X2")]
    out += [("draw_no_bet", 0.0, s) for s in ("HOME", "AWAY")]
    for ln in OU_LINES:
        out += [("over_under", ln, "OVER"), ("over_under", ln, "UNDER")]
    out += [("btts", 0.0, "YES"), ("btts", 0.0, "NO")]
    return out


def market_key(market: str, line: float = 0.0) -> str:
    return market if not line else f"{market}_{line:g}"


def label_ro(market: str, line: float, sel: str) -> str:
    if market == "1x2":
        return {"HOME": "1", "DRAW": "X", "AWAY": "2"}[sel]
    if market == "double_chance":
        return sel
    if market == "draw_no_bet":
        return "DNB 1" if sel == "HOME" else "DNB 2"
    if market == "over_under":
        return f"{'Peste' if sel == 'OVER' else 'Sub'} {line:g}"
    if market == "btts":
        return "GG" if sel == "YES" else "NG"
    return f"{market} {sel}"


def market_name_ro(key: str) -> str:
    if key.startswith("over_under_"):
        return f"Peste/Sub {key.split('_')[-1]}"
    return {"1x2": "Rezultat final", "double_chance": "Șansă dublă", "draw_no_bet": "Egal = pariu returnat",
            "btts": "Ambele marchează"}.get(key, key)


def probs_from_matrix(m: Sequence[Sequence[float]]) -> Dict[Selection, float]:
    home = draw = away = btts = 0.0
    totals = {ln: 0.0 for ln in OU_LINES}  # P(total > line)
    for h, row in enumerate(m):
        for a, p in enumerate(row):
            if h > a:
                home += p
            elif h == a:
                draw += p
            else:
                away += p
            if h > 0 and a > 0:
                btts += p
            for ln in OU_LINES:
                if h + a > ln:
                    totals[ln] += p
    out: Dict[Selection, float] = {
        ("1x2", 0.0, "HOME"): home, ("1x2", 0.0, "DRAW"): draw, ("1x2", 0.0, "AWAY"): away,
        ("double_chance", 0.0, "1X"): home + draw, ("double_chance", 0.0, "12"): home + away,
        ("double_chance", 0.0, "X2"): draw + away,
        ("btts", 0.0, "YES"): btts, ("btts", 0.0, "NO"): 1 - btts,
    }
    nd = max(1e-9, home + away)
    out[("draw_no_bet", 0.0, "HOME")] = home / nd
    out[("draw_no_bet", 0.0, "AWAY")] = away / nd
    for ln in OU_LINES:
        out[("over_under", ln, "OVER")] = totals[ln]
        out[("over_under", ln, "UNDER")] = 1 - totals[ln]
    return {k: min(1.0, max(0.0, v)) for k, v in out.items()}


def settle_selection(market: str, line: float, sel: str, hs: Optional[int], as_: Optional[int]) -> Optional[str]:
    """Rezultatul unei selecții pe scorul final (90 min). None = nu se poate deconta."""
    if hs is None or as_ is None:
        return None
    if market == "1x2":
        actual = "HOME" if hs > as_ else ("AWAY" if hs < as_ else "DRAW")
        return "won" if sel == actual else "lost"
    if market == "double_chance":
        actual = "1" if hs > as_ else ("2" if hs < as_ else "X")
        return "won" if actual in {"1X": "1X", "12": "12", "X2": "X2"}[sel] else "lost"
    if market == "draw_no_bet":
        if hs == as_:
            return "void"
        return "won" if (sel == "HOME") == (hs > as_) else "lost"
    if market == "over_under":
        total = hs + as_
        if abs(total - line) < 1e-9:
            return "void"  # linie întreagă: push
        over = total > line
        return "won" if (sel == "OVER") == over else "lost"
    if market == "btts":
        yes = hs > 0 and as_ > 0
        return "won" if (sel == "YES") == yes else "lost"
    return None


def profit_1u(result: Optional[str], odds: Optional[float]) -> Optional[float]:
    if result is None or not odds:
        return None
    return {"won": round(odds - 1, 4), "lost": -1.0, "void": 0.0,
            "half_won": round((odds - 1) / 2, 4), "half_lost": -0.5}.get(result)


def leg_factor(result: Optional[str], odds: float) -> Optional[float]:
    """Multiplicatorul unei selecții într-un acumulator decontat (void → 1.00)."""
    return {"won": odds, "lost": 0.0, "void": 1.0, "half_won": (1 + odds) / 2, "half_lost": 0.5}.get(result or "")
