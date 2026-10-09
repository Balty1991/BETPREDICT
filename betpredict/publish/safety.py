"""Indicatorul „Siguranță” (MIX, 0–100): combină șansa calibrată cu încrederea (fiabilitatea datelor).

Scorul e mare doar când AMBELE sunt mari: 70% din componenta minimă + 30% din media geometrică.
  p = 95%, încredere 50 → 56 (mediu);   p = 70%, încredere 80 → 71 (mare).
„Siguranță mare” (filtrul rapid) = șansă ≥ 60% ȘI încredere bună/mare (grad A/B).
"""

from __future__ import annotations

import math
from typing import Optional

GRADE_CONF = {"A": 82, "B": 70, "C": 60, "D": 45}
HIGH_MIN_P = 0.60


def safety_score(p: Optional[float], confidence: Optional[float], grade: Optional[str] = None) -> Optional[int]:
    if p is None:
        return None
    c = confidence if confidence is not None else GRADE_CONF.get(grade or "", 50)
    pc, cc = max(0.0, min(1.0, p)), max(0.0, min(1.0, c / 100.0))
    return int(round(100 * (0.7 * min(pc, cc) + 0.3 * math.sqrt(pc * cc))))


def is_high_safety(p: Optional[float], grade: Optional[str], odds: Optional[float] = 1.0) -> bool:
    """Șansă ≥ 60% ȘI încredere bună/mare ȘI cotă reală disponibilă."""
    return p is not None and odds is not None and p >= HIGH_MIN_P and grade in ("A", "B")
