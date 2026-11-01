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


def _kind(market: str, selection: str, line: Optional[float]) -> str:
    sel = selection or ""
    mk = market or ""
    if mk == "1x2" and sel == "HOME" or sel in {"R:1x2:0:HOME"}:
        return "home_win"
    if mk == "1x2" and sel == "AWAY" or sel in {"R:1x2:0:AWAY"}:
        return "away_win"
    if sel in {"HO15"} or (mk in {"team_total_home"} and sel == "OVER" and line == 1.5):
        return "home_o15"
    if sel in {"AO15"} or (mk in {"team_total_away"} and sel == "OVER" and line == 1.5):
        return "away_o15"
    if (mk == "over_under" and sel == "OVER" and line == 2.5) or sel in {"O25"}:
        return "over25"
    if (mk == "over_under" and sel == "UNDER" and line == 3.5):
        return "under35"
    if (mk == "btts" and sel == "YES") or sel in {"GG", "GGO25"}:
        return "gg_yes"
    if mk == "btts" and sel == "NO":
        return "gg_no"
    if mk in {"corners"} or sel in {"C65", "C75", "C85", "C95"} or sel.startswith(("H1C", "BB_C", "BB_H1C")):
        return "corners"
    return f"{mk}:{sel}:{line}"


def pair_lift(a: dict, b: dict) -> Optional[float]:
    """Lift cunoscut pentru două selecții de pe același meci. None = corelație necunoscută."""
    ka = _kind(str(a.get("market") or ""), str(a.get("selection") or ""), a.get("line"))
    kb = _kind(str(b.get("market") or ""), str(b.get("selection") or ""), b.get("line"))
    pair = {ka, kb}
    if pair == {"home_win", "home_o15"} or pair == {"away_win", "away_o15"}:
        return LIFTS["fav_win_fav_o15"]
    if pair == {"over25", "gg_yes"}:
        return LIFTS["over25_gg"]
    if pair == {"under35", "gg_no"}:
        return LIFTS["under35_gg_no"]
    if "corners" in pair and pair & {"home_win", "away_win"}:
        return LIFTS["fav_win_corners"]
    return None


def correlated_chance(legs: list) -> dict:
    """Șansa biletului. Selecțiile de pe meciuri diferite se înmulțesc. Pe același meci se folosește liftul,
    iar fără lift nu se mai pretinde independență (``unknown``)."""
    groups: dict = {}
    for leg in legs:
        groups.setdefault(leg.get("match_id"), []).append(leg)
    p = 1.0
    correlated = False
    unknown = False
    for group in groups.values():
        probs = []
        for leg in group:
            raw = leg.get("p")
            if raw is None:
                unknown = True
                continue
            probs.append(float(raw))
        if len(group) == 1:
            if probs:
                p *= probs[0]
            continue
        correlated = True
        if len(group) != 2 or len(probs) != 2:
            unknown = True
            continue
        lift = pair_lift(group[0], group[1])
        if lift is None:
            unknown = True
            continue
        p *= joint_p(probs[0], probs[1], lift)
    if unknown or not legs:
        return {"p": None, "correlated": correlated, "unknown": True}
    return {"p": round(min(0.99, p), 6), "correlated": correlated, "unknown": False}


def log_vs_superbet(p_a: float, p_b: float, kind: str, sb_odds: Optional[float]) -> dict:
    lift = LIFTS[kind]
    p = joint_p(p_a, p_b, lift)
    fair = fair_odds(p_a, p_b, lift)
    gap = None if not sb_odds or not fair else round(sb_odds / fair - 1, 4)
    return {"kind": kind, "lift": lift, "p": round(p, 4), "fair_odds": fair, "sb_odds": sb_odds,
            "gap": gap, "paper": True}
