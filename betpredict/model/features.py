"""Feature-uri pre-meci calculate SECVENȚIAL (fără scurgeri din viitor): pentru fiecare meci
starea se citește ÎNAINTE de a fi actualizată cu rezultatul lui.

Grupuri: ELO (cu avantaj de teren și multiplicator de marjă reglabile), forță ofensivă/defensivă
EWMA (generală și pe teren propriu/deplasare, relativ la media ligii), formă (puncte/meci 5/10,
pe teren), zile de odihnă și aglomerare, clasament din sezon (ppg, golaveraj, poziție),
H2H (ultimele 8 directe), profilul ligii (goluri, % 1/X, peste 2.5, GG) și acoperire (câte meciuri
știm despre echipă). xG, absențele și mișcarea cotelor nu există în istoric → se folosesc doar
live (contextul din engine), nu în antrenare."""

from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np

from betpredict.model.data import History


@dataclass
class EloParams:
    k: float = 20.0
    home_adv: float = 60.0
    margin: float = 0.5      # multiplicator: 1 + margin * ln(1 + |gd|) — 0 = fără marjă
    new_team_offset: float = -40.0  # echipă nouă = media ligii + offset (promovate / ligi mici)
    regress: float = 0.0     # regresie spre media ligii la pauza dintre sezoane (>60 zile)


FEATURE_NAMES: List[str] = [
    "elo_h", "elo_a", "elo_diff", "elo_exp",
    "att_h", "def_h", "att_a", "def_a", "atth_h", "defh_h", "atta_a", "defa_a",
    "ppm5_h", "ppm5_a", "ppm10_h", "ppm10_a", "ppmv_h", "ppmv_a",
    "gf5_h", "ga5_h", "gf5_a", "ga5_a", "o25r_h", "o25r_a", "bttsr_h", "bttsr_a",
    "cs_h", "cs_a", "fts_h", "fts_a",
    "rest_h", "rest_a", "load14_h", "load14_a",
    "ppg_h", "ppg_a", "gdpg_h", "gdpg_a", "pos_h", "pos_a", "played_h", "played_a", "season_prog",
    "h2h_n", "h2h_pts", "h2h_goals", "h2h_o25", "h2h_btts",
    "lg_hg", "lg_ag", "lg_hw", "lg_dr", "lg_o25", "lg_btts", "lg_n",
    "cov_h", "cov_a",
]


def _pts(gf: float, ga: float) -> int:
    return 3 if gf > ga else (1 if gf == ga else 0)


