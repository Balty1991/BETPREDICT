"""Robotul de bilete mari: în fiecare zi multe bilete de ~1.000, ~5.000 și ~10.000, pe hârtie, ca să vedem câte prindem.

Matematica (arhiva BSD, 4.689 de meciuri cu cote, 2025–2026): marja casei se adună pe fiecare selecție, așa că un bilet de
1.000 din selecții obișnuite are șansa de ~1 la 2.500; nicio piață nu a ieșit constant peste cotă în ambele jumătăți ale
perioadei. Singura pârghie reală e marja: robotul ia selecțiile cu cea mai mare șansă pentru cota lor (−ln p / ln cotă cât mai
mic, cu p = probabilitatea onestă, 90% piață fără marjă) și le preferă pe cele unde Superbet dă peste prețul corect. NG și Sub
2.5 / Sub 1.5 nu intră (în arhivă au ieșit cu 10–20% sub cotă). Biletele sunt variate (alt punct de pornire), un meci apare de
o singură dată în toată ziua (o selecție foarte sigură, de cel mult ``MAX_REUSE`` ori; două bilete au cel mult
``MAX_SHARED`` meciuri comune), cel mult 3 meciuri din aceeași ligă pe bilet. Rezultatele: ``stats_doc``."""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from betpredict.store import repo
from betpredict.timeutil import canon_utc

