"""Calea 100+ (25.10.2026, cererea lui Alin: „să prindem bilete câștigătoare de cotă 100+”). Reguli ÎNGHEȚATE (c100-v2),
urmărite prospectiv din 25.10.2026, separat de toate celelalte statistici.

Cercetarea (date reale: 24k selecții Superbet urmărite, 223 de bilete 100+/Stil/Test decontate, toate pierdute):
- Șansa unui bilet ≈ (1 + EV) / cotă. La cota 100 cu selecții „corecte” (EV 0) șansa e ~1%; fiecare selecție cu marjă
  o scade. Pe biletele noastre de cotă mare selecțiile au intrat 60.6% față de 64.8% cât spunea cota (−6.5% pe selecție);
  doar 23 din 223 au pierdut la o singură selecție, 67 la cinci sau mai multe.
- Niciun filtru (ligă, piață, prag de cotă, linia Pinnacle) n-a arătat avantaj robust în afara eșantionului → șansa afișată
  e cea onestă (cu marja pe fiecare selecție), nu cea a modelului.

A) „Biletul SuperBonus” (acca_calea): ÎN FIECARE ZI (Alin, 25.10), cascadă pe trepte, ca la piramidele riscante:
   T0 — doar selecții unde cota Superbet bate prețul corect Pinnacle (fără marjă, ambele cote ≤ 2h) + Gol în repriza 2 1-3
        și Cartonașe sub 5.5 (singurele piețe Stil cu lovire peste cea implicită pe istoric);
   T1 — + piețele Stil cu marjă mică și EV model ≥ 0, + Cote mărite cu EV > 0;
   T2 — + orice piață Stil cu EV model > −3%;
   T3 — cele mai probabile selecții (probabilitate calibrată) din toată oferta zilei.
   Treapta cea mai sigură care ajunge la cota 100 câștigă; cât mai puține selecții (5–12), cota 1.35–3.0, un meci o dată,
   max. 3 pe ligă, fără start 00:00–07:00, poarta cartonașelor, fără piețele/ligile care au „omorât” biletele noastre.
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

VERSION = "c100-v2"
START = "2026-10-25"          # prospectiv: nimic înainte nu intră în bilanț
KIND, VARIANT = "acca_calea", "c100_bonus"
# T0: piețe Stil cu lovire peste cea implicită de cota Superbet (ss_track, 12 zile): H2G13 77.7% vs 74.7% (n 695), YCU55 69.3 vs 69.0
T0_KEYS = frozenset({"H2G13", "YCU55"})
# T1: piețele Stil cu marjă mică pe istoric (fără R1R2, YCU45, G25: au pierdut 6.7–8.9 pp pe biletele noastre de cotă mare)
KEYS = frozenset({"H2G13", "YCU55", "H13x2", "HO15", "R1O15", "C85", "C75", "H1C35"})
# „ucigașii” de bilete (223 de bilete de cotă mare decontate, lovire − probabilitatea din cotă, n ≥ 30): nu intră deloc
BAD_KEYS = frozenset({"R1R2", "YCU45", "G25", "G24", "BB_H1C25_U65", "C65", "AY15", "HY15", "AY25", "HY25", "YC45", "YC35",
                      "H1C25", "H1U65", "H1O15", "H1O05", "DCX2_O15", "H1C56", "H1C7P", "H1CLT5", "R:draw_no_bet:0:HOME"})
BAD_LEAGUES = frozenset({"Liga MX Apertura", "Liga MX Clausura", "Brasileirão Serie A", "Brasileirão Serie B", "Ligue 1", "Serie B",
                         "Championship", "Segunda División"})
LEG_ODDS = (1.35, 3.0)
BOOST_ODDS = (1.35, 3.5)
MAX_BOOSTS = 2
LEGS = (5, 12)
TARGET = 100.0
MAX_PER_LEAGUE = 3
MAX_PER_KEY = 4               # o singură piață nu umple biletul (erorile modelului pe o piață se mișcă împreună)
TIERS = {0: ("T0 · Superbet peste Pinnacle", -0.02, 0.2), 1: ("T1 · marjă mică, EV ≥ 0", -0.03, 0.2),
         2: ("T2 · EV > −3%", -0.045, 0.1), 3: ("T3 · cele mai probabile din ofertă", -0.065, 0.1)}  # (nume, ROI onest pe selecție, miză u)
STAKE_U = 0.1                 # 1 leu (T2/T3); T0/T1 2 lei
LEG_ROI = -0.03
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


def _leg(match_id, league_id, ko, market, selection, odds, p, tier, src) -> Dict[str, Any]:
    return {"match_id": match_id, "league_id": league_id, "kickoff_utc": ko, "market": market, "selection": selection,
            "odds": float(odds), "p": p, "cost": -math.log(max(1e-6, p)) / math.log(float(odds)), "tier": tier, "src": src,
            "boost": market == "boost|0"}


def candidates(conn: sqlite3.Connection, rows: Sequence[Dict[str, Any]], today: date, now: datetime) -> List[Dict[str, Any]]:
    """Toate selecțiile eligibile, fiecare cu treapta minimă la care intră (0 = cea mai sigură)."""
    from betpredict.builder.pyramid_risk import night_kickoff
    from betpredict.experimental.supersocial import card_gate

    soon = canon_utc((now + timedelta(minutes=10)).isoformat())
    until = _day_end_utc(today)
    try:
        paused = {r[0] for r in conn.execute("SELECT mkey FROM market_state WHERE status='paused'")}
    except sqlite3.Error:
        paused = set()
    try:
        bad_lg = {r[0] for r in conn.execute(f"SELECT id FROM league WHERE name IN ({','.join('?' * len(BAD_LEAGUES))})", tuple(BAD_LEAGUES))}
    except sqlite3.Error:
        bad_lg = set()

    def ok_time(ko: str) -> bool:
        return bool(ko) and soon < ko <= until and not night_kickoff(ko)

    out: List[Dict[str, Any]] = []
    # T0a: Superbet peste prețul corect Pinnacle (marja scoasă „power”, ambele cote văzute în ultimele 2 ore), fără 1X2
    try:
        from betpredict.publish import value_alerts as VA

        old = (VA.MIN_VALUE, VA.MAX_ODDS)
        VA.MIN_VALUE, VA.MAX_ODDS = 0.0, LEG_ODDS[1]
        try:
            alerts = VA.find(conn, now)
        finally:
            VA.MIN_VALUE, VA.MAX_ODDS = old
        lg = {}
        for a in alerts:
            if a["superbet"] < LEG_ODDS[0] or not ok_time(a["kickoff_utc"]) or a["value"] > 0.10:
                continue
            mk = a["market"]
            if mk.startswith("over_under_"):
                market = f"over_under|{mk.rsplit('_', 1)[1]}"
            elif mk == "btts":
                market = "btts|0"
            else:
                continue
            if a["match_id"] not in lg:
                r = conn.execute("SELECT league_id FROM match WHERE id=?", (a["match_id"],)).fetchone()
                lg[a["match_id"]] = r[0] if r else None
            if lg[a["match_id"]] in bad_lg:
                continue
            p = float(a["p_fair"]) * 0.98  # prudență: și Pinnacle greșește, iar 16 zile de probă n-au arătat avantaj clar
            out.append(_leg(a["match_id"], lg[a["match_id"]], a["kickoff_utc"], market, a["outcome"], a["superbet"], p, 0, "pinnacle"))
    except Exception:  # noqa: BLE001 — fără Pinnacle proaspăt, treapta 0 rămâne doar cu piețele Stil
        pass
    # piețele Stil (predicțiile zilei), cu poarta cartonașelor
    for r in card_gate(list(rows)):
        k = r.get("key")
        if not k or k in BAD_KEYS or k in paused or r.get("suspect") or r.get("est") or not r.get("odds") or not r.get("p"):
            continue
        if not LEG_ODDS[0] <= r["odds"] <= LEG_ODDS[1] or r.get("league_id") in bad_lg or not ok_time(r.get("kickoff_utc") or ""):
            continue
        edge = r.get("edge")
        edge = float(r["p"]) * float(r["odds"]) - 1 if edge is None else float(edge)
        if k in T0_KEYS and edge >= 0:
            tier = 0
        elif k in KEYS and edge >= 0:
            tier = 1
        elif edge > -0.03:
            tier = 2
        else:
            tier = 3
        p = min(0.95, float(r["p"])) * (1.0 if k in KEYS else 0.97)  # în afara piețelor dovedite: prudență în plus
        out.append(_leg(r["match_id"], r.get("league_id"), r["kickoff_utc"], "ss|0", k, r["odds"], p, tier, "stil"))
    # Cote mărite (core) cu EV > 0 și metodă de încredere: singura componentă cu ROI pozitiv pe istoric (+29%, n=77) → T1
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
        if nb >= MAX_BOOSTS or not ok_time(b["kickoff_utc"]) or b["league_id"] in bad_lg:
            continue
        out.append(_leg(b["match_id"], b["league_id"], b["kickoff_utc"], "boost|0", b["name"], b["price"], float(b["p_fair"]), 1, "boost"))
        nb += 1
    return out


def pick(pool: Sequence[Dict[str, Any]], max_legs: int = LEGS[1]) -> Optional[List[Dict[str, Any]]]:
    """Cât mai puține selecții până la cota 100: lacom după „cost” = −log p / log cotă (șansa pierdută pe unitatea de cotă)."""
    legs: List[Dict[str, Any]] = []
    leagues: Dict[Any, int] = {}
    keys: Dict[str, int] = {}
    # treptele sigure întâi (T0 preferat), apoi după cost; cotele mărite cu EV > 0 primele în treapta lor
    for c in sorted(pool, key=lambda c: (c["tier"], -1.0 if c.get("boost") else c["cost"])):
        if any(l["match_id"] == c["match_id"] for l in legs) or leagues.get(c["league_id"], 0) >= MAX_PER_LEAGUE \
                or keys.get(c["selection"], 0) >= MAX_PER_KEY:
            continue
        legs.append(c)
        leagues[c["league_id"]] = leagues.get(c["league_id"], 0) + 1
        keys[c["selection"]] = keys.get(c["selection"], 0) + 1
        if (math.prod(l["odds"] for l in legs) >= TARGET and len(legs) >= LEGS[0]) or len(legs) >= max_legs:
            break
    total = math.prod(l["odds"] for l in legs) if legs else 0.0
    if total < TARGET or len(legs) < LEGS[0]:
        return None
    # cota a sărit mult peste 100 la ultima selecție: încearcă să o înlocuiești cu una mai mică (șansă mai mare)
    last = legs[-1]
    base = total / last["odds"]
    used = {l["match_id"] for l in legs[:-1]}
    alt = [c for c in pool if c["match_id"] not in used and base * c["odds"] >= TARGET and c["odds"] < last["odds"]
           and c["tier"] <= last["tier"] and leagues.get(c["league_id"], 0) - (1 if c["league_id"] == last["league_id"] else 0) < MAX_PER_LEAGUE
           and keys.get(c["selection"], 0) - (1 if c["selection"] == last["selection"] else 0) < MAX_PER_KEY]
    if alt:
        legs[-1] = min(alt, key=lambda c: (c["odds"], c["cost"]))
    return legs


def choose(pool: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for tier in sorted(TIERS):
        legs = pick([c for c in pool if c["tier"] <= tier])
        if legs:
            return {"tier": tier, "legs": legs}
    return None


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
    ch = choose(pool)
    if not ch:
        return {"made": 0, "pool": len(pool), "reason": "nici treapta 3 nu ajunge la cota 100 (ofertă prea mică azi)"}
    tier, legs = ch["tier"], ch["legs"]
    tname, leg_roi, stake = TIERS[tier]
    odds = [l["odds"] for l in legs]
    total = math.prod(odds)
    bonus = superbonus(sum(o >= 1.35 for o in odds))
    p_h = honest_chance(odds, leg_roi)
    p_model = math.prod(l["p"] for l in legs)
    ev_h = ev_with_bonus(p_h, total, bonus)
    src = sorted({l["src"] for l in legs})
    notes = {"calea": True, "label": f"Calea 100+ · {tname.split(' · ')[0]}", "version": VERSION, "paper": False, "risk_acknowledged": True,
             "tier": tier, "tier_label": tname, "leg_roi": leg_roi,
             "p_honest": round(p_h, 5), "p_model": round(p_model, 5), "superbonus": bonus, "ev_honest_bonus": round(ev_h, 4),
             "reasons": [f"Treapta {tname}: {len(legs)} selecții la cota {min(odds):.2f}–{max(odds):.2f} → SuperBonus +{bonus:.0%} din profit la Superbet.",
                         "Surse: " + ", ".join({"pinnacle": "cota Superbet peste prețul corect Pinnacle", "stil": "piețe Stil",
                                                 "boost": "Cote mărite cu EV > 0"}[s] for s in src)
                         + "; un meci o dată, max. 3 pe ligă, fără 00:00–07:00, fără piețele/ligile care au pierdut biletele noastre.",
                         f"Șansă onestă ~{p_h:.2%} (≈ 1 din {round(1 / p_h) if p_h else 0}), cu {leg_roi:+.1%} pe selecție; EV cu SuperBonus {ev_h:+.0%}. "
                         f"Miză {stake * 10:g} {'leu' if stake * 10 == 1 else 'lei'}.",
                         f"Reguli înghețate {VERSION}, urmărite separat din {START[8:10]}.{START[5:7]}.{START[:4]}, pe trepte."]}
    from betpredict.builder.label_gate import below_label

    if below_label("acca_100", total):  # dublă siguranță: „100+” doar ≥ 100
        return {"made": 0}
    with conn:
        cur = conn.execute(
            """INSERT INTO ticket (kind, variant, created_by, target_odds, total_odds, p_ticket, ev, stake, status, created_at, notes, day)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (KIND, f"c100_t{tier}", "robot", TARGET, round(total, 2), round(p_h, 6), round(ev_h, 4), stake, "pending", repo.now_iso(),
             json.dumps(notes, ensure_ascii=False), today.isoformat()))
        for l in sorted(legs, key=lambda l: l["kickoff_utc"]):
            conn.execute("INSERT INTO ticket_leg (ticket_id, prediction_id, match_id, market, selection, odds, odds_source) VALUES (?,?,?,?,?,?,?)",
                         (cur.lastrowid, None, l["match_id"], l["market"], l["selection"], l["odds"], "superbet"))
    return {"made": 1, "tier": tier, "legs": len(legs), "odds": round(total, 2), "p_honest": round(p_h, 5), "bonus": bonus, "pool": len(pool)}


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
    rows = conn.execute("SELECT variant, status, total_odds, stake FROM ticket WHERE kind=? AND status IN ('won','lost') AND day >= ?", (KIND, START)).fetchall()

    def agg(rs):
        staked = sum(r["stake"] or 0 for r in rs)
        ret = sum((r["stake"] or 0) * r["total_odds"] for r in rs if r["status"] == "won")
        return {"played": len(rs), "won": sum(r["status"] == "won" for r in rs), "staked_u": round(staked, 2), "returned_u_no_bonus": round(ret, 2),
                "roi_no_bonus": round(ret / staked - 1, 3) if staked else None}

    out = agg(rows)
    out["by_tier"] = {f"T{t}": {"label": TIERS[t][0], **agg([r for r in rows if r["variant"] == f"c100_t{t}"])} for t in TIERS}
    return out


