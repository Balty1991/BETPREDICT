"""Modelul de cornere (Stil Supersocial).

Total cornere ~ Binomial Negativ (r = 60) cu media = media ligii + 0.2 × (estimarea pe echipe − media ligii).
Estimarea pe echipe: cornere obținute/cedate (ultimele 10 meciuri, micșorate spre media ligii cu 4 meciuri fictive),
raportate la media ligii pe gazde/oaspeți. Parametrii (0.2, r = 60) aleși pe football-data 2021–2026 (34k meciuri,
walk-forward 60/40): test log-loss 2.6155 vs 2.6193 doar media ligii vs 2.6210 Poisson; calibrare O6.5 test 83.0% prezis /
83.0% real, O7.5 73.3% / 73.2%, p>0.8 la O6.5: 84.4% / 84.5%. Cornerele în prima repriză: aceeași formă cu media × cota R1
(măsurată din datele BSD când există ≥ 200 meciuri; altfel 0.46)."""

from __future__ import annotations

import math
import sqlite3
from collections import defaultdict, deque
from typing import Dict, Optional, Tuple

B, R_DISP, K_LAST, SHRINK = 0.2, 60.0, 10, 4.0
GLOBAL_MEAN, H1_DEFAULT = 9.8, 0.46


def nb_pmf(k: int, mean: float, r: float) -> float:
    p = r / (r + mean)
    return math.exp(math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1) + r * math.log(p) + k * math.log1p(-p))


def nb_cdf(k: int, mean: float, r: float) -> float:
    return sum(nb_pmf(i, mean, r) for i in range(0, k + 1)) if k >= 0 else 0.0


def p_between(lo: int, hi: Optional[int], mean: float, r: float) -> float:
    """P(lo ≤ X ≤ hi); hi=None → fără limită superioară."""
    up = 1.0 if hi is None else nb_cdf(hi, mean, r)
    return max(0.0, up - nb_cdf(lo - 1, mean, r))


class CornerModel:
    def __init__(self, conn: sqlite3.Connection):
        from betpredict.ingest.corners import ensure

        ensure(conn)
        self.tf: Dict[int, deque] = defaultdict(lambda: deque(maxlen=K_LAST))
        self.ta: Dict[int, deque] = defaultdict(lambda: deque(maxlen=K_LAST))
        self.lg: Dict[int, list] = defaultdict(list)
        ht = tot = 0
        for r in conn.execute("""SELECT league_id, home_id, away_id, corners_home, corners_away,
                                        corners_ht_home, corners_ht_away FROM match
                                 WHERE corners_home IS NOT NULL AND corners_away IS NOT NULL ORDER BY kickoff_utc"""):
            lid, h, a, ch, ca = r[0], r[1], r[2], r[3], r[4]
            self.tf[h].append(ch); self.ta[h].append(ca); self.tf[a].append(ca); self.ta[a].append(ch)
            self.lg[lid].append((ch, ca))
            if r[5] is not None and r[6] is not None:
                ht += r[5] + r[6]; tot += ch + ca
        n_ht = conn.execute("SELECT COUNT(*) FROM match WHERE corners_ht_home IS NOT NULL").fetchone()[0]
        self.h1_share = ht / tot if n_ht >= 200 and tot else H1_DEFAULT
        self.n_matches = sum(len(v) for v in self.lg.values())

    def mean(self, league_id: int, home_id: int, away_id: int) -> Tuple[Optional[float], str]:
        L = self.lg.get(league_id) or []
        if len(L) >= 20:
            lh = sum(x[0] for x in L[-300:]) / len(L[-300:]); la = sum(x[1] for x in L[-300:]) / len(L[-300:])
            src = "liga"
        else:
            lh, la, src = GLOBAL_MEAN * 0.53, GLOBAL_MEAN * 0.47, "global"
        lm = lh + la
        half = lm / 2
        if len(self.tf[home_id]) >= 3 and len(self.tf[away_id]) >= 3:
            sh = lambda q: (sum(q) + SHRINK * half) / (len(q) + SHRINK)  # noqa: E731
            mh = sh(self.tf[home_id]) * sh(self.ta[away_id]) / half * (lh / half)
            ma = sh(self.tf[away_id]) * sh(self.ta[home_id]) / half * (la / half)
            return lm + B * (mh + ma - lm), src + "+echipe"
        if src == "global":
            return None, "fără date"
        return lm, src

    def probs(self, mean: float) -> Dict[str, float]:
        m1, r1 = mean * self.h1_share, R_DISP * self.h1_share
        return {
            "C65": p_between(7, None, mean, R_DISP), "C75": p_between(8, None, mean, R_DISP),
            "C85": p_between(9, None, mean, R_DISP), "C95": p_between(10, None, mean, R_DISP),
            "H1C25": p_between(3, None, m1, r1), "H1C35": p_between(4, None, m1, r1),
            "BB_C65_U145": p_between(7, 14, mean, R_DISP), "BB_H1C25_U65": p_between(3, 6, m1, r1),
        }
