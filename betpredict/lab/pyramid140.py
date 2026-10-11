"""Backtest Piramida 1.40 pe football-data: python -m betpredict.lab.pyramid140 <fd.db> [out.json].

Zilnic: selecții cu șansa pieței la deschidere (fără marjă) ≥ 80%, cotă 1.04–1.45 (închidere, marjă Superbet),
fără cote în creștere > 5%, câte una pe meci; combinația de 1–4 selecții cu cota totală 1.35–1.45 și șansa comună
maximă. Un pas pe zi; o pierdere încheie seria (pași câștigați la rând)."""

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


def pick_day(legs, band=(1.35, 1.45), min_p=0.80, top=18):
    best = {}
    for l in legs:
        if l.p >= min_p and 1.04 <= l.odds <= 1.45 and l.drift <= 0.05:
            if l.match not in best or l.p > best[l.match].p:
                best[l.match] = l
    cands = sorted(best.values(), key=lambda l: l.p, reverse=True)[:top]
    out = None
    for k in range(1, 5):
        for c in itertools.combinations(cands, k):
            o = math.prod(x.odds for x in c)
            if band[0] <= o <= band[1]:
                p = math.prod(x.p for x in c)
                if out is None or p > out[0]:
                    out = (p, o, c)
    return out


NEED = ("avg_h", "avg_d", "avg_a", "avg_o25", "avg_u25", "avgc_h", "avgc_d", "avgc_a", "avgc_o25", "avgc_u25", "fthg", "ftag")


def backtest(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows = [r for r in rows if all(r.get(k) is not None for k in NEED)]
    legs = build_legs(rows)
    by_day = defaultdict(list)
    for r, ls in zip(rows, legs):
        by_day[r["day"]].extend(ls)
    seq = []
    for d in sorted(by_day):
        pk = pick_day(by_day[d])
        if pk:
            p, o, c = pk
            seq.append({"day": d, "p": p, "odds": o, "legs": len(c), "won": all(x.win for x in c)})
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
    res = backtest([dict(r) for r in c.execute("SELECT * FROM fd_match ORDER BY day")])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else OUT
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "distribution"}, ensure_ascii=False))