KIND = "acca_super"
# (variantă, țintă, câte bilete pe zi, selecții min/max)
# SuperBonus Superbet: +25% din profit la 10 selecții de la 1.35, +5% pentru fiecare în plus (max. +100%). Cu marja obișnuită
# (~3% pe selecție) EV-ul biletului e ≈ 0.97^n × (1 + bonus) − 1: −8% la 10 selecții, ≈ −5% de la 12 la 22 (fără bonus: −30…−45%).
# De aceea: fiecare selecție de la 1.35 (intră la bonus) și cel puțin 12 selecții pe bilet.
# 17.11: câteva bilete scurte de ~10 (se prind mai des) și restul lungi, toate din piețele recomandate (REC)
# (varianta, cota țintă, câte bilete pe zi, (min, max) selecții). Selecțiile recomandate sunt mici (~1.30–1.55), deci
# biletele lungi au nevoie de multe meciuri; Superbet primește până la 30 de evenimente pe bilet.
TIERS = (("s10", 10.0, 3, (3, 9)), ("s1000", 1000.0, 3, (20, 30)), ("s5000", 5000.0, 2, (20, 30)), ("s10000", 10000.0, 2, (22, 30)))
# Biletele lungi: 20–30 selecții, toate de cel puțin 1.35 → SuperBonus +75…+100% din profit. Backtest pe arhivă
# (48.800 meciuri): 25 de favoriți la 1.35–1.45 au ieșit +46% (2020–24) și +121% (2024–26) cu bonus; aceleași bilete
# cu selecții la întâmplare 1.35–1.55: −46%. Bonusul face plusul, selecțiile trebuie doar să fie aproape de prețul corect.
LONG_MIN_ODDS = 1.35
LONG_MAX_ODDS = 1.65   # marja Superbet: ~4.5% la 1.30–1.60, ~8% la 1.60–2.20 (50.568 selecții decontate) → pe 20+ selecții contează
LONG_SPAN = 4.0       # la biletele lungi contează numărul de selecții (bonusul): 1.000 → 1.000–4.000
MAX_PER_SEL = 10      # pe un bilet, cel mult 12 selecții de același tip (dacă o piață e prost cotată, nu cade tot)
SHORT = {"s10"}       # biletele de ~10 au meciurile lor; un meci poate fi o dată pe un bilet de 10 și o dată pe unul lung
SPAN = 2.5            # cota biletului: de la țintă până la 2,5 × țintă
LEG_ODDS = (1.25, 2.30)  # A doua repriză 1-3 e pe la 1.30; pe biletele lungi selecțiile de la 1.35 aduc SuperBonusul
MIN_EV = -0.05        # sub atât marja e prea mare pe selecție
MAX_REUSE = 2         # doar pentru selecțiile foarte sigure (SAFE_P); celelalte apar o singură dată în toată ziua
SAFE_P = 0.80
MAX_SHARED = 2        # două bilete au în comun cel mult 2 meciuri: un rezultat-surpriză nu pierde toate biletele deodată
LEAGUE_CAP = 3
SHORT_LEAGUE_CAP = 5  # biletele de ~10 au doar meciurile zilei: în zilele cu puține ligi se acceptă până la 5 dintr-o ligă
HORIZON_H = 36        # Stil/ofertă clasică; biletele de ~10 iau doar meciurile zilei (vezi build)
LONG_HORIZON_H = 168  # biletele lungi au nevoie de ~25 de meciuri: iau din următoarele 7 zile (cât are oferta Superbet)
STAKE_U = 0.02        # ~2 lei la o bancă de 100 de unități
RULES_V = "rec5"       # versiunea regulilor (SuperBonus + fără meciuri repetate); biletele neîncepute mai vechi se refac
MIN_TICKET_EV = -0.10  # cu SuperBonus inclus; biletele mai slabe nu se publică (mai bine mai puține, dar bune)
MARKETS = {"1x2", "double_chance", "over_under", "btts", "draw_no_bet", "ss", "bb"}
# Piețele recomandate (analiza din 17.11 pe 5 surse: football-data 48.826 meciuri / 7 sezoane, cote de închidere Superbet,
# predicțiile robotului, Bet Builder-ele Superbet, auditul din octombrie): (piața Superbet, selecția) → (piață, selecție,
# cotă min, cotă max, ROI măsurat micșorat). Șansa folosită = (1 + ROI) / cotă: prețul, cu cât a ieșit de fapt, fără modelul,
# care unde vedea „valoare” a pierdut −10…−31%.
REC = {
    ("A doua repriză - Interval goluri", "1-3"): ("ss", "H2G13", 1.25, 1.45, 0.03),
    ("Ambele echipe marchează (GG)", "Da"): ("btts", "YES", 1.50, 2.10, 0.015),  # 1.85–2.10 arhivă/Superbet; 1.50–1.80 Robot +2.5% (125)
    ("Total goluri", "Peste 1.5"): ("over_under", "OVER", 1.30, 1.50, 0.03, 1.5),  # istoricul Robotului: +5% (127 selecții, 78% intrate)
    ("Prima repriză - Total goluri", "Sub 1.5"): ("ss", "H1U15", 1.45, 1.70, 0.0),
    ("Final", "1"): ("1x2", "HOME", 1.20, 1.45, 0.0),   # gazdă 1.35–1.45: +0.1% / +0.5% pe cele două perioade
    ("Final", "2"): ("1x2", "AWAY", 1.30, 1.45, 0.0),   # oaspete favorit doar până la 1.45 (1.45–1.55 a căzut pe minus)
}
REC_COMBO_ROI = 0.0  # Peste 0.5 goluri & Peste 7.5 cornere, 1.40–1.60: arhivă +6.7% (354), noiembrie 52–60%: la zero
REC_ONLY = True
# Tipare pe ligi din arhiva de 48.800 de meciuri (2020–2026), care au ținut pe aproape toate sezoanele.
# Intră doar pe biletele lungi (egalurile au cote ~3: pe un bilet de ~10 ar fi prea riscante).
# (id ligă, ieșire „Final”) → (piață, selecție, cotă min, cotă max, ROI istoric, de unde vine)
LEAGUE_REC = {
    (100, "X"): ("1x2", "DRAW", 2.60, 3.40, 0.08, "Serie B: egal +8% (1.847 meciuri, 6/7 sezoane pe plus)"),
    (4, "2"): ("1x2", "AWAY", 1.30, 1.90, 0.08, "Serie A: oaspete favorit +8% (393 meciuri, 7/7 sezoane)"),
    (11, "2"): ("1x2", "AWAY", 1.30, 1.90, 0.10, "Turcia: oaspete favorit +16% (224 meciuri, 6/7 sezoane)"),
    (3, "1"): ("1x2", "HOME", 1.30, 1.70, 0.05, "La Liga: gazdă favorită +6% (445 meciuri, 5/7 sezoane)"),
    (24, "X"): ("1x2", "DRAW", 2.60, 3.40, 0.04, "Grecia: egal +5% (809 meciuri, 5/7 sezoane)"),
    (2, "X"): ("1x2", "DRAW", 2.60, 3.40, 0.04, "Portugalia: egal +4% (935 meciuri, 5/7 sezoane)"),
    (3, "X"): ("1x2", "DRAW", 2.60, 3.40, 0.04, "La Liga: egal +4% (1.108 meciuri, 5/7 sezoane)"),
}
LEAGUE_GRADE = "L"  # marcaj pe selecțiile din tiparele pe ligi (doar biletele lungi, au prioritate pe meciul lor)
# Piețele Stil Supersocial care au ieșit pe plus la cotele reale Superbet (audit 23.10.2026, 400+ rezultate fiecare):
# A doua repriză 1-3 goluri +5%, Cartonașe Sub 4.5 +2.6%, Gol în ambele reprize +0.9%, Cartonașe Sub 5.5 +1%. Restul au pierdut
# constant (−2% … −20%). Șansa folosită: cât au ieșit de fapt la cota lor (ROI micșorat), niciodată peste șansa modelului.
STIL_ROI = {"H2G13": 0.02, "YCU45": 0.0, "R1R2": 0.005, "YCU55": 0.0}


