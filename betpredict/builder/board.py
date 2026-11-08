"""Acumulator scurt, nu loterie.

Regula (jurnal 09.10–08.11.2026 + grila de laborator):
* doar 1X2 (1 sau 2) și GG, cotă Superbet 1,95–2,40 — banda în care modelul nu e umflat;
* modelul și piața fără marjă diferă cu cel mult 4 puncte;
* prețul Superbet e cu 2–15% peste piața fără marjă (sub 2% nu e edge, peste 15% e cotă suspectă);
* un meci intră în cel mult un bilet, ca un rezultat să nu doboare tot setul;
* bilet de joc: 2–4 selecții, cotă totală 4–12;
* opțional, cel mult două bilete medii: 6–8 selecții, cotă 200–450, miză un sfert;
* în total 0–10 bilete, până la 15 doar dacă mai rămân picioare cu edge ≥ 3%.

Loteriile 50–2000, stilul supersocial, Calea 100+, mono, test și piramidele nu se mai generează
din ``build_horizon``. La prima rulare după schimbare, jurnalul de bilete și pistele de piramidă
se golesc o singură dată, ca statistica să pornească de la zero.
"""

from __future__ import annotations

import math
import sqlite3
from datetime import date, datetime, timedelta
from itertools import combinations
from typing import Any, Dict, List, Optional, Sequence, Tuple

from betpredict.builder.pool import Cand, load_pool
from betpredict.builder.v4tickets import insert_ticket, ticket_stats
from betpredict.store import repo

RESET_KEY = "tickets.board_reset_2026_11_08"
KIND = "acca_board"

ODDS = (1.95, 2.40)
P_BAND = (0.43, 0.52)
AGREE = 0.04
EDGE_MIN = 0.02
EDGE_STALE = 0.15
DRIFT_MAX = 0.08
EDGE_STRICT = 0.03

PLAY_LEGS = (2, 4)
PLAY_TOTAL = (4.0, 12.0)
PLAY_TARGET = 8.0
PLAY_STAKE = 1.0

MED_LEGS = (6, 8)
MED_TOTAL = (200.0, 450.0)
MED_TARGET = 300.0
MED_STAKE = 0.25
MED_MAX = 2

SOFT_CAP = 10
HARD_CAP = 15
PLAY_FIRST = 8


def market_edge(c: Cand) -> float:
    """Cât plătește Superbet peste probabilitatea fără marjă. -1 dacă nu avem piață."""
    if c.p_market is None or not (0.0 < c.p_market < 1.0) or c.odds <= 1:
        return -1.0
    return c.odds * c.p_market - 1.0


def qualifies(c: Cand) -> bool:
    """Piciorul poate intra pe un bilet. Nu relaxăm pragurile ca să umplem lista."""
    if c.price_suspect or c.odds_source != "superbet":
        return False
    if c.market == "1x2" and c.selection in ("HOME", "AWAY"):
        pass
    elif c.market == "btts" and c.selection == "YES":
        pass
    else:
        return False
    if not (ODDS[0] <= c.odds <= ODDS[1]):
        return False
    if c.p_market is None or abs(c.p - c.p_market) > AGREE:
        return False
    if not (P_BAND[0] <= c.p_honest <= P_BAND[1]):
        return False
    if c.drift is not None and c.drift > DRIFT_MAX:
        return False
    edge = market_edge(c)
    return EDGE_MIN <= edge <= EDGE_STALE


def best_per_match(cands: Sequence[Cand]) -> List[Cand]:
    best: Dict[int, Cand] = {}
    for c in cands:
        if not qualifies(c):
            continue
        cur = best.get(c.match_id)
        if cur is None or (market_edge(c), c.p_honest) > (market_edge(cur), cur.p_honest):
            best[c.match_id] = c
    return sorted(best.values(), key=lambda c: (market_edge(c), c.p_honest), reverse=True)


def _search(cands: Sequence[Cand], n: int, band: Tuple[float, float], target: float, top: int = 28) -> Optional[List[Cand]]:
    pool = list(cands[:top])
    if len(pool) < n:
        return None
    best: Optional[List[Cand]] = None
    best_key: Optional[Tuple[float, float, float]] = None
    for legs in combinations(pool, n):
        if len({c.league_id for c in legs}) < n:
            continue
        total = math.prod(c.odds for c in legs)
        if not (band[0] <= total <= band[1]):
            continue
        edge = sum(market_edge(c) for c in legs)
        chance = math.prod(c.p_honest for c in legs)
        key = (edge, chance, -abs(math.log(total) - math.log(target)))
        if best_key is None or key > best_key:
            best_key, best = key, list(legs)
    return best


def pick_play(cands: Sequence[Cand], strict: bool) -> Optional[List[Cand]]:
    order = (3, 2, 4)
    for n in order:
        if not (PLAY_LEGS[0] <= n <= PLAY_LEGS[1]):
            continue
        legs = _search(cands, n, PLAY_TOTAL, PLAY_TARGET)
        if not legs:
            continue
        if strict and min(market_edge(c) for c in legs) < EDGE_STRICT:
            continue
        return sorted(legs, key=lambda c: c.kickoff_utc)
    return None