class FeatureState:
    def __init__(self, elo: Optional[EloParams] = None, ewma: float = 0.08):
        self.ep = elo or EloParams()
        self.alpha = ewma
        self.elo: Dict[int, float] = {}
        self.team_league: Dict[int, int] = {}
        self.league_elo_sum: Dict[int, List[float]] = defaultdict(lambda: [0.0, 0])
        self.att: Dict[int, float] = {}
        self.dfn: Dict[int, float] = {}
        self.atth: Dict[int, float] = {}
        self.defh: Dict[int, float] = {}
        self.atta: Dict[int, float] = {}
        self.defa: Dict[int, float] = {}
        self.recent: Dict[int, Deque[Tuple[int, float, float, int, float]]] = defaultdict(lambda: deque(maxlen=10))
        self.last_t: Dict[int, float] = {}
        self.ngames: Dict[int, int] = defaultdict(int)
        self.table: Dict[Tuple[int, int], Dict[int, List[float]]] = defaultdict(dict)
        self.season_start: Dict[Tuple[int, int], float] = {}
        self.h2h: Dict[Tuple[int, int], Deque[Tuple[int, float, float]]] = defaultdict(lambda: deque(maxlen=8))
        self.lg: Dict[int, List[float]] = {}
        self.glob = [1.45, 1.15, 0.45, 0.26, 0.50, 0.50, 0]

    # ---------------- ELO
    def _rating(self, team: int, league: int) -> float:
        r = self.elo.get(team)
        if r is None:
            s = self.league_elo_sum.get(league)
            base = (s[0] / s[1]) if s and s[1] >= 6 else 1500.0
            r = base + self.ep.new_team_offset
        return r

    def elo_expected(self, h: int, a: int, league: int) -> float:
        rh, ra = self._rating(h, league), self._rating(a, league)
        return 1.0 / (1.0 + 10 ** ((ra - rh - self.ep.home_adv) / 400.0))

    # ---------------- read
    def _league(self, league: int) -> List[float]:
        return self.lg.get(league) or list(self.glob)

    def features(self, h: int, a: int, league: int, season: int, t: float) -> List[float]:
        lg = self._league(league)
        lhg, lag = lg[0], lg[1]
        rh, ra = self._rating(h, league), self._rating(a, league)
        exp = 1.0 / (1.0 + 10 ** ((ra - rh - self.ep.home_adv) / 400.0))
        f: List[float] = [rh, ra, rh - ra, exp]
        lavg = (lhg + lag) / 2
        f += [self.att.get(h, lavg) / lavg, self.dfn.get(h, lavg) / lavg, self.att.get(a, lavg) / lavg, self.dfn.get(a, lavg) / lavg,
              self.atth.get(h, lhg) / lhg, self.defh.get(h, lag) / lag, self.atta.get(a, lag) / lag, self.defa.get(a, lhg) / lhg]
        rec = []
        for team, venue in ((h, 1), (a, 0)):
            r = list(self.recent.get(team, ()))
            n = len(r)
            l5 = r[-5:]
            ppm5 = sum(x[0] for x in l5) / len(l5) if l5 else np.nan
            ppm10 = sum(x[0] for x in r) / n if n else np.nan
            v = [x for x in r if x[3] == venue][-5:]
            ppmv = sum(x[0] for x in v) / len(v) if v else np.nan
            gf5 = sum(x[1] for x in l5) / len(l5) if l5 else np.nan
            ga5 = sum(x[2] for x in l5) / len(l5) if l5 else np.nan
            o25 = sum(1 for x in r if x[1] + x[2] > 2.5) / n if n else np.nan
            btts = sum(1 for x in r if x[1] > 0 and x[2] > 0) / n if n else np.nan
            cs = sum(1 for x in r if x[2] == 0) / n if n else np.nan
            fts = sum(1 for x in r if x[1] == 0) / n if n else np.nan
            rest = min(30.0, t - self.last_t[team]) if team in self.last_t else np.nan
            load = sum(1 for x in r if t - x[4] <= 14)
            rec.append((ppm5, ppm10, ppmv, gf5, ga5, o25, btts, cs, fts, rest, load))
        (h5, h10, hv, hgf, hga, ho, hb, hcs, hft, hr, hl), (a5, a10, av, agf, aga, ao, ab, acs, aft, ar, al) = rec
        f += [h5, a5, h10, a10, hv, av, hgf, hga, agf, aga, ho, ao, hb, ab, hcs, acs, hft, aft, hr, ar, hl, al]
        tab = self.table.get((league, season)) or {}
        sh, sa = tab.get(h), tab.get(a)
        if tab:
            order = sorted(tab.items(), key=lambda kv: (-kv[1][0], -kv[1][1]))
            pos = {tm: i + 1 for i, (tm, _) in enumerate(order)}
            nt = max(1, len(order))
        else:
            pos, nt = {}, 1
        def _s(s, i):
            return s[i] / s[2] if s and s[2] > 0 else np.nan
        f += [_s(sh, 0), _s(sa, 0), _s(sh, 1), _s(sa, 1),
              pos.get(h, np.nan) / nt if pos else np.nan, pos.get(a, np.nan) / nt if pos else np.nan,
              sh[2] if sh else 0.0, sa[2] if sa else 0.0,
              min(1.0, (t - self.season_start[(league, season)]) / 280.0) if (league, season) in self.season_start else 0.0]
        key = (min(h, a), max(h, a))
        hh = list(self.h2h.get(key, ()))
        if hh:
            pts = goals = o25 = bt = 0.0
            for hid, x, y in hh:
                gf, ga = (x, y) if hid == h else (y, x)
                pts += _pts(gf, ga)
                goals += x + y
                o25 += 1 if x + y > 2.5 else 0
                bt += 1 if x > 0 and y > 0 else 0
            n = len(hh)
            f += [n, pts / n, goals / n, o25 / n, bt / n]
        else:
            f += [0, np.nan, np.nan, np.nan, np.nan]
        f += [lg[0], lg[1], lg[2], lg[3], lg[4], lg[5], min(lg[6], 500)]
        f += [min(self.ngames.get(h, 0), 60), min(self.ngames.get(a, 0), 60)]
        return f

    # ---------------- write
    def update(self, h: int, a: int, league: int, season: int, t: float, gh: float, ga: float) -> None:
        ep = self.ep
        # regresie la începutul unui sezon nou (pauză lungă)
        for tm in (h, a):
            if ep.regress and tm in self.last_t and t - self.last_t[tm] > 60 and tm in self.elo:
                s = self.league_elo_sum.get(self.team_league.get(tm, league))
                if s and s[1]:
                    self.elo[tm] = self.elo[tm] + ep.regress * (s[0] / s[1] - self.elo[tm])
        rh, ra = self._rating(h, league), self._rating(a, league)
        exp = 1.0 / (1.0 + 10 ** ((ra - rh - ep.home_adv) / 400.0))
        act = 1.0 if gh > ga else (0.0 if gh < ga else 0.5)
        mult = 1.0 + ep.margin * math.log1p(abs(gh - ga)) if ep.margin else 1.0
        d = ep.k * mult * (act - exp)
        for tm, new in ((h, rh + d), (a, ra - d)):
            old_l = self.team_league.get(tm)
            if tm in self.elo and old_l is not None:
                s = self.league_elo_sum[old_l]
                s[0] -= self.elo[tm]
                s[1] -= 1
            self.elo[tm] = new
            self.team_league[tm] = league
            s = self.league_elo_sum[league]
            s[0] += new
            s[1] += 1
        al = self.alpha
        lg = self.lg.get(league)
        if lg is None:
            lg = list(self.glob)
            lg[6] = 0
            self.lg[league] = lg
        lavg = (lg[0] + lg[1]) / 2
        for tm, gf, gag in ((h, gh, ga), (a, ga, gh)):
            self.att[tm] = (1 - al) * self.att.get(tm, lavg) + al * gf
            self.dfn[tm] = (1 - al) * self.dfn.get(tm, lavg) + al * gag
        a2 = min(0.25, 2 * al)
        self.atth[h] = (1 - a2) * self.atth.get(h, lg[0]) + a2 * gh
        self.defh[h] = (1 - a2) * self.defh.get(h, lg[1]) + a2 * ga
        self.atta[a] = (1 - a2) * self.atta.get(a, lg[1]) + a2 * ga
        self.defa[a] = (1 - a2) * self.defa.get(a, lg[0]) + a2 * gh
        self.recent[h].append((_pts(gh, ga), gh, ga, 1, t))
        self.recent[a].append((_pts(ga, gh), ga, gh, 0, t))
        self.last_t[h] = t
        self.last_t[a] = t
        self.ngames[h] += 1
        self.ngames[a] += 1
        key = (league, season)
        tab = self.table[key]
        if key not in self.season_start:
            self.season_start[key] = t
        for tm, gf, gag in ((h, gh, ga), (a, ga, gh)):
            s = tab.setdefault(tm, [0.0, 0.0, 0.0])
            s[0] += _pts(gf, gag)
            s[1] += gf - gag
            s[2] += 1
        self.h2h[(min(h, a), max(h, a))].append((h, gh, ga))
        la = 0.02
        lg[0] = (1 - la) * lg[0] + la * gh
        lg[1] = (1 - la) * lg[1] + la * ga
        lg[2] = (1 - la) * lg[2] + la * (1.0 if gh > ga else 0.0)
        lg[3] = (1 - la) * lg[3] + la * (1.0 if gh == ga else 0.0)
        lg[4] = (1 - la) * lg[4] + la * (1.0 if gh + ga > 2.5 else 0.0)
        lg[5] = (1 - la) * lg[5] + la * (1.0 if gh > 0 and ga > 0 else 0.0)
        lg[6] += 1
        g = self.glob
        g[0] = 0.999 * g[0] + 0.001 * gh
        g[1] = 0.999 * g[1] + 0.001 * ga


