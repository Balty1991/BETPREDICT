"""Bilete din combinații cu cornere, publicate la Bilete.

Scurt: 10–12 selecții, cotă 1,30–1,80. Lung: 14–16, doar dacă mai încape.
Un meci stă pe cel mult 4 bilete. Două bilete au cel mult 4 meciuri la fel.
"""

from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from betpredict.store import repo

KIND = "acca_corners"
MAX_N = 15
MAX_SHARE = 4


def _bonus(n: int) -> float:
    if n < 3:
        return 0.0
    if n >= 25:
        return 1.0
    table = {3: 0.03, 4: 0.04, 5: 0.06, 6: 0.08, 7: 0.10}
    return table.get(n, min(1.0, 0.15 + (n - 8) * 0.05))


def _corner(label: str, raw: str) -> bool:
    return "corner" in f"{label} {raw}".lower()


def _pool(conn, now: str, hi: float, until: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """SELECT b.match_id, b.label, b.p_joint, b.sb_price, b.legs_json, m.kickoff_utc
           FROM bb_suggestion b JOIN match m ON m.id = b.match_id
           WHERE b.source='superbet' AND b.sb_price>=1.30 AND b.sb_price<=?
             AND b.result IS NULL AND m.kickoff_utc>? AND m.kickoff_utc<?""",
        (hi, now, until)).fetchall()
    best: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        raw = r["legs_json"] or ""
        if not _corner(r["label"] or "", raw):
            continue
        try:
            sb = (json.loads(raw).get("superbet") or {})
        except ValueError:
            continue
        if not sb.get("market") or not sb.get("outcome"):
            continue
        cur = best.get(r["match_id"])
        if cur is None or abs(r["sb_price"] - 1.5) < abs(cur["odds"] - 1.5):
            best[r["match_id"]] = {
                "match_id": r["match_id"], "label": r["label"], "p": r["p_joint"], "odds": r["sb_price"],
                "kickoff": r["kickoff_utc"], "market": sb["market"], "outcome": sb["outcome"],
            }
    return list(best.values())


def _grab(pool: List[Dict[str, Any]], uses: Dict[int, int], made: List[List[Dict[str, Any]]],
          nmin: int, nmax: int, stop: float, cap: float, use_cap: int,
          priority: Optional[Dict[int, int]] = None) -> Optional[List[Dict[str, Any]]]:
    def rank(c: Dict[str, Any]):
        on = sum(1 for prev in made if any(x["match_id"] == c["match_id"] for x in prev))
        pref = (priority or {}).get(c["match_id"], 0)
        return (uses.get(c["match_id"], 0), on, pref, c["kickoff"])

    take: List[Dict[str, Any]] = []
    prod = 1.0
    for c in sorted(pool, key=rank):
        if uses.get(c["match_id"], 0) >= use_cap or len(take) >= nmax:
            continue
        ids = {x["match_id"] for x in take}
        ids.add(c["match_id"])
        if any(sum(x["match_id"] in ids for x in prev) > MAX_SHARE for prev in made):
            continue
        nxt = prod * c["odds"]
        if len(take) >= nmin and prod >= stop:
            break
        if len(take) >= nmin and nxt > cap:
            continue
        take.append(c)
        prod = nxt
    return take if len(take) >= nmin else None


def _pack(pool: List[Dict[str, Any]], seed: int) -> List[tuple]:
    """10 selecții. Un meci pe cel mult 4 bilete, două bilete au cel mult 4 meciuri la fel."""
    rng = random.Random(seed)
    made: List[List[Dict[str, Any]]] = []
    uses: Dict[int, int] = {}
    for _ in range(20):
        order = pool[:]
        rng.shuffle(order)
        order.sort(key=lambda c: uses.get(c["match_id"], 0))
        take: List[Dict[str, Any]] = []
        for c in order:
            if uses.get(c["match_id"], 0) >= 4:
                continue
            ids = {x["match_id"] for x in take}
            ids.add(c["match_id"])
            if any(sum(x["match_id"] in ids for x in prev) > MAX_SHARE for prev in made):
                continue
            take.append(c)
            if len(take) >= 10:
                break
        if len(take) < 10:
            break
        made.append(take)
        for c in take:
            uses[c["match_id"]] = uses.get(c["match_id"], 0) + 1
    return [("short", legs) for legs in made]


def _best_plan(pool: List[Dict[str, Any]], wide: List[Dict[str, Any]]) -> List[tuple]:
    best: List[tuple] = []
    for seed in range(40):
        plan = _pack(pool, seed)
        if len(plan) > len(best):
            best = plan
    uses: Dict[int, int] = {}
    made = [legs for _, legs in best]
    for legs in made:
        for c in legs:
            uses[c["match_id"]] = uses.get(c["match_id"], 0) + 1
    priority = {c["match_id"]: i for i, c in enumerate(sorted(wide, key=lambda c: c["kickoff"]))}
    long = _grab(wide, uses, made, 14, 16, 400, 8000, 4, priority)
    if long and len(best) < MAX_N:
        best.append(("long", long))
    return best[:MAX_N]