def doc(conn: sqlite3.Connection, today: date) -> Dict[str, Any]:
    t = conn.execute("SELECT id, total_odds, p_ticket, ev, notes, stake, (SELECT COUNT(*) FROM ticket_leg WHERE ticket_id=ticket.id) legs FROM ticket WHERE kind=? AND day=? AND status!='replaced' ORDER BY id DESC LIMIT 1",
                     (KIND, today.isoformat())).fetchone()
    return {"schema": "betpredict.calea100.v1", "version": VERSION, "start": START, "generated_at": repo.now_iso(),
            "rules": {"bonus": {"legs": list(LEGS), "leg_odds": list(LEG_ODDS), "markets": sorted(KEYS), "t0_markets": sorted(T0_KEYS), "max_boosts": MAX_BOOSTS,
                                "tiers": {f"T{t}": {"label": v[0], "leg_roi": v[1], "stake_lei": round(v[2] * 10, 1)} for t, v in TIERS.items()},
                                "bad_markets": sorted(BAD_KEYS), "bad_leagues": sorted(BAD_LEAGUES), "no_night": "00:00–07:00"},
                      "roll": {"start_lei": ROLL_START_LEI, "target": ROLL_TARGET, "source": "Pontul zilei"}},
            "today": ({"ticket_id": t["id"], "odds": t["total_odds"], "p_honest": t["p_ticket"], "ev_bonus": t["ev"],
                       "superbonus": json.loads(t["notes"] or "{}").get("superbonus"), "tier": json.loads(t["notes"] or "{}").get("tier"),
                       "tier_label": json.loads(t["notes"] or "{}").get("tier_label"), "stake_lei": round((t["stake"] or 0) * 10, 1),
                       "legs": t["legs"]} if t else None),
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
