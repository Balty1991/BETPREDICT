"""Bilete din combinații cu cornere, publicate la Bilete.

Cele de 4 și de 6 meciuri nu împart meciuri: astea se joacă.
Cele mari (500, 1.000, 10.000) au cel mult 5 meciuri în comun între ele.
Ale 5 sunt cele cu șansa cea mai mare. Restul evenimentelor sunt diferite.
Dacă bazinul nu ajunge, se publică mai puține bilete, nu copii.
"""

from __future__ import annotations

import json
import random
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from betpredict.store import repo

KIND = "acca_corners"
MAX_N = 15
SHARE = 5
_TARGET = {"500": 500.0, "1000": 1000.0, "10000": 10000.0}
# Cele mai grele întâi, ca să prindă cota din cât mai puține meciuri și să lase restul altora.
_RECIPES = (
    ("10000", "1000", "500", "500"),
    ("10000", "1000", "500"),
    ("10000", "500", "500"),
    ("10000", "1000"),
    ("10000", "500"),
    ("1000", "1000", "500", "500"),
    ("1000", "1000", "500"),
    ("1000", "500", "500"),
    ("1000", "1000"),
    ("1000", "500"),
    ("10000",),
    ("500", "500", "500"),
    ("500", "500"),
    ("500",),
)


def _bonus(n: int) -> float:
    if n < 3:
        return 0.0
    if n >= 25:
        return 1.0
    table = {3: 0.03, 4: 0.04, 5: 0.06, 6: 0.08, 7: 0.10}
    return table.get(n, min(1.0, 0.15 + (n - 8) * 0.05))


def _corner(label: str, raw: str) -> bool:
    return "corner" in f"{label} {raw}".lower()


_COMBO = re.compile(r"peste 0\.5 goluri; peste (6\.5|7\.5) cornere")


def offer_combo_rows(conn, lo: str, hi: str, price_lo: float = 1.25, price_hi: float = 2.20) -> List[Dict[str, Any]]:
    """Combinația gata făcută din oferta Superbet: „Peste 0.5 goluri; Peste 7.5 (sau 6.5) cornere”.

    Sugestiile Bet Builder (bb_suggestion) o au doar la câteva meciuri (17.11: 5), oferta citită la mult mai multe (26).
    Aceleași câmpuri ca rândurile din bb_suggestion. Șansa e cea din preț (1 / cotă, cu ~4% marjă): fără avantaj inventat."""
    try:
        rows = conn.execute(
            """SELECT o.match_id, o.market_name, o.outcome, MAX(o.price) AS price,
                      m.kickoff_utc, m.home_name, m.away_name, m.league_id, l.name AS league
               FROM sb_offer o JOIN match m ON m.id = o.match_id LEFT JOIN league l ON l.id = m.league_id
               WHERE m.kickoff_utc>? AND m.kickoff_utc<? AND o.price>=? AND o.price<=?
                 AND lower(o.market_name) LIKE '%gol%' AND lower(o.market_name) LIKE '%cornere%'
               GROUP BY o.match_id, o.market_name, o.outcome""",
            (lo, hi, price_lo, price_hi)).fetchall()
    except Exception:  # noqa: BLE001 — fără ofertă citită
        return []
    out = []
    for r in rows:
        name, outcome = r["market_name"] or "", r["outcome"] or ""
        text = name if name.strip().lower() == outcome.strip().lower() else f"{name} {outcome}"
        t = re.sub(r"\s+", " ", text.lower().replace(",", ".").strip())
        if not _COMBO.fullmatch(t):
            continue
        price = float(r["price"])
        out.append({"match_id": r["match_id"], "label": text, "p_joint": round(1 / (price * 1.04), 4), "sb_price": price,
                    "legs_json": json.dumps({"superbet": {"market": name, "outcome": outcome}}, ensure_ascii=False),
                    "kickoff_utc": r["kickoff_utc"], "home_name": r["home_name"], "away_name": r["away_name"],
                    "league_id": r["league_id"], "league": r["league"], "from_offer": True})
    return out


