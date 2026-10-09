"""Model de goluri: Poisson cu atac/apărare pe echipă, nivel pe ligă, avantaj de teren,
decădere exponențială în timp (timp de înjumătățire ~180 zile) și corecția Dixon-Coles
pentru scoruri mici (din ``analytics_core``). Plus ELO pe tot istoricul."""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from betpredict.config import ROOT

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from analytics_core import EloConfig, EloRatings, football_score_matrix  # noqa: E402  (nucleul matematic păstrat)

from betpredict.robot.markets import Selection, probs_from_matrix  # noqa: E402

RHO = -0.08


@dataclass
class GoalModel:
    as_of: str = ""
    half_life_days: float = 180.0
    home_adv: float = 0.25
    global_mu: float = 0.1
    league_mu: Dict[int, float] = field(default_factory=dict)
    attack: Dict[int, float] = field(default_factory=dict)
    defense: Dict[int, float] = field(default_factory=dict)
    games: Dict[int, float] = field(default_factory=dict)  # greutatea efectivă a datelor pe echipă
    n_matches: int = 0

    def lambdas(self, home_id: Optional[int], away_id: Optional[int], league_id: Optional[int]) -> Tuple[float, float]:
        mu = self.league_mu.get(league_id, self.global_mu) if league_id is not None else self.global_mu
        ah, dh = self.attack.get(home_id, 0.0), self.defense.get(home_id, 0.0)
        aa, da = self.attack.get(away_id, 0.0), self.defense.get(away_id, 0.0)
        lh = math.exp(mu + self.home_adv + ah - da)
        la = math.exp(mu + aa - dh)
        return min(6.0, max(0.05, lh)), min(6.0, max(0.05, la))

    def coverage(self, team_id: Optional[int]) -> float:
        """0–1: cât de bine cunoaște modelul echipa (greutate efectivă ~ meciuri recente)."""
        return min(1.0, self.games.get(team_id, 0.0) / 10.0)


def fit_goal_model(rows: Sequence, as_of: datetime, half_life_days: float = 180.0, years: float = 3.0,
                   shrink: float = 3.0, iters: int = 30) -> GoalModel:
    """``rows``: (id, league_id, kickoff_utc, home_id, away_id, ft_home, ft_away) până la ``as_of``."""
    cutoff = (as_of - timedelta(days=365 * years)).strftime("%Y-%m-%dT%H:%M:%SZ")
    as_of_s = as_of.strftime("%Y-%m-%dT%H:%M:%SZ")
    data = [r for r in rows if cutoff <= r[2] < as_of_s and r[3] is not None and r[4] is not None]
    model = GoalModel(as_of=as_of_s, half_life_days=half_life_days, n_matches=len(data))
    if len(data) < 50:
        return model
    teams = sorted({r[3] for r in data} | {r[4] for r in data})
    tix = {t: i for i, t in enumerate(teams)}
    leagues = sorted({(r[1] if r[1] is not None else -1) for r in data})
    lix = {l: i for i, l in enumerate(leagues)}
    hi = np.array([tix[r[3]] for r in data])
    ai = np.array([tix[r[4]] for r in data])
    li = np.array([lix[r[1] if r[1] is not None else -1] for r in data])
    gh = np.array([float(r[5]) for r in data])
    ga = np.array([float(r[6]) for r in data])
    age = np.array([(as_of - datetime.fromisoformat(r[2].replace("Z", "+00:00"))).total_seconds() / 86400 for r in data])
    w = np.power(0.5, age / half_life_days)
    T, L = len(teams), len(leagues)
    att, dfn, mu = np.zeros(T), np.zeros(T), np.full(L, math.log(max(0.1, (gh.sum() + ga.sum()) / (2 * len(data)))))
    h = 0.25
    c = 1.3
    for _ in range(iters):
        eh = np.exp(mu[li] + h + att[hi] - dfn[ai])
        ea = np.exp(mu[li] + att[ai] - dfn[hi])
        S = np.bincount(hi, w * gh, T) + np.bincount(ai, w * ga, T)
        E = np.bincount(hi, w * eh / np.exp(att[hi]), T) + np.bincount(ai, w * ea / np.exp(att[ai]), T)
        att = np.log((S + shrink * c) / (E + shrink * c))
        eh = np.exp(mu[li] + h + att[hi] - dfn[ai])
        ea = np.exp(mu[li] + att[ai] - dfn[hi])
        C = np.bincount(ai, w * gh, T) + np.bincount(hi, w * ga, T)
        B = np.bincount(ai, w * eh * np.exp(dfn[ai]), T) + np.bincount(hi, w * ea * np.exp(dfn[hi]), T)
        dfn = -np.log((C + shrink * c) / (B + shrink * c))
        eh = np.exp(mu[li] + h + att[hi] - dfn[ai])
        ea = np.exp(mu[li] + att[ai] - dfn[hi])
        G = np.bincount(li, w * (gh + ga), L)
        BL = np.bincount(li, w * (eh + ea) / np.exp(mu[li]), L)
        gm = float(np.log((w * (gh + ga)).sum() / max(1e-9, (w * (eh + ea) / np.exp(mu[li])).sum())))
        mu = np.log((G + 20 * math.exp(gm)) / (BL + 20))  # nivel pe ligă, micșorat spre media globală
        eh = np.exp(mu[li] + h + att[hi] - dfn[ai])
        h = float(h + math.log(max(1e-9, (w * gh).sum()) / max(1e-9, (w * eh).sum())))
    games = np.bincount(hi, w, T) + np.bincount(ai, w, T)
    model.home_adv = h
    model.league_mu = {int(l): float(mu[i]) for l, i in lix.items() if l != -1}
    model.global_mu = float(np.average(mu, weights=np.bincount(li, w, L) + 1e-9))
    model.attack = {int(t): float(att[i]) for t, i in tix.items()}
    model.defense = {int(t): float(dfn[i]) for t, i in tix.items()}
    model.games = {int(t): float(games[i]) for t, i in tix.items()}
    return model


