"""Backtest piramidele sigure (1.20 / 1.40 / 1.60) pe football-data:
python -m betpredict.lab.pyramid140 <fd.db> [1.20|1.40|1.60|all].

Zilnic: selecții cu șansa pieței la deschidere (fără marjă) peste prag, cota pe selecție în interval (închidere, marjă
Superbet), fără cote în creștere > 5%; până la 3 selecții pe meci, un meci o dată pe bilet; combinația cu cota totală în
bandă și șansa comună maximă, șansa fiind corectată walk-forward cu cât a intrat de fapt fiecare piață până în ziua aceea.
Un pas pe zi; o pierdere încheie seria (pași câștigați la rând). Regulile sunt cele din ``builder.pyramid``."""

from __future__ import annotations

import itertools
import json
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

from betpredict.lab.engine import build_legs

OUT = Path(__file__).with_name("pyramid140_backtest.json")


TRACKS = {"1.20": ((1.16, 1.25), 0.75, 1, (1.04, 1.25)), "1.40": ((1.35, 1.45), 0.65, 1, (1.04, 1.40)),
          "1.60": ((1.52, 1.70), 0.70, 2, (1.05, 1.40))}
PREFER_DRIFT = {"1.20": -0.02}  # ca în builder.pyramid: întâi meciurile cu cota în scădere ≥ 2%
REL_PRIOR = 200


def pick_day(legs, band=(1.35, 1.45), min_p=0.70, max_legs=3, leg_odds=(1.04, 1.45), rel=None, top=30):
    rel = rel or {}
    q = lambda l: min(0.99, l.p + rel.get(l.sel, 0.0))  # noqa: E731
    per = defaultdict(list)
    floor = max(leg_odds[0], band[0] ** (1 / max_legs) * 0.97)  # ca în builder.pyramid: banda trebuie să se poată atinge
    for l in legs:
        if l.p >= min_p and floor <= l.odds <= leg_odds[1] and l.drift <= 0.05:
            per[l.match].append(l)
    allc = []
    for ls in per.values():
        allc.extend(sorted(ls, key=q, reverse=True)[:3])
    cands = sorted(allc, key=q, reverse=True)[:top]
    out = None
    for k in range(1, max_legs + 1):
        for c in itertools.combinations(cands, k):
            if len({x.match for x in c}) < k:
                continue
            o = math.prod(x.odds for x in c)
            if band[0] <= o <= band[1]:
                p = math.prod(q(x) for x in c)
                if out is None or p > out[0]:
                    out = (p, o, c)
    return out


NEED = ("avg_h", "avg_d", "avg_a", "avg_o25", "avg_u25", "avgc_h", "avgc_d", "avgc_a", "avgc_o25", "avgc_u25", "fthg", "ftag")


def backtest(rows: List[Dict[str, Any]], track: str = "1.40", by_day=None) -> Dict[str, Any]:
    band, min_p, max_legs, leg_odds = TRACKS[track]
    if by_day is None:
        rows = [r for r in rows if all(r.get(k) is not None for k in NEED)]
        legs = build_legs(rows)
        by_day = defaultdict(list)
        for r, ls in zip(rows, legs):
            by_day[r["day"]].extend(ls)
    seq = []
    hist: Dict[str, List[float]] = defaultdict(lambda: [0, 0.0])  # corecția pe piață, doar din zilele de dinainte
    for d in sorted(by_day):
        rel = {k: v[1] / (v[0] + REL_PRIOR) for k, v in hist.items()}
        pk = None
        if track in PREFER_DRIFT:
            pk = pick_day([l for l in by_day[d] if l.drift <= PREFER_DRIFT[track]], band, min_p, max_legs, leg_odds, rel)
        pk = pk or pick_day(by_day[d], band, min_p, max_legs, leg_odds, rel)
        if pk:
            p, o, c = pk
            seq.append({"day": d, "p": p, "odds": o, "legs": len(c), "won": all(x.win for x in c)})
        for l in by_day[d]:
            if l.p >= min_p:
                h = hist[l.sel]
                h[0] += 1
                h[1] += float(l.win) - l.p
    streaks, cur = [], 0
    bank, withdrawn, staked = 100.0, 0.0, 0.0
    for s in seq:
        if s["won"]:
            cur += 1
            prof = bank * (s["odds"] - 1)
            withdrawn += prof * 0.5
            bank += prof * 0.5
        else:
            streaks.append(cur)
            cur = 0
            staked += 100.0
            bank = 100.0
    active = cur
    n = len(seq)
    w = sum(s["won"] for s in seq)
    dist = Counter(min(x, 20) for x in streaks)
    reach = {str(k): round(sum(1 for x in streaks if x >= k) / len(streaks), 4) for k in (1, 2, 3, 5, 7, 10, 15, 17, 20)} if streaks else {}
    return {
        "track": track, "rules": {"band": list(band), "min_leg_p": min_p, "max_legs": max_legs, "leg_odds": list(leg_odds)},
        "source": "football-data (deschidere fără marjă → șansă; închidere cu marjă Superbet → cotă)",
        "days": n, "from": seq[0]["day"] if seq else None, "to": seq[-1]["day"] if seq else None,
        "win_rate": round(w / n, 4) if n else None, "avg_p": round(sum(s["p"] for s in seq) / n, 4) if n else None,
        "avg_odds": round(sum(s["odds"] for s in seq) / n, 3) if n else None,
        "avg_legs": round(sum(s["legs"] for s in seq) / n, 2) if n else None,
        "runs": len(streaks), "avg_steps": round(sum(streaks) / len(streaks), 2) if streaks else None,
        "median_steps": sorted(streaks)[len(streaks) // 2] if streaks else None, "max_steps": max(streaks) if streaks else None,
        "distribution": [{"steps": k if k < 20 else "20+", "runs": dist[k]} for k in sorted(dist)],
        "reach_probability": reach, "active_streak_at_end": active,
        "bank_sim": {"start_bank": 100.0, "restarts_cost": round(staked, 2), "withdrawn": round(withdrawn, 2),
                     "net": round(withdrawn + bank - staked - 100.0, 2)},
    }


if __name__ == "__main__":
    c = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    which = sys.argv[2] if len(sys.argv) > 2 else "all"
    rows = [r for r in (dict(x) for x in c.execute("SELECT * FROM fd_match ORDER BY day")) if all(r.get(k) is not None for k in NEED)]
    bd = defaultdict(list)
    for r, ls in zip(rows, build_legs(rows)):
        bd[r["day"]].extend(ls)
    for tr in (TRACKS if which == "all" else [which]):
        res = backtest([], tr, bd)
        out = Path(__file__).with_name(f"pyramid{tr.replace('.', '')}_backtest.json")
        out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        print(tr, json.dumps({k: v for k, v in res.items() if k not in ("distribution", "rules")}, ensure_ascii=False))
