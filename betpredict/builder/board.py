"""Acumulatori la cotă 100, 1.000 și 10.000.

Din jurnalul Superbet (09.10–08.11.2026), în banda 1,80–2,50:
* GG/NU la 1,90–2,10 și 2,30–2,50 e singura piață pe plus;
* oaspeții (1X2) de la 2,00 în sus sunt pe zero;
* gazdele, peste 2,5, DNB și șansa dublă sunt pe minus.

100 se face din 6–8 single-uri în banda asta. 1.000 și 10.000 se fac din Bet Builder
Superbet (1X2 sau șansă dublă cu goluri / GG / interval), cotă 2,55–4,50, doar dacă
probabilitatea Poisson a robotului e la cel mult 12% de preț. Un meci, un bilet.
Maxim 10 bilete, până la 15 doar din piețele pe plus. Miza e mică și fixă.

La prima rulare se șterg biletele și pistele vechi, o singură dată.
"""

from __future__ import annotations

import math
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from betpredict.builder.pool import Cand, load_pool
from betpredict.builder.v4tickets import insert_ticket, ticket_stats
from betpredict.store import repo

RESET_KEY = "tickets.board_reset_2026_11_08"
RESET_FLAG = "ticket_reset.flag"

# (variantă, fel, țintă, selecții, bandă cotă, miză în unități)
TIERS: Tuple[Tuple[str, str, float, Tuple[int, int], Tuple[float, float], float], ...] = (
    ("t100", "acca_100", 100.0, (6, 8), (100.0, 180.0), 0.20, "short"),
    ("t1000", "acca_1000", 1000.0, (5, 8), (1000.0, 2800.0), 0.05, "long"),
    ("t10000", "acca_10000", 10000.0, (6, 10), (10000.0, 28000.0), 0.02, "long"),
)
# întâi cotele mari (au nevoie de Bet Builder), apoi 100 din single-uri
FILL = ("t10000", "t1000", "t100", "t1000", "t100", "t10000", "t100", "t1000")
SOFT_CAP, HARD_CAP = 10, 15
AGREE = 0.08
LEAGUE_CAP = 2


def _priority(c: Cand) -> Optional[int]:
    """3 = piață pe plus, 2 = pe zero, 1 = aproape de zero, 0 = umplutură. None = nu intră."""
    if c.price_suspect or c.odds_source != "superbet" or c.odds <= 1:
        return None
    if c.drift is not None and c.drift > 0.08:
        return None
    if c.p_market is not None and abs(c.p - c.p_market) > AGREE:
        return None
    if c.market == "bb":
        ev = c.p * c.odds - 1
        if not (2.20 <= c.odds <= 4.50) or ev < -0.12 or ev > 0.12:
            return None
        return 2 if ev >= -0.04 else 1
    o = c.odds
    if c.market == "btts" and c.selection == "NO" and (1.90 <= o <= 2.10 or 2.30 <= o <= 2.50):
        return 3
    if c.market == "1x2" and c.selection == "AWAY" and 2.00 <= o <= 2.50:
        return 2
    if c.market == "btts" and c.selection == "YES" and 1.85 <= o <= 2.25:
        return 1
    if c.market == "1x2" and c.selection == "HOME" and 2.00 <= o <= 2.40:
        return 0
    return None


def qualifies(c: Cand) -> bool:
    return _priority(c) is not None


def best_per_match(cands: Sequence[Cand]) -> List[Cand]:
    best: Dict[int, Cand] = {}
    for c in cands:
        p = _priority(c)
        if p is None:
            continue
        cur = best.get(c.match_id)
        if cur is None or (p, -abs((c.p_market or c.p) - c.p)) > (_priority(cur), -abs((cur.p_market or cur.p) - cur.p)):
            best[c.match_id] = c
    return sorted(best.values(), key=lambda c: (_priority(c) or 0, c.odds), reverse=True)


def _league(c: Cand):
    return c.league_id if c.league_id is not None else f"m{c.match_id}"


def _beam(cands: Sequence[Cand], n_min: int, n_max: int, band: Tuple[float, float], target: float) -> Optional[List[Cand]]:
    """Construiește un bilet din selecțiile a căror cotă e aproape de cota ideală pentru țintă.

    Cele mai lungi bet builder-e (4,50) sar peste 1.000 și peste 10.000 deopotrivă, așa că
    nu le preferăm doar pentru că au cotă mare.
    """
    if len(cands) < n_min:
        return None
    ideal = target ** (1.0 / ((n_min + n_max) / 2.0))
    pool = sorted(cands, key=lambda c: (abs(math.log(c.odds) - math.log(ideal)), -(_priority(c) or 0)))
    best: Optional[Tuple[float, List[Cand]]] = None
    for start in range(min(16, len(pool))):
        legs: List[Cand] = []
        leagues: Dict[Any, int] = {}
        order = pool[start:] + pool[:start]
        for c in order:
            if len(legs) >= n_max:
                break
            lg = _league(c)
            if leagues.get(lg, 0) >= LEAGUE_CAP:
                continue
            prod = math.prod(x.odds for x in legs) * c.odds if legs else c.odds
            if prod > band[1]:
                continue
            legs.append(c)
            leagues[lg] = leagues.get(lg, 0) + 1
            if len(legs) >= n_min and prod >= band[0]:
                key = -abs(math.log(prod) - math.log(target))
                if best is None or key > best[0]:
                    best = (key, list(legs))
                break
    return None if best is None else sorted(best[1], key=lambda c: c.kickoff_utc)


