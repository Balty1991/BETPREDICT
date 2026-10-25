"""Calea 100+ (25.10.2026, cererea lui Alin: „să prindem bilete câștigătoare de cotă 100+”). Reguli ÎNGHEȚATE (c100-v1),
urmărite prospectiv din 26.10.2026, separat de toate celelalte statistici.

Cercetarea (date reale, 24k selecții Superbet urmărite 14–25.10 + bilete decontate):
- Șansa unui bilet ≈ (1 + EV) / cotă. La cota 100 cu selecții „corecte” (EV 0) șansa e ~1%; fiecare selecție cu marjă
  o scade. Marja Superbet crește cu cota: −4% la 1.35–2, −10% la 2–4, −20% la 4–10 → puține selecții la cote mari (corect,
  pauză/final, scor exact) e cel mai prost drum; multe selecții la 1.35–2 + SuperBonus e cel mai ieftin.
- Niciun filtru (ligă, piață, prag de cotă) n-a arătat avantaj robust în afara eșantionului → șansa afișată e cea onestă.

Două drumuri, ambele cu mize mici fixe:
A) „Biletul SuperBonus” (acca_calea / c100_bonus): o dată pe zi, 8–14 selecții la cota 1.35–2.20 (toate contează la
   SuperBonus: 8 → +15%, 10 → +25%, 12 → +35%, 14 → +45% din profit), doar din piețele Stil cu marjă mică pe istoric și
   Cote mărite cu EV > 0, un meci o dată, max. 3 pe ligă, fără start 00:00–07:00. Cota reală ≥ 100, altfel nu se face.
B) „Rularea Pontului” (doar citire din Pontul zilei, nu-l schimbă): 2 lei pe Pontul zilei, câștigul întreg pe Pontul
   de a doua zi, până când cota cumulată trece de 100 (~13 zile la ~1.43). O pierdere → se reia cu 2 lei.
"""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

from betpredict.store import repo
from betpredict.timeutil import canon_utc

VERSION = "c100-v1"
START = "2026-10-26"          # prospectiv: nimic înainte nu intră în bilanț
KIND, VARIANT = "acca_calea", "c100_bonus"
# piețele Stil cu cea mai mică marjă pe istoric (ROI pe hârtie ≥ −2% la cota 1.35–2.20, fără jumătate de perioadă sub −3.5%),
# fixate la 25.10 din ss_track (n ≥ 150 fiecare): Cartonașe sub 4.5/5.5, Gol în ambele reprize, Gazdele peste 1.5,
# Interval goluri 2-5, Prima repriză 1-3 goluri / x2 etc. Nu se schimbă pe parcurs (altfel bilanțul nu mai e onest).
KEYS = frozenset({"YCU45", "YCU55", "R1R2", "HO15", "G25", "H13x2", "H2G13"})
LEG_ODDS = (1.35, 2.20)
BOOST_ODDS = (1.35, 3.50)
MAX_BOOSTS = 2
LEGS = (8, 14)
TARGET = 100.0
MAX_PER_LEAGUE = 3
STAKE_U = 0.1                 # 1 leu la bugetul de 50 lei/săptămână
LEG_ROI = -0.03               # randamentul onest pe selecție (−4.4% măsurat în afara eșantionului pe toată oferta; −1…−3% la piețele alese)
BONUS = {3: 0.03, 4: 0.04, 5: 0.06, 6: 0.08, 7: 0.10, 8: 0.15, 9: 0.20, 10: 0.25}  # SuperBonus Superbet (din profit)
ROLL_START_LEI, ROLL_TARGET = 2.0, 100.0


def superbonus(n_eligible: int) -> float:
    """Procentul SuperBonus Superbet după câte selecții au cota ≥ 1.35 (min. 3; peste 10: +5% pe selecție, max. 100%)."""
    if n_eligible < 3:
        return 0.0
    if n_eligible <= 10:
        return BONUS[n_eligible]
    return min(1.0, 0.25 + 0.05 * (n_eligible - 10))


def honest_chance(odds_list: Sequence[float], leg_roi: float = LEG_ROI) -> float:
    """Șansa onestă a biletului: Π(1 + ROI pe selecție) / cota totală (marja casei plătită la fiecare selecție)."""
    total = math.prod(odds_list)
    return (1 + leg_roi) ** len(odds_list) / total if total > 0 else 0.0


def ev_with_bonus(p: float, total: float, bonus: float) -> float:
    return p * (total + (total - 1) * bonus) - 1


