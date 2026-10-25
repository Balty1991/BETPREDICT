"""Poarta de etichetă (25.10.2026, aprobat de Alin): un bilet numit „100+ / 500+ / 1000+” are cota totală reală cel puțin
pragul. Altfel nu se creează (la construire) și nu se publică (după re-prețuirea Superbet la publicare)."""

from __future__ import annotations

import re
from typing import Optional

KIND_MIN = {"acca_100": 100.0, "acca_500": 500.0, "acca_1000": 1000.0, "acca_2000": 2000.0}
_PLUS = re.compile(r"(\d{3,4})\s*\+")


def label_min(kind: Optional[str], label: Optional[str] = None) -> Optional[float]:
    """Pragul promis de numele biletului: felul (acca_100…) sau o etichetă de forma „Stil 500+”."""
    if kind in KIND_MIN:
        return KIND_MIN[kind]
    m = _PLUS.search(label or "")
    return float(m.group(1)) if m and int(m.group(1)) >= 100 else None


def below_label(kind: Optional[str], total: Optional[float], label: Optional[str] = None) -> bool:
    lim = label_min(kind, label)
    return lim is not None and (total or 0.0) + 1e-9 < lim
