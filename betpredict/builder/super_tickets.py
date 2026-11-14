"""Robotul de bilete mari: în fiecare zi multe bilete de ~1.000, ~5.000 și ~10.000, pe hârtie, ca să vedem câte prindem.

Matematica (arhiva BSD, 4.689 de meciuri cu cote, 2025–2026): marja casei se adună pe fiecare selecție, așa că un bilet de
1.000 din selecții obișnuite are șansa de ~1 la 2.500; nicio piață nu a ieșit constant peste cotă în ambele jumătăți ale
perioadei. Singura pârghie reală e marja: robotul ia selecțiile cu cea mai mare șansă pentru cota lor (−ln p / ln cotă cât mai
mic, cu p = probabilitatea onestă, 90% piață fără marjă) și le preferă pe cele unde Superbet dă peste prețul corect. NG și Sub
2.5 / Sub 1.5 nu intră (în arhivă au ieșit cu 10–20% sub cotă). Biletele sunt variate (alt punct de pornire), un meci apare de
cel mult ``MAX_REUSE`` ori în toată ziua, cel mult 3 meciuri din aceeași ligă pe bilet. Rezultatele: ``stats_doc``."""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

from betpredict.store import repo
from betpredict.timeutil import canon_utc

KIND = "acca_super"
# (variantă, țintă, câte bilete pe zi, selecții min/max)
TIERS = (("s1000", 1000.0, 6, (7, 18)), ("s5000", 5000.0, 5, (9, 22)), ("s10000", 10000.0, 5, (10, 24)))
SPAN = 2.5            # cota biletului: de la țintă până la 2,5 × țintă
LEG_ODDS = (1.25, 2.30)
MIN_EV = -0.05        # sub atât marja e prea mare pe selecție
MAX_REUSE = 3
LEAGUE_CAP = 3
HORIZON_H = 36        # doar meciuri din următoarele 36 de ore: biletul se încheie repede
STAKE_U = 0.02        # ~2 lei la o bancă de 100 de unități
MARKETS = {"1x2", "double_chance", "over_under", "btts", "draw_no_bet"}


def leg_ok(c) -> bool:
    if c.odds_source != "superbet" or c.price_suspect or c.market not in MARKETS:
        return False
    if c.drift is not None and c.drift > 0.05:
        return False
    if not LEG_ODDS[0] <= c.odds <= LEG_ODDS[1]:
        return False
    if c.market == "btts" and c.selection == "NO":
        return False
    if c.market == "over_under" and c.selection == "UNDER" and (c.line or 0) <= 2.5:
        return False
    return c.ev_honest >= MIN_EV


def cost(c) -> float:
    """Cât „costă” selecția din șansa biletului pentru cota pe care o aduce (mai mic = mai bine); EV-ul pozitiv ajută."""
    p = max(1e-6, min(0.99, c.p_honest))
    return -math.log(p) / math.log(c.odds) - 0.5 * max(0.0, c.ev_honest)


def candidates(pool: Sequence, now: datetime) -> List:
    soon = canon_utc((now + timedelta(minutes=10)).isoformat())
    until = canon_utc((now + timedelta(hours=HORIZON_H)).isoformat())
    best: Dict[int, Any] = {}
    for c in pool:
        if not (soon < (c.kickoff_utc or "") <= until) or not leg_ok(c):
            continue
        if c.match_id not in best or cost(c) < cost(best[c.match_id]):
            best[c.match_id] = c
    return sorted(best.values(), key=cost)


def build_one(pool: Sequence, target: float, legs_rng, start: int, used: Dict[int, int]) -> Optional[List]:
    legs: List = []
    leagues: Dict[Any, int] = {}
    total = 1.0
    order = list(pool[start:]) + list(pool[:start])
    for c in order:
        if used.get(c.match_id, 0) >= MAX_REUSE:
            continue
        lg = c.league_id if c.league_id is not None else f"m{c.match_id}"
        if leagues.get(lg, 0) >= LEAGUE_CAP:
            continue
        if total * c.odds > target * SPAN:
            continue  # ar sări peste fereastră: căutăm o selecție mai mică
        legs.append(c)
        leagues[lg] = leagues.get(lg, 0) + 1
        total *= c.odds
        if total >= target and len(legs) >= legs_rng[0]:
            return legs
        if len(legs) >= legs_rng[1]:
            return None
    return None


