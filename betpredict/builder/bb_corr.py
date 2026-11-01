"""Preț de hârtie pentru Bet Builder: marginalele pieței × liftul empiric, comparat cu prețul Superbet.

Nu intră în bilete. Lifturile sunt din cercetarea pe combinații frecvente:
favorit câștigă și favoritul peste 1.5 ~1.66 (favoriți 40–55%), peste 2.5 și GG ~1.53,
sub 3.5 și GG Nu ~1.32, favorit și cornere ~0.90–0.97 (corelație negativă).
"""

from __future__ import annotations

from typing import Optional

LIFTS = {
    "fav_win_fav_o15": 1.66,
    "over25_gg": 1.53,
    "under35_gg_no": 1.32,
    "fav_win_corners": 0.94,
}


def joint_p(p_a: float, p_b: float, lift: float) -> float:
    """P(A și B) ≈ P(A) · P(B) · lift, tăiat la 0.99."""
    return min(0.99, max(0.0, p_a * p_b * lift))


def fair_odds(p_a: float, p_b: float, lift: float) -> Optional[float]:
    p = joint_p(p_a, p_b, lift)
    return round(1 / p, 2) if p > 0.01 else None


def log_vs_superbet(p_a: float, p_b: float, kind: str, sb_odds: Optional[float]) -> dict:
    lift = LIFTS[kind]
    p = joint_p(p_a, p_b, lift)
    fair = fair_odds(p_a, p_b, lift)
    gap = None if not sb_odds or not fair else round(sb_odds / fair - 1, 4)
    return {"kind": kind, "lift": lift, "p": round(p, 4), "fair_odds": fair, "sb_odds": sb_odds,
            "gap": gap, "paper": True}
