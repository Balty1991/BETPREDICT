"""Clasificarea cotelor față de fluierul de start.

O cotă intră în evaluarea premeci doar dacă timestampul observării este prezent,
se poate compara cu kickoff-ul și nu este după start. Lipsa timestampului este
„necunoscut”, nu premeci. Filtrul de plauzibilitate nu înlocuiește timestampul:
o cotă live poate arăta „normal” și totuși să fie capturată în meci.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def _parse(ts: Optional[str]) -> Optional[datetime]:
    if not ts or not str(ts).strip():
        return None
    raw = str(ts).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def odds_time_status(observed_at: Optional[str], kickoff_utc: Optional[str]) -> str:
    """``prematch`` dacă observarea e la sau înainte de start, ``live`` după, altfel ``unknown``."""
    obs, ko = _parse(observed_at), _parse(kickoff_utc)
    if obs is None or ko is None:
        return "unknown"
    return "prematch" if obs <= ko else "live"


def prematch_eval_ok(observed_at: Optional[str], kickoff_utc: Optional[str], plausible: bool) -> bool:
    """Eligibil pentru ROI/CLV premeci: timestamp dovedit premeci și filtru de plauzibilitate."""
    return plausible and odds_time_status(observed_at, kickoff_utc) == "prematch"