def fit_elo(rows: Iterable, until_utc: Optional[str] = None) -> EloRatings:
    elo = EloRatings(EloConfig(k_factor=20.0, home_advantage=60.0))
    for r in rows:
        if until_utc and r[2] >= until_utc:
            break
        elo.update(r[3], r[4], r[5], r[6])
    return elo


def match_probabilities(model: GoalModel, elo: Optional[EloRatings], home_id, away_id, league_id,
                        elo_weight: float = 0.35) -> Tuple[Dict[Selection, float], Dict[str, object]]:
    lh, la = model.lambdas(home_id, away_id, league_id)
    matrix = football_score_matrix(lh, la, max_goals=10, rho=RHO)
    probs = probs_from_matrix(matrix)
    info: Dict[str, object] = {"lambda_home": round(lh, 3), "lambda_away": round(la, 3)}
    if elo is not None and home_id is not None and away_id is not None:
        e = elo.expected_home(home_id, away_id)
        pd = probs[("1x2", 0.0, "DRAW")]
        ph_elo = min(0.97, max(0.01, e - 0.5 * pd))
        pa_elo = max(0.01, 1 - pd - ph_elo)
        ph = (1 - elo_weight) * probs[("1x2", 0.0, "HOME")] + elo_weight * ph_elo
        pa = (1 - elo_weight) * probs[("1x2", 0.0, "AWAY")] + elo_weight * pa_elo
        s = ph + pd + pa
        ph, pd2, pa = ph / s, pd / s, pa / s
        probs[("1x2", 0.0, "HOME")], probs[("1x2", 0.0, "DRAW")], probs[("1x2", 0.0, "AWAY")] = ph, pd2, pa
        probs[("double_chance", 0.0, "1X")] = ph + pd2
        probs[("double_chance", 0.0, "12")] = ph + pa
        probs[("double_chance", 0.0, "X2")] = pd2 + pa
        probs[("draw_no_bet", 0.0, "HOME")] = ph / (ph + pa)
        probs[("draw_no_bet", 0.0, "AWAY")] = pa / (ph + pa)
        info["elo_home"] = round(elo.rating(home_id), 1)
        info["elo_away"] = round(elo.rating(away_id), 1)
    flat = sorted(((h, a, p) for h, row in enumerate(matrix) for a, p in enumerate(row)), key=lambda x: -x[2])
    info["most_likely_score"] = f"{flat[0][0]}-{flat[0][1]}"
    info["top_scores"] = [{"score": f"{h}-{a}", "p": round(p, 4)} for h, a, p in flat[:6]]
    return probs, info
