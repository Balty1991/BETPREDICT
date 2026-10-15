"""Modelul de cartonașe (Stil Supersocial).

Cartonașe pe echipă ~ Poisson, cu media = media ligii (gazde/oaspeți) corectată de echipă: cartonașe primite și „provocate”
(primite de adversari) în ultimele 10 meciuri, micșorate spre media ligii cu 4 meciuri fictive, apoi doar 50% din abaterea
față de ligă (ca la cornere, echipele contează mai puțin decât pare). Laboratorul de piețe (47.960 meciuri football-data)
arată că „Peste 1.5” pe echipă intră cu ~2,5% mai des decât spune un Poisson; corecția TEAM_LIFT ține cont de asta."""

from __future__ import annotations

import math
import sqlite3
from collections import defaultdict, deque
from typing import Dict, Optional, Tuple

K_LAST, SHRINK, B = 10, 4.0, 0.5
GLOBAL_HOME, GLOBAL_AWAY = 1.9, 2.2
MIN_LEAGUE = 20
TEAM_LIFT = 1.02  # prudent: laboratorul dă +2,4% (gazde) și +2,5–3,8% (oaspeți) la Peste 1.5


def _tail(lam: float, k: int) -> float:
    """P(X > k), X ~ Poisson(lam)."""
    return 1.0 - sum(math.exp(-lam) * lam ** i / math.factorial(i) for i in range(k + 1))


class CardModel:
    def __init__(self, conn: sqlite3.Connection):
        from betpredict.ingest.cards import ensure

        ensure(conn)
        self.got: Dict[int, deque] = defaultdict(lambda: deque(maxlen=K_LAST))
        self.drawn: Dict[int, deque] = defaultdict(lambda: deque(maxlen=K_LAST))
        self.lg: Dict[int, list] = defaultdict(list)
        for lid, h, a, ch, ca in conn.execute("""SELECT league_id, home_id, away_id, cards_home, cards_away FROM match
                                                 WHERE cards_home IS NOT NULL AND cards_away IS NOT NULL ORDER BY kickoff_utc"""):
            self.got[h].append(ch); self.drawn[h].append(ca); self.got[a].append(ca); self.drawn[a].append(ch)
            self.lg[lid].append((ch, ca))
        self.n_matches = sum(len(v) for v in self.lg.values())

    def means(self, league_id: int, home_id: int, away_id: int) -> Tuple[Optional[float], Optional[float], str]:
        L = self.lg.get(league_id) or []
        if len(L) >= MIN_LEAGUE:
            L = L[-300:]
            lh, la, src = sum(x[0] for x in L) / len(L), sum(x[1] for x in L) / len(L), "liga"
        else:
            lh, la, src = GLOBAL_HOME, GLOBAL_AWAY, "global"
        half = (lh + la) / 2
        if len(self.got[home_id]) >= 3 and len(self.got[away_id]) >= 3:
            sh = lambda q: (sum(q) + SHRINK * half) / (len(q) + SHRINK)  # noqa: E731
            mh = sh(self.got[home_id]) * sh(self.drawn[away_id]) / half * (lh / half)
            ma = sh(self.got[away_id]) * sh(self.drawn[home_id]) / half * (la / half)
            return lh + B * (mh - lh), la + B * (ma - la), src + "+echipe"
        if src == "global":
            return None, None, src  # fără ligă și fără echipe: nu ghicim
        return lh, la, src

    @staticmethod
    def probs(mh: float, ma: float) -> Dict[str, float]:
        tot = mh + ma
        h15, a15 = min(0.99, _tail(mh, 1) * TEAM_LIFT), min(0.99, _tail(ma, 1) * TEAM_LIFT)
        return {"YC35": _tail(tot, 3), "YC45": _tail(tot, 4), "YCU45": 1 - _tail(tot, 4), "YCU55": 1 - _tail(tot, 5),
                "BOTH15": h15 * a15}