def pick_medium(cands: Sequence[Cand]) -> Optional[List[Cand]]:
    for n in (7, 6, 8):
        legs = _search(cands, n, MED_TOTAL, MED_TARGET, top=18)
        if legs:
            return sorted(legs, key=lambda c: c.kickoff_utc)
    return None


def _drop(cands: List[Cand], legs: Sequence[Cand]) -> List[Cand]:
    gone = {c.match_id for c in legs}
    return [c for c in cands if c.match_id not in gone]


def plan(cands: Sequence[Cand]) -> List[Tuple[str, List[Cand]]]:
    """Lista de bilete, fără meciuri comune. Goale dacă nu sunt destule picioare bune."""
    left = list(cands)
    out: List[Tuple[str, List[Cand]]] = []
    while len(out) < PLAY_FIRST:
        legs = pick_play(left, strict=False)
        if not legs:
            break
        out.append((f"joc_{len(legs)}", legs))
        left = _drop(left, legs)
    med = 0
    while med < MED_MAX and len(out) < HARD_CAP:
        legs = pick_medium(left)
        if not legs:
            break
        out.append((f"mediu_{len(legs)}", legs))
        left = _drop(left, legs)
        med += 1
    while len(out) < HARD_CAP:
        if len(out) >= SOFT_CAP:
            legs = pick_play(left, strict=True)
        else:
            legs = pick_play(left, strict=False)
        if not legs:
            break
        out.append((f"joc_{len(legs)}", legs))
        left = _drop(left, legs)
    return out


def purge_legacy_once(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Șterge biletele și pistele de piramidă deja făcute. O singură dată, marcat în ingest_state.

    Pistele 1.40 / 1.20 / mix au tabele proprii cu ``ticket_id`` spre ``ticket``. Le golim pe toate,
    altfel ștergerea biletelor pică pe cheie străină și jurnalul vechi rămâne în statistici.
    """
    if repo.get_state(conn, RESET_KEY):
        return {"skipped": True}
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    steps = [n for n in tables if n == "pyramid_step" or n.endswith("_step")]
    runs = [n for n in tables if n == "pyramid_run" or n.endswith("_run")]
    conn.commit()
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        with conn:
            n_t = conn.execute("SELECT COUNT(*) FROM ticket").fetchone()[0]
            n_l = conn.execute("SELECT COUNT(*) FROM ticket_leg").fetchone()[0]
            for name in steps + runs:
                conn.execute(f"DELETE FROM {name}")
            conn.execute("DELETE FROM ticket_leg")
            conn.execute("DELETE FROM ticket")
            repo.set_state(conn, RESET_KEY, repo.now_iso())
    finally:
        conn.execute("PRAGMA foreign_keys=ON")
    return {"skipped": False, "tickets": n_t, "legs": n_l, "pyramid_steps": len(steps), "pyramid_runs": len(runs)}


def _replace_pending(conn: sqlite3.Connection, today: date) -> int:
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM ticket WHERE kind=? AND status='pending' AND day>=?",
        (KIND, today.isoformat()))]
    for i in ids:
        conn.execute("UPDATE ticket SET status='replaced' WHERE id=?", (i,))
    return len(ids)


def build_board(conn: sqlite3.Connection, today: date, days_ahead: int = 6,
                now: Optional[datetime] = None, rebuild: bool = False) -> Dict[str, Any]:
    """Bilete pending pe orizontul de zile. Refresh-ul orar nu le dublează; rularea zilnică le reface."""
    pending = conn.execute(
        "SELECT COUNT(*) FROM ticket WHERE kind=? AND status='pending' AND day>=?",
        (KIND, today.isoformat())).fetchone()[0]
    if pending and not rebuild:
        return {"skipped_existing": pending, "tickets": 0}
    pool: List[Cand] = []
    for i in range(days_ahead + 1):
        pool.extend(load_pool(conn, today + timedelta(days=i), now))
    ranked = best_per_match(pool)
    made = plan(ranked)
    created = repo.now_iso()
    ids: List[int] = []
    with conn:
        replaced = _replace_pending(conn, today)
        for variant, legs in made:
            medium = variant.startswith("mediu_")
            total, p, ev = ticket_stats(legs)
            stake = MED_STAKE if medium else PLAY_STAKE
            n = len(legs)
            reasons = [
                f"{'Mediu' if medium else 'Joc'}: {n} selecții, ligi diferite, cotă {total:.2f}",
                "Fiecare picior: 1X2 sau GG, cotă Superbet 1,95–2,40, modelul la cel mult 4pp de piață",
                f"Edge mediu față de piața fără marjă {sum(market_edge(c) for c in legs) / n:+.1%} · șansă onestă {p:.1%}",
                "Un meci, un bilet. Fără loterie și fără 20 de favorite.",
            ]
            tid = insert_ticket(
                conn, KIND, variant, round(total, 2), legs, stake, reasons, today, created, {},
                {"honest": True, "risk_acknowledged": not medium, "informational": medium,
                 "label": ("Mediu ~300 · " if medium else "Acumulator scurt · ") + f"{n} selecții",
                 "board": "v1"})
            if tid:
                ids.append(tid)
    return {"tickets": len(ids), "ids": ids, "pool": len(pool), "qualified": len(ranked),
            "replaced_pending": replaced, "play": sum(1 for v, _ in made if v.startswith("joc_")),
            "medium": sum(1 for v, _ in made if v.startswith("mediu_"))}