def _tier(name: str):
    return next(t for t in TIERS if t[0] == name)


def plan(cands: Sequence[Cand]) -> List[Tuple[str, List[Cand]]]:
    """Până la 10 bilete (15 dacă mai rămân doar piețe pe plus), fără meci comun.

    100 se face din single-uri (și bet builder scurt). 1.000 și 10.000 din bet builder,
    unde un meci are cotă 2,60–4,50.
    """
    short = [c for c in cands if c.market != "bb" or c.odds <= 2.55]
    long = [c for c in cands if c.market == "bb" and c.odds >= 2.55]
    out: List[Tuple[str, List[Cand]]] = []
    wanted = [t[0] for t in reversed(TIERS)] + list(FILL)
    for name in wanted:
        if len(out) >= HARD_CAP:
            break
        if len(out) >= SOFT_CAP:
            # peste 10 doar dacă tot biletul e din piețele care au ieșit pe plus sau pe zero
            pass
        variant, _kind, target, ns, band, _stake, pool_kind = _tier(name)
        source = short if pool_kind == "short" else long
        legs = _beam(source, ns[0], ns[1], band, target)
        if not legs:
            continue
        if len(out) >= SOFT_CAP and min(_priority(c) or 0 for c in legs) < 2:
            continue
        out.append((variant, legs))
        gone = {c.match_id for c in legs}
        short = [c for c in short if c.match_id not in gone]
        long = [c for c in long if c.match_id not in gone]
    return out


def _flag(conn: sqlite3.Connection) -> None:
    row = conn.execute("PRAGMA database_list").fetchone()
    path = row[2] if row and row[2] else ""
    if path and path != ":memory:":
        Path(path).with_name(RESET_FLAG).write_text(repo.now_iso(), encoding="utf-8")


def purge_legacy_once(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Șterge biletele și pistele de piramidă deja făcute. O singură dată.

    Pistele paralele au ``ticket_id`` spre ``ticket``. Le golim pe toate, altfel ștergerea
    pică pe cheie străină. Scrie și un marcaj lângă bază, ca publicarea să accepte resetul.
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
            _flag(conn)
    finally:
        conn.execute("PRAGMA foreign_keys=ON")
    return {"skipped": False, "tickets": n_t, "legs": n_l, "pyramid_steps": len(steps), "pyramid_runs": len(runs)}


def _pending(conn: sqlite3.Connection, today: date) -> List[int]:
    return [r[0] for r in conn.execute(
        "SELECT id FROM ticket WHERE variant IN ('t100','t1000','t10000') AND status='pending' AND day>=?",
        (today.isoformat(),))]


def build_board(conn: sqlite3.Connection, today: date, days_ahead: int = 6,
                now: Optional[datetime] = None, rebuild: bool = False) -> Dict[str, Any]:
    """Bilete pending pe orizontul de zile. Refresh-ul orar nu le dublează; rularea zilnică le reface."""
    pending = _pending(conn, today)
    if pending and not rebuild:
        return {"skipped_existing": len(pending), "tickets": 0}
    pool: List[Cand] = []
    for i in range(days_ahead + 1):
        pool.extend(load_pool(conn, today + timedelta(days=i), now))
    ranked = best_per_match(pool)
    try:
        from betpredict.builder.bb_legs import load_builders

        builders = load_builders(conn, today, days_ahead, now)
    except sqlite3.Error:
        builders = []
    taken = {c.match_id for c in ranked}
    # un meci cu single bun rămâne single; bet builder-ul umple meciurile fără single în bandă
    ranked.extend(b for b in builders if b.match_id not in taken)
    made = plan(ranked)
    created = repo.now_iso()
    ids: List[int] = []
    with conn:
        for i in _pending(conn, today):
            conn.execute("UPDATE ticket SET status='replaced' WHERE id=?", (i,))
        for variant, legs in made:
            spec = _tier(variant)
            total, p, ev = ticket_stats(legs)
            n = len(legs)
            reasons = [
                f"Cotă {spec[2]:g}: {n} selecții, ligi diferite, produs {total:.0f}",
                "Piețe: GG/NU și oaspeți din jurnal; Bet Builder Superbet (1X2/șansă dublă cu goluri sau GG) unde modelul e la ±12% de cotă",
                "Fără peste 2,5, fără șansă dublă, fără favorite scurte. Un meci, un bilet.",
                f"Șansă onestă {p:.2%} · miză fixă {spec[5]:g}u. Nu e un bilet de bancă.",
            ]
            tid = insert_ticket(
                conn, spec[1], variant, spec[2], legs, spec[5], reasons, today, created, {},
                {"honest": True, "risk_acknowledged": True, "lottery": True, "board": "v2",
                 "label": f"Cotă {int(spec[2]):,}".replace(",", ".")})
            if tid:
                ids.append(tid)
    counts = {name: sum(1 for v, _ in made if v == name) for name in ("t100", "t1000", "t10000")}
    return {"tickets": len(ids), "ids": ids, "pool": len(pool), "qualified": len(ranked),
            "replaced_pending": len(pending), **counts}
