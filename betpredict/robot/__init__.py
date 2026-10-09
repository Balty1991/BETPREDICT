"""Robotul de analiză: Dixon-Coles cu decădere în timp + ELO + blend cu piața/BSD + calibrare."""

MODEL_VERSION = "robot-v1"
# Robotul 3.0 (pipeline-ul nou). Statisticile numără doar predicțiile lui, publicate de la această dată.
ROBOT_VERSION = "v3"
STATS_SINCE = "2026-10-09"

# Recomandare conservatoare (single): probabilitate calibrată mare, EV pozitiv, cotă mică, grad A/B.
REC_MIN_P = 0.60
REC_MIN_ODDS = 1.15
REC_MAX_ODDS = 2.20
REC_MIN_EV = 0.0
REC_GRADES = ("A", "B")


def is_recommended(p, odds, ev, grade, healthy=True) -> bool:
    """Predicție „recomandată”: p ≥ 60%, EV > 0, cotă 1.15–2.20, grad A/B, piață sănătoasă."""
    if p is None or odds is None or ev is None:
        return False
    return bool(healthy and grade in REC_GRADES and p >= REC_MIN_P and REC_MIN_ODDS <= odds <= REC_MAX_ODDS and ev > REC_MIN_EV)
