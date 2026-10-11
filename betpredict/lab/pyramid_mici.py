"""Backtest Piramida 2.00 Ligi mici (test iul. 2024 → azi, 100 lei/serie): python -m betpredict.lab.pyramid_mici <fd.db>."""

import json
import sqlite3
import sys
from pathlib import Path

from betpredict.lab import pyramid_grid as PG

OUT = Path(__file__).with_name("pyramid_mici_backtest.json")


def run(db: str) -> dict:
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True); c.row_factory = sqlite3.Row
    rows = [r for r in (dict(x) for x in c.execute("SELECT * FROM fd_match ORDER BY day")) if all(r.get(k) is not None for k in PG.NEED)]
    out = {}
    for per, test in (("train", False), ("test", True)):
        seq = []
        for d, dl in PG.prep(rows).items():
            if (d >= PG.SPLIT) == test:
                k = PG.pick(dl, PG.PYRAMIDS["2.00"], PG.MARKETS["1x2_fav"], "altele", False, 0.50, 3)
                if k:
                    seq.append(k)
        S, runs, bank, wd, inv, cur, mx, streaks = 100.0, 1, 100.0, 0.0, 100.0, 0, 0, []
        for _, o, won in seq:
            if won:
                cur += 1; mx = max(mx, cur); bank *= o
                if cur >= 7:
                    wd += bank; streaks.append(cur); runs += 1; inv += S; bank = S; cur = 0
            else:
                streaks.append(cur); runs += 1; inv += S; bank = S; cur = 0
        n = len(seq)
        out[per] = {"days": n, "win_rate": round(sum(x[2] for x in seq) / n, 4), "avg_odds": round(sum(x[1] for x in seq) / n, 3),
                    "runs": runs, "staked": inv, "returned": round(wd + bank, 1), "net": round(wd + bank - inv, 1),
                    "roi_pct": round(100 * (wd + bank - inv) / inv, 1), "max_steps": mx, "cashouts_at_7": sum(1 for s in streaks if s >= 7)}
    out["note"] = "Cote = media pieței (football-data), nu Superbet; ~50 serii pe test, rezultat incert (±8% ROI la miză fixă)."
    return out


if __name__ == "__main__":
    res = run(sys.argv[1])
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(res)
