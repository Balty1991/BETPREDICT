"""Lista recomandată se verifică singură: pentru fiecare piață recomandată, cum a ieșit pe Superbet în ultimele zile
(cotele de închidere salvate în ``sb_offer_close`` și rezultatele meciurilor). O piață care pierde clar pe destule selecții
iese automat de pe bilete până își revine; cifrele apar și în Predicții → Top."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from betpredict.timeutil import canon_utc

DAYS = 30
MIN_N = 150          # sub atât nu decidem nimic
DROP_ROI = -0.06     # sub −6% pe cel puțin MIN_N selecții piața iese de pe bilete
COMBO = "COMBO"      # Peste 0.5 goluri + peste 7.5 cornere


def _ou(text: str, total: int) -> Optional[bool]:
    m = re.fullmatch(r"(Peste|Sub) (\d+\.5)", text.strip())
    if not m:
        return None
    return total > float(m.group(2)) if m.group(1) == "Peste" else total < float(m.group(2))


def settle(mn: str, oc: str, fh: int, fa: int, hh: Optional[int], ha: Optional[int],
           ch: Optional[int] = None, ca: Optional[int] = None) -> Optional[bool]:
    """Rezultatul unei selecții recomandate din scor (final, pauză) și cornere; None dacă nu se poate decide."""
    if mn == "Final":
        r = "1" if fh > fa else "X" if fh == fa else "2"
        return r == oc if oc in ("1", "X", "2") else None
    if mn == "Ambele echipe marchează (GG)":
        return (fh > 0 and fa > 0) if oc == "Da" else (not (fh > 0 and fa > 0)) if oc == "Nu" else None
    if mn == "Total goluri":
        return _ou(oc, fh + fa)
    if hh is None or ha is None:
        return None
    if mn == "Prima repriză - Total goluri":
        return _ou(oc, hh + ha)
    if mn == "A doua repriză - Interval goluri":
        m = re.fullmatch(r"(\d+)-(\d+)", oc.strip())
        h2 = fh + fa - hh - ha
        return int(m.group(1)) <= h2 <= int(m.group(2)) if m else None
    if re.sub(r"\s+", " ", mn.lower().replace(",", ".")).startswith("peste 0.5 goluri; peste 7.5 cornere"):
        if ch is None or ca is None:
            return None
        return fh + fa > 0 and ch + ca > 7.5
    return None


def market_stats(conn: sqlite3.Connection, rec: Dict[Tuple[str, str], tuple], combo_window: Tuple[float, float],
                 now: Optional[datetime] = None, days: int = DAYS) -> Dict[Any, Dict[str, Any]]:
    """Pe fiecare piață recomandată (în fereastra ei de cote): selecții, intrate, ROI la cota de închidere Superbet."""
    now = now or datetime.now(timezone.utc)
    since = canon_utc((now - timedelta(days=days)).isoformat())
    out: Dict[Any, Dict[str, Any]] = {}
    try:
        rows = conn.execute(
            """SELECT s.market_name, s.outcome, MAX(s.price), m.ft_home, m.ft_away, m.ht_home, m.ht_away, m.corners_home, m.corners_away
               FROM sb_offer_close s JOIN match m ON m.id=s.match_id
               WHERE m.status='finished' AND m.ft_home IS NOT NULL AND m.kickoff_utc>=?
               GROUP BY s.match_id, s.market_name, s.outcome""", (since,)).fetchall()
    except sqlite3.OperationalError:
        return out
    for mn, oc, price, fh, fa, hh, ha, ch, ca in rows:
        if not price or price <= 1:
            continue
        spec = rec.get((mn, oc))
        if spec:
            key, lo, hi = (mn, oc), spec[2], spec[3]
        elif re.sub(r"\s+", " ", (mn or "").lower().replace(",", ".")).startswith("peste 0.5 goluri; peste 7.5 cornere"):
            key, (lo, hi) = COMBO, combo_window
        else:
            continue
        if not lo <= price <= hi:
            continue
        won = settle(mn, oc, fh, fa, hh, ha, ch, ca)
        if won is None:
            continue
        b = out.setdefault(key, {"n": 0, "won": 0, "ret": 0.0})
        b["n"] += 1
        b["won"] += won
        b["ret"] += price if won else 0.0
    for b in out.values():
        b["roi"] = round(b["ret"] / b["n"] - 1, 4) if b["n"] else None
        b["hit"] = round(b["won"] / b["n"], 4) if b["n"] else None
        b["off"] = b["n"] >= MIN_N and (b["roi"] or 0) < DROP_ROI
        b["days"] = days
    return out
