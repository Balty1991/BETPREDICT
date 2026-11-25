"""Bilete din combinația Superbet „peste 0.5 goluri + peste 6.5/7.5 cornere”, publicate la Bilete (rubrica Cornere).

5 bilete în joc (până la 7 când oferta e bogată), praguri 100 / 500 / 1.000 / 5.000 / 10.000.
Un bilet în joc nu se mai schimbă; când se termină, la următoarea rulare vine altul.
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
SHORT_N, SHORT_TARGET, SHORT_LEGS = 3, 10.0, (5, 9)  # biletele zilei: cotă ~10, nu 3-4
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


def _norm(label: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (label or "").lower().replace(",", ".").strip())


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
    rows = [r for r in rows if _COMBO.fullmatch(_norm(r["label"]))]
    seen = {r["match_id"] for r in rows}  # un meci cu altă combinație în sugestii ia combinația bună din ofertă
    rows = list(rows) + [r for r in offer_combo_rows(conn, now, until, 1.30, hi) if r["match_id"] not in seen]
    from betpredict.ingest.corners import blind_leagues

    try:
        at = datetime.fromisoformat((now or "").replace("Z", "+00:00"))
        at = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
    except ValueError:
        at = None
    no_corners = blind_leagues(conn, at)
    league_of: Dict[int, Any] = {}
    # liga fiecărui meci: ligile fără cornere în BSD ies (selecția n-ar mai putea fi decontată și ar ține biletul în
    # așteptare), ligile secunde au o preferință mică la ordine (vezi super_tickets.SECOND_DIV)
    ids = list({r["match_id"] for r in rows})
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        league_of.update(conn.execute(f"SELECT id, league_id FROM match WHERE id IN ({','.join('?' * len(chunk))})", chunk).fetchall())
    from betpredict.builder.super_tickets import SECOND_DIV
    best: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        if league_of.get(r["match_id"]) in no_corners:
            continue
        raw = r["legs_json"] or ""
        if not _corner(r["label"] or "", raw):
            continue
        try:
            sb = (json.loads(raw).get("superbet") or {})
        except ValueError:
            continue
        if not sb.get("market") or not sb.get("outcome"):
            continue
        l = _norm(r["label"])
        # Doar „Peste 0.5 goluri; Peste 6.5/7.5 cornere”. Audit 25.11 (închideri Superbet 13–24.11, la 1.25–2.20):
        # „Peste 1.5 goluri; Peste 7.5 cornere” −16% (241 meciuri, 90%: −24%..−8%), negativ în ambele jumătăți (−17%, −15%);
        # „Peste 1.5 goluri; Peste 6.5 cornere” −18% (70). „0.5 goluri + 7.5 cornere” −1% (287). Combinațiile „Sub … cornere” nu țin
        # de biletul de cornere peste. Pe biletele de cornere de la 19.11 intraseră 24 de selecții cu 1.5 goluri și 5 cu „Sub”.
        if not _COMBO.fullmatch(l):
            continue
        tier = 0 if "7.5 cornere" in l else 1
        cur = best.get(r["match_id"])
        if cur is None or tier < cur["tier"] or (tier == cur["tier"] and abs(r["sb_price"] - 1.50) < abs(cur["odds"] - 1.50)):
            best[r["match_id"]] = {
                "match_id": r["match_id"], "label": r["label"], "p": r["p_joint"], "odds": r["sb_price"],
                "kickoff": r["kickoff_utc"], "market": sb["market"], "outcome": sb["outcome"], "tier": tier,
                "pref": league_of.get(r["match_id"]) in SECOND_DIV,
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


def _take_to(pool: List[Dict[str, Any]], uses: Dict[int, int], made: List[List[Dict[str, Any]]], target: float,
             rng: random.Random) -> Optional[List[Dict[str, Any]]]:
    """Selecții pe meciuri nefolosite până se strânge cota țintă (cel mult SHORT_LEGS[1] meciuri)."""
    order = [c for c in pool if not uses.get(c["match_id"])]
    rng.shuffle(order)
    order.sort(key=lambda c: c["kickoff"])
    take: List[Dict[str, Any]] = []
    for c in order:
        if any(x["match_id"] == c["match_id"] for x in take) or _prod(take) * c["odds"] > target * 2:
            continue
        take.append(c)
        if _prod(take) >= target and len(take) >= SHORT_LEGS[0]:
            return take
        if len(take) >= SHORT_LEGS[1]:
            break
    return None


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


def _best_plan(pool: List[Dict[str, Any]], short_until: Optional[str] = None) -> List[tuple]:
    # biletele de ~10: doar meciurile zilei (se încheie azi: piramidă cu reinvestire); cele mari au toată fereastra
    short_pool = [c for c in pool if not short_until or (c["kickoff"] or "") < short_until]
    best: List[tuple] = []
    for seed in range(24):
        rng = random.Random(seed)
        plan: List[tuple] = []
        made: List[List[Dict[str, Any]]] = []
        uses: Dict[int, int] = {}
        for _ in range(SHORT_N):  # 3 bilete de ~10, fără meciuri comune între ele
            legs = _take_to(short_pool, uses, made, SHORT_TARGET, rng)
            if not legs:
                break
            plan.append(("10", legs))
            made.append(legs)
            for c in legs:
                uses[c["match_id"]] = uses.get(c["match_id"], 0) + 1
        if (len(plan), -sum(abs(_prod(l) - SHORT_TARGET) for _, l in plan)) > (
                len(best), -sum(abs(_prod(l) - SHORT_TARGET) for _, l in best)):
            best = plan

    return (best + _big_plan(pool))[:MAX_N]


def _fp(shape: str, legs: List[Dict[str, Any]]) -> str:
    return shape + ":" + ",".join(str(c["match_id"]) for c in sorted(legs, key=lambda c: c["match_id"]))


def _copy(shape: str, n: int, total: float) -> Tuple[str, str, str]:
    if shape == "10":
        return (f"Cornere · cotă {total:.0f} · {n} meciuri",
                f"{n} selecții 0.5 goluri + cornere, cotă {total:.1f}. Unul din cele 3 bilete de ~10 ale zilei.",
                "Biletele de ~10 nu au meciuri în comun între ele: o ratare doboară unul singur.")
    if shape == "4":
        return ("Cornere · 4 meciuri",
                "Patru cornere. Asta se joacă, 3 lei. Șansa e cam 30%, dacă fiecare selecție intră ca în istoric.",
                "Biletele de 4 nu au meciuri în comun. O ratare doboară unul singur.")
    if shape == "6":
        return ("Cornere · 6 meciuri",
                "Șase cornere. Tot de jucat, 3 lei. Intră cam o dată din șase.",
                "Are cel mult 2 meciuri la fel cu un bilet de 4.")
    return (f"Cornere {shape}+ · cotă {round(total)}",
            f"{n} selecții „peste 0.5 goluri + cornere”, cotă reală {round(total)}. 2 lei, rar. Cota vine din înmulțirea selecțiilor de 1,35–1,90, nu din meciuri slabe.",
            f"Un meci e pe cel mult {USE_CAP} bilete de cornere în joc; două bilete au cel mult {SHARE_MAX} meciuri în comun.")


# Biletele de cornere în joc (cerut 21.11): 5 în joc, până la 7 când oferta e bogată; un bilet nou doar când se termină unul.
# Praguri ca la biletele lungi: 100, 500, 1.000, 5.000, 10.000 — întâi cele care lipsesc din joc.
ACTIVE = 5
ACTIVE_MAX = 7
PREVIEW_KEY = "corners.preview.2511"  # o singură dată: bilete de cornere cu regulile din 25.11, lângă cele vechi
RICH_POOL = 60          # câte meciuri cu combinația în ofertă fac o zi „bogată”
PER_EXTRA = 15          # un bilet în plus doar dacă rămân ~15 meciuri nefolosite pe celelalte bilete
CYCLE = ("100", "500", "1000", "5000", "10000")
TIER_LEGS = {"100": (10, 15), "500": (13, 19), "1000": (15, 21), "5000": (18, 25), "10000": (20, 27)}
TIER_TARGET = {"100": 100.0, "500": 500.0, "1000": 1000.0, "5000": 5000.0, "10000": 10000.0}
LEG_MIN = 1.35          # sub 1.35 selecția nu intră la SuperBonus
LEG_MAX = 1.90
USE_CAP = 2             # un meci pe cel mult 2 bilete de cornere în joc
SHARE_MAX = 6           # două bilete au cel mult 6 meciuri în comun
SPAN_C = 2.0            # cota biletului: între țintă și de 2 ori ținta
HORIZON_D = 7
# Ligile secunde: „0.5 goluri + 7.5 cornere” +19% la închiderile Superbet 13–24.11 (42 de meciuri, pe plus în ambele
# jumătăți), restul −8% (92); arhiva: mai multe cornere decât spune cota de goluri în 6 din 7 sezoane. Doar la ordine
# (ca 2 puncte de șansă), șansa afișată rămâne cea din cotă.
PREF_2ND = 0.02


def _active(conn) -> List[Tuple[int, str, set]]:
    out = []
    for r in conn.execute("SELECT id, variant FROM ticket WHERE kind=? AND status='pending'", (KIND,)).fetchall():
        ms = {x[0] for x in conn.execute("SELECT match_id FROM ticket_leg WHERE ticket_id=?", (r[0],))}
        out.append((r[0], r[1], ms))
    return out


def _build_to(pool: List[Dict[str, Any]], target: float, rng_legs: Tuple[int, int], uses: Dict[int, int],
              made: List[set], rng: random.Random) -> Optional[List[Dict[str, Any]]]:
    """Selecții până la ținta biletului: întâi meciurile nefolosite, cele cu șansa cea mai mare (cu puțin noroc la ordine)."""
    order = pool[:]
    rng.shuffle(order)
    order.sort(key=lambda c: (uses.get(c["match_id"], 0), -round(((c["p"] or 0) + (PREF_2ND if c.get("pref") else 0.0)) * 20), not c.get("pref")))
    maxo = max((c["odds"] for c in pool), default=1.0)
    take: List[Dict[str, Any]] = []
    total = 1.0
    for c in order:
        if uses.get(c["match_id"], 0) >= USE_CAP:
            continue
        ids = _ids(take) | {c["match_id"]}
        if any(len(ids & m) > SHARE_MAX for m in made):
            continue
        if total * c["odds"] > target * SPAN_C:
            continue
        if total * c["odds"] * maxo ** (rng_legs[1] - len(take) - 1) < target:
            continue
        take.append(c)
        total *= c["odds"]
        if total >= target and len(take) >= rng_legs[0]:
            return take
        if len(take) >= rng_legs[1]:
            return None
    return None


def build(conn, today: date, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Completează biletele de cornere în joc (5, până la 7 în zilele bogate). Cele în joc nu se mai schimbă."""
    now = now or datetime.now(timezone.utc)
    active = _active(conn)
    try:  # o singură dată (cerut 25.11): se completează până la ACTIVE_MAX cu regulile noi, lângă cele vechi
        preview = not repo.get_state(conn, PREVIEW_KEY)
    except Exception:  # noqa: BLE001
        preview = False
    if len(active) >= ACTIVE_MAX and not preview:
        return {"skipped_existing": len(active)}
    lo = now.strftime("%Y-%m-%dT%H:%M:%S")
    until = (now + timedelta(days=HORIZON_D)).strftime("%Y-%m-%dT%H:%M:%S")
    pool = [c for c in _pool(conn, lo, LEG_MAX, until) if c["odds"] >= LEG_MIN]
    uses: Dict[int, int] = {}
    for _, _, ms in active:
        for m in ms:
            uses[m] = uses.get(m, 0) + 1
    free = len({c["match_id"] for c in pool} - set(uses))
    need = max(0, ACTIVE - len(active))
    if today.weekday() >= 4 or len(pool) >= RICH_POOL:
        need = max(need, min(ACTIVE_MAX - len(active), free // PER_EXTRA))
    if preview:
        need = max(need, ACTIVE_MAX - len(active), 2)
        try:
            repo.set_state(conn, PREVIEW_KEY, now.strftime("%Y-%m-%dT%H:%M:%SZ"))
        except Exception:  # noqa: BLE001
            pass
    if not need:
        return {"skipped_existing": len(active), "pool": len(pool), "free": free}
    have = [v for _, v, _ in active]
    made = [ms for _, _, ms in active]
    inserted = []
    created = repo.now_iso()
    with conn:
        for i in range(need):
            shape = min(CYCLE, key=lambda x: (have.count(x), CYCLE.index(x)))
            have.append(shape)
            legs = None
            best_p = -1.0
            for seed in range(12):
                cand = _build_to(pool, TIER_TARGET[shape], TIER_LEGS[shape], uses, made, random.Random(seed * 31 + i))
                if not cand:
                    continue
                p = 1.0
                for c in cand:
                    p *= c["p"] or 0.0
                if p > best_p:
                    legs, best_p = cand, p
            if not legs:
                continue
            for c in legs:
                uses[c["match_id"]] = uses.get(c["match_id"], 0) + 1
            made.append(_ids(legs))
            inserted.append(_insert(conn, shape, legs, today, created))
    return {"pool": len(pool), "free": free, "active_before": len(active), "inserted": len(inserted), "made": inserted}


def _insert(conn, shape: str, legs: List[Dict[str, Any]], today: date, created: str) -> Dict[str, Any]:
    total = _prod(legs)
    p = 1.0
    for c in legs:
        p *= c["p"] or 0.0
    bonus = _bonus(sum(1 for c in legs if c["odds"] >= 1.35))
    back = total + bonus * (total - 1)
    label, why, overlap = _copy(shape, len(legs), total)
    notes = {
        "paper": True, "experimental": True, "risk_acknowledged": True,
        "tier": shape, "label": label, "fp": _fp(shape, legs), "superbonus": round(bonus * 100),
        "payout_bonus": round(back, 2),
        "reasons": [why, overlap,
                    f"Superbonus {round(bonus * 100)}% din profit. La 2 lei, plata cu bonus e cam {round(2 * back)} lei.",
                    "Nu e marcat plasat. Îl pui tu, dacă vrei."],
        "leg_reasons": [{"m": c["match_id"], "s": f"{c['market']}|{c['outcome']}",
                         "r": [f"Șansă {round((c['p'] or 0) * 100)}% · cotă Superbet {c['odds']}"]} for c in legs],
    }
    cur = conn.execute(
        """INSERT INTO ticket (kind, variant, created_by, target_odds, total_odds, p_ticket, ev, stake, status, created_at, notes, day)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (KIND, shape, "robot", TIER_TARGET.get(shape), round(total, 2), round(p, 6), round(p * back - 1, 4), None, "pending",
         created, json.dumps(notes, ensure_ascii=False), today.isoformat()))
    for c in sorted(legs, key=lambda c: c["kickoff"]):
        conn.execute(
            "INSERT INTO ticket_leg (ticket_id, prediction_id, match_id, market, selection, odds, odds_source) VALUES (?,?,?,?,?,?,?)",
            (cur.lastrowid, None, c["match_id"], "bb", f"{c['market']}|{c['outcome']}", c["odds"], "superbet"))
    return {"variant": shape, "id": cur.lastrowid, "legs": len(legs), "odds": round(total, 2), "p": round(p, 6)}


def stats_doc(conn, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Urmărirea biletelor de cornere de la noul început (19.11): pe prag și total, selecții intrate, ultimele rezultate."""
    from betpredict.builder.super_tickets import TICKETS_RESET_AT

    now = now or datetime.now(timezone.utc)
    rows = conn.execute("SELECT id, variant, status, total_odds, p_ticket, notes, day FROM ticket WHERE kind=? AND status!='replaced' "
                        "AND created_at>=? ORDER BY created_at", (KIND, TICKETS_RESET_AT)).fetchall()

    def pay(r) -> float:
        try:
            return float(json.loads(r[5] or "{}").get("payout_bonus") or r[3] or 0)
        except ValueError:
            return float(r[3] or 0)

    def agg(rs) -> Dict[str, Any]:
        done = [r for r in rs if r[2] in ("won", "lost")]
        won = [r for r in done if r[2] == "won"]
        return {"n": len(done), "won": len(won), "lost": len(done) - len(won), "pending": sum(1 for r in rs if r[2] == "pending"),
                "expected": round(sum(r[4] or 0 for r in done), 2),
                "roi": round(sum(pay(r) for r in won) / len(done) - 1, 4) if done else None,
                "best": max((pay(r) for r in won), default=None)}

    legs = conn.execute("""SELECT SUM(l.result='won'), SUM(l.result IN ('won','lost')) FROM ticket_leg l JOIN ticket t ON t.id=l.ticket_id
                           WHERE t.kind=? AND t.status!='replaced' AND t.created_at>=?""", (KIND, TICKETS_RESET_AT)).fetchone()
    last = [{"variant": r[1], "status": r[2], "odds": round(r[3] or 0, 2), "day": r[6]} for r in rows if r[2] in ("won", "lost")][-12:]
    return {"generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "since": TICKETS_RESET_AT,
            "tiers": [{"variant": v, "target": TIER_TARGET[v], **agg([r for r in rows if r[1] == v])} for v in CYCLE],
            "all": agg(rows), "active_target": ACTIVE, "active_max": ACTIVE_MAX,
            "leg_hit": round(legs[0] / legs[1], 4) if legs and legs[1] else None, "legs": (legs[1] or 0) if legs else 0, "last": last}


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
           FROM ticket_leg tl JOIN ticket t ON t.id=tl.ticket_id AND t.kind IN (?, 'pyramid', 'acca_super') AND t.status!='replaced'
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