def build_features(hist: History, elo: Optional[EloParams] = None, ewma: float = 0.08,
                   extra: Optional[List[Tuple[int, int, int, int, float]]] = None) -> Tuple[np.ndarray, FeatureState, Optional[np.ndarray]]:
    """Feature-uri pre-meci pentru tot istoricul (în ordine) + starea finală.
    ``extra``: meciuri viitoare (home, away, league, season, t) evaluate cu starea finală."""
    st = FeatureState(elo, ewma)
    X = np.empty((len(hist), len(FEATURE_NAMES)), dtype=np.float32)
    H, A, L, S, T, GH, GA = (hist.home.tolist(), hist.away.tolist(), hist.league.tolist(), hist.season.tolist(),
                             hist.t.tolist(), hist.gh.tolist(), hist.ga.tolist())
    for i in range(len(H)):
        X[i] = st.features(H[i], A[i], L[i], S[i], T[i])
        st.update(H[i], A[i], L[i], S[i], T[i], GH[i], GA[i])
    Xe = None
    if extra:
        Xe = np.array([st.features(*e) for e in extra], dtype=np.float32)
    return X, st, Xe


def elo_only(hist: History, ep: EloParams) -> np.ndarray:
    """Doar așteptarea ELO pre-meci (rapid, pentru reglarea parametrilor ELO)."""
    elo: Dict[int, float] = {}
    lsum: Dict[int, List[float]] = defaultdict(lambda: [0.0, 0])
    tl: Dict[int, int] = {}
    last: Dict[int, float] = {}
    out = np.empty(len(hist))
    H, A, L, T, GH, GA = hist.home.tolist(), hist.away.tolist(), hist.league.tolist(), hist.t.tolist(), hist.gh.tolist(), hist.ga.tolist()
    for i in range(len(H)):
        h, a, lgid = H[i], A[i], L[i]
        rr = []
        for tm in (h, a):
            r = elo.get(tm)
            if r is None:
                s = lsum.get(lgid)
                r = ((s[0] / s[1]) if s and s[1] >= 6 else 1500.0) + ep.new_team_offset
            elif ep.regress and tm in last and T[i] - last[tm] > 60:
                s = lsum.get(tl.get(tm, lgid))
                if s and s[1]:
                    r = r + ep.regress * (s[0] / s[1] - r)
            rr.append(r)
        rh, ra = rr
        e = 1.0 / (1.0 + 10 ** ((ra - rh - ep.home_adv) / 400.0))
        out[i] = e
        gh, ga = GH[i], GA[i]
        act = 1.0 if gh > ga else (0.0 if gh < ga else 0.5)
        d = ep.k * (1.0 + ep.margin * math.log1p(abs(gh - ga))) * (act - e)
        for tm, new in ((h, rh + d), (a, ra - d)):
            ol = tl.get(tm)
            if tm in elo and ol is not None:
                lsum[ol][0] -= elo[tm]
                lsum[ol][1] -= 1
            elo[tm] = new
            tl[tm] = lgid
            lsum[lgid][0] += new
            lsum[lgid][1] += 1
            last[tm] = T[i]
    return out