def leg_ok(c) -> bool:
    if c.odds_source != "superbet" or c.price_suspect or c.market not in MARKETS:
        return False
    if c.drift is not None and c.drift > 0.05:
        return False
    if not LEG_ODDS[0] <= c.odds <= LEG_ODDS[1] and getattr(c, "grade", None) != LEAGUE_GRADE:
        return False
    if c.market == "ss" and c.selection not in STIL_ROI and c.selection not in {v[1] for v in REC.values() if v[0] == "ss"}:
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


def _rank(c) -> float:
    # pe același meci, tiparul pe ligă (dovadă pe 7 sezoane) trece înaintea unei selecții generale cu cost apropiat
    return cost(c) - (0.08 if getattr(c, "grade", None) == LEAGUE_GRADE else 0.0)


def candidates(pool: Sequence, now: datetime, hours: int = HORIZON_H, until_utc: Optional[str] = None, per_match: bool = True) -> List:
    soon = canon_utc((now + timedelta(minutes=10)).isoformat())
    until = until_utc or canon_utc((now + timedelta(hours=hours)).isoformat())
    best: Dict[int, Any] = {}
    for c in pool:
        if not (soon < (c.kickoff_utc or "") <= until) or not leg_ok(c):
            continue
        key = c.match_id if per_match else (c.match_id, c.market, c.selection, c.line)
        if key not in best or _rank(c) < _rank(best[key]):
            best[key] = c
    return sorted(best.values(), key=_rank)


def build_one(pool: Sequence, target: float, legs_rng, start: int, used: Dict[int, int], made: Sequence[set] = (), span: float = SPAN,
              league_cap: int = 0) -> Optional[List]:
    league_cap = league_cap or LEAGUE_CAP
    legs: List = []
    leagues: Dict[Any, int] = {}
    total = 1.0
    order = list(pool[start:]) + list(pool[:start])
    maxo = max((c.odds for c in pool), default=1.0)
    for c in order:
        if any(x.match_id == c.match_id for x in legs):
            continue  # o singură selecție pe meci (în zilele slabe, pe un meci pot fi mai multe variante recomandate)
        n = used.get(c.match_id, 0)
        if n >= (MAX_REUSE if c.p_honest >= SAFE_P else 1):
            continue  # meciul e deja pe alt bilet: se repetă doar o selecție foarte sigură, de cel mult 2 ori
        if n and any(c.match_id in m and len(m & {x.match_id for x in legs}) >= MAX_SHARED for m in made):
            continue  # ar face ca acest bilet să aibă prea multe meciuri comune cu unul deja făcut
        lg = c.league_id if c.league_id is not None else f"m{c.match_id}"
        if leagues.get(lg, 0) >= league_cap:
            continue
        if sum(1 for x in legs if x.selection == c.selection) >= MAX_PER_SEL:
            continue
        if total * c.odds > target * span:
            continue  # ar sări peste fereastră: căutăm o selecție mai mică
        if total * c.odds * (maxo ** (legs_rng[1] - len(legs) - 1)) < target:
            continue  # cu ea, selecțiile rămase n-ar mai ajunge la țintă: o selecție mică intră doar dacă mai e loc
        legs.append(c)
        leagues[lg] = leagues.get(lg, 0) + 1
        total *= c.odds
        if total >= target and len(legs) >= legs_rng[0]:
            return legs
        if len(legs) >= legs_rng[1]:
            return None
    return None