def build(conn: sqlite3.Connection, today: date, now: Optional[datetime] = None, pool: Optional[Sequence] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    have = conn.execute("SELECT COUNT(*) FROM ticket WHERE kind=? AND day=? AND status!='replaced'", (KIND, today.isoformat())).fetchone()[0]
    if have:
        return {"skipped_existing": have}
    if pool is None:
        from betpredict.builder.pool import load_pool

        pool = load_pool(conn, today, now) + load_pool(conn, today + timedelta(days=1), now)
    cands = candidates(pool, now)
    used: Dict[int, int] = {}
    seen: set = set()
    made: List[Dict[str, Any]] = []
    created = repo.now_iso()
    tries = {v: 0 for v, *_ in TIERS}
    made_n = {v: 0 for v, *_ in TIERS}
    with conn:
        progress = True
        while progress:  # pe rând, câte un bilet din fiecare țintă: când meciurile sunt puține, toate țintele au bilete
            progress = False
            for variant, target, count, rng in TIERS:
                if made_n[variant] >= count or tries[variant] >= count * 4:
                    continue
                step = max(1, len(cands) // (count + 1))
                start = (tries[variant] * step + len(made)) % max(1, len(cands))
                tries[variant] += 1
                progress = True
                legs = build_one(cands, target, rng, start, used)
                if not legs:
                    continue
                key = frozenset((c.match_id, c.market, c.selection) for c in legs)
                if key in seen:
                    continue
                seen.add(key)
                for c in legs:
                    used[c.match_id] = used.get(c.match_id, 0) + 1
                made.append({"variant": variant, **_insert(conn, variant, target, legs, today, created)})
                made_n[variant] += 1
    return {"pool": len(cands), "tickets": len(made), "made": made}


def _insert(conn: sqlite3.Connection, variant: str, target: float, legs: Sequence, day: date, created: str) -> Dict[str, Any]:
    total = math.prod(c.odds for c in legs)
    p = math.prod(min(0.99, c.p_honest) for c in legs)
    over = sum(1 for c in legs if c.ev_honest > 0)
    notes = {"label": f"Robot {int(target):,}+".replace(",", "."), "super": True, "paper": True, "risk_acknowledged": True,
             "reasons": [f"{len(legs)} selecții cu cea mai mare șansă pentru cota lor (marjă mică), din meciurile următoarelor {HORIZON_H} de ore.",
                         f"{over} din {len(legs)} selecții au cota Superbet peste prețul corect.",
                         f"Șansa biletului: ~1 la {max(1, round(1 / p)):,}".replace(",", ".") + f" · cotă {total:,.0f}".replace(",", ".")
                         + ". Miză mică (~2 lei); se urmărește câte bilete ies din multe."]}
    cur = conn.execute(
        """INSERT INTO ticket (kind, variant, created_by, target_odds, total_odds, p_ticket, ev, stake, status, created_at, notes, day)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (KIND, variant, "robot", target, round(total, 2), round(p, 8), round(p * total - 1, 4), STAKE_U, "pending", created,
         json.dumps(notes, ensure_ascii=False), day.isoformat()))
    tid = cur.lastrowid
    for c in sorted(legs, key=lambda c: c.kickoff_utc):
        pid = c.prediction_id if c.prediction_id and c.prediction_id > 0 else None
        conn.execute("INSERT INTO ticket_leg (ticket_id, prediction_id, match_id, market, selection, odds, odds_source) VALUES (?,?,?,?,?,?,?)",
                     (tid, pid, c.match_id, f"{c.market}|{(c.line or 0):g}", c.selection, c.odds, c.odds_source))
    return {"legs": len(legs), "odds": round(total, 2), "p": p}


def stats_doc(conn: sqlite3.Connection, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Pe țintă: bilete terminate, câștigate, câte erau de așteptat după șansă, ROI la miză egală."""
    now = now or datetime.now(timezone.utc)
    out = []
    for variant, target, *_ in TIERS:
        rows = conn.execute("SELECT status, total_odds, p_ticket FROM ticket WHERE kind=? AND variant=? AND status!='replaced'",
                            (KIND, variant)).fetchall()
        done = [r for r in rows if r[0] in ("won", "lost")]
        won = [r for r in done if r[0] == "won"]
        out.append({"variant": variant, "target": target, "n": len(done), "won": len(won),
                    "pending": sum(1 for r in rows if r[0] == "pending"),
                    "expected": round(sum(r[2] or 0 for r in done), 3),
                    "roi": round(sum(r[1] for r in won) / len(done) - 1, 4) if done else None,
                    "best": max((r[1] for r in won), default=None)})
    legs = conn.execute("""SELECT SUM(l.result='won'), SUM(l.result IN ('won','lost')) FROM ticket_leg l JOIN ticket t ON t.id=l.ticket_id
                           WHERE t.kind=? AND t.status!='replaced'""", (KIND,)).fetchone()
    return {"generated_at": canon_utc(now.isoformat()), "tiers": out,
            "leg_hit": round(legs[0] / legs[1], 4) if legs and legs[1] else None, "legs": legs[1] if legs else 0}
