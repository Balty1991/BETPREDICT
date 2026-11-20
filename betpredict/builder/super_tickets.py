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
import re
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
TIERS = (("s10", 10.0, 2, (6, 9)), ("s1000", 1000.0, 3, (20, 25)), ("s5000", 5000.0, 2, (20, 25)), ("s10000", 10000.0, 2, (22, 25)))
# Biletele lungi: 20–30 selecții, toate de cel puțin 1.35 → SuperBonus +75…+100% din profit. Backtest pe arhivă
# (48.800 meciuri): 25 de favoriți la 1.35–1.45 au ieșit +46% (2020–24) și +121% (2024–26) cu bonus; aceleași bilete
# cu selecții la întâmplare 1.35–1.55: −46%. Bonusul face plusul, selecțiile trebuie doar să fie aproape de prețul corect.
LONG_MIN_ODDS = 1.35
LONG_MAX_ODDS = 1.65   # marja Superbet: ~4.5% la 1.30–1.60, ~8% la 1.60–2.20 (50.568 selecții decontate) → pe 20+ selecții contează
LONG_SPAN = 4.0       # la biletele lungi contează numărul de selecții (bonusul): 1.000 → 1.000–4.000
INTL = re.compile(r"international|nations league|world cup|qualif|friendl|euro 20|copa am|gold cup|africa cup", re.I)
INTL_PENALTY = 0.15   # internaționale și amicale: pe Superbet −8% față de +6% la cluburi (633 selecții recomandate) → mai rar pe bilete
INTL_CAP = {"short": 2, "long": 4}
SHORT_MAX_ODDS = 1.65  # biletul de ~10: 6–9 selecții mici (structurile scurte cu selecții de 1.6–2.1 au ieșit cel mai prost)
SHORT_EXCLUDE = {"YES"}  # GG: 36% intrate față de 54% așteptat pe biletele de ~10; −4.5% pe Superbet
SEL_CAP = {"YES": 4}
SHORT_SEL_CAP = {"H2G13": 5}  # R2 1–3 la ~1.30 e ușor pe minus în arhivă: pe biletul de ~10 cel mult 5, restul din alte piețe  # GG: −5% pe Superbet în ultimele zile, doar câteva pe un bilet
MAX_PER_SEL = 10      # pe un bilet, cel mult 12 selecții de același tip (dacă o piață e prost cotată, nu cade tot)
SHORT = {"s10"}       # biletele de ~10 au meciurile lor; un meci poate fi o dată pe un bilet de 10 și o dată pe unul lung
SPAN = 2.5            # cota biletului: de la țintă până la 2,5 × țintă
LEG_ODDS = (1.25, 2.30)  # A doua repriză 1-3 e pe la 1.30; pe biletele lungi selecțiile de la 1.35 aduc SuperBonusul
MIN_EV = -0.05        # sub atât marja e prea mare pe selecție
MAX_REUSE = 2         # doar pentru selecțiile foarte sigure (SAFE_P); celelalte apar o singură dată în toată ziua
SAFE_P = 0.80
MAX_SHARED = 2        # două bilete au în comun cel mult 2 meciuri: un rezultat-surpriză nu pierde toate biletele deodată
LEAGUE_CAP = 3
# (cel mult din aceeași ligă, cel mult în același interval de 2 ore): se încearcă în ordine, primul care dă bilet
DIVERSITY_SHORT = ((2, 3), (3, 4), (5, 99))
DIVERSITY_LONG = ((LEAGUE_CAP, 6), (LEAGUE_CAP, 99))
SHORT_LEAGUE_CAP = 5  # biletele de ~10 au doar meciurile zilei: în zilele cu puține ligi se acceptă până la 5 dintr-o ligă
HORIZON_H = 36        # Stil/ofertă clasică; biletele de ~10 iau doar meciurile zilei (vezi build)
LONG_HORIZON_H = 168  # biletele lungi au nevoie de ~25 de meciuri: iau din următoarele 7 zile (cât are oferta Superbet)
STAKE_U = 0.02        # ~2 lei la o bancă de 100 de unități
RULES_V = "rec9"       # versiunea regulilor (rec9: șansă calibrată pe cotele de închidere, marja pe meci, ligi/ore variate); biletele neîncepute mai vechi se refac
MIN_TICKET_EV = -0.10  # cu SuperBonus inclus; biletele mai slabe nu se publică (mai bine mai puține, dar bune)
MARKETS = {"1x2", "double_chance", "over_under", "btts", "draw_no_bet", "ss", "bb", "sb"}
# Piețele recomandate (analiza din 17.11 pe 5 surse: football-data 48.826 meciuri / 7 sezoane, cote de închidere Superbet,
# predicțiile robotului, Bet Builder-ele Superbet, auditul din octombrie): (piața Superbet, selecția) → (piață, selecție,
# cotă min, cotă max, ROI măsurat micșorat). Șansa folosită = (1 + ROI) / cotă: prețul, cu cât a ieșit de fapt, fără modelul,
# care unde vedea „valoare” a pierdut −10…−31%.
REC = {
    ("A doua repriză - Interval goluri", "1-3"): ("ss", "H2G13", 1.25, 1.45, 0.03),
    ("A doua repriză - Interval goluri", "1-2"): ("ss", "H2G12", 1.45, 1.65, 0.0),  # Superbet +6.6% (119), pe ambele jumătăți ale zilelor
    ("Ambele echipe marchează (GG)", "Da"): ("btts", "YES", 1.50, 2.10, 0.015),  # 1.85–2.10 arhivă/Superbet; 1.50–1.80 Robot +2.5% (125)
    ("Total goluri", "Peste 1.5"): ("over_under", "OVER", 1.30, 1.50, 0.03, 1.5),  # istoricul Robotului: +5% (127 selecții, 78% intrate)
    ("Prima repriză - Total goluri", "Sub 1.5"): ("ss", "H1U15", 1.45, 1.70, 0.0),
    ("Final", "1"): ("1x2", "HOME", 1.20, 1.45, 0.0),   # gazdă 1.35–1.45: +0.1% / +0.5% pe cele două perioade
    ("Final", "2"): ("1x2", "AWAY", 1.30, 1.60, 0.01),  # oaspete favorit 1.35–1.60: arhivă +1.9% (2020–24) / +2.5% (2024–26)
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
    if c.market == "ss" and c.selection not in STIL_ROI and c.selection not in {v[1] for v in REC.values() if v[0] == "ss"} \
            and c.selection not in DISC_KEYS:
        return False
    if c.market == "sb" and c.selection not in DISC_KEYS:
        return False  # piață generală: doar cele trecute de probă
    if c.market == "btts" and c.selection == "NO":
        return False
    if c.market == "over_under" and c.selection == "UNDER" and (c.line or 0) <= 2.5:
        return False
    return c.ev_honest >= MIN_EV


def cost(c) -> float:
    """Cât „costă” selecția din șansa biletului pentru cota pe care o aduce (mai mic = mai bine); EV-ul pozitiv ajută."""
    p = max(1e-6, min(0.99, c.p_honest))
    return -math.log(p) / math.log(c.odds) - 0.5 * max(0.0, c.ev_honest)


def day_hours_ok(c) -> bool:
    """Doar meciuri de la 10:00 la 24:00 ora României: selecțiile de noapte au intrat 43% față de 69% cât era de așteptat."""
    from zoneinfo import ZoneInfo

    try:
        return datetime.fromisoformat((c.kickoff_utc or "").replace("Z", "+00:00")).astimezone(ZoneInfo("Europe/Bucharest")).hour >= SHORT_FROM_HOUR_RO
    except ValueError:
        return False


def is_intl(c) -> bool:
    return bool(INTL.search(getattr(c, "league", None) or ""))


def _rank(c) -> float:
    # pe același meci, tiparul pe ligă (dovadă pe 7 sezoane) trece înaintea unei selecții generale cu cost apropiat
    return cost(c) - (0.08 if getattr(c, "grade", None) == LEAGUE_GRADE else 0.0) + (INTL_PENALTY if is_intl(c) else 0.0) + OVR_RANK_W * ovr_gap(c)


def ovr_gap(c) -> float:
    """Marja Superbet a selecției la acest meci față de marja obișnuită a pieței (negativ = mai ieftină decât de obicei)."""
    ex = getattr(c, "extra", None) or {}
    o, t = ex.get("ovr"), ex.get("ovr_typ")
    return (o - t) / t if o and t else 0.0


def slot(c) -> Optional[int]:
    """Intervalul de 2 ore (ora României) în care începe meciul: pe biletul de ~10 nu vrem toate meciurile la aceeași oră."""
    from zoneinfo import ZoneInfo

    try:
        return datetime.fromisoformat((c.kickoff_utc or "").replace("Z", "+00:00")).astimezone(ZoneInfo("Europe/Bucharest")).hour // 2
    except ValueError:
        return None


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
              league_cap: int = 0, intl_cap: int = 99, sel_cap: Optional[Dict[str, int]] = None, slot_cap: int = 99) -> Optional[List]:
    sel_cap = {**SEL_CAP, **(sel_cap or {})}
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
        if is_intl(c) and sum(1 for x in legs if is_intl(x)) >= intl_cap:
            continue
        if sum(1 for x in legs if x.selection == c.selection) >= sel_cap.get(c.selection, MAX_PER_SEL):
            continue
        if slot_cap < 99 and sum(1 for x in legs if slot(x) == slot(c)) >= slot_cap:
            continue  # prea multe meciuri care încep în aceleași 2 ore
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