def load_stil(conn: sqlite3.Connection, now: datetime) -> List:
    """Selecțiile Stil din piețele care au ieșit pe plus, cu cotă Superbet reală (nu estimată), ca selecții de bilet."""
    from betpredict.builder.pool import Cand
    from betpredict.experimental import supersocial as SS

    lift = SS.key_lift(conn)
    out = []
    for c in SS.candidates(conn, now, HORIZON_H):
        k = c["key"]
        if k not in STIL_ROI or c.get("est") or not c.get("odds"):
            continue
        p = min(SS.realistic_p(c, lift), (1 + STIL_ROI[k]) / c["odds"])
        out.append(Cand(prediction_id=0, match_id=c["match_id"], league_id=c.get("league_id"), league=None,
                        kickoff_utc=c["kickoff_utc"], home=c.get("home"), away=c.get("away"), market="ss", line=0.0, selection=k,
                        odds=c["odds"], p=p, ev=p * c["odds"] - 1, grade="B", confidence=0, p_market=p, odds_source="superbet"))
    return out


PIN_MIN_RATIO = 0.98   # cota Superbet / prețul corect Pinnacle: sub atât selecția 1X2 nu intră (marja ar mânca bonusul)
PIN_VALUE_RATIO = 1.00 # la preț corect sau peste, un favorit 1.35–1.80 intră și în afara ferestrelor istorice
PIN_WINDOW = (1.35, 1.80)
OUT_1X2 = {"1": "HOME", "X": "DRAW", "2": "AWAY"}


def pin_fair(conn: sqlite3.Connection, match_ids: Sequence[int], now: datetime) -> Dict[Tuple[int, str], float]:
    """Șansa corectă (fără marjă) după ultima cotă Pinnacle 1X2 dinainte de acum, pe meci și ieșire (HOME/DRAW/AWAY)."""
    out: Dict[Tuple[int, str], float] = {}
    ids = list(set(match_ids))
    at = canon_utc(now.isoformat())
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        last: Dict[int, Dict[str, Tuple[str, float]]] = {}
        for mid, oc, dec, obs in conn.execute(
                f"""SELECT match_id, UPPER(outcome), decimal, observed_at FROM odds_snapshot WHERE source='bsd:pinnacle' AND market='1x2'
                    AND observed_at<=? AND match_id IN ({",".join("?" * len(chunk))})""", (at, *chunk)):
            if dec and dec > 1 and (oc not in last.setdefault(mid, {}) or obs > last[mid][oc][0]):
                last[mid][oc] = (obs, float(dec))
        for mid, d in last.items():
            if {"HOME", "DRAW", "AWAY"} <= set(d):
                inv = sum(1 / d[k][1] for k in ("HOME", "DRAW", "AWAY"))
                for k in ("HOME", "DRAW", "AWAY"):
                    out[(mid, k)] = (1 / d[k][1]) / inv
    return out