def _fp(shape: str, legs: List[Dict[str, Any]]) -> str:
    return shape + ":" + ",".join(str(c["match_id"]) for c in sorted(legs, key=lambda c: c["match_id"]))


def build(conn, today: date) -> Dict[str, int]:
    """Înlocuiește biletele de cornere încă neîncepute. Cele deja începute rămân."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    until = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S")
    short_pool = _pool(conn, now, 1.80, until)
    wide_pool = _pool(conn, now, 2.50, until)
    planned = _best_plan(short_pool, wide_pool)
    keep = {_fp(s, legs) for s, legs in planned}
    kept = 0
    with conn:
        for t in conn.execute("SELECT id, notes FROM ticket WHERE kind=? AND status='pending'", (KIND,)).fetchall():
            try:
                fp = (json.loads(t["notes"] or "{}")).get("fp")
            except ValueError:
                fp = None
            if fp in keep:
                kept += 1
                keep.discard(fp)
                continue
            conn.execute("DELETE FROM ticket_leg WHERE ticket_id=?", (t["id"],))
            conn.execute("DELETE FROM ticket WHERE id=?", (t["id"],))
        inserted = 0
        for shape, legs in planned:
            fp = _fp(shape, legs)
            if fp not in keep:
                continue
            total = 1.0
            p = 1.0
            for c in legs:
                total *= c["odds"]
                p *= c["p"] or 0.0
            bonus = _bonus(len(legs))
            back = total + bonus * (total - 1)
            over = any(c["odds"] > 1.80 for c in legs)
            label = f"Cornere {'scurt' if shape == 'short' else 'lung'} · cotă {round(total)}"
            why = (f"{len(legs)} cornere, cotă 1,30–1,80. Pe 798 de meciuri banda asta a fost pe plus circa 3–5%."
                   if shape == "short" else
                   f"{len(legs)} cornere, mai multe meciuri.{' Are și cote peste 1,80.' if over else ''}")
            notes = {
                "paper": True, "experimental": True, "risk_acknowledged": True,
                "tier": "short" if shape == "short" else "lung",
                "label": label, "fp": fp, "superbonus": round(bonus * 100),
                "reasons": [why, f"Superbonus {round(bonus * 100)}% din profit. La 2 lei, plata cu bonus e cam {round(2 * back)} lei.",
                            "Nu e marcat plasat. Îl pui tu, dacă vrei. Un meci e pe cel mult 4 bilete."],
                "leg_reasons": [{"m": c["match_id"], "s": f"{c['market']}|{c['outcome']}",
                                 "r": [f"Șansă {round((c['p'] or 0) * 100)}% · cotă Superbet {c['odds']}"]} for c in legs],
            }
            cur = conn.execute(
                """INSERT INTO ticket (kind, variant, created_by, target_odds, total_odds, p_ticket, ev, stake, status, created_at, notes, day)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (KIND, shape, "robot", None, round(total, 2), round(p, 6), round(p * back - 1, 4), None, "pending",
                 repo.now_iso(), json.dumps(notes, ensure_ascii=False), today.isoformat()))
            for c in sorted(legs, key=lambda c: c["kickoff"]):
                conn.execute(
                    "INSERT INTO ticket_leg (ticket_id, prediction_id, match_id, market, selection, odds, odds_source) VALUES (?,?,?,?,?,?,?)",
                    (cur.lastrowid, None, c["match_id"], "bb", f"{c['market']}|{c['outcome']}", c["odds"], "superbet"))
            inserted += 1
    return {"pool": len(short_pool), "wide": len(wide_pool), "kept": kept, "inserted": inserted, "planned": len(planned)}


def settle_legs(conn) -> int:
    n = 0
    rows = conn.execute(
        """SELECT tl.id, tl.selection, b.result, b.legs_json
           FROM ticket_leg tl JOIN ticket t ON t.id=tl.ticket_id AND t.kind=?
           JOIN bb_suggestion b ON b.match_id=tl.match_id
           WHERE tl.result IS NULL AND b.result IN ('won','lost')""",
        (KIND,)).fetchall()
    for r in rows:
        try:
            sb = json.loads(r["legs_json"] or "{}").get("superbet") or {}
        except ValueError:
            continue
        if f"{sb.get('market')}|{sb.get('outcome')}" != r["selection"]:
            continue
        conn.execute("UPDATE ticket_leg SET result=? WHERE id=?", (r["result"], r["id"]))
        n += 1
    return n