def _pool(conn, now: str, hi: float, until: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """SELECT b.match_id, b.label, b.p_joint, b.sb_price, b.legs_json, m.kickoff_utc
           FROM bb_suggestion b JOIN match m ON m.id = b.match_id
           WHERE b.source='superbet' AND b.sb_price>=1.30 AND b.sb_price<=?
             AND b.result IS NULL AND m.kickoff_utc>? AND m.kickoff_utc<?""",
        (hi, now, until)).fetchall()
    seen = {r["match_id"] for r in rows}
    rows = list(rows) + [r for r in offer_combo_rows(conn, now, until, 1.30, hi) if r["match_id"] not in seen]
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
        l = (r["label"] or "").lower()
        if any(x in l for x in ("5.5 cornere", "8.5 cornere", "9.5 cornere", "4.5 cornere")):
            continue
        tier = 0 if "7.5 cornere" in l else 1 if "6.5 cornere" in l else 2
        cur = best.get(r["match_id"])
        if cur is None or tier < cur["tier"] or (tier == cur["tier"] and abs(r["sb_price"] - 1.50) < abs(cur["odds"] - 1.50)):
            best[r["match_id"]] = {
                "match_id": r["match_id"], "label": r["label"], "p": r["p_joint"], "odds": r["sb_price"],
                "kickoff": r["kickoff_utc"], "market": sb["market"], "outcome": sb["outcome"], "tier": tier,
            }
    return list(best.values())


def _take(pool: List[Dict[str, Any]], uses: Dict[int, int], made: List[List[Dict[str, Any]]],
          n: int, use_cap: int, share: int, rng: random.Random) -> Optional[List[Dict[str, Any]]]:
    order = pool[:]
    rng.shuffle(order)
    order.sort(key=lambda c: (uses.get(c["match_id"], 0), c["kickoff"]))
    take: List[Dict[str, Any]] = []
    for c in order:
        if uses.get(c["match_id"], 0) >= use_cap:
            continue
        ids = {x["match_id"] for x in take}
        ids.add(c["match_id"])
        if any(sum(x["match_id"] in ids for x in prev) > share for prev in made):
            continue
        take.append(c)
        if len(take) >= n:
            break
    return take if len(take) >= n else None


def _prod(legs: List[Dict[str, Any]]) -> float:
    p = 1.0
    for c in legs:
        p *= c["odds"]
    return p


def _ids(legs: List[Dict[str, Any]]) -> set:
    return {c["match_id"] for c in legs}


def _min_legs(free: List[Dict[str, Any]], anchors: List[Dict[str, Any]], target: float) -> Optional[List[Dict[str, Any]]]:
    """Cât mai puține meciuri noi, cotele mari întâi. Ancorele, cele sigure, se adaugă doar dacă nu ajunge cota."""
    ex = sorted(free, key=lambda c: (-c["odds"], c["kickoff"], c["match_id"]))
    for k in range(0, len(ex) + 1):
        chosen = ex[:k]
        prod = _prod(chosen) if chosen else 1.0
        if len(chosen) >= 8 and prod >= target:
            return chosen
        for a in anchors:
            chosen = chosen + [a]
            prod *= a["odds"]
            if len(chosen) >= 8 and prod >= target:
                return chosen
    return None


def _try_recipe(exclusive: List[Dict[str, Any]], anchors: List[Dict[str, Any]], recipe: Tuple[str, ...]) -> Optional[List[tuple]]:
    anchor_ids = _ids(anchors)
    free = list(exclusive)
    made: List[List[Dict[str, Any]]] = []
    plan: List[tuple] = []
    for shape in sorted(recipe, key=lambda s: -_TARGET[s]):
        legs = _min_legs(free, anchors, _TARGET[shape])
        if not legs or _prod(legs) < _TARGET[shape]:
            return None
        ids = _ids(legs)
        if any(len(ids & _ids(prev)) > SHARE for prev in made):
            return None
        free = [c for c in free if c["match_id"] not in (ids - anchor_ids)]
        made.append(legs)
        plan.append((shape, legs))
    return plan


