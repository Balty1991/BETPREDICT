"""Rubrica „Test”: cât prindem dacă jucăm MULTE bilete în stilul Supersocial (o singură piață, cotă ~100).

În fiecare zi Robotul face 10–20 de bilete, fiecare dintr-o singură piață care merge pe rezultatele reale (corecția
pieței peste pragul de scoatere, cu destule rezultate) plus R1 cornere 3-6 și 3-7 (fiecare separat). Pe același bilet un meci apare o
singură dată; în toată rubrica un meci apare de cel mult ``MAX_REUSE`` ori. Urmărite pe hârtie (miză 0.1u);
``stats_doc`` arată câte bilete au ieșit, ROI-ul la miză egală și pe ce piețe."""

from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from betpredict.builder import mono_tickets as MT
from betpredict.timeutil import canon_utc

KIND = "acca_test"
MAX_TICKETS, MIN_TICKETS = 20, 10
PER_MARKET = 4
MAX_REUSE = 2
STAKE_U = 0.1


def market_groups(conn: sqlite3.Connection) -> List[Tuple[Tuple[str, ...], str]]:
    """Piețele care merg acum: R1 cornere 3-6/3-7 și piețele Stil cu destule rezultate și corecția peste prag."""
    from betpredict.experimental import supersocial as SS

    # 3-6 și 3-7 separat: pe aceeași cotă totală 3-6 iese la limită mai bine pe model, deci amestecate 3-7 n-ar intra niciodată
    groups: List[Tuple[Tuple[str, ...], str]] = [(("BB_H1C25_U65",), "R1 cornere 3-6"), (("BB_H1C25_U75",), "R1 cornere 3-7")]
    lift = SS.key_lift(conn)
    ok = sorted((k for k, v in lift.items() if (v.get("n") or 0) >= SS.LIFT_MIN_N and (v.get("lift") or 0) >= SS.LIFT_DROP
                 and not SS.is_robot(k) and k not in SS.STIL_BANNED and k not in MT.R1_CORNERS),
                key=lambda k: -lift[k]["lift"])
    groups += [((k,), SS.label(k)) for k in ok]
    return groups


