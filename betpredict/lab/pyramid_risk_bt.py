"""Backtest walk-forward pentru piramidele ~5 și ~10 (betpredict/builder/pyramid_risk.py).

Pentru fiecare zi: scorurile piețelor/ligilor folosesc DOAR rezultatele de dinainte de acea zi; starea adaptivă
(țintă, familia evitată) vine doar din biletele simulate anterior. Selecțiile = predicțiile decontate ale zilei, cu cota
și probabilitatea publicate. Rulare: python -m betpredict.lab.pyramid_risk_bt data.db"""

from __future__ import annotations

import json
import math
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from betpredict.builder import pyramid_risk as R
from betpredict.builder.pool import Cand

OUT = Path(__file__).with_name("pyramid_risk_backtest.json")


def ro_day(ko: str) -> str:
    return (datetime.fromisoformat(ko.replace("Z", "+00:00")) + timedelta(hours=3)).date().isoformat()


def run(db: str) -> dict:
    conn = sqlite3.connect(db)
    rows = conn.execute(
        """SELECT p.id, p.match_id, m.league_id, m.kickoff_utc, p.market, p.line, p.selection, p.odds_shown, p.p_calibrated,
                  p.p_market_novig, p.ev, p.grade, p.result FROM prediction p JOIN match m ON m.id=p.match_id
           WHERE p.result IN ('won','lost') AND p.odds_shown > 1 AND p.p_calibrated IS NOT NULL""").fetchall()
    days = defaultdict(list)
    res = {}
    for r in rows:
        c = Cand(r[0], r[1], r[2], None, r[3], None, None, r[4], r[5] or 0.0, r[6], r[7], r[8], r[10] or 0.0, r[9] or "C", 0,
                 p_market=r[9])
        days[ro_day(r[3])].append(c)
        res[r[0]] = r[12] == "won"
    out = {}
    for tr, rules in (("r5", R.RULES_R5), ("r10", R.RULES_R10)):
        hist = []  # (status, families)
        bank, step, invested, back, steps_log = rules["start_bank"], 0, 0.0, 0.0, []
        for d in sorted(days):
            losses = 0
            for h in reversed(hist):
                if h[0] != "lost":
                    break
                losses += 1
            lo, hi = rules["band"]
            t = rules["target_odds"]
            if losses:
                t = max(lo, t * 0.9 ** min(losses, 3))
            elif hist and hist[-1][0] == "won":
                t = min(hi, t * 1.1)
            st = {"losses": losses, "target": t, "band": [max(lo, t * 0.85), min(hi, t * 1.2)],
                  "avoid": sorted(hist[-1][1]) if losses else [], "paused": []}
            scores = R.recent_scores(conn, d + "T00:00:00Z")
            pk = R.pick(days[d], rules, scores, st)
            if pk["status"] != "pick":
                continue
            legs, p = pk["main"]
            o = math.prod(c.odds for c in legs)
            won = all(res[c.prediction_id] for c in legs)
            if step == 0:
                invested += rules["start_bank"]; bank = rules["start_bank"]
            steps_log.append({"date": d, "step": step + 1, "odds": round(o, 2), "p": round(p, 3), "legs": len(legs), "won": won})
            if won:
                bank *= o; step += 1
                if step >= rules["max_steps"]:
                    back += bank; step = 0
            else:
                step = 0
            hist.append(("won" if won else "lost", {R.family(c.market) for c in legs}))
        if step:
            back += bank
        n = len(steps_log); w = sum(s["won"] for s in steps_log)
        exp = sum(s["p"] for s in steps_log)
        out[tr] = {"days": len(days), "tickets": n, "won": w, "hit": round(w / n, 3) if n else None,
                   "expected_hit": round(exp / n, 3) if n else None, "avg_odds": round(sum(s["odds"] for s in steps_log) / n, 2) if n else None,
                   "flat_roi": round(sum((s["odds"] - 1) if s["won"] else -1 for s in steps_log) / n, 3) if n else None,
                   "invested_lei": round(invested, 2), "returned_lei": round(back, 2),
                   "from": min(days), "to": max(days), "steps": steps_log[-30:],
                   "note": "Walk-forward pe predicțiile decontate (cote publicate, fără marja Superbet aplicată separat). Eșantion mic."}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    r = run(sys.argv[1])
    for k, v in r.items():
        print(k, {x: v[x] for x in v if x != "steps"})
