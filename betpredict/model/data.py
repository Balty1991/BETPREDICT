"""Încărcarea istoricului pentru modelare: meciuri terminate (DB) + cote istorice.

Cote istorice: ``data/warehouse/events_season_*.json`` (sezonul 2025/26, ~4.8k meciuri cu 1X2,
O/U 1.5/2.5/3.5, GG) și ``odds_snapshot`` din DB (consens BSD, cu cota de deschidere = opening
și ultima cotă înainte de start ≈ closing)."""

from __future__ import annotations

import glob
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

# cheile de cote folosite în harness (selecție compactă)
ODDS_KEYS = ("H", "D", "A", "O15", "U15", "O25", "U25", "O35", "U35", "BY", "BN", "1X", "12", "X2", "DH", "DA")

WAREHOUSE_MAP = {"odds_home": "H", "odds_draw": "D", "odds_away": "A", "odds_over_15": "O15", "odds_under_15": "U15",
                 "odds_over_25": "O25", "odds_under_25": "U25", "odds_over_35": "O35", "odds_under_35": "U35",
                 "odds_btts_yes": "BY", "odds_btts_no": "BN"}

SNAP_MAP = {("1x2", 0.0, "HOME"): "H", ("1x2", 0.0, "DRAW"): "D", ("1x2", 0.0, "AWAY"): "A",
            ("over_under", 1.5, "OVER"): "O15", ("over_under", 1.5, "UNDER"): "U15",
            ("over_under", 2.5, "OVER"): "O25", ("over_under", 2.5, "UNDER"): "U25",
            ("over_under", 3.5, "OVER"): "O35", ("over_under", 3.5, "UNDER"): "U35",
            ("btts", 0.0, "YES"): "BY", ("btts", 0.0, "NO"): "BN",
            ("double_chance", 0.0, "1X"): "1X", ("double_chance", 0.0, "12"): "12", ("double_chance", 0.0, "X2"): "X2",
            ("draw_no_bet", 0.0, "HOME"): "DH", ("draw_no_bet", 0.0, "AWAY"): "DA"}


@dataclass
class History:
    """Coloane numpy sortate după kickoff (doar meciuri terminate cu echipe cunoscute)."""
    ids: np.ndarray
    league: np.ndarray
    season: np.ndarray
    ko: np.ndarray          # str ISO UTC
    t: np.ndarray           # zile de la epoch (float)
    home: np.ndarray
    away: np.ndarray
    gh: np.ndarray
    ga: np.ndarray

    def __len__(self) -> int:
        return len(self.ids)


def _days(ko: str) -> float:
    return float(np.datetime64(ko[:19]).astype("datetime64[s]").astype(np.int64)) / 86400.0


def load_history(conn: sqlite3.Connection, until_utc: Optional[str] = None) -> History:
    q = ("SELECT id, COALESCE(league_id,-1), COALESCE(season_id,-1), kickoff_utc, home_id, away_id, ft_home, ft_away "
         "FROM match WHERE status='finished' AND ft_home IS NOT NULL AND ft_away IS NOT NULL "
         "AND home_id IS NOT NULL AND away_id IS NOT NULL")
    args: List = []
    if until_utc:
        q += " AND kickoff_utc < ?"
        args.append(until_utc)
    q += " ORDER BY kickoff_utc, id"
    rows = conn.execute(q, args).fetchall()
    if not rows:
        z = np.zeros(0)
        return History(z.astype(int), z.astype(int), z.astype(int), z.astype(str), z, z.astype(int), z.astype(int), z, z)
    a = list(zip(*[tuple(r) for r in rows]))
    ko = np.array(a[3], dtype=object)
    t = np.array([s[:19] for s in a[3]], dtype="datetime64[s]").astype(np.int64) / 86400.0
    return History(np.array(a[0], dtype=np.int64), np.array(a[1], dtype=np.int64), np.array(a[2], dtype=np.int64), ko, t,
                   np.array(a[4], dtype=np.int64), np.array(a[5], dtype=np.int64),
                   np.array(a[6], dtype=float), np.array(a[7], dtype=float))


def _sane(o: Dict[str, float]) -> Dict[str, float]:
    """Elimină seturile de cote incoerente (marjă < 0 sau > 25%)."""
    out = dict(o)
    for grp in (("H", "D", "A"), ("O15", "U15"), ("O25", "U25"), ("O35", "U35"), ("BY", "BN")):
        if all(k in out for k in grp):
            s = sum(1 / out[k] for k in grp)
            if not (1.0 <= s <= 1.25):
                for k in grp:
                    out.pop(k, None)
    return {k: v for k, v in out.items() if v and v > 1.0}


def load_warehouse_odds(warehouse_dir: Path) -> Dict[int, Dict[str, float]]:
    out: Dict[int, Dict[str, float]] = {}
    for f in sorted(glob.glob(str(Path(warehouse_dir) / "events_season_*.json"))):
        try:
            rows = json.loads(Path(f).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(rows, dict):
            rows = rows.get("events") or rows.get("results") or []
        for r in rows:
            if not isinstance(r, dict) or not r.get("odds_home") and not r.get("odds_over_25"):
                continue
            o = {}
            for k, kk in WAREHOUSE_MAP.items():
                v = r.get(k)
                try:
                    if v is not None and float(v) > 1.0:
                        o[kk] = float(v)
                except (TypeError, ValueError):
                    pass
            o = _sane(o)
            if o and r.get("event_id") is not None:
                out[int(r["event_id"])] = o
    return out


def load_snapshot_odds(conn: sqlite3.Connection, before_kickoff: bool = True) -> Dict[int, Dict[str, Dict[str, float]]]:
    """{match_id: {"close": {...}, "open": {...}}} din odds_snapshot (ultima cotă observată înainte de start)."""
    out: Dict[int, Dict[str, Dict[str, float]]] = {}
    q = """SELECT o.match_id, o.market, o.line, o.outcome, o.decimal, o.opening_decimal, o.observed_at
           FROM odds_snapshot o JOIN match m ON m.id=o.match_id
           WHERE o.period='FT'""" + (" AND o.observed_at <= m.kickoff_utc" if before_kickoff else "") + \
        " ORDER BY o.observed_at"
    for r in conn.execute(q):
        k = SNAP_MAP.get((r[1], float(r[2] or 0.0), r[3]))
        if not k:
            continue
        d = out.setdefault(int(r[0]), {"close": {}, "open": {}})
        d["close"][k] = float(r[4])
        if r[5] and k not in d["open"]:
            d["open"][k] = float(r[5])
    for mid, d in out.items():
        d["close"] = _sane(d["close"])
        d["open"] = _sane(d["open"])
    return out


def novig_market(o: Dict[str, float]) -> Dict[str, float]:
    """Probabilități fără marjă (normalizare proporțională) pe cheile compacte."""
    p: Dict[str, float] = {}
    for grp in (("H", "D", "A"), ("O15", "U15"), ("O25", "U25"), ("O35", "U35"), ("BY", "BN"), ("DH", "DA")):
        if all(k in o for k in grp):
            inv = [1 / o[k] for k in grp]
            s = sum(inv)
            for k, x in zip(grp, inv):
                p[k] = x / s
    if all(k in p for k in ("H", "D", "A")):
        p["1X"], p["12"], p["X2"] = p["H"] + p["D"], p["H"] + p["A"], p["D"] + p["A"]
        p.setdefault("DH", p["H"] / (p["H"] + p["A"]))
        p.setdefault("DA", p["A"] / (p["H"] + p["A"]))
    return p