def _day_end_utc(today: date) -> str:
    from zoneinfo import ZoneInfo

    end = datetime(today.year, today.month, today.day, 23, 59, 59, tzinfo=ZoneInfo("Europe/Bucharest"))
    return canon_utc(end.astimezone(timezone.utc).isoformat())


def candidates(conn: sqlite3.Connection, rows: Sequence[Dict[str, Any]], today: date, now: datetime) -> List[Dict[str, Any]]:
    from betpredict.builder.pyramid_risk import night_kickoff

    soon = canon_utc((now + timedelta(minutes=10)).isoformat())
    until = _day_end_utc(today)
    try:
        paused = {r[0] for r in conn.execute("SELECT mkey FROM market_state WHERE status='paused'")}
    except sqlite3.Error:
        paused = set()
    best: Dict[Any, Dict[str, Any]] = {}
    for r in rows:
        if r.get("key") not in KEYS or r["key"] in paused or r.get("suspect") or r.get("est") or not r.get("odds") or not r.get("p"):
            continue
        if not LEG_ODDS[0] <= r["odds"] <= LEG_ODDS[1]:
            continue
        ko = r.get("kickoff_utc") or ""
        if not soon < ko <= until or night_kickoff(ko):
            continue
        p = min(0.97, float(r["p"]))
        c = {"match_id": r["match_id"], "league_id": r.get("league_id"), "kickoff_utc": ko, "market": "ss|0", "selection": r["key"],
             "odds": float(r["odds"]), "p": p, "cost": -math.log(p) / math.log(float(r["odds"])), "boost": False}
        if r["match_id"] not in best or c["cost"] < best[r["match_id"]]["cost"]:
            best[r["match_id"]] = c
    # Cote mărite (core) cu EV > 0 și metodă de încredere: singura componentă cu ROI pozitiv pe istoric (+29%, n=77)
    try:
        boosts = conn.execute(
            """SELECT b.match_id, b.name, b.price, b.p_fair, b.ev, b.method, m.kickoff_utc, m.league_id FROM sb_boost b JOIN match m ON m.id=b.match_id
               WHERE b.kind!='super_cota' AND b.ev > 0 AND b.ev <= 0.30 AND b.p_fair > 0 AND b.price BETWEEN ? AND ?
                 AND m.kickoff_utc > ? AND m.kickoff_utc <= ? AND b.last_seen >= ?
                 AND (b.method LIKE 'piață%' OR b.method LIKE 'model%') ORDER BY b.ev DESC""",
            (*BOOST_ODDS, soon, until, canon_utc((now - timedelta(hours=12)).isoformat()))).fetchall()
    except sqlite3.Error:
        boosts = []
    nb = 0
    for b in boosts:
        if nb >= MAX_BOOSTS or night_kickoff(b["kickoff_utc"]):
            continue
        p = float(b["p_fair"])
        best[b["match_id"]] = {"match_id": b["match_id"], "league_id": b["league_id"], "kickoff_utc": b["kickoff_utc"], "market": "boost|0",
                               "selection": b["name"], "odds": float(b["price"]), "p": p, "cost": -1.0, "boost": True}
        nb += 1
    return sorted(best.values(), key=lambda c: c["cost"])


