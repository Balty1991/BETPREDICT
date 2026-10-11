"""Grilă de backtest pentru ambele piramide (2.00 și 1.40) pe football-data 2021–2026.

python -m betpredict.lab.pyramid_grid <fd.db> — scrie betpredict/lab/pyramid_grid.json.
Selecție zilnică = combinația cu cea mai mare șansă comună (piața de deschidere fără marjă) în banda de cotă.
Alegerea variantelor pe antrenare (2021/22–2023/24), raportare pe test (2024/25–2026/27).
Prețuri reale: 1X2 (H/A) și Peste/Sub 2.5; restul piețelor au cote modelate din piața de închidere (marjă Superbet 1.05)."""

from __future__ import annotations

import itertools
import json
import math
import sqlite3
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from betpredict.lab.engine import Leg, build_legs, novig, TOP_DIVS
from betpredict.lab.pyramid140 import NEED

OUT = Path(__file__).with_name("pyramid_grid.json")
SECOND = {"E1", "D2", "I2", "SP2", "F2", "SC1"}
PYRAMIDS = {"2.00": (1.85, 2.20), "1.40": (1.35, 1.45)}
MARKETS = {
    "1x2_fav": ("H", "A"), "ou25_real": ("O25", "U25"), "real_mix": ("H", "A", "O25", "U25"),
    "sansa_dubla": ("DC1X", "DCX2", "DC12"), "peste_0.5_1.5": ("O05", "O15"), "sub_3.5_4.5": ("U35", "U45"),
    "mix_tot": ("H", "A", "O25", "U25", "DC1X", "DCX2", "DC12", "O05", "O15", "U35", "U45"),
}
REAL = {"1x2_fav", "ou25_real", "real_mix"}
LEAGUES = ("toate", "top", "liga2", "altele")
MIN_P = (0.50, 0.75, 0.80, 0.85, 0.90)
MAX_LEGS = (1, 2, 3, 4)
WITHDRAW = (0.0, 0.5, 1.0)
SPLIT = "2024-07-01"
SB_HAIRCUT = 0.97  # cotele Superbet ≈ 3% sub media pieței folosită de football-data
G = {}


def group(div):
    return "top" if div in TOP_DIVS else "liga2" if div in SECOND else "altele"


def prep(rows):
    legs = build_legs(rows)
    by_day = defaultdict(list)
    for i, (r, ls) in enumerate(zip(rows, legs)):
        g = group(r["div"])
        po, pu = novig(r["avg_o25"], r["avg_u25"])
        o25 = Leg(i, "O25", po, r["avgc_o25"], r["fthg"] + r["ftag"] > 2, r["avgc_o25"] / r["avg_o25"] - 1, False)
        u25 = Leg(i, "U25", pu, r["avgc_u25"], r["fthg"] + r["ftag"] < 3, r["avgc_u25"] / r["avg_u25"] - 1, False)
        for l in ls + [o25, u25]:
            by_day[r["day"]].append((l, g))
    return dict(sorted(by_day.items()))


def pick(day_legs, band, mset, lg, drift, min_p, max_legs, top=14):
    best = {}
    for l, g in day_legs:
        if l.sel not in mset or (lg != "toate" and g != lg) or l.p < min_p or not (band[0] ** (1 / max_legs) - 0.005 <= l.odds <= band[1]):
            continue
        if drift and l.drift > 0.05:
            continue
        if l.match not in best or l.p > best[l.match].p:
            best[l.match] = l
    # eficiență: cât din șansă „costă” fiecare unitate de cotă (−ln p / ln cotă), cele mai eficiente primele
    c = sorted(best.values(), key=lambda l: -math.log(l.p) / math.log(l.odds) if l.odds > 1.0 else 9e9)[:top]
    out = None
    for k in range(1, max_legs + 1):
        for combo in itertools.combinations(c, k):
            o = math.prod(x.odds for x in combo)
            if band[0] <= o <= band[1]:
                p = math.prod(x.p for x in combo)
                if out is None or p > out[0]:
                    out = (p, o, all(x.win for x in combo))
    return out