# ------------------------------------------------------------------ calibrarea șansei pe selecție
# 19.11: vechea șansă (1 + ROI/2) / cotă a promis 71% pe selecțiile biletelor de ~10 și au intrat 49% (53 de selecții, multe
# noaptea și la internaționale). Acum șansa vine din cât au intrat de fapt selecțiile pieței la cotele de închidere Superbet
# (ultimele CAL_DAYS zile, doar meciuri deja jucate), pe segment (cluburi/internaționale × zi/noapte), micșorată Bayes spre
# „aproape de prețul corect” (CAL_Q0) cu CAL_K câștiguri virtuale la fiecare nivel: toate piețele → piața → piața pe segment.
# q = câte au intrat / Σ(1/cotă) (1 = exact la cotă); șansa = q / cotă × ajustarea pentru marja meciului.
CAL_DAYS = 45
CAL_K = 120.0          # replay 13–18.11 (471 selecții de zi): K mic (60) urmărește zgomotul primelor zile; 120 e mai aproape de rezultate
CAL_Q0 = 1.0           # fără date: exact la cotă (piețele recomandate au ieșit aproape de prețul de închidere; media generală e −6%)
CAL_Q_MAX = 1.0        # niciodată peste preț: oricât de bine ar fi ieșit pe puține zile, nu afișăm avantaj (marja e reală)
CAL_Q_MIN = 0.75
# Marja pe meci față de media pieței NU intră în șansă: în replay (13–18.11, 465 de selecții pe treimi de marjă) intrarea față de
# cotă a fost 1.03 / 1.00 / 1.07 de la marja mică la cea mare — niciun semnal măsurabil. Rămâne doar ca departajare la clasare
# (la șanse egale, prețul mai puțin încărcat) și în explicații.
OVR_RANK_W = 1.0
SEGMENTS = ("club_day", "club_night", "intl_day", "intl_night")
# piața complementară din care se calculează marja Superbet pe meci (suma 1/cotă pe toate ieșirile)
COMPLEMENT: Dict[Tuple[str, str], Tuple[Tuple[str, str], ...]] = {
    ("Final", "1"): (("Final", "X"), ("Final", "2")),
    ("Final", "2"): (("Final", "X"), ("Final", "1")),
    ("Total goluri", "Peste 1.5"): (("Total goluri", "Sub 1.5"),),
    ("Prima repriză - Total goluri", "Sub 1.5"): (("Prima repriză - Total goluri", "Peste 1.5"),),
    ("Ambele echipe marchează (GG)", "Da"): (("Ambele echipe marchează (GG)", "Nu"),),
    ("A doua repriză - Interval goluri", "1-3"): (("A doua repriză - Total goluri", "Sub 0.5"), ("A doua repriză - Total goluri", "Peste 3.5")),
    ("A doua repriză - Interval goluri", "1-2"): (("A doua repriză - Total goluri", "Sub 0.5"), ("A doua repriză - Total goluri", "Peste 2.5")),
}
CAL_MARKETS = sorted({k[0] for k in COMPLEMENT} | {x[0] for v in COMPLEMENT.values() for x in v})


