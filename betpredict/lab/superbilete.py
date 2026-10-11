"""„Super bilete”: bilete zilnice după cele mai bune strategii din laborator (data/lab/results.json).

Strategiile au fost alese pe 2021/22–2023/24 și confirmate pe 2024/25–2026/27 (ROI pozitiv în ambele), dar numărul
lor nu depășește ce ar da întâmplarea — sunt jucabile cu risc asumat, miză fixă mică, EV realist afișat."""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from betpredict.builder.pool import Cand, load_pool

RESULTS = Path(__file__).resolve().parents[2] / "data" / "lab" / "results.json"
VARIANT = "super"
STAKE_U = 0.10
MAX_USES = 2
MAX_LEGS = 30
DRIFT_MAX = 0.03
LAB_SEL = {("1x2", 0.0, "HOME"): "H", ("1x2", 0.0, "AWAY"): "A", ("double_chance", 0.0, "1X"): "DC1X",
           ("double_chance", 0.0, "X2"): "DCX2", ("double_chance", 0.0, "12"): "DC12", ("over_under", 0.5, "OVER"): "O05",
           ("over_under", 1.5, "OVER"): "O15", ("over_under", 3.5, "UNDER"): "U35", ("over_under", 4.5, "UNDER"): "U45",
           ("btts", 0.0, "NO"): "BTTSN"}


def load_results(path: Path = RESULTS) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def lab_sel(c: Cand) -> Optional[str]:
    return LAB_SEL.get((c.market, float(c.line or 0.0), c.selection))


def _league_top(league_id: Any) -> bool:
    from betpredict.model.calib import league_group
    return league_group(league_id) == "top"


def _min_leg_p() -> float:
    from betpredict.selflearn import tuned

    return tuned("super", "min_leg_p", 0.0)


def pick_legs(pool: Sequence[Cand], st: Dict[str, Any], sel_used: Dict[int, int]) -> Optional[List[Cand]]:
    from betpredict.lab.engine import MARKET_SETS

    mset = set(MARKET_SETS[st["market_set"]])
    lo, hi = st["band"]
    score = (lambda c: c.p_honest) if st["key"] == "p" else (lambda c: c.p_honest * c.odds)
    best: Dict[int, Cand] = {}
    for c in pool:
        s = lab_sel(c)
        if s not in mset or not (lo <= c.odds <= hi) or c.odds_source != "superbet" or c.price_suspect:
            continue
        if st.get("drift_filter") and c.drift is not None and c.drift > DRIFT_MAX:  # ca în laborator: cota a crescut >3%
            continue
        if st.get("league") == "top" and not _league_top(c.league_id):
            continue
        if sel_used.get(c.prediction_id, 0) >= MAX_USES:
            continue
        if c.p_honest < _min_leg_p():  # auto-tuning zilnic (selflearn)
            continue
        if c.match_id not in best or score(c) > score(best[c.match_id]):
            best[c.match_id] = c
    legs, tot = [], 1.0
    for c in sorted(best.values(), key=score, reverse=True):
        legs.append(c)
        tot *= c.odds
        if tot >= st["tier"]:
            return legs
        if len(legs) >= MAX_LEGS:
            break
    return None


def short_name(st: Dict[str, Any]) -> str:
    ms = {"sigure_mix": "Mix sigure", "goluri_peste": "Goluri peste", "goluri_sub": "Goluri sub", "sansa_dubla": "Șansă dublă",
          "favoriti_1x2": "Favoriți 1X2", "goluri_mix": "Goluri mix"}.get(st["market_set"], st["market_set"])
    sysn = "acumulator" if not st["system"] else f"sistem N−{st['system']}/N"
    return f"{ms} {st['band'][0]:.2f}–{st['band'][1]:.2f} · ~{st['tier']} · {sysn}"


def build_super(conn: sqlite3.Connection, today: date, days: Sequence[date], now: Optional[datetime] = None,
                replace: bool = False, sel_used: Optional[Dict[int, int]] = None, results: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    from betpredict.builder.v4tickets import insert_ticket
    from betpredict.store import repo

    res = results if results is not None else load_results()
    strategies = res.get("super") or []
    if not strategies:
        return {"tickets": 0, "reason": "fără rezultate de laborator"}
    existing = conn.execute("SELECT COUNT(*) FROM ticket WHERE day=? AND variant=? AND status!='replaced'",
                            (today.isoformat(), VARIANT)).fetchone()[0]
    if existing and not replace:
        return {"skipped_existing": True}
    sel_used = {} if sel_used is None else sel_used
    pool: List[Cand] = []
    for d in days:
        pool.extend(load_pool(conn, d, now))
    made, skipped = 0, []
    created = repo.now_iso()
    with conn:
        if existing:
            conn.execute("UPDATE ticket SET status='replaced' WHERE day=? AND variant=? AND status='pending'", (today.isoformat(), VARIANT))
        for st in strategies:
            legs = pick_legs(pool, st, sel_used)
            if not legs:
                skipped.append(st["name"])
                continue
            te, tr = st["test"], st["train"]
            bt = {"strategy": st["name"], "label": short_name(st), "system": st["system"], "avg_legs": st["avg_legs"],
                  "train": tr, "test": te, "significant": False}
            insert_ticket(conn, f"acca_{st['tier']}", VARIANT, st["tier"], legs, STAKE_U,
                          [f"Super bilet · {short_name(st)} · {len(legs)} selecții",
                           f"Backtest test 2024–2026: lovit {te['hit_rate']:.1%} din {te['n']} bilete, ROI {te['roi']:+.0%} "
                           f"(± {te['roi_se']:.0%}); antrenare 2021–2024: ROI {tr['roi']:+.0%} din {tr['n']}",
                           "Atenție: nesemnificativ statistic — din 3,204 strategii, câte au ieșit pozitive în ambele perioade e cât ar da întâmplarea. "
                           f"Risc asumat, miză fixă {STAKE_U:g}u."],
                          today, created, sel_used, {"lottery": True, "super": True, "risk_acknowledged": True, "backtest": bt})
            made += 1
    return {"tickets": made, "skipped": skipped, "pool": len(pool)}