def load_recommended(conn: sqlite3.Connection, now: datetime) -> List:
    """Selecțiile din piețele recomandate, din oferta Superbet citită pentru următoarele ``HORIZON_H`` ore."""
    import re

    from betpredict.builder.pool import Cand

    lo = canon_utc((now + timedelta(minutes=10)).isoformat())
    hi = canon_utc((now + timedelta(hours=LONG_HORIZON_H)).isoformat())
    rows = conn.execute(
        """SELECT o.match_id, o.market_name, o.outcome, MAX(o.price) AS price, m.kickoff_utc, m.home_name, m.away_name,
                  m.league_id, l.name AS league
           FROM sb_offer o JOIN match m ON m.id=o.match_id LEFT JOIN league l ON l.id=m.league_id
           WHERE m.kickoff_utc>? AND m.kickoff_utc<=? GROUP BY o.match_id, o.market_name, o.outcome""", (lo, hi)).fetchall()
    out = []
    from betpredict.builder.rec_monitor import COMBO, market_stats

    live = market_stats(conn, REC, (1.40, 1.60), now)
    off = {k for k, v in live.items() if v.get("off")}  # piețe care pierd clar în ultimele 30 de zile: stau pe bară
    fair = pin_fair(conn, [r["match_id"] for r in rows if r["market_name"] == "Final"], now)
    for r in rows:
        mn, oc, price = r["market_name"] or "", r["outcome"] or "", float(r["price"] or 0)
        pf = fair.get((r["match_id"], OUT_1X2.get(oc, ""))) if mn == "Final" else None
        if pf is not None and price * pf < PIN_MIN_RATIO:
            continue  # Superbet plătește vizibil sub prețul corect Pinnacle: marja ar mânca bonusul
        if pf is not None and price * pf >= PIN_VALUE_RATIO and OUT_1X2.get(oc) != "DRAW" and PIN_WINDOW[0] <= price <= PIN_WINDOW[1] \
                and (r["league_id"], oc) not in LEAGUE_REC:
            p = min(0.97, pf)
            out.append(Cand(prediction_id=0, match_id=r["match_id"], league_id=r["league_id"], league=r["league"], kickoff_utc=r["kickoff_utc"],
                            home=r["home_name"], away=r["away_name"], market="1x2", line=0.0, selection=OUT_1X2[oc], odds=price, p=p,
                            ev=p * price - 1, grade="P", confidence=0, p_market=p, odds_source="superbet"))
            continue  # favorit plătit la prețul corect Pinnacle sau peste
        spec = REC.get((mn, oc))
        lspec = LEAGUE_REC.get((r["league_id"], oc)) if mn == "Final" else None
        grade = "B"
        if lspec:
            market, sel, a, b, roi, _why = lspec
            grade = LEAGUE_GRADE
            if not a <= price <= b and spec:  # în afara ferestrei tiparului: poate intra ca selecție generală
                market, sel, a, b, roi = spec[:5]
                grade = "B"
        elif spec:
            if (mn, oc) in off:
                continue
            market, sel, a, b, roi = spec[:5]
        else:
            text = mn if mn.strip().lower() == oc.strip().lower() else f"{mn} {oc}"
            if not re.fullmatch(r"peste 0\.5 goluri; peste 7\.5 cornere", re.sub(r"\s+", " ", text.lower().replace(",", ".").strip())):
                continue
            if COMBO in off:
                continue
            market, sel, a, b, roi = "bb", f"{mn}|{oc}", 1.40, 1.60, REC_COMBO_ROI
        if not a <= price <= b:
            continue
        p = min(0.97, (1 + roi / 2) / price)  # jumătate din plusul istoric: nu promitem mai mult decât am văzut
        if pf is not None:
            p = min(0.97, (p + pf) / 2)  # 1X2 cu Pinnacle: jumătate tiparul, jumătate prețul corect al meciului
        out.append(Cand(prediction_id=0, match_id=r["match_id"], league_id=r["league_id"], league=r["league"], kickoff_utc=r["kickoff_utc"],
                        home=r["home_name"], away=r["away_name"], market=market, line=float(spec[5]) if spec and len(spec) > 5 and grade == "B" else 0.0,
                        selection=sel, odds=price, p=p, ev=p * price - 1, grade=grade, confidence=0, p_market=p, odds_source="superbet"))
    return out


SHORT_FROM_HOUR_RO = 10  # biletele de ~10: doar meciuri de la ora 10 (ora României) până la miezul nopții
SHORT_PER_DAY = 2     # biletele de ~10 ale zilei: 1–2, meciuri diferite, doar din ziua curentă
LONG_ACTIVE = 5       # biletele lungi: mereu cel mult 5 în joc; când se pierde/termină unul, vine altul în loc
LONG_CYCLE = ("s1000", "s5000", "s10000")


def _ticket_matches(conn: sqlite3.Connection, ids: Sequence[int]) -> Tuple[Dict[int, int], List[set]]:
    used: Dict[int, int] = {}
    sets: List[set] = []
    for tid in ids:
        ms = {r[0] for r in conn.execute("SELECT match_id FROM ticket_leg WHERE ticket_id=?", (tid,))}
        sets.append(ms)
        for m in ms:
            used[m] = used.get(m, 0) + 1
    return used, sets