def pick(pool: Sequence[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    legs: List[Dict[str, Any]] = []
    leagues: Dict[Any, int] = {}
    for c in pool:
        if any(l["match_id"] == c["match_id"] for l in legs) or leagues.get(c["league_id"], 0) >= MAX_PER_LEAGUE:
            continue
        legs.append(c)
        leagues[c["league_id"]] = leagues.get(c["league_id"], 0) + 1
        if (math.prod(l["odds"] for l in legs) >= TARGET and len(legs) >= LEGS[0]) or len(legs) >= LEGS[1]:
            break
    total = math.prod(l["odds"] for l in legs) if legs else 0.0
    return legs if len(legs) >= LEGS[0] and total >= TARGET else None


def build(conn: sqlite3.Connection, today: date, now: Optional[datetime] = None, rows: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    if today.isoformat() < START:
        return {"skipped": "before_start"}
    if conn.execute("SELECT 1 FROM ticket WHERE kind=? AND day=? AND status!='replaced'", (KIND, today.isoformat())).fetchone():
        return {"skipped_existing": True}
    if rows is None:
        from betpredict.experimental.supersocial import today_doc

        rows = today_doc(conn, now)["rows"]
    pool = candidates(conn, rows, today, now)
    legs = pick(pool)
    if not legs:
        return {"made": 0, "pool": len(pool), "reason": "sub cota 100 sau sub 8 selecții eligibile"}
    odds = [l["odds"] for l in legs]
    total = math.prod(odds)
    bonus = superbonus(sum(o >= 1.35 for o in odds))
    p_h = honest_chance(odds)
    p_model = math.prod(l["p"] for l in legs)
    ev_h = ev_with_bonus(p_h, total, bonus)
    notes = {"calea": True, "label": "Calea 100+ · SuperBonus", "version": VERSION, "paper": False, "risk_acknowledged": True,
             "p_honest": round(p_h, 5), "p_model": round(p_model, 5), "superbonus": bonus, "ev_honest_bonus": round(ev_h, 4),
             "reasons": [f"{len(legs)} selecții la cota {min(odds):.2f}–{max(odds):.2f}, toate ≥ 1.35 → SuperBonus +{bonus:.0%} din profit la Superbet.",
                         "Doar piețe cu marjă mică pe istoric" + (" + Cote mărite cu EV > 0" if any(l["boost"] for l in legs) else "")
                         + "; un meci o dată, max. 3 pe ligă, fără meciuri 00:00–07:00.",
                         f"Șansă onestă ~{p_h:.2%} (≈ 1 din {round(1 / p_h) if p_h else 0}); EV cu SuperBonus {ev_h:+.0%}. Miză fixă 1 leu.",
                         "Reguli înghețate c100-v1, urmărite separat din 26.10.2026."]}
    from betpredict.builder.label_gate import below_label

    if below_label("acca_100", total):  # dublă siguranță: „100+” doar ≥ 100
        return {"made": 0}
    with conn:
        cur = conn.execute(
            """INSERT INTO ticket (kind, variant, created_by, target_odds, total_odds, p_ticket, ev, stake, status, created_at, notes, day)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (KIND, VARIANT, "robot", TARGET, round(total, 2), round(p_h, 6), round(ev_h, 4), STAKE_U, "pending", repo.now_iso(),
             json.dumps(notes, ensure_ascii=False), today.isoformat()))
        for l in sorted(legs, key=lambda l: l["kickoff_utc"]):
            conn.execute("INSERT INTO ticket_leg (ticket_id, prediction_id, match_id, market, selection, odds, odds_source) VALUES (?,?,?,?,?,?,?)",
                         (cur.lastrowid, None, l["match_id"], l["market"], l["selection"], l["odds"], "superbet"))
    return {"made": 1, "legs": len(legs), "odds": round(total, 2), "p_honest": round(p_h, 5), "bonus": bonus, "pool": len(pool)}


def rolling_state(conn: sqlite3.Connection, today: date) -> Dict[str, Any]:
    """Rularea Pontului din START: 2 lei, tot câștigul pe Pontul următor, până la cota cumulată ≥ 100. Doar citire."""
    rows = conn.execute("SELECT day, status, total_odds, p_ticket FROM ticket WHERE kind='acca_pont' AND variant='pontul_zilei' "
                        "AND status!='replaced' AND day >= ? ORDER BY day", (START,)).fetchall()
    chains: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None
    pending = None
    for r in rows:
        if r["status"] == "pending":
            pending = r
            continue
        if r["status"] not in ("won", "lost"):
            continue
        if cur is None:
            cur = {"start": r["day"], "steps": 0, "odds": 1.0, "status": "active"}
        if r["status"] == "won":
            cur["steps"] += 1
            cur["odds"] *= r["total_odds"]
            if cur["odds"] >= ROLL_TARGET:
                cur.update(status="won", end=r["day"])
                chains.append(cur)
                cur = None
        else:
            cur.update(status="lost", end=r["day"], steps_won=cur["steps"])
            chains.append(cur)
            cur = None
    odds_now = cur["odds"] if cur else 1.0
    steps = cur["steps"] if cur else 0
    avg = 1.43
    left = max(0, math.ceil(math.log(ROLL_TARGET / odds_now) / math.log(avg))) if odds_now < ROLL_TARGET else 0
    # șansa de a ajunge la 100 din punctul curent: fără avantaj (șansa implicită din cotă, după marjă ~4%) → cu avantaj (șansa Pontului ~0.74)
    p_lo = (0.96 / avg) ** left
    p_hi = 0.74 ** left
    stake_now = round(ROLL_START_LEI * odds_now, 2)
    return {"version": VERSION, "start": START, "target": ROLL_TARGET, "start_lei": ROLL_START_LEI,
            "active": {"step": steps + 1, "odds": round(odds_now, 3), "stake_lei": stake_now, "steps_left": left,
                       "p_reach_lo": round(p_lo, 4), "p_reach_hi": round(p_hi, 4),
                       "today": ({"day": pending["day"], "odds": pending["total_odds"]} if pending else None)},
            "record": {"chains": len(chains), "won": sum(c["status"] == "won" for c in chains),
                       "best_steps": max([c.get("steps_won", c["steps"]) for c in chains] + [steps]),
                       "staked_lei": ROLL_START_LEI * (len(chains) + (1 if cur or pending else 0)),
                       "returned_lei": round(sum(ROLL_START_LEI * c["odds"] for c in chains if c["status"] == "won"), 2)},
            "chains": [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in c.items()} for c in chains[-20:]]}


def record(conn: sqlite3.Connection) -> Dict[str, Any]:
    rows = conn.execute("SELECT status, total_odds, stake FROM ticket WHERE kind=? AND status IN ('won','lost') AND day >= ?", (KIND, START)).fetchall()
    staked = sum(r["stake"] for r in rows)
    ret = sum(r["stake"] * r["total_odds"] for r in rows if r["status"] == "won")
    return {"played": len(rows), "won": sum(r["status"] == "won" for r in rows), "staked_u": round(staked, 2), "returned_u_no_bonus": round(ret, 2),
            "roi_no_bonus": round(ret / staked - 1, 3) if staked else None}


def doc(conn: sqlite3.Connection, today: date) -> Dict[str, Any]:
    t = conn.execute("SELECT id, total_odds, p_ticket, ev, notes FROM ticket WHERE kind=? AND day=? AND status!='replaced' ORDER BY id DESC LIMIT 1",
                     (KIND, today.isoformat())).fetchone()
    return {"schema": "betpredict.calea100.v1", "version": VERSION, "start": START, "generated_at": repo.now_iso(),
            "rules": {"bonus": {"legs": list(LEGS), "leg_odds": list(LEG_ODDS), "markets": sorted(KEYS), "max_boosts": MAX_BOOSTS,
                                "stake_lei": 1, "leg_roi_assumed": LEG_ROI, "no_night": "00:00–07:00"},
                      "roll": {"start_lei": ROLL_START_LEI, "target": ROLL_TARGET, "source": "Pontul zilei"}},
            "today": ({"ticket_id": t["id"], "odds": t["total_odds"], "p_honest": t["p_ticket"], "ev_bonus": t["ev"],
                       "superbonus": json.loads(t["notes"] or "{}").get("superbonus")} if t else None),
            "bonus_record": record(conn), "roll": rolling_state(conn, today),
            "research": {"note": "Șansa la 100+ ≈ (1+EV)/cotă. Fără avantaj real pe selecții, niciun drum nu trece de ~1% pe bilet.",
                         "rows": RESEARCH}}


RESEARCH = [  # 25.10.2026, din ss_track (24k selecții Superbet) + bilete decontate; miză 1 leu, buget 50 lei/săptămână
    {"route": "a) 2–3 selecții la cote 4–10 (scor corect, pauză/final, goluri exacte)", "p": 0.005, "ev": -0.45, "lei_per_win": 200,
     "verdict": "cel mai prost: marja 20–35% pe selecție (corect R1 +30%, R2 +33%)"},
    {"route": "b+e) 8–14 selecții 1.35–2.20, piețe cu marjă mică + SuperBonus", "p": 0.0065, "ev": -0.14, "lei_per_win": 155,
     "verdict": "ales: Calea 100+ · SuperBonus (A)"},
    {"route": "c) Rularea Pontului zilei (13 pași la ~1.43)", "p": 0.01, "ev": -0.10, "lei_per_win": 200,
     "verdict": "ales: Rularea Pontului (B); 0.6–2% după cât de real e avantajul Pontului"},
    {"route": "d) Sisteme 2/3, 3/4, Trixie, Yankee", "p": 0.0065, "ev": -0.18, "lei_per_win": None,
     "verdict": "fără SuperBonus, miza se împarte → câștig parțial, dar 100+ doar cu o fracție din miză"},
    {"route": "Stil „o piață” ×10–25 (cornere R1 3-6, interval goluri, fiecare echipă 2.5 cornere)", "p": 0.003, "ev": -0.70, "lei_per_win": 330,
     "verdict": "lovire pe selecție sub cea implicită: R1 3-6 57.7% vs 66% necesar; Test 0/39"},
]