def build(conn: sqlite3.Connection, today: date, now: Optional[datetime] = None, rows: Optional[List[Dict[str, Any]]] = None,
          groups: Optional[List[Tuple[Tuple[str, ...], str]]] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    groups = groups if groups is not None else market_groups(conn)
    # ziua e deja făcută: se completează doar piețele care n-au încă niciun bilet azi (ex. o piață nouă adăugată peste zi)
    used: Dict[Any, int] = defaultdict(int)
    per_group: Dict[str, set] = defaultdict(set)  # meciurile deja folosite pe piața respectivă
    count: Dict[str, int] = defaultdict(int)
    have = 0
    for tid, variant in conn.execute("SELECT id, variant FROM ticket WHERE kind=? AND day=? AND status!='replaced'", (KIND, today.isoformat())).fetchall():
        have += 1
        key = (variant or "").removeprefix("test_").rsplit("_", 1)[0]
        count[key] += 1
        for (mid,) in conn.execute("SELECT match_id FROM ticket_leg WHERE ticket_id=?", (tid,)):
            used[mid] += 1
            per_group[key].add(mid)
    if have:
        groups = [g for g in groups if not count[g[0][0]]]
        if not groups:
            return {"skipped_existing": have}
    if rows is None:
        from betpredict.experimental.supersocial import today_doc

        rows = today_doc(conn, now)["rows"]
    rates: Dict[str, Any] = {}
    pools = [(keys, name, MT.candidates(conn, rows, keys, today, now, rates)) for keys, name in groups]
    made: List[Dict[str, Any]] = []
    limit = MAX_TICKETS if not have else len(groups)  # la completare: câte un bilet pe piața nouă
    with conn:
        progress = True
        while len(made) < limit and progress:  # pe rând, câte un bilet pe piață, ca să fie piețe diferite
            progress = False
            for keys, name, pool in pools:
                if len(made) >= limit or count[keys[0]] >= PER_MARKET or (have and count[keys[0]]):
                    continue
                banned = per_group[keys[0]] | {m for m, n in used.items() if n >= MAX_REUSE}
                legs = MT.pick(pool, banned)
                if not legs:
                    continue
                count[keys[0]] += 1
                p = math.prod(l["p_mix"] for l in legs)
                total = math.prod(l["odds"] for l in legs)
                notes = {"label": f"Test · {name}", "test": True, "mono": True, "paper": True, "risk_acknowledged": True,
                         "reasons": [f"Rubrica Test: multe bilete pe zi în stilul Supersocial, o singură piață ({name}), {len(legs)} meciuri.",
                                     "Meciurile unde piața iese cel mai des (șansa pe meci și liga); un meci apare de cel mult "
                                     f"{MAX_REUSE} ori în toată rubrica.",
                                     f"Șansa estimată: {p:.1%} · cotă {total:.2f}. Miză {STAKE_U:g}u (urmărit pe hârtie)."]}
                made.append({"key": keys[0], **MT.insert(conn, KIND, f"test_{keys[0]}_{count[keys[0]]}", today, legs, notes, stake=STAKE_U)})
                for l in legs:
                    used[l["match_id"]] += 1
                    per_group[keys[0]].add(l["match_id"])
                progress = True
    return {"tickets": made, "markets": len(pools), "below_min": len(made) < MIN_TICKETS}


def stats_doc(conn: sqlite3.Connection, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Randamentul rubricii Test: bilete câștigate, ROI la miză egală (1 pe bilet), pe piață și pe zi."""
    now = now or datetime.now(timezone.utc)
    rows = conn.execute("SELECT id, variant, day, status, total_odds, notes FROM ticket WHERE kind=? AND status!='replaced'", (KIND,)).fetchall()
    by_m: Dict[str, Dict[str, Any]] = {}
    by_d: Dict[str, Dict[str, Any]] = {}
    tot = {"n": 0, "won": 0, "lost": 0, "pending": 0, "ret": 0.0}
    legs_won = legs_n = 0
    for t in rows:
        key = (t[1] or "").removeprefix("test_").rsplit("_", 1)[0]
        for bucket in (tot, by_m.setdefault(key, {"key": key, "n": 0, "won": 0, "lost": 0, "pending": 0, "ret": 0.0}),
                       by_d.setdefault(t[2], {"day": t[2], "n": 0, "won": 0, "lost": 0, "pending": 0, "ret": 0.0})):
            if t[3] == "pending":
                bucket["pending"] += 1
                continue
            if t[3] not in ("won", "lost"):
                continue
            bucket["n"] += 1
            bucket["won" if t[3] == "won" else "lost"] += 1
            if t[3] == "won":
                bucket["ret"] += t[4] or 0
        for r in conn.execute("SELECT result FROM ticket_leg WHERE ticket_id=? AND result IN ('won','lost')", (t[0],)):
            legs_n += 1
            legs_won += r[0] == "won"

    def fin(b: Dict[str, Any]) -> Dict[str, Any]:
        b = dict(b)
        b["roi"] = round(b.pop("ret") / b["n"] - 1, 4) if b["n"] else None
        return b

    from betpredict.experimental.supersocial import label

    markets = [{**fin(b), "label": label(b["key"])} for b in by_m.values()]
    markets.sort(key=lambda b: (-(b["won"]), -(b["n"])))
    return {"generated_at": canon_utc(now.isoformat()), "summary": {**fin(tot), "legs": legs_n, "legs_won": legs_won,
            "leg_hit": round(legs_won / legs_n, 4) if legs_n else None},
            "markets": markets, "days": sorted((fin(b) for b in by_d.values()), key=lambda b: b["day"], reverse=True)[:30]}