def money(seq, w):
    streaks, cur, bank, withdrawn, invested, wins = [], 0, 100.0, 0.0, 100.0, 0
    for _, o, won in seq:
        if won:
            cur += 1; wins += 1
            prof = bank * (o - 1)
            withdrawn += prof * w
            bank += prof * (1 - w)
        else:
            streaks.append(cur); cur = 0; invested += 100.0; bank = 100.0
    streaks.append(cur)  # seria activă la final
    n = len(seq)
    reach = {str(k): round(sum(1 for s in streaks if s >= k) / len(streaks), 4) for k in (3, 5, 7, 10, 15)}
    net = withdrawn + bank - invested
    flat = sum((o * SB_HAIRCUT if won else 0.0) - 1 for _, o, won in seq) / n if n else None
    return {"days": n, "win_rate": round(wins / n, 4) if n else None, "runs": len(streaks), "max_step": max(streaks),
            "avg_steps": round(sum(streaks) / len(streaks), 2), "reach": reach, "invested": invested,
            "net": round(net, 1), "roi_pct": round(100 * net / invested, 1),
            "flat_roi_pct": round(100 * flat, 1) if flat is not None else None, "avg_odds": round(sum(o for _, o, _ in seq) / n, 3) if n else None}


def run_cfg(cfg):
    pyr, mk, lg, drift, mp, ml = cfg
    seq_tr, seq_te = [], []
    for d, dl in G["days"].items():
        r = pick(dl, PYRAMIDS[pyr], MARKETS[mk], lg, drift, mp, ml)
        if r:
            (seq_te if d >= SPLIT else seq_tr).append(r)
    out = []
    if len(seq_tr) < 60 or len(seq_te) < 40:
        return out
    for w in WITHDRAW:
        out.append({"pyramid": pyr, "markets": mk, "real_prices": mk in REAL, "leagues": lg, "drift_filter": drift,
                    "min_leg_p": mp, "max_legs": ml, "withdraw": w, "train": money(seq_tr, w), "test": money(seq_te, w)})
    return out


def init(days):
    G["days"] = days


def main(db):
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True); c.row_factory = sqlite3.Row
    rows = [r for r in (dict(x) for x in c.execute("SELECT * FROM fd_match ORDER BY day")) if all(r.get(k) is not None for k in NEED)]
    days = prep(rows)
    cfgs = list(itertools.product(PYRAMIDS, MARKETS, LEAGUES, (True, False), MIN_P, MAX_LEGS))
    res = []
    with ProcessPoolExecutor(8, initializer=init, initargs=(days,)) as ex:
        for r in ex.map(run_cfg, cfgs, chunksize=8):
            res.extend(r)
    doc = {"matches": len(rows), "split": SPLIT, "variants_tested": len(res), "pyramids": {}}
    for pyr in PYRAMIDS:
        rs = [r for r in res if r["pyramid"] == pyr]
        live = (0.50, 3) if pyr == "2.00" else (0.80, 4)  # aproximarea regulii live
        base = next((r for r in rs if r["markets"] == "mix_tot" and r["leagues"] == "toate" and r["drift_filter"] and r["min_leg_p"] == live[0]
                     and r["max_legs"] == live[1] and r["withdraw"] == 0.5), None)
        # clasament pe antrenare după ROI la miză fixă (stabil; ROI-ul piramidei depinde de 1–2 serii lungi), min 100 zile
        top = sorted([r for r in rs if r["withdraw"] == 0.5 and r["train"]["days"] >= 100],
                     key=lambda r: r["train"]["flat_roi_pct"], reverse=True)[:5]
        top_test = sorted(rs, key=lambda r: r["test"]["roi_pct"], reverse=True)[:5]
        robust = [r for r in rs if r["train"]["flat_roi_pct"] > 0 and r["test"]["flat_roi_pct"] > 0 and r["train"]["days"] >= 100 and r["test"]["days"] >= 80]
        doc["pyramids"][pyr] = {"tested": len(rs), "baseline": base, "top_by_train": top, "top_by_test": top_test,
                                "both_positive": len(robust), "robust": sorted(robust, key=lambda r: min(r["train"]["flat_roi_pct"], r["test"]["flat_roi_pct"]), reverse=True)[:5],
                                "test_positive_share": round(sum(r["test"]["roi_pct"] > 0 for r in rs) / max(1, len(rs)), 3)}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    for pyr, d in doc["pyramids"].items():
        print(pyr, d["tested"], "both+", d["both_positive"], "test+share", d["test_positive_share"])


if __name__ == "__main__":
    main(sys.argv[1])