def _big_plan(pool: List[Dict[str, Any]]) -> List[tuple]:
    """Alege rețeta care acoperă cele mai multe praguri, apoi cele mai multe bilete, fără mai mult de 5 meciuri comune."""
    if len(pool) < 8:
        return []
    anchors = sorted(pool, key=lambda c: (-(c["p"] or 0), -c["odds"], c["match_id"]))[:SHARE]
    anchor_ids = _ids(anchors)
    exclusive = [c for c in pool if c["match_id"] not in anchor_ids]
    best: List[tuple] = []
    best_key = (-1, -1, -1)
    for recipe in _RECIPES:
        plan = _try_recipe(exclusive, anchors, recipe)
        if not plan:
            continue
        bands = len({s for s, _ in plan})
        key = (bands, len(plan), sum(_TARGET[s] for s, _ in plan))
        if key > best_key:
            best, best_key = plan, key
    return best


def _best_plan(pool: List[Dict[str, Any]]) -> List[tuple]:
    best: List[tuple] = []
    for seed in range(24):
        rng = random.Random(seed)
        plan: List[tuple] = []
        made: List[List[Dict[str, Any]]] = []
        uses: Dict[int, int] = {}
        for _ in range(4):
            legs = _take(pool, uses, made, 4, 2, 0, rng)
            if not legs:
                break
            plan.append(("4", legs))
            made.append(legs)
            for c in legs:
                uses[c["match_id"]] = uses.get(c["match_id"], 0) + 1
        for _ in range(2):
            legs = _take(pool, uses, made, 6, 3, 2, rng)
            if not legs:
                break
            plan.append(("6", legs))
            made.append(legs)
            for c in legs:
                uses[c["match_id"]] = uses.get(c["match_id"], 0) + 1
        if (sum(1 for s, _ in plan if s == "4"), sum(1 for s, _ in plan if s == "6")) > (
                sum(1 for s, _ in best if s == "4"), sum(1 for s, _ in best if s == "6")):
            best = plan

    return (best + _big_plan(pool))[:MAX_N]


def _fp(shape: str, legs: List[Dict[str, Any]]) -> str:
    return shape + ":" + ",".join(str(c["match_id"]) for c in sorted(legs, key=lambda c: c["match_id"]))


def _copy(shape: str, n: int, total: float) -> Tuple[str, str, str]:
    if shape == "4":
        return ("Cornere · 4 meciuri",
                "Patru cornere. Asta se joacă, 3 lei. Șansa e cam 30%, dacă fiecare selecție intră ca în istoric.",
                "Biletele de 4 nu au meciuri în comun. O ratare doboară unul singur.")
    if shape == "6":
        return ("Cornere · 6 meciuri",
                "Șase cornere. Tot de jucat, 3 lei. Intră cam o dată din șase.",
                "Are cel mult 2 meciuri la fel cu un bilet de 4.")
    name = {"500": "500+", "1000": "1000+", "10000": "10000+"}.get(shape, "")
    return (f"Cornere {name} · cotă {round(total)}",
            f"{n} cornere, cotă reală {round(total)}. 2 lei, rar. Cota vine din înmulțirea selecțiilor de 1,30–1,80, nu din meciuri slabe.",
            "Cel mult 5 meciuri în comun cu alt bilet mare. Alea sunt cele cu șansa cea mai mare. Restul sunt alte meciuri.")