def build(conn: sqlite3.Connection, today: date, now: Optional[datetime] = None, pool: Optional[Sequence] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    start = canon_utc(now.isoformat())
    with conn:
        # biletele făcute cu reguli mai vechi se refac, dacă niciun meci de pe ele n-a început
        for t in conn.execute("SELECT id, notes FROM ticket WHERE kind=? AND status='pending'", (KIND,)).fetchall():
            if json.loads(t[1] or "{}").get("rules") == RULES_V:
                continue
            first = conn.execute("SELECT MIN(m.kickoff_utc) FROM ticket_leg l JOIN match m ON m.id=l.match_id WHERE l.ticket_id=?", (t[0],)).fetchone()[0]
            if first and first > start:
                conn.execute("UPDATE ticket SET status='replaced' WHERE id=?", (t[0],))
    cur_rules = lambda n: json.loads(n or "{}").get("rules") == RULES_V  # noqa: E731
    short_today = [r[0] for r in conn.execute("SELECT id, notes FROM ticket WHERE kind=? AND day=? AND variant IN ({}) AND status!='replaced'".format(
        ",".join("?" * len(SHORT))), (KIND, today.isoformat(), *SHORT)).fetchall() if cur_rules(r[1])]
    long_active = [(r[0], r[2]) for r in conn.execute("SELECT id, notes, variant FROM ticket WHERE kind=? AND status='pending' AND variant NOT IN ({})".format(
        ",".join("?" * len(SHORT))), (KIND, *SHORT)).fetchall()]
    need_short = max(0, SHORT_PER_DAY - len(short_today))
    need_long = max(0, LONG_ACTIVE - len(long_active))
    if not need_short and not need_long:
        return {"skipped_existing": len(short_today) + len(long_active)}
    if pool is None and REC_ONLY:
        pool = load_recommended(conn, now)
    if pool is None:
        from betpredict.builder.pool import load_pool

        pool = load_pool(conn, today, now) + load_pool(conn, today + timedelta(days=1), now)
    # biletele de ~10: doar meciurile zilei (ora României), ca să se încheie azi (piramidă cu reinvestire în 2 pași)
    from betpredict.timeutil import ro_day_bounds_utc

    day_start, day_end = ro_day_bounds_utc(today)
    # fără meciurile de noapte (00–10 ora României): biletul zilei se joacă ziua, nu se pierde cât dormi
    from_utc = canon_utc((datetime.fromisoformat(day_start.replace("Z", "+00:00")) + timedelta(hours=SHORT_FROM_HOUR_RO)).isoformat())
    cands_by = {"short": candidates([c for c in pool if getattr(c, "grade", None) != LEAGUE_GRADE and (c.kickoff_utc or "") >= from_utc],
                                    now, until_utc=day_end, per_match=False),
                "long": candidates([c for c in pool if LONG_MIN_ODDS <= c.odds <= LONG_MAX_ODDS], now, LONG_HORIZON_H)}
    # meciurile de pe biletele încă în joc nu se repetă pe cele noi
    u_s, s_s = _ticket_matches(conn, short_today)
    u_l, s_l = _ticket_matches(conn, [t for t, _ in long_active])
    used_by = {"short": u_s, "long": u_l}
    sets_by: Dict[str, List[set]] = {"short": s_s, "long": s_l}
    # ce ținte lipsesc din biletele lungi în joc: întâi cele care nu sunt deloc
    have_v = [v for _, v in long_active]
    plan: List[str] = [v for v in ("s10",) * need_short]
    for _ in range(need_long):
        v = min(LONG_CYCLE, key=lambda x: (have_v.count(x), LONG_CYCLE.index(x)))
        have_v.append(v)
        plan.append(v)
    spec = {v: (t, rng) for v, t, _, rng in TIERS}
    made: List[Dict[str, Any]] = []
    created = repo.now_iso()
    with conn:
        for i, variant in enumerate(plan):
            target, rng = spec[variant]
            fam = "short" if variant in SHORT else "long"
            cands = cands_by[fam]
            used, made_sets = used_by[fam], sets_by[fam]
            legs = None
            for k in range(6):  # câteva porniri diferite în listă; prima care dă un bilet bun
                st = (k * max(1, len(cands) // 6) + i) % max(1, len(cands))
                cand_legs = build_one(cands, target, rng, st, used, made_sets, SPAN if fam == "short" else LONG_SPAN,
                                      SHORT_LEAGUE_CAP if fam == "short" else LEAGUE_CAP)
                if not cand_legs:
                    continue
                total = math.prod(c.odds for c in cand_legs)
                p_t = math.prod(min(0.99, c.p_honest) for c in cand_legs)
                if p_t * (total + (total - 1) * superbonus(cand_legs)) - 1 >= MIN_TICKET_EV:
                    legs = cand_legs
                    break
            if not legs:
                continue
            for c in legs:
                used[c.match_id] = used.get(c.match_id, 0) + 1
            made_sets.append({c.match_id for c in legs})
            made.append({"variant": variant, **_insert(conn, variant, target, legs, today, created)})
    return {"pool": len(cands_by["long"]), "tickets": len(made), "made": made,
            "short_today": len(short_today) + sum(1 for m in made if m["variant"] in SHORT),
            "long_active": len(long_active) + sum(1 for m in made if m["variant"] not in SHORT)}


def superbonus(legs: Sequence) -> float:
    from betpredict.builder.calea100 import superbonus as sb

    return round(sb(sum(1 for c in legs if c.odds >= 1.35)), 4)


def _insert(conn: sqlite3.Connection, variant: str, target: float, legs: Sequence, day: date, created: str) -> Dict[str, Any]:
    total = math.prod(c.odds for c in legs)
    p = math.prod(min(0.99, c.p_honest) for c in legs)
    over = sum(1 for c in legs if c.ev_honest > 0)
    bonus = superbonus(legs)
    stil = sum(1 for c in legs if c.market == "ss")
    notes = {"label": f"Robot {int(target):,}+".replace(",", "."), "super": True, "paper": True, "risk_acknowledged": True,
             "rules": RULES_V, "superbonus": bonus, "payout_bonus": round(total + (total - 1) * bonus, 2),
             "reasons": [f"{len(legs)} selecții cu cea mai mare șansă pentru cota lor (marjă mică), " + ("din meciurile de azi" if target < 100 else f"din meciurile următoarelor {LONG_HORIZON_H // 24} zile")
                         + (f"; {stil} din piețele Stil care au ieșit pe plus." if stil else "."),
                         f"{over} din {len(legs)} selecții au cota Superbet peste prețul corect. SuperBonus Superbet: +{bonus:.0%} din profit "
                         f"(câștig la 1 leu: {total + (total - 1) * bonus:,.0f} în loc de {total:,.0f}).".replace(",", "."),
                         f"Șansa biletului: ~1 la {max(1, round(1 / p)):,}".replace(",", ".") + f" · cotă {total:,.0f}".replace(",", ".")
                         + ". Miză mică (~2 lei); se urmărește câte bilete ies din multe."]}
    cur = conn.execute(
        """INSERT INTO ticket (kind, variant, created_by, target_odds, total_odds, p_ticket, ev, stake, status, created_at, notes, day)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (KIND, variant, "robot", target, round(total, 2), round(p, 8), round(p * (total + (total - 1) * bonus) - 1, 4), STAKE_U, "pending", created,
         json.dumps(notes, ensure_ascii=False), day.isoformat()))
    tid = cur.lastrowid
    for c in sorted(legs, key=lambda c: c.kickoff_utc):
        pid = c.prediction_id if c.prediction_id and c.prediction_id > 0 else None
        conn.execute("INSERT INTO ticket_leg (ticket_id, prediction_id, match_id, market, selection, odds, odds_source) VALUES (?,?,?,?,?,?,?)",
                     (tid, pid, c.match_id, "bb" if c.market == "bb" else f"{c.market}|{(c.line or 0):g}", c.selection, c.odds, c.odds_source))
    return {"legs": len(legs), "odds": round(total, 2), "p": p, "bonus": bonus, "ev": round(p * (total + (total - 1) * bonus) - 1, 4)}


def stats_doc(conn: sqlite3.Connection, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Pe țintă: bilete terminate, câștigate, câte erau de așteptat după șansă, ROI la miză egală."""
    now = now or datetime.now(timezone.utc)
    out = []
    for variant, target, *_ in TIERS:
        rows = [(r[0], (json.loads(r[3] or "{}").get("payout_bonus") or r[1]), r[2]) for r in conn.execute(
            "SELECT status, total_odds, p_ticket, notes FROM ticket WHERE kind=? AND variant=? AND status!='replaced'", (KIND, variant))]
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


SEL_LABEL = {"OVER": "Peste 1.5 goluri", "H2G13": "Repriza 2: 1–3 goluri", "H1U15": "Repriza 1: sub 1.5 goluri", "YES": "Ambele marchează (GG)",
             "HOME": "1 · câștigă gazda", "AWAY": "2 · câștigă oaspeții", "DRAW": "X · egal"}
SEL_WHY = {"OVER": "Peste 1.5 goluri la 1.30–1.50: +5% în istoricul Robotului (127 selecții, 78% intrate).",
           "H2G13": "Superbet: +5% în octombrie (459 selecții), R2 peste 0.5 +3% în istoricul Robotului.",
           "H1U15": "Superbet, cote 1.45–1.65: +2.6% (182 selecții). De urmărit: puține zile.",
           "YES": "GG: la 1.85–2.10 arhivă +20% / +2% și Superbet +1.6% (185); la 1.50–1.80 Robot +2.5% (125).",
           "HOME": "Gazdă favorită 1.35–1.45: aproape de prețul corect în arhivă (+0.1% / +0.5% pe 48.800 de meciuri).",
           "AWAY": "Oaspete favorit 1.30–1.45: aproape de prețul corect în arhivă.",
           "COMBO": "Peste 0.5 goluri + peste 7.5 cornere la 1.40–1.60: arhivă +6.7% (354), cam la prețul corect acum."}


def recommended_doc(conn: sqlite3.Connection, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Selecțiile recomandate (cele din care Robotul face biletele), pe următoarele zile, cu motivul din istoric."""
    from betpredict.timeutil import ro_date_of as ro_day

    now = now or datetime.now(timezone.utc)
    from betpredict.builder.rec_monitor import COMBO, market_stats

    live = market_stats(conn, REC, (1.40, 1.60), now)
    key_of = {v[1]: k for k, v in REC.items()}
    rows = []
    league_why = {(lg, OUT_1X2[oc]): v[5] for (lg, oc), v in LEAGUE_REC.items()}
    soon = canon_utc((now + timedelta(minutes=5)).isoformat())
    for c in load_recommended(conn, now):
        if (c.kickoff_utc or "") <= soon or not leg_ok(c):
            continue
        combo = c.market == "bb"
        if c.grade == LEAGUE_GRADE:
            why, kind = league_why.get((c.league_id, c.selection), "Tipar pe ligă din arhivă."), "liga"
        elif c.grade == "P":
            why, kind = "Superbet plătește cel puțin prețul corect Pinnacle pentru acest meci.", "pinnacle"
        else:
            why, kind = SEL_WHY.get("COMBO" if combo else c.selection, ""), "tipar"
            st = live.get(COMBO if combo else key_of.get(c.selection))
            if st and st["n"] >= 30:
                why += f" Ultimele {st['days']} de zile pe Superbet: {st['roi']:+.0%} pe {st['n']} selecții."
        rows.append({"match_id": c.match_id, "kickoff_utc": c.kickoff_utc, "day": ro_day(c.kickoff_utc).isoformat() if ro_day(c.kickoff_utc) else None,
                     "home": c.home, "away": c.away, "league": c.league,
                     "label": "Peste 0.5 goluri + peste 7.5 cornere" if combo else SEL_LABEL.get(c.selection, c.selection),
                     "odds": round(c.odds, 2), "p": round(c.p_honest, 4), "bonus_ok": c.odds >= LONG_MIN_ODDS, "kind": kind, "why": why})
    rows.sort(key=lambda r: (r["kickoff_utc"], -r["p"]))
    markets = [{"label": "Peste 0.5 goluri + peste 7.5 cornere" if k == COMBO else SEL_LABEL.get(REC[k][1], k[1]), **v}
               for k, v in live.items()]
    return {"generated_at": canon_utc(now.isoformat()), "count": len(rows), "rows": rows, "markets": markets,
            "note": "Selecțiile din care Robotul face biletele: piețe care au ieșit aproape de prețul corect sau peste, în istoric. "
                    "Nu sunt sigure una câte una; pe biletele lungi, SuperBonusul (de la 1.35) face diferența."}