def segment(league: Optional[str], kickoff_utc: Optional[str]) -> str:
    from betpredict.builder.rec_monitor import is_intl_league, is_night

    return ("intl" if is_intl_league(league) else "club") + ("_night" if is_night(kickoff_utc) else "_day")


def overround(prices: Dict[Tuple[str, str], float], key: Tuple[str, str]) -> Optional[float]:
    """Marja Superbet pe meci pentru selecția ``key``: Σ 1/cotă pe ieșirea aleasă și complementul ei (None dacă lipsește)."""
    own = prices.get(key)
    comp = [prices.get(x) for x in COMPLEMENT.get(key, ())]
    if not own or own <= 1 or not comp or not all(x and x > 1 for x in comp):
        return None
    return 1 / own + sum(1 / x for x in comp)  # type: ignore[operator]


def _shrink(won: float, inv: float, parent: float, k: Optional[float] = None) -> float:
    k = CAL_K if k is None else k
    return (won + k * parent) / (inv + k)


def leg_calibration(conn: sqlite3.Connection, now: datetime, days: int = CAL_DAYS) -> Dict[str, Any]:
    """Cât au intrat piețele recomandate la cotele de închidere Superbet (meciuri jucate în ultimele ``days`` zile, până la
    acum − 3 h): q pe piață și segment, micșorat ierarhic. ``q[(key, seg)]`` = multiplicatorul față de 1/cotă."""
    from betpredict.builder.rec_monitor import settle

    lo = canon_utc((now - timedelta(days=days)).isoformat())
    hi = canon_utc((now - timedelta(hours=3)).isoformat())
    try:
        rows = conn.execute(
            f"""SELECT s.match_id, s.market_name, s.outcome, MAX(s.price), m.ft_home, m.ft_away, m.ht_home, m.ht_away, m.kickoff_utc, l.name
                FROM sb_offer_close s JOIN match m ON m.id=s.match_id LEFT JOIN league l ON l.id=m.league_id
                WHERE m.status='finished' AND m.ft_home IS NOT NULL AND m.kickoff_utc>=? AND m.kickoff_utc<?
                  AND s.market_name IN ({",".join("?" * len(CAL_MARKETS))})
                GROUP BY s.match_id, s.market_name, s.outcome""", (lo, hi, *CAL_MARKETS)).fetchall()
    except sqlite3.OperationalError:
        rows = []
    per: Dict[int, Dict[str, Any]] = {}
    for mid, mn, oc, pr, fh, fa, hh, ha, ko, lg in rows:
        d = per.setdefault(mid, {"p": {}, "r": (fh, fa, hh, ha), "seg": segment(lg, ko)})
        if pr:
            d["p"][(mn, oc)] = float(pr)
    acc: Dict[Any, List[float]] = {}

    def add(k, won, inv):
        a = acc.setdefault(k, [0, 0.0, 0.0])
        a[0] += 1; a[1] += won; a[2] += inv  # noqa: E702

    for d in per.values():
        for key, spec in REC.items():
            pr = d["p"].get(key)
            if not pr or not spec[2] <= pr <= spec[3]:
                continue
            won = settle(key[0], key[1], *d["r"])
            if won is None:
                continue
            for k in ("all", ("seg", d["seg"]), key, (key, d["seg"])):
                add(k, int(won), 1 / pr)
    get = lambda k: acc.get(k, [0, 0.0, 0.0])  # noqa: E731
    q_all = _shrink(get("all")[1], get("all")[2], CAL_Q0)
    g = {s: _shrink(get(("seg", s))[1], get(("seg", s))[2], q_all) / q_all for s in SEGMENTS}
    q: Dict[Any, float] = {}
    n: Dict[Any, Tuple[int, int]] = {}
    for key in REC:
        q_m = _shrink(get(key)[1], get(key)[2], q_all)
        for s in SEGMENTS:
            a = get((key, s))
            q[(key, s)] = max(CAL_Q_MIN, min(CAL_Q_MAX, _shrink(a[1], a[2], q_m * g[s])))
            n[(key, s)] = (int(a[0]), int(a[1]))
    return {"q": q, "n": n, "g": g, "q_all": q_all, "days": days, "selections": int(get("all")[0])}


