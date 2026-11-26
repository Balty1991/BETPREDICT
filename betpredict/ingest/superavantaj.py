"""Decontarea SuperAvantaj pentru Piramida SuperAvantaj (varianta „psa”).

Pe Superbet, pariul pre-meci pe 1/2 dintr-o competiție eligibilă câștigă și dacă echipa conduce ORICÂND cu 2 goluri.
Scorul final nu arată asta, așa că pentru selecțiile 1X2 ale piramidei a căror echipă NU a câștigat, citim incidentele
meciului (BSD /events/{id}/incidents/, scorul după fiecare gol) ÎNAINTE de decontarea obișnuită și marcăm selecția câștigată
dacă echipa a avut la un moment dat un avans de 2 goluri."""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, Optional

VARIANTS = ("psa",)


def led_by_two(js: Any, home: bool) -> Optional[bool]:
    """True dacă echipa (gazde/oaspeți) a condus oricând cu 2+ goluri; None dacă incidentele lipsesc sau meciul nu are final."""
    inc = js.get("incidents") if isinstance(js, dict) else js
    if not isinstance(inc, list) or not inc:
        return None
    if not any(isinstance(i, dict) and i.get("type") == "period" and i.get("text") in ("FT", "AET", "AP") for i in inc):
        return None
    for i in inc:
        if not isinstance(i, dict) or i.get("type") != "goal":
            continue
        h, a = i.get("home_score"), i.get("away_score")
        if h is None or a is None:
            continue
        if (h - a if home else a - h) >= 2:
            return True
    return False


def settle(conn: sqlite3.Connection, client) -> Dict[str, int]:
    """Selecțiile 1X2 nedecontate ale piramidei SA, cu meciul terminat și echipa fără victorie: verificăm avansul de 2 goluri."""
    st = {"checked": 0, "saved": 0}
    if client is None:
        return st
    q = ",".join("?" * len(VARIANTS))
    rows = conn.execute(
        f"""SELECT tl.ticket_id, tl.match_id, tl.selection, m.ft_home, m.ft_away
            FROM ticket_leg tl JOIN ticket t ON t.id=tl.ticket_id JOIN match m ON m.id=tl.match_id
            WHERE t.kind='pyramid' AND t.variant IN ({q}) AND t.status='pending' AND tl.result IS NULL
              AND tl.market LIKE '1x2%' AND tl.selection IN ('HOME','AWAY')
              AND m.status='finished' AND m.ft_home IS NOT NULL""", VARIANTS).fetchall()
    for tid, mid, sel, fh, fa in rows:
        if (sel == "HOME" and fh > fa) or (sel == "AWAY" and fa > fh):
            continue  # a câștigat oricum: decontarea obișnuită
        try:
            js = client.get(f"events/{mid}/incidents/")
        except Exception:  # noqa: BLE001
            continue
        st["checked"] += 1
        if led_by_two(js, sel == "HOME"):
            with conn:
                conn.execute("UPDATE ticket_leg SET result='won' WHERE ticket_id=? AND match_id=? AND selection=?", (tid, mid, sel))
            st["saved"] += 1
    return st