def build(conn, today: date) -> Dict[str, int]:
    """Înlocuiește biletele de cornere încă neîncepute. Cele deja începute rămân."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    until = (datetime.now(timezone.utc) + timedelta(days=4)).strftime("%Y-%m-%dT%H:%M:%S")
    pool = _pool(conn, now, 1.90, until)
    planned = _best_plan(pool)
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
            total = _prod(legs)
            p = 1.0
            for c in legs:
                p *= c["p"] or 0.0
            bonus = _bonus(len(legs))
            back = total + bonus * (total - 1)
            label, why, overlap = _copy(shape, len(legs), total)
            notes = {
                "paper": True, "experimental": True, "risk_acknowledged": True,
                "tier": shape, "label": label, "fp": fp, "superbonus": round(bonus * 100),
                "reasons": [why, overlap,
                            f"Superbonus {round(bonus * 100)}% din profit. La 2 lei, plata cu bonus e cam {round(2 * back)} lei.",
                            "Nu e marcat plasat. Îl pui tu, dacă vrei."],
                "leg_reasons": [{"m": c["match_id"], "s": f"{c['market']}|{c['outcome']}",
                                 "r": [f"Șansă {round((c['p'] or 0) * 100)}% · cotă Superbet {c['odds']}"]} for c in legs],
            }
            cur = conn.execute(
                """INSERT INTO ticket (kind, variant, created_by, target_odds, total_odds, p_ticket, ev, stake, status, created_at, notes, day)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (KIND, shape, "robot", {"4": 4, "6": 8, "500": 500, "1000": 1000, "10000": 10000}.get(shape),
                 round(total, 2), round(p, 6), round(p * back - 1, 4), None, "pending",
                 repo.now_iso(), json.dumps(notes, ensure_ascii=False), today.isoformat()))
            for c in sorted(legs, key=lambda c: c["kickoff"]):
                conn.execute(
                    "INSERT INTO ticket_leg (ticket_id, prediction_id, match_id, market, selection, odds, odds_source) VALUES (?,?,?,?,?,?,?)",
                    (cur.lastrowid, None, c["match_id"], "bb", f"{c['market']}|{c['outcome']}", c["odds"], "superbet"))
            inserted += 1
    return {"pool": len(pool), "kept": kept, "inserted": inserted, "planned": len(planned)}


def settle_legs(conn) -> int:
    n = 0
    rows = conn.execute(
        """SELECT tl.ticket_id, tl.match_id, tl.market, tl.selection, b.result, b.legs_json
           FROM ticket_leg tl JOIN ticket t ON t.id=tl.ticket_id AND t.kind IN (?, 'pyramid', 'acca_super')
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
        conn.execute(
            "UPDATE ticket_leg SET result=? WHERE ticket_id=? AND match_id=? AND market=? AND selection=?",
            (r["result"], r["ticket_id"], r["match_id"], r["market"], r["selection"]))
        n += 1
    # Fără rând în bb_suggestion: decontăm din scor și cornere, dacă meciul e terminat.
    rows2 = conn.execute(
        """SELECT tl.ticket_id, tl.match_id, tl.market, tl.selection, m.home_name, m.away_name,
                  m.ft_home, m.ft_away, m.ht_home, m.ht_away, m.corners_home, m.corners_away
           FROM ticket_leg tl JOIN ticket t ON t.id=tl.ticket_id AND t.kind IN (?, 'pyramid', 'acca_super') AND t.status='pending'
           JOIN match m ON m.id=tl.match_id
           WHERE tl.result IS NULL AND tl.market='bb' AND m.status='finished' AND m.ft_home IS NOT NULL""",
        (KIND,)).fetchall()
    import numpy as np
    from betpredict.model import sim as SIM

    for r in rows2:
        text = r["selection"] or ""
        market, _, outcome = text.partition("|")
        outcome = outcome or market
        if "cornere" in outcome.lower() and r["corners_home"] is None:
            continue
        legs = SIM.parse_combo(market, outcome, r["home_name"] or "", r["away_name"] or "")
        if not legs:
            continue
        h1, a1 = r["ht_home"] or 0, r["ht_away"] or 0
        S = {"h": np.array([r["ft_home"]]), "a": np.array([r["ft_away"]]),
             "h1": np.array([h1]), "a1": np.array([a1]),
             "h2": np.array([r["ft_home"] - h1]), "a2": np.array([r["ft_away"] - a1]),
             "ch": np.array([r["corners_home"] or 0]), "ca": np.array([r["corners_away"] or 0]),
             "ch1": np.array([0]), "ca1": np.array([0])}
        won = bool(SIM.joint(S, legs) > 0.5)
        conn.execute(
            "UPDATE ticket_leg SET result=? WHERE ticket_id=? AND match_id=? AND market=? AND selection=?",
            ("won" if won else "lost", r["ticket_id"], r["match_id"], r["market"], r["selection"]))
        n += 1
    return n