DISC_KEYS: set = set()  # piețele găsite singur și trecute de probă (betpredict/builder/discovery.py)


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
    from betpredict.builder import discovery
    from betpredict.builder.rec_monitor import COMBO, market_stats

    from betpredict.builder import market_settle as MS

    disc = discovery.active_specs(conn)  # piețe noi, active după probă: intră ca piețele recomandate
    disc_sb = discovery.active_sb(conn)  # piețe generale (orice tip Superbet) active după probă
    sb_teams: Dict[int, Any] = {}
    DISC_KEYS.clear()
    DISC_KEYS.update(v[1] for v in disc.values())
    DISC_KEYS.update(disc_sb)
    rec_all = {**disc, **REC}

    live = market_stats(conn, REC, (1.40, 1.60), now)
    off = {k for k, v in live.items() if v.get("off")}  # piețe care pierd clar în ultimele 30 de zile: stau pe bară
    fair = pin_fair(conn, [r["match_id"] for r in rows if r["market_name"] == "Final"], now)
    cal = leg_calibration(conn, now)
    prices: Dict[int, Dict[Tuple[str, str], float]] = {}
    for r in rows:
        if r["price"]:
            prices.setdefault(r["match_id"], {})[(r["market_name"] or "", r["outcome"] or "")] = float(r["price"])
    typ: Dict[Tuple[str, str], float] = {}  # marja obișnuită a pieței acum (mediana pe meciurile din ofertă)
    for key in COMPLEMENT:
        vals = sorted(o for o in (overround(d, key) for d in prices.values()) if o)
        if vals:
            typ[key] = vals[len(vals) // 2]

    def mk(r, market, sel, price, p, grade, line=0.0, key=None, seg=None, q=None, why=None):
        ovr = overround(prices.get(r["match_id"], {}), key) if key else None
        c = Cand(prediction_id=0, match_id=r["match_id"], league_id=r["league_id"], league=r["league"], kickoff_utc=r["kickoff_utc"],
                 home=r["home_name"], away=r["away_name"], market=market, line=line, selection=sel, odds=price, p=p,
                 ev=p * price - 1, grade=grade, confidence=0, p_market=p, odds_source="superbet")
        c.extra.update({"seg": seg, "q": q, "ovr": ovr, "ovr_typ": typ.get(key) if key else None, "cal_n": cal["n"].get((key, seg)) if key else None,
                        "cal_days": cal["days"], "why": why})
        return c

    for r in rows:
        mn, oc, price = r["market_name"] or "", r["outcome"] or "", float(r["price"] or 0)
        seg = segment(r["league"], r["kickoff_utc"])
        g = cal["g"].get(seg, 1.0)
        pf = fair.get((r["match_id"], OUT_1X2.get(oc, ""))) if mn == "Final" else None
        if pf is not None and price * pf < PIN_MIN_RATIO:
            continue  # Superbet plătește vizibil sub prețul corect Pinnacle: marja ar mânca bonusul
        if pf is not None and price * pf >= PIN_VALUE_RATIO and OUT_1X2.get(oc) != "DRAW" and PIN_WINDOW[0] <= price <= PIN_WINDOW[1] \
                and (r["league_id"], oc) not in LEAGUE_REC:
            # favorit plătit la prețul corect Pinnacle sau peste: jumătate Pinnacle, jumătate cât au intrat selecțiile la cota lor
            p = min(0.97, (pf + min(CAL_Q_MAX, cal["q_all"] * g) / price) / 2)
            out.append(mk(r, "1x2", OUT_1X2[oc], price, p, "P", key=(mn, oc), seg=seg, why="pinnacle"))
            continue
        spec = rec_all.get((mn, oc))
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
            sbk = None
            if disc_sb:  # piață generală găsită de Robot (cheie canonică, echipele → {H}/{A})
                t = sb_teams.setdefault(r["match_id"], MS.teams(prices.get(r["match_id"], {})))
                k = MS.key_of(MS.canon(mn, t), MS.canon(oc, t))
                sbk = k if k in disc_sb else None
            if sbk:
                market, sel, (a, b), roi = "sb", sbk, disc_sb[sbk], 0.0
            else:
                text = mn if mn.strip().lower() == oc.strip().lower() else f"{mn} {oc}"
                if not re.fullmatch(r"peste 0\.5 goluri; peste 7\.5 cornere", re.sub(r"\s+", " ", text.lower().replace(",", ".").strip())):
                    continue
                if COMBO in off:
                    continue
                market, sel, a, b, roi = "bb", f"{mn}|{oc}", 1.40, 1.60, REC_COMBO_ROI
        if not a <= price <= b:
            continue
        key = (mn, oc) if spec and grade == "B" else None
        if key:
            q = cal["q"][(key, seg)]
            p = min(0.97, q / price)
        elif grade == LEAGUE_GRADE:  # tipar pe ligă (7 sezoane): jumătate din plusul istoric, cu efectul segmentului
            q = min(CAL_Q_MAX, (1 + roi / 2) * g)
            p = min(0.97, q / price)
        else:
            q = min(CAL_Q_MAX, CAL_Q0 * g)
            p = min(0.97, q / price)
        if pf is not None:
            p = min(0.97, (p + pf) / 2)  # 1X2 cu Pinnacle: jumătate calibrarea, jumătate prețul corect al meciului
        out.append(mk(r, market, sel, price, p, grade, line=float(spec[5]) if spec and len(spec) > 5 and grade == "B" else 0.0,
                      key=key or ((mn, oc) if mn == "Final" else None), seg=seg, q=q, why="liga" if grade == LEAGUE_GRADE else "tipar"))
    return out


SHORT_FROM_HOUR_RO = 10  # biletele de ~10: doar meciuri de la ora 10 (ora României) până la miezul nopții
TICKETS_RESET_AT = "2026-11-19T06:45:00Z"  # nou început (cerut): biletele Robotului de dinainte nu mai apar și nu intră în statistică
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
        # nou început: biletele de dinainte de reset ies din joc (rămân în bază, nu mai apar și nu se numără)
        if start >= TICKETS_RESET_AT:
            conn.execute("UPDATE ticket SET status='replaced' WHERE kind=? AND status='pending' AND created_at<?", (KIND, TICKETS_RESET_AT))
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
        try:  # o dată pe zi: caută piețe noi (probă → activă), vezi discovery.py
            from betpredict.builder.discovery import update_daily

            ch = update_daily(conn, now)
            if ch and any(ch.values()):
                print(f"piețe noi: {ch}")
        except Exception as exc:  # noqa: BLE001 — scanarea nu oprește biletele
            print(f"piețe noi: {exc}")
        pool = load_recommended(conn, now)
    if pool is None:
        from betpredict.builder.pool import load_pool

        pool = load_pool(conn, today, now) + load_pool(conn, today + timedelta(days=1), now)
    # biletele de ~10: doar meciurile zilei (ora României), ca să se încheie azi (piramidă cu reinvestire în 2 pași)
    from betpredict.timeutil import ro_day_bounds_utc

    day_start, day_end = ro_day_bounds_utc(today)
    # fără meciurile de noapte (00–10 ora României): biletul zilei se joacă ziua, nu se pierde cât dormi
    from_utc = canon_utc((datetime.fromisoformat(day_start.replace("Z", "+00:00")) + timedelta(hours=SHORT_FROM_HOUR_RO)).isoformat())
    cands_by = {"short": candidates([c for c in pool if getattr(c, "grade", None) != LEAGUE_GRADE and (c.kickoff_utc or "") >= from_utc
                                     and c.odds <= SHORT_MAX_ODDS and c.market != "bb" and c.selection not in SHORT_EXCLUDE],
                                    now, until_utc=day_end, per_match=False),
                "long": candidates([c for c in pool if LONG_MIN_ODDS <= c.odds <= LONG_MAX_ODDS and c.market != "bb" and day_hours_ok(c)],
                                   now, LONG_HORIZON_H)}  # fără cornere pe cele lungi: −3…−7% pe selecție
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
            # întâi cât mai variat (ligi diferite, ore diferite), apoi, în zilele cu puține meciuri, cu limite mai largi;
            # din câteva porniri diferite în listă, biletul cu cea mai mare șansă onestă care trece pragul de EV (nu primul găsit)
            for lcap, scap in (DIVERSITY_SHORT if fam == "short" else DIVERSITY_LONG):
                best_p = -1.0
                for k in range(6):
                    st = (k * max(1, len(cands) // 6) + i) % max(1, len(cands))
                    cand_legs = build_one(cands, target, rng, st, used, made_sets, SPAN if fam == "short" else LONG_SPAN,
                                          lcap, INTL_CAP[fam], SHORT_SEL_CAP if fam == "short" else None, scap)
                    if not cand_legs:
                        continue
                    total = math.prod(c.odds for c in cand_legs)
                    p_t = math.prod(min(0.99, c.p_honest) for c in cand_legs)
                    if p_t * (total + (total - 1) * superbonus(cand_legs)) - 1 >= MIN_TICKET_EV and p_t > best_p:
                        legs, best_p = cand_legs, p_t
                if legs:
                    break
            if not legs:
                continue
            for c in legs:
                used[c.match_id] = used.get(c.match_id, 0) + 1
            made_sets.append({c.match_id for c in legs})
            made.append({"variant": variant, **_insert(conn, variant, target, legs, today, created)})
    short_now = len(short_today) + sum(1 for m in made if m["variant"] in SHORT)
    try:
        repo.set_state(conn, f"super.short.{today.isoformat()}", json.dumps(
            {"made": short_now, "matches": len({c.match_id for c in cands_by["short"]}), "at": start}))
    except sqlite3.Error:
        pass
    return {"pool": len(cands_by["long"]), "tickets": len(made), "made": made,
            "short_today": len(short_today) + sum(1 for m in made if m["variant"] in SHORT),
            "long_active": len(long_active) + sum(1 for m in made if m["variant"] not in SHORT)}


def superbonus(legs: Sequence) -> float:
    from betpredict.builder.calea100 import superbonus as sb

    return round(sb(sum(1 for c in legs if c.odds >= 1.35)), 4)


SEG_RO = {"club_day": "cluburi, ziua", "club_night": "cluburi, noaptea", "intl_day": "internaționale, ziua",
          "intl_night": "internaționale, noaptea"}


def _pct(x: float) -> str:
    return f"{x * 100:.1f}".replace(".", ",") + "%"


def leg_reasons(c) -> List[str]:
    """De ce e selecția pe bilet, în română: șansa onestă față de cotă, marja Superbet la meci față de media pieței și
    cât a intrat piața la cotele de închidere, pe segmentul meciului."""
    ex = getattr(c, "extra", None) or {}
    p = min(0.99, c.p_honest)
    out = [f"Cota {c.odds:.2f}: șansă estimată {p:.0%} (cota cu marjă spune {1 / c.odds:.0%}); "
           + ("aproape de prețul corect." if c.ev_honest >= -0.01 else f"marja casei rămâne ~{-c.ev_honest:.0%} pe selecție.")]
    bits = []
    o, t = ex.get("ovr"), ex.get("ovr_typ")
    if o and t:
        gap = (o - t) / t
        bits.append(f"marja Superbet aici {_pct(o - 1)} (media pieței {_pct(t - 1)}"
                    + ("; mai ieftină decât de obicei)" if gap < -0.005 else "; mai scumpă decât de obicei)" if gap > 0.005 else ")"))
    if ex.get("why") == "pinnacle":
        bits.append("Superbet plătește cel puțin prețul corect Pinnacle")
    elif getattr(c, "grade", None) == LEAGUE_GRADE:
        why = next((v[5] for (lg, oc), v in LEAGUE_REC.items() if lg == c.league_id and OUT_1X2.get(oc) == c.selection), "")
        if why:
            bits.append(why)
    n = ex.get("cal_n")
    if n and n[0]:
        bits.append(f"ultimele {ex.get('cal_days', CAL_DAYS)} de zile ({SEG_RO.get(ex.get('seg'), '')}): {n[1]} din {n[0]} intrate la închidere")
    elif ex.get("seg"):
        bits.append(f"încă puține rezultate pe {SEG_RO.get(ex.get('seg'), 'segment')}: șansa stă aproape de cotă")
    if bits:
        out.append(bits[0][:1].upper() + "; ".join(bits)[1:] + ".")
    return out


def _insert(conn: sqlite3.Connection, variant: str, target: float, legs: Sequence, day: date, created: str) -> Dict[str, Any]:
    total = math.prod(c.odds for c in legs)
    p = math.prod(min(0.99, c.p_honest) for c in legs)
    over = sum(1 for c in legs if c.ev_honest > 0)
    bonus = superbonus(legs)
    ev = p * (total + (total - 1) * bonus) - 1
    stil = sum(1 for c in legs if c.market == "ss" and c.selection in STIL_ROI and c.selection not in {v[1] for v in REC.values()})
    leagues = len({c.league_id if c.league_id is not None else f"m{c.match_id}" for c in legs})
    cheap = sum(1 for c in legs if ovr_gap(c) < -0.005)
    notes = {"label": f"Robot {int(target):,}+".replace(",", "."), "super": True, "paper": True, "risk_acknowledged": True,
             "rules": RULES_V, "superbonus": bonus, "payout_bonus": round(total + (total - 1) * bonus, 2),
             "leg_p": {f"{c.match_id}|{c.selection}": round(min(0.99, c.p_honest), 4) for c in legs},
             "leg_reasons": [{"m": c.match_id, "s": c.selection, "r": leg_reasons(c)} for c in legs],
             "reasons": [f"{len(legs)} selecții din piețele recomandate, din {leagues} ligi, " + ("din meciurile de azi (10–24)" if target < 100 else f"din meciurile următoarelor {LONG_HORIZON_H // 24} zile")
                         + (f"; {stil} din piețele Stil care au ieșit pe plus." if stil else ".")
                         + (f" La {cheap} dintre ele marja Superbet pe meci e sub media pieței." if cheap else ""),
                         "Șansa fiecărei selecții vine din cât au intrat de fapt piețele la cotele de închidere Superbet "
                         f"(ultimele {CAL_DAYS} de zile, cluburi/internaționale, zi/noapte), micșorată spre cotă când sunt puține rezultate.",
                         f"{over} din {len(legs)} selecții sunt estimate peste prețul corect. SuperBonus Superbet: +{bonus:.0%} din profit "
                         f"(câștig la 1 leu: {total + (total - 1) * bonus:,.0f} în loc de {total:,.0f}).".replace(",", "."),
                         f"Șansa onestă a biletului: ~1 la {max(1, round(1 / p)):,}".replace(",", ".") + f" · cotă {total:,.0f}".replace(",", ".")
                         + f" · valoare așteptată cu bonus {ev:+.0%}. Miză mică (~2 lei); se urmărește câte bilete ies din multe."]}
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
    """Urmărirea biletelor Robotului de la noul început: pe țintă și total — jucate, câștigate, în joc, ROI la miză egală
    (plata cu SuperBonus), cel mai bun câștig, selecții intrate și ultimele rezultate."""
    now = now or datetime.now(timezone.utc)
    since = TICKETS_RESET_AT if canon_utc(now.isoformat()) >= TICKETS_RESET_AT else ""
    rows = conn.execute("SELECT id, variant, status, total_odds, p_ticket, notes, day FROM ticket WHERE kind=? AND status!='replaced' "
                        "AND created_at>=? ORDER BY created_at", (KIND, since)).fetchall()

    def pay(r) -> float:
        return float(json.loads(r[5] or "{}").get("payout_bonus") or r[3] or 0)

    def agg(rs) -> Dict[str, Any]:
        done = [r for r in rs if r[2] in ("won", "lost")]
        won = [r for r in done if r[2] == "won"]
        return {"n": len(done), "won": len(won), "lost": len(done) - len(won), "pending": sum(1 for r in rs if r[2] == "pending"),
                "expected": round(sum(r[4] or 0 for r in done), 2),
                "roi": round(sum(pay(r) for r in won) / len(done) - 1, 4) if done else None,
                "best": max((pay(r) for r in won), default=None)}

    tiers = [{"variant": v, "target": t, **agg([r for r in rows if r[1] == v])} for v, t, *_ in TIERS]
    short = [r for r in rows if r[1] in SHORT]
    long_ = [r for r in rows if r[1] not in SHORT]
    legs = conn.execute("""SELECT SUM(l.result='won'), SUM(l.result IN ('won','lost')) FROM ticket_leg l JOIN ticket t ON t.id=l.ticket_id
                           WHERE t.kind=? AND t.status!='replaced' AND t.created_at>=?""", (KIND, since)).fetchone()
    last = [{"variant": r[1], "status": r[2], "odds": round(r[3] or 0, 2), "day": r[6]} for r in rows if r[2] in ("won", "lost")][-12:]
    from betpredict.timeutil import ro_today

    try:
        today_short = json.loads(repo.get_state(conn, f"super.short.{ro_today(now).isoformat()}") or "null")
    except (sqlite3.Error, ValueError):
        today_short = None
    return {"generated_at": canon_utc(now.isoformat()), "since": since or None, "tiers": tiers, "today_short": today_short,
            "short": agg(short), "long": agg(long_), "all": agg(rows),
            "leg_hit": round(legs[0] / legs[1], 4) if legs and legs[1] else None, "legs": (legs[1] or 0) if legs else 0, "last": last}


SEL_LABEL = {"H2G12": "Repriza 2: 1–2 goluri", "OVER": "Peste 1.5 goluri", "H2G13": "Repriza 2: 1–3 goluri", "H1U15": "Repriza 1: sub 1.5 goluri", "YES": "Ambele marchează (GG)",
             "HOME": "1 · câștigă gazda", "AWAY": "2 · câștigă oaspeții", "DRAW": "X · egal"}
SEL_WHY = {"H2G12": "Repriza 2: 1–2 goluri la 1.45–1.65: Superbet +6.6% (119 selecții), pe plus în ambele părți ale perioadei.",
           "OVER": "Peste 1.5 goluri la 1.30–1.50: +5% în istoricul Robotului (127 selecții, 78% intrate).",
           "H2G13": "Superbet: +5% în octombrie (459 selecții), R2 peste 0.5 +3% în istoricul Robotului.",
           "H1U15": "Superbet, cote 1.45–1.65: +2.6% (182 selecții). De urmărit: puține zile.",
           "YES": "GG: la 1.85–2.10 arhivă +20% / +2% și Superbet +1.6% (185); la 1.50–1.80 Robot +2.5% (125).",
           "HOME": "Gazdă favorită 1.35–1.45: aproape de prețul corect în arhivă (+0.1% / +0.5% pe 48.800 de meciuri).",
           "AWAY": "Oaspete favorit 1.35–1.60: arhivă +1.9% (2020–24) și +2.5% (2024–26).",
           "COMBO": "Peste 0.5 goluri + peste 7.5 cornere la 1.40–1.60: arhivă +6.7% (354), cam la prețul corect acum."}


def _ss_label(key: str) -> str:
    if key.startswith("SB:"):
        from betpredict.builder.market_settle import label as sb_label

        return sb_label(key)
    try:
        from betpredict.experimental.supersocial import label

        return label(key)
    except Exception:  # noqa: BLE001
        return key


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
            if c.selection in DISC_KEYS:
                why, kind = "Piață găsită de Robot: pe plus în ultimele 60 de zile și confirmată în probă pe meciuri noi.", "nou"
            st = live.get(COMBO if combo else key_of.get(c.selection))
            if st and st["n"] >= 30:
                why += f" Ultimele {st['days']} de zile pe Superbet: {st['roi']:+.0%} pe {st['n']} selecții."
        rows.append({"match_id": c.match_id, "kickoff_utc": c.kickoff_utc, "day": ro_day(c.kickoff_utc).isoformat() if ro_day(c.kickoff_utc) else None,
                     "home": c.home, "away": c.away, "league": c.league,
                     "label": "Peste 0.5 goluri + peste 7.5 cornere" if combo else SEL_LABEL.get(c.selection) or _ss_label(c.selection),
                     "odds": round(c.odds, 2), "p": round(c.p_honest, 4), "bonus_ok": c.odds >= LONG_MIN_ODDS, "kind": kind, "why": why,
                     # piața internă, ca generatorul manual să facă bilete care se decontează (ss / 1x2 / over_under / btts)
                     "market": c.market, "sel": c.selection, "line": c.line or None,
                     "intl": is_intl(c), "night": not day_hours_ok(c)})
    rows.sort(key=lambda r: (r["kickoff_utc"], -r["p"]))
    markets = [{"label": "Peste 0.5 goluri + peste 7.5 cornere" if k == COMBO else SEL_LABEL.get(REC[k][1], k[1]), **v}
               for k, v in live.items()]
    try:
        from betpredict.builder.discovery import doc as disc_doc

        discovered = disc_doc(conn)
    except Exception:  # noqa: BLE001
        discovered = []
    return {"generated_at": canon_utc(now.isoformat()), "count": len(rows), "rows": rows, "markets": markets, "discovery": discovered,
            "note": "Selecțiile din care Robotul face biletele: piețe care au ieșit aproape de prețul corect sau peste, în istoric. "
                    "Nu sunt sigure una câte una; pe biletele lungi, SuperBonusul (de la 1.35) face diferența."}
