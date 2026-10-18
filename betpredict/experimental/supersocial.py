"""„Stil Supersocial”: slipuri de tipster (Superbet), prețuri reale Superbet.

Piețe din biletele lui publice: cornere Peste 6.5/7.5 (~1.24–1.30), prima repriză Peste 2.5/3.5
(~1.39–1.42), interval 1–3 în fiecare repriză (~1.78–1.80), Peste 0.5 în ambele reprize (~1.48–1.50),
Bet Builder cornere 6.5 & sub 14.5 (~1.35), R1 cornere 2.5 & sub 6.5 (~1.55), 1–3 în fiecare repriză & peste 1.5 (~1.80).

Probabilitate goluri: λ robot → Poisson pe reprize. Cota de goluri din prima repriză e măsurată pe meciurile
terminate din baza noastră (pe ligă, dacă sunt ≥80; altfel pe tot istoricul), micșorată spre 0.446.
Cornere: NegBin calibrat (experimental/corners.py). Fără istoric de ligă: mediana din cotele BSD, altfel media globală 9.8.
Decontare din BSD /events/{id}/stats/ și HC/AC din football-data.
Superbet nu publică intervalul 3–6 la cornere pe prima repriză. Piața reală este
„Prima repriză - Interval cornere” cu <5, 5-6 și 7+. Cota 3–6 se estimează din Peste 2.5 și Sub 6.5.
Bilete paper, miză 0.05u, selecții din următoarele 7 zile, cota finală 80–200.
Se oprește la prima combinație validă (șansă maximă de verde). Peste 200 se taie; sub 80 nu se publică.
Un meci pe cel mult 2 bilete, cel mult 4 din aceeași ligă.
"""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from betpredict.lab.patterns import _probs, _won
from betpredict.timeutil import canon_utc

KIND, VARIANT = "acca_stil", "stil_supersocial"
STAKE_U = 0.05
# Biletul vizibil: cotă mare, miză mică. Sub 20 nu se publică (ăla de 4–5 nu e stilul).
SUPERS_ODDS = (20.0, 200.0)
SUPERS_EDGE = -0.03
H1_SHARE = 0.446  # prior; h1_shares() îl înlocuiește cu frecvența măsurată
H1_PRIOR_N = 200.0
MIN_LEGS, MAX_LEGS = 10, 22
# Oferta din care alege: 7 zile. Cota finală 80–200. Se oprește la prima combinație validă,
# pentru că fiecare selecție în plus scade șansa ca biletul să iasă verde.
HORIZON_H = 24 * 7
ODDS_LO, ODDS_HI = 80.0, 200.0
ODDS_HI_HARD = ODDS_HI * 1.04
BAND = (1.20, 2.20)
MIN_EDGE = 0.0
MAX_TICKETS_PER_MATCH = 2
MAX_PER_LEAGUE = 4
MAX_PER_KEY = 5  # biletele cu mai mult de 2 piețe: cel mult 5 selecții din aceeași piață
# λ goluri: piața (consens multi-casă + Pinnacle, fără marjă) amestecată cu robotul. Corecțiile BIAS au fost măsurate în
# laborator tocmai pe λ din cote, deci piața are ponderea mare; robotul aduce forma recentă. Fără cote: doar robotul.
MKT_W = 0.7
# Ordinea în bilet: șansa modelului (cu corecția învățată) și șansa din cota Superbet (fără marjă, cu aceeași corecție),
# amestecate în spațiul logit. Unde modelul și casa nu se înțeleg, selecția coboară în listă.
RANK_W = 0.5
# ponderea modelului pe familii, din rezultatele reale (1.648 selecții urmărite, 14–15.10.2026): la cornere și goluri
# modelul a prezis mai prost decât cota Superbet (log-loss 0,582 vs 0,563 la cornere, 0,609 vs 0,604 la goluri), iar
# selecțiile unde doar modelul vedea „valoare” peste 5% au pierdut (−42% cornere, −20% goluri). Decide piața + rezultatele.
RANK_W_FAMILY = {"cornere": 0.15, "goluri": 0.25, "rezultat": 0.25, "cartonase": 0.5}
# Avantaj prea mare față de cota Superbet la goluri/cartonașe = aproape sigur o eroare (date lipsă, λ greșit), nu un cadou.
EDGE_SUSPECT = 0.25  # EV > 25%: „EV suspect” (model greșit sau piață confundată), nu intră pe bilete
# „Alegerea robotului”: cele mai sigure selecții din toate piețele, cel mult 3 din aceeași piață (o piață prețuită greșit
# de model nu poate strica tot biletul) și un mic avantaj minim.
# Audit 17.10.2026: biletele Stil de 10–22 selecții au ieșit 0 din 37. De acum: 3–6 selecții, doar din piețele cu
# ROI pozitiv pe rezultatele reale (lista se recalculează la fiecare rulare din ss_track; fără destule date: STIL_DEFAULT_KEYS).
STIL_COMPACT = True  # False = regula veche (10–22 selecții, cotă 80–200); rămâne doar pentru teste/comparație
STIL_LEGS = (3, 6)
STIL_ODDS = (20.0, 40.0)  # regula lui Alin (16.10): bilete de la cota 20; cu 3–6 selecții asta înseamnă cote de ~1.6–2.0
STIL_DEFAULT_KEYS = ("H2G13", "H13x2", "G25", "GG")
STIL_BANNED = frozenset({"H1C56", "AY25", "HY25", "DCX2_O15"})
STIL_POS_MIN_N = 40
# Trepte de cotă mare (cerute 17.10): aceleași piețe cu ROI pozitiv, control de suprapunere, sistem N−1 de la 12 selecții.
# Bilete-loterie: miză mică, informative; frecvența estimată e în raportul de build.
STIL_TIERS = (("Stil 100+", (100.0, 200.0), 8, 14), ("Stil 500+", (500.0, 900.0), 11, 18), ("Stil 1000+", (1000.0, 2000.0), 12, 20))
# Cartonașe: modelul promitea ~95% unde istoric intră ~80%. Șansa se trage spre frecvența reală pe piață (bayesian).
CARD_CAL_K = 30.0
CARD_CAL_MIN_N = 20
CHAIN_NAME = "Lanț pe ore"
CHAIN_STEPS = (3, 4)          # trepte (bilete mici succesive)
CHAIN_STEP_ODDS = (3.2, 6.0)  # cota pe treaptă; 4 × ~3.2 ≈ 100+
CHAIN_GAP_MIN = 120           # o treaptă începe după ce s-au jucat (start + 2 h) meciurile treptei anterioare
CHAIN_MIN_TOTAL = 100.0
# backtest 17.10 (ss_track, 4 zile): piețele pe plus dau 76% selecții câștigate vs 71% pe toată oferta,
# dar formează treapta doar 1–2 zile din 4; oferta completă rămâne rezervă, nu prima alegere
STIL_TIER_GLOBAL = True
# treptele 100+/500+/1000+: întâi toată oferta cotată, doar picioare cu EV ≥ 0 (p × cotă ≥ 1). Backtest pe ss_track
# 15–18.10, zile neprivite: rata pe picior 0.745 față de 0.72 (toate) și 0.58 (doar piețe ROI>0, care supraînvață pe 4 zile)
STIL_TIER_EV_FIRST = True
TIER_NAMES = frozenset([*(n for n, *_ in STIL_TIERS), CHAIN_NAME])
LINEUP_REBUILD_MIN = 75       # cu ≤ 75 min înainte de primul meci, treptele mari se refac pe echipele confirmate
KEY_IMP = 0.6                 # titular de bază: ≥ 60% din minute în ultimele 10 meciuri sau 4 goluri+pase decisive
LINEUP_SIDE_GAP = 2           # o echipă cu ≥ 2 titulari importanți lipsă mai mult decât adversara: piețele ei pe goluri ies
LINEUP_TOTAL_MAX = 4          # ≥ 4 titulari importanți lipsă în total: piețele de goluri pe meci ies
DRIFT_OUT, DRIFT_IN = 0.03, -0.03  # Pinnacle Peste 2.5: cota +3% de la deschidere = piața pleacă (scoatem); −3% = vine (preferăm)
DRIFT_BONUS = 1.02
GOAL_UP_KEYS = frozenset({"GG", "GGO25", "G24", "G25", "H13x2", "R1R2", "R1O15", "R1O25", "H2G13", "H1O05", "H1O15", "BB_H13x2_O15"})

BEST_NAME = "Alegerea robotului"
BEST_SAFE_NAME = "Alegerea robotului · cotă 20–40"  # același amestec, mai puține selecții: șansă de ~5× mai mare
SPEC_ODDS = {BEST_SAFE_NAME: (20.0, 40.0)}
BEST_MIN_EDGE = 0.02
BEST_PER_KEY = 3
BEST_PER_FAMILY = 8  # și cel mult 8 din aceeași familie (cornere / cartonașe / goluri): un model greșit nu ia tot biletul
# (nume piață Superbet, rezultat) → cheie
MARKETS: Dict[Tuple[str, str], str] = {
    ("Interval goluri", "2-4"): "G24", ("Interval goluri", "2-5"): "G25", ("Interval goluri", "1-3"): "G13",
    ("Gol marcat în ambele reprize", "Da"): "R1R2",
    ("Total goluri prima repriză & Total goluri a doua repriză", "Peste 0.5 & Peste 0.5"): "R1R2",
    ("Total goluri prima repriză & Total goluri", "Peste 0.5 & Peste 1.5"): "R1O15",
    ("Total goluri prima repriză & Total goluri", "Peste 0.5 & Peste 2.5"): "R1O25",
    ("Interval goluri în fiecare repriză", "1-3"): "H13x2",
    ("GG sau Peste 2.5 goluri", "Da"): "GGO25", ("Prima repriză - Total goluri", "Peste 0.5"): "H1O05",
    ("Prima repriză - Total goluri", "Peste 1.5"): "H1O15",
    ("A doua repriză - Interval goluri", "1-3"): "H2G13",
    # numele exacte, din catalogul ofertei (api/supersocial/markets.json, 15.10.2026)
    ("Ambele echipe marchează (GG)", "Da"): "GG",
    ("Șansă dublă & Total goluri (1.5)", "X2 & Peste 1.5"): "DCX2_O15",
    ("Total cartonașe", "Peste 3.5"): "YC35", ("Total cartonașe", "Peste 4.5"): "YC45",
    ("Total cartonașe", "Sub 4.5"): "YCU45", ("Total cartonașe", "Sub 5.5"): "YCU55",
    ("Fiecare echipă va primi peste X cartonașe", "Peste 1.5 - Da"): "BOTH15",
    ("Total cornere", "Peste 6.5"): "C65", ("Total cornere", "Peste 7.5"): "C75",
    ("Total cornere", "Peste 8.5"): "C85", ("Total cornere", "Peste 9.5"): "C95",
    ("Prima repriză - Interval cornere", "3-6"): "BB_H1C25_U65", ("Prima repriză - Interval cornere", "3 - 6"): "BB_H1C25_U65",
    ("Interval cornere prima repriză", "3-6"): "BB_H1C25_U65",
    ("Prima repriză - Interval cornere", "<5"): "H1CLT5", ("Prima repriză - Interval cornere", "5-6"): "H1C56",
    ("Prima repriză - Interval cornere", "7+"): "H1C7P",
    ("Prima repriză - Total cornere", "Peste 2.5"): "H1C25", ("Prima repriză - Total cornere", "Peste 3.5"): "H1C35",
    ("Prima repriză - Total cornere", "Sub 6.5"): "H1U65",
    ("Total cornere", "Sub 14.5"): "CU145",
    # doar ca să știm că se pot pune pe Superbet (picioarele Bet Builder-elor pe echipă), nu sunt piețe de bilet
    ("Prima repriză - Total goluri", "Sub 3.5"): "H1U35", ("Prima repriză - Total goluri", "Sub 4.5"): "H1U45",
    ("Total goluri", "Peste 1.5"): "O15",
}
# picioarele fiecărui Bet Builder: toate trebuie să fie în oferta Superbet, altfel combinația nu se poate pune
BB_LEGS = {"BB_C65_U145": ("C65", "CU145"), "BB_H1C25_U65": ("H1C25", "H1U65"), "BB_H13x2_O15": ("H13x2", "O15")}
LABELS = {"G24": "Interval goluri 2-4", "G25": "Interval goluri 2-5", "G13": "Interval goluri 1-3",
          "R1R2": "Gol în fiecare repriză (R1 Peste 0.5 & R2 Peste 0.5)", "R1O15": "Combo R1 Peste 0.5 & meci Peste 1.5",
          "R1O25": "Combo R1 Peste 0.5 & meci Peste 2.5",
          "GGO25": "GG sau Peste 2.5 goluri", "H1O05": "Prima repriză Peste 0.5 goluri", "GG": "Ambele echipe marchează (GG)", "YC35": "Cartonașe Peste 3.5", "YC45": "Cartonașe Peste 4.5",
          "YCU45": "Cartonașe Sub 4.5", "YCU55": "Cartonașe Sub 5.5", "BOTH15": "Fiecare echipă peste 1.5 cartonașe",
          "HY15": "Cartonașe gazde Peste 1.5", "AY15": "Cartonașe oaspeți Peste 1.5", "HY25": "Cartonașe gazde Peste 2.5",
          "AY25": "Cartonașe oaspeți Peste 2.5", "HO05": "Gazdele marchează (Peste 0.5)", "HO15": "Gazdele Peste 1.5 goluri",
          "AO05": "Oaspeții marchează (Peste 0.5)", "AO15": "Oaspeții Peste 1.5 goluri", "DCX2_O15": "Șansă dublă X2 & Peste 1.5",
          "H1O15": "Prima repriză Peste 1.5 goluri",
          "O15": "Total goluri Peste 1.5", "O25": "Total goluri Peste 2.5", "OTHER": "Altă piață","H2G13": "A doua repriză 1-3 goluri",
          "SHOTS": "Total șuturi (fără date la noi)",
          "H13x2": "Interval 1-3 goluri în fiecare repriză",
          "C65": "Cornere Peste 6.5", "C75": "Cornere Peste 7.5", "C85": "Cornere Peste 8.5", "C95": "Cornere Peste 9.5",
          "H1C25": "R1 Cornere Peste 2.5", "H1C35": "R1 Cornere Peste 3.5",
          "H1CLT5": "R1 Cornere sub 5", "H1C56": "R1 Cornere 5-6", "H1C7P": "R1 Cornere 7+",
          "BB_C65_U145": "BB Cornere Peste 6.5 & Sub 14.5", "BB_H1C25_U65": "R1 Cornere interval 3-6",
          "BB_H13x2_O15": "BB 1-3 goluri în fiecare repriză & Peste 1.5",
          "CU145": "Cornere Sub 14.5", "H1U65": "R1 Cornere Sub 6.5",
          "HG13": "Gazdele: interval 1-3 goluri", "AG13": "Oaspeții: interval 1-3 goluri",
          "BB_HG13_U35": "BB Gazdele 1-3 goluri & R1 Sub 3.5", "BB_AG13_U35": "BB Oaspeții 1-3 goluri & R1 Sub 3.5",
          "BB_HG14_U45": "BB Gazdele 1-4 goluri & R1 Sub 4.5", "BB_AG14_U45": "BB Oaspeții 1-4 goluri & R1 Sub 4.5"}
# grupe pentru filtrul Predicții (tip piață → sub-chipuri pe piață)
GROUP = {"H13x2": "reprize", "R1R2": "reprize", "BB_H13x2_O15": "reprize", "R1O15": "combo", "R1O25": "combo", "GGO25": "combo", "H1O05": "reprize", "GG": "combo", "DCX2_O15": "combo", "YC35": "cartonase", "YC45": "cartonase", "YCU45": "cartonase",
         "YCU55": "cartonase", "BOTH15": "cartonase", "HY15": "cartonase", "AY15": "cartonase", "HY25": "cartonase", "AY25": "cartonase",
         "HO05": "echipe", "HO15": "echipe", "AO05": "echipe", "AO15": "echipe", "H1O15": "reprize", "H2G13": "reprize",
         "G13": "interval", "G24": "interval", "G25": "interval", "C65": "cornere", "C75": "cornere", "C85": "cornere",
         "C95": "cornere", "BB_C65_U145": "cornere", "H1C25": "r1_cornere", "H1C35": "r1_cornere",
         "H1CLT5": "r1_cornere", "H1C56": "r1_cornere", "H1C7P": "r1_cornere", "BB_H1C25_U65": "r1_cornere",
         "CU145": "cornere", "H1U65": "r1_cornere", "HG13": "echipe", "AG13": "echipe", "BB_HG13_U35": "echipe",
         "BB_AG13_U35": "echipe", "BB_HG14_U45": "echipe", "BB_AG14_U45": "echipe"}
# Poarta cartonașelor pe bilete (analiză 18.10 pe ss_track, 1 081 selecții decontate 15–18.10):
#  - cartonașe pe o echipă (HY*/AY*) ROI −4% … −21%, iar pe biletele decontate au intrat 9/26 → nu mai intră pe bilete;
#  - pe total, doar când modelul vede clar mai mult decât piața (p − 1/(cotă×1.07) ≥ 0.10): acolo 70.5% câștigate, ROI +18% (n 173);
#    sub prag ROI −3% … −30%. Selecțiile se urmăresc în continuare toate (ss_track), poarta e doar pe bilete.
CARD_TICKET_GATE = True
CARD_TEAM_KEYS = ("HY15", "AY15", "HY25", "AY25")
CARD_MIN_GAP = 0.10


def card_gate(cands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not CARD_TICKET_GATE:
        return cands
    out = []
    for c in cands:
        if c.get("key") in CARD_KEYS:
            o = c.get("odds") or 0
            if c["key"] in CARD_TEAM_KEYS or o <= 1 or (c.get("p") or 0) - 1 / (o * 1.07) < CARD_MIN_GAP:
                continue
        out.append(c)
    return out


# ---- sănătatea piețelor: zilnic, pe ultimele 14 zile decontate (ss_track), per piață+linie ----
MH_DAYS = 14
MH_MIN_N = 40
MH_PAUSE_ROI = -0.06      # ROI micșorat spre −5% (40 de pseudo-pariuri), ca la positive_keys
MH_PAUSE_GAP = 0.03       # și modelul promite cu ≥ 3 pp mai mult decât intră
MH_REOPEN_ROI = -0.02     # redeschidere: ROI micșorat ≥ −2% sau modelul nu mai supraestimează
MH_SCHEMA = """CREATE TABLE IF NOT EXISTS market_state (mkey TEXT PRIMARY KEY, status TEXT, since TEXT, n INTEGER,
               hit REAL, p REAL, roi REAL, updated_at TEXT)"""


def market_health(conn: sqlite3.Connection, now: Optional[datetime] = None, write: bool = True) -> Dict[str, Dict[str, Any]]:
    """Pauză automată pe piețele unde modelul supraestimează și pierde; redeschidere când își revin (cu histerezis)."""
    now = now or datetime.now(timezone.utc)
    _ensure_track(conn)
    conn.execute(MH_SCHEMA)
    lo = (now - timedelta(days=MH_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    prev = {r[0]: (r[1], r[2]) for r in conn.execute("SELECT mkey, status, since FROM market_state")}
    out: Dict[str, Dict[str, Any]] = {}
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    for k, n, w, mp, pl in conn.execute("""SELECT mkey, COUNT(*), SUM(result='won'), AVG(p),
                                           SUM(CASE WHEN result='won' THEN odds-1 ELSE -1 END)
                                           FROM ss_track WHERE result IN ('won','lost') AND kickoff_utc >= ? AND odds > 1
                                           GROUP BY mkey""", (lo,)):
        hit = w / n
        roi = (pl + 40 * -0.05) / (n + 40)
        was, since = prev.get(k, ("active", stamp))
        if n < MH_MIN_N:
            st = was
        elif was == "paused":
            st = "active" if (roi >= MH_REOPEN_ROI or hit >= mp) else "paused"
        else:
            st = "paused" if (roi < MH_PAUSE_ROI and hit < mp - MH_PAUSE_GAP) else "active"
        if st != was:
            since = stamp
        out[k] = {"status": st, "since": since, "n": n, "hit": round(hit, 4), "p": round(mp, 4), "roi": round(roi, 4)}
    if write:
        with conn:
            for k, v in out.items():
                conn.execute("""INSERT INTO market_state VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(mkey) DO UPDATE SET
                                status=excluded.status, since=excluded.since, n=excluded.n, hit=excluded.hit, p=excluded.p,
                                roi=excluded.roi, updated_at=excluded.updated_at""",
                             (k, v["status"], v["since"], v["n"], v["hit"], v["p"], v["roi"], stamp))
    return out


def health_doc(conn: sqlite3.Connection) -> Dict[str, Any]:
    conn.execute(MH_SCHEMA)
    rows = [dict(zip(("key", "status", "since", "n", "hit", "p", "roi"), r)) for r in conn.execute(
        "SELECT mkey, status, since, n, hit, p, roi FROM market_state ORDER BY status DESC, roi")]
    for r in rows:
        r["label"] = LABELS.get(r["key"], r["key"])
    return {"days": MH_DAYS, "min_n": MH_MIN_N, "rule": f"pauză: ROI < {MH_PAUSE_ROI:+.0%} și modelul promite cu ≥ {MH_PAUSE_GAP*100:.0f} pp peste ce intră; "
            f"redeschidere: ROI ≥ {MH_REOPEN_ROI:+.0%} sau rata reală ≥ promisiunea", "markets": rows}


CARD_PER_TICKET = 2  # cel mult 2 picioare de cartonașe pe bilet (ex. Sub 4.5 / Sub 5.5): nu concentrăm biletul pe o piață

CARD_KEYS = ("YC35", "YC45", "YCU45", "YCU55", "BOTH15", "HY15", "AY15", "HY25", "AY25")
CORNER_KEYS = ("C65", "C75", "C85", "C95", "H1C25", "H1C35")
BB_KEYS = ("BB_C65_U145", "BB_H1C25_U65", "BB_H13x2_O15", "BB_HG13_U35", "BB_AG13_U35", "BB_HG14_U45", "BB_AG14_U45")
BB_ANCHOR = {"BB_C65_U145": "C65", "BB_H1C25_U65": "H1C25", "BB_H13x2_O15": "H13x2", "BB_HG13_U35": "HG13", "BB_AG13_U35": "AG13",
             "BB_HG14_U45": "HO05", "BB_AG14_U45": "AO05"}
# Interval 1-3 goluri pe echipă (Superbet: „Interval goluri <echipă>”), singur sau în BB cu prima repriză Sub 3.5.
# Pe football-data (47.980 meciuri, echipa favorită după cote): Poisson dă 70,1%, real 72,2% (1-3) și 68,4% vs 70,8%
# (1-3 & R1 Sub 3.5), în fiecare treaptă de λ și în ambele perioade → corecția de mai jos, din perioada mai slabă
# (antrenare, până în 07.2024): +1,5 puncte, +2 la favoritele mari (λ ≥ 2.1), +0,3 în plus cu R1 Sub 3.5.
# R1 Sub 3.5 costă ~1,5 puncte de șansă și aduce ~1.03 la cotă.
TEAM13_BIAS, TEAM13_BIAS_BIG, TEAM13_BIAS_BB = 0.015, 0.02, 0.003
# 1-4 & R1 Sub 4.5 (BB: echipa Peste 0.5 + echipa Sub 4.5 + R1 Sub 4.5; 1-4 pe echipă nu e în ofertă): Poisson 75,6%,
# real 77,5%; în antrenare +1,1 / +1,2 puncte sub λ 1.7 și +2,1 / +2,5 peste. Prețul pleacă de la „echipa Peste 0.5”.
TEAM14_BIAS, TEAM14_BIAS_BIG = 0.012, 0.02
TEAM14_NAME = "BB echipă 1–4 & R1 sub 4.5"
# Rețete verificate pe istoric (7 sezoane, câte un bilet pe zi): se publică zilnic, chiar dacă piața de azi nu arată
# avantaj, cu pragul de mai jos pe selecție și fără poarta de EV (corecția învățată pornește de la marja casei, deci ar
# tăia biletul mereu). 1–4 & R1 Sub 4.5, 20 de selecții: 11 bilete câștigate din 683, cotă ~110, ROI +47% (norocos:
# ±16 puncte pe bilet); pe selecție −1,6% / +0,1% (antrenare / test).
# trei bilete pe zi, fiecare cu alte selecții (nicio selecție nu se repetă între bilete): rezultate independente
TEAM14_NAMES = (TEAM14_NAME, f"{TEAM14_NAME} · 2", f"{TEAM14_NAME} · 3")
HIST_FLOOR = {n: -0.05 for n in TEAM14_NAMES}
# corecția Poisson-ului (puncte de probabilitate): cât intră în plus pe istoric, din laboratorul de piețe (47.960 meciuri,
# 7 sezoane, 15.10.2026), luată din perioada mai slabă dintre antrenare și test; R1 Peste 0.5/1.5 ies calibrate, deci 0
BIAS = {"R1R2": 0.018, "H13x2": 0.024, "R1O15": 0.012, "R1O25": 0.009, "GGO25": 0.010, "H1O05": 0.0, "H1O15": 0.0,
        "H2G13": 0.020, "GG": 0.014, "DCX2_O15": 0.012, "G24": 0.008, "G25": 0.009, "G13": 0.0}
# (nume, piețe, min, max, ordonare, banda) — slipurile tipsterilor, apoi intervalul 2–4/2–5
TICKETS = (
    (BEST_NAME, ("*",), 4, 16, "p", (1.15, 2.20)),
    (BEST_SAFE_NAME, ("*",), 4, 10, "p", (1.15, 2.20)),
    ("Combo R1 0.5 & meci 1.5", ("R1O15",), 4, 12, "p", (1.15, 1.60)),
    ("Combo R1 0.5 & meci 2.5", ("R1O25",), 4, 12, "p", (1.35, 1.80)),
    ("Goluri 1–3", ("G13",), 4, 12, "edge", BAND),
    ("R1 cornere interval 3-6", ("BB_H1C25_U65",), 4, 12, "p", (1.30, 2.10)),
    ("Cornere 6.5/7.5", ("C65", "C75"), 4, 22, "p", (1.15, 1.45)),
    ("Cornere prima repriză", ("H1C25", "H1C35"), 4, 22, "p", (1.12, 1.60)),
    ("1–3 în fiecare repriză", ("H13x2",), 4, 22, "p", (1.65, 1.95)),
    ("Peste 0.5 ambele reprize", ("R1R2",), 4, 22, "p", (1.40, 1.65)),
    ("BB cornere 6.5 și sub 14.5", ("BB_C65_U145",), 4, 22, "p", (1.20, 1.70)),
    ("BB 1–3 reprize și peste 1.5", ("BB_H13x2_O15",), 4, 22, "p", (1.65, 2.05)),
    ("A doua repriză 1–3 goluri", ("H2G13",), 4, 22, "p", (1.25, 1.45)),
    ("GG sau Peste 2.5", ("GGO25",), 4, 22, "p", (1.25, 1.55)),
    ("Prima repriză Peste 0.5", ("H1O05",), 4, 22, "p", (1.18, 1.50)),
    ("Ambele marchează (GG)", ("GG",), 4, 12, "p", (1.50, 2.10)),
    ("X2 & Peste 1.5", ("DCX2_O15",), 4, 12, "p", (1.45, 2.20)),
    ("Cartonașe Peste 3.5", ("YC35",), 4, 12, "p", (1.35, 1.90)),
    ("Cartonașe pe echipă Peste 1.5", ("HY15", "AY15"), 4, 12, "p", (1.40, 2.10)),
    ("Echipa cu potențial 1–3 goluri", ("HG13", "AG13"), 4, 22, "p", (1.25, 1.60)),
    ("BB echipă 1–3 & R1 sub 3.5", ("BB_HG13_U35", "BB_AG13_U35"), 4, 22, "p", (1.25, 1.65)),
    *((n, ("BB_HG14_U45", "BB_AG14_U45"), 4, 22, "p", (1.18, 1.35)) for n in TEAM14_NAMES),
    ("Goluri 2–4 / 2–5", ("G24", "G25"), 4, 12, "edge", BAND),
    ("Mix Supersocial", ("G24", "G25", "G13", "R1R2", "R1O15", "H13x2", "C65", "C75", "H1C25"), 4, 12, "edge", BAND),
)
CORNER_MIN_EDGE = 0.0
# Piețe „pe val”: suficiente rezultate și un plus clar, nu un ROI de câteva procente.
# Fără istoric decontat rămâne catalogul experimental.
WAVE_MIN_N = 30
WAVE_MIN_ROI = 0.10
# Corecția învățată pe piață: de câte ori intră selecția față de cât promite cota (1/cotă, cu marja inclusă).
# Micșorată bayesian spre LIFT_PRIOR (≈ marja casei): cu puține rezultate rămâne aproape de prior.
LIFT_K = 20.0
LIFT_PRIOR = 0.95
LIFT_MIN_N = 10       # sub atâtea rezultate decontate piața nu e judecată (rămâne ca înainte)
LIFT_DROP = 0.97      # sub acest raport piața iese din biletele Stil (intră constant sub cotă)
LIFT_PER_DAY = 15     # câte rezultate dintr-o zi contează (zilele sunt corelate între ele)

SCHEMA = """CREATE TABLE IF NOT EXISTS ss_price (
  match_id INTEGER NOT NULL, mkey TEXT NOT NULL, day TEXT NOT NULL, price_first REAL NOT NULL, price_last REAL NOT NULL,
  first_at TEXT NOT NULL, last_at TEXT NOT NULL, PRIMARY KEY (match_id, mkey, day))"""


def snapshot(conn: sqlite3.Connection, now: Optional[datetime] = None) -> int:
    """Instantaneu zilnic al prețurilor Superbet pentru piețele de mai sus (primul și ultimul preț al zilei)."""
    conn.execute(SCHEMA)
    day = (now or datetime.now(timezone.utc)).date().isoformat()
    n = 0
    with conn:
        for (mname, out), key in MARKETS.items():
            for r in conn.execute("SELECT match_id, price, observed_at FROM sb_offer WHERE market_name=? AND outcome=?", (mname, out)).fetchall():
                conn.execute(
                    "INSERT INTO ss_price VALUES (?,?,?,?,?,?,?) ON CONFLICT(match_id, mkey, day) DO UPDATE SET "
                    "price_last=excluded.price_last, last_at=excluded.last_at",
                    (r[0], key, day, r[1], r[1], r[2], r[2]))
                n += 1
    return n


TRACK_SCHEMA = """CREATE TABLE IF NOT EXISTS ss_track (
  match_id INTEGER NOT NULL, mkey TEXT NOT NULL, kickoff_utc TEXT NOT NULL, p REAL NOT NULL, odds REAL NOT NULL,
  updated_at TEXT NOT NULL, result TEXT, odds_first REAL, PRIMARY KEY (match_id, mkey))"""


def _ensure_track(conn: sqlite3.Connection) -> None:
    conn.execute(TRACK_SCHEMA)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(ss_track)")}
    if "odds_first" not in cols:  # tabela creată înainte de CLV
        conn.execute("ALTER TABLE ss_track ADD COLUMN odds_first REAL")
    # selecțiile de cartonașe pe echipă urmărite cu prețul cartonașelor roșii (16–18, piață confundată până la 17.10.2026):
    # nu învățăm din ele (Peste 1.5 / 2.5 pe echipă nu trece realist de cota 6)
    conn.execute("DELETE FROM ss_track WHERE mkey IN ('HY15','AY15','HY25','AY25') AND (odds >= 6 OR odds_first >= 6)")


def track(conn: sqlite3.Connection, cands: Sequence[Dict[str, Any]], now: datetime) -> int:
    """Urmărește TOATE selecțiile Supersocial cu preț Superbet real, nu doar pe cele puse pe bilete.
    Prețul se actualizează până la start (ultimul preț văzut), apoi rămâne înghețat. Din ele învață ``key_lift``."""
    _ensure_track(conn)
    ts = canon_utc(now.isoformat())
    n = 0
    with conn:
        for c in cands:
            if not c.get("odds") or c.get("est") or c["odds"] <= 1 or c["kickoff_utc"] <= ts:
                continue
            conn.execute(
                "INSERT INTO ss_track (match_id, mkey, kickoff_utc, p, odds, updated_at, odds_first) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(match_id, mkey) DO UPDATE SET p=excluded.p, odds=excluded.odds, updated_at=excluded.updated_at, "
                "odds_first=COALESCE(ss_track.odds_first, excluded.odds_first) "
                "WHERE ss_track.result IS NULL AND ss_track.kickoff_utc > excluded.updated_at",
                (c["match_id"], c["key"], c["kickoff_utc"], c["p"], c["odds"], ts, c["odds"]))
            n += 1
    return n


def _scaled(price: Optional[float], p_leg: Optional[float], p_combo: Optional[float]) -> Optional[float]:
    if not price or not p_leg or not p_combo or p_combo <= 0:
        return None
    return price * p_leg / p_combo


# Superbet pune pe Bet Builder o marjă în plus față de piețele simple: pe un bilet real (16.10.2026, 11 BB „echipă 1-4 &
# R1 Sub 4.5”) Superbet a dat în medie 1.218, estimarea din piețele simple era 1.247 → prețul estimat × 0.975.
BB_MARGIN = 0.975


def _bb_price(key: str, ps: Dict[str, float], offers: Dict[str, float]) -> Optional[float]:
    """Cota combinației din liniile Superbet (ambele capete, dacă există), nu un preț copiat, cu marja Bet Builder."""
    legs = {"BB_H1C25_U65": ("H1C25", "H1U65"), "BB_C65_U145": ("C65", "CU145")}.get(key)
    if legs is None:
        anchor = BB_ANCHOR.get(key)
        legs = (anchor,) if anchor else ()
    vals = [v for leg in legs if (v := _scaled(offers.get(leg), ps.get(leg), ps.get(key)))]
    if not vals:
        return None
    g = math.exp(sum(math.log(v) for v in vals) / len(vals)) * BB_MARGIN
    return round(min(6.0, max(1.05, g)), 2)


def h1_shares(conn: sqlite3.Connection) -> Dict[Any, float]:
    """Cota de goluri din prima repriză, pe ligă (≥80 meciuri, micșorată spre 0.446) sau pe tot istoricul."""
    def q(where: str, args: tuple = ()) -> Tuple[Any, Any, Any]:
        return conn.execute(
            "SELECT SUM(ht_home+ht_away), SUM(ft_home+ft_away), COUNT(*) FROM match WHERE status='finished' "
            "AND ht_home IS NOT NULL AND ht_away IS NOT NULL AND ft_home IS NOT NULL AND ft_away IS NOT NULL "
            "AND (ft_home+ft_away)>0 " + where, args).fetchone()

    g1, g, n = q("")
    base = (g1 / g) if g and n and n >= 500 else H1_SHARE
    out: Dict[Any, float] = {None: max(0.40, min(0.52, base))}
    for lg, a, b, c in conn.execute(
            "SELECT league_id, SUM(ht_home+ht_away), SUM(ft_home+ft_away), COUNT(*) FROM match WHERE status='finished' "
            "AND ht_home IS NOT NULL AND ht_away IS NOT NULL AND ft_home IS NOT NULL AND ft_away IS NOT NULL "
            "AND (ft_home+ft_away)>0 GROUP BY league_id"):
        if b and c and c >= 80:
            out[lg] = max(0.40, min(0.52, (a + H1_SHARE * H1_PRIOR_N) / (b + H1_PRIOR_N)))
        else:
            out[lg] = out[None]
    return out


TEAM_GOALS = {"Peste 0.5": "O05", "Peste 1.5": "O15", "Sub 4.5": "U45"}
TEAM_CARDS = {"Peste 1.5": "Y15", "Peste 2.5": "Y25"}
TEAM_INTERVAL = {"1-3": "G13"}


OTHER_CARD_WORDS = ("roșii", "rosii", "galbene", "galbene/roșii")


def team_market(market: str, outcome: str, home: str, away: str) -> Optional[str]:
    """Piețele cu numele echipei în titlu („Total goluri Bahia”, „Total cartonașe Rapid Viena”) → HO05 / AY15 etc."""
    from betpredict.ingest.superbet import name_sim

    for prefix, table in (("Total goluri ", TEAM_GOALS), ("Total cartonașe ", TEAM_CARDS), ("Interval goluri ", TEAM_INTERVAL)):
        if not market.startswith(prefix) or outcome not in table:
            continue
        team = market[len(prefix):].strip()
        low = team.lower()
        if not team or team[0] in "(&-" or "repriz" in low or any(w in low.split() for w in OTHER_CARD_WORDS):
            # „Total goluri (2.5)”, „Total goluri & GG”, „Total goluri prima repriză …” nu sunt pe echipă; „Total cartonașe
            # roșii <echipă>” (cote 16–18) e altă piață: confundată cu cartonașele echipei, învăța un câștig fals (16.10.2026)
            return None
        sh, sa = name_sim(team, home), name_sim(team, away)
        if max(sh, sa) < 0.75 or abs(sh - sa) < 0.1:
            return None
        return ("H" if sh > sa else "A") + table[outcome]
    return None


def team13_p(lt: float, lo: float, share: float, ht_max: Optional[int] = None, hi: int = 3) -> float:
    """Echipa marchează 1-``hi`` goluri (și, cu ``ht_max``, prima repriză are cel mult atâtea goluri): Poisson pe reprize."""
    pois = lambda lam, k: math.exp(-lam) * lam ** k / math.factorial(k)  # noqa: E731
    if hi == 3:
        bias = (TEAM13_BIAS_BIG if lt >= 2.1 else TEAM13_BIAS) + (TEAM13_BIAS_BB if ht_max is not None else 0.0)
    else:
        bias = TEAM14_BIAS_BIG if lt >= 1.7 else TEAM14_BIAS
    if ht_max is None:
        return min(0.995, sum(pois(lt, k) for k in range(1, hi + 1)) + bias)
    p = 0.0
    for t1 in range(min(hi, ht_max) + 1):
        for o1 in range(ht_max - t1 + 1):
            p += pois(lt * share, t1) * pois(lo * share, o1) * sum(pois(lt * (1 - share), t2) for t2 in range(max(0, 1 - t1), hi + 1 - t1))
    return min(0.995, p + bias)


def team_p(lh: Optional[float], la: Optional[float], yh: Optional[float], ya: Optional[float],
           share: float = H1_SHARE) -> Dict[str, float]:
    """Goluri pe echipă (Poisson din λ robot) și cartonașe pe echipă (CardModel, cu corecția din laborator)."""
    from betpredict.experimental.cards import TEAM_LIFT

    tail = lambda lam, k: 1.0 - sum(math.exp(-lam) * lam ** i / math.factorial(i) for i in range(k + 1))  # noqa: E731
    out: Dict[str, float] = {}
    if lh is not None and la is not None:
        out.update({"HO05": tail(lh, 0), "HO15": tail(lh, 1), "AO05": tail(la, 0), "AO15": tail(la, 1),
                    "HG13": team13_p(lh, la, share), "AG13": team13_p(la, lh, share),
                    "BB_HG13_U35": team13_p(lh, la, share, 3), "BB_AG13_U35": team13_p(la, lh, share, 3),
                    "BB_HG14_U45": team13_p(lh, la, share, 4, 4), "BB_AG14_U45": team13_p(la, lh, share, 4, 4)})
    if yh is not None and ya is not None:
        out.update({"HY15": min(0.99, tail(yh, 1) * TEAM_LIFT), "AY15": min(0.99, tail(ya, 1) * TEAM_LIFT),
                    "HY25": min(0.99, tail(yh, 2) * TEAM_LIFT), "AY25": min(0.99, tail(ya, 2) * TEAM_LIFT)})
    return out


def model_p(lh: float, la: float, share: float = H1_SHARE) -> Dict[str, float]:
    p = _probs(lh, la, share, None)
    return {k: min(0.995, p[k] + BIAS.get(k, 0.0)) for k in BIAS}


def _bsd_corner_mean(conn: sqlite3.Connection, match_id: int) -> Optional[float]:
    """Mediana cornerelor din liniile OVER ale BSD (unde p trece prin 0.5)."""
    try:
        rows = conn.execute(
            "SELECT line, probability FROM provider_prediction WHERE source='bsd' AND match_id=? "
            "AND market='total_corners' AND selection='OVER'", (match_id,)).fetchall()
    except sqlite3.OperationalError:
        return None
    pts = sorted((float(a), float(b)) for a, b in rows if b is not None)
    for (l1, p1), (l2, p2) in zip(pts, pts[1:]):
        if p1 >= 0.5 >= p2 and p1 != p2:
            return l1 + (p1 - 0.5) / (p1 - p2) * (l2 - l1)
    return None


def market_lambdas(conn: sqlite3.Connection, ids: Sequence[int]) -> Dict[int, Tuple[float, float]]:
    """λ gazde/oaspeți din cote: 1X2 și Peste/Sub 2.5 fără marjă (consens BSD amestecat cu Pinnacle), toate meciurile odată."""
    if not ids:
        return {}
    try:
        import numpy as np

        from betpredict.lab.engine import lambdas_from_market
        from betpredict.robot.engine import blend_pinnacle, market_probs
        from betpredict.store import repo

        cons = repo.latest_odds(conn, list(ids))
        pin = repo.latest_odds(conn, list(ids), source="bsd:pinnacle")
    except Exception:  # noqa: BLE001  (fără tabelul de cote: doar robotul)
        return {}
    got, H, A, O = [], [], [], []
    for mid in ids:
        mk = blend_pinnacle(market_probs(cons.get(mid, {})), market_probs(pin.get(mid, {})))
        h, a, o = mk.get(("1x2", 0.0, "HOME")), mk.get(("1x2", 0.0, "AWAY")), mk.get(("over_under", 2.5, "OVER"))
        if h and a and o and 0.05 < o < 0.95:
            got.append(mid); H.append(h); A.append(a); O.append(o)
    if not got:
        return {}
    lh, la = lambdas_from_market(np.array(H), np.array(A), np.array(O))
    return {mid: (float(x), float(y)) for mid, x, y in zip(got, lh, la)}


def goal_lambdas(lh: Optional[float], la: Optional[float], mkt: Optional[Tuple[float, float]]) -> Tuple[Optional[float], Optional[float], str]:
    if mkt and lh is not None and la is not None:
        return MKT_W * mkt[0] + (1 - MKT_W) * lh, MKT_W * mkt[1] + (1 - MKT_W) * la, "goluri (piață + robot)"
    if mkt:
        return mkt[0], mkt[1], "goluri (piață)"
    return lh, la, "goluri (λ robot)"


def candidates(conn: sqlite3.Connection, now: datetime, horizon_h: int = 60, band=(1.01, 50.0)) -> List[Dict[str, Any]]:
    from betpredict.experimental.corners import CornerModel

    lo, hi = canon_utc(now.isoformat()), canon_utc((now + timedelta(hours=horizon_h)).isoformat())
    rows = conn.execute(
        """SELECT m.id, m.kickoff_utc, m.home_name, m.away_name, m.league_id, m.home_id, m.away_id,
                  mm.lambda_home lh, mm.lambda_away la
           FROM match m LEFT JOIN match_model mm ON mm.match_id = m.id
           WHERE m.kickoff_utc > ? AND m.kickoff_utc <= ?""", (lo, hi)).fetchall()
    cm = CornerModel(conn)
    mkt_lams = market_lambdas(conn, [r["id"] for r in rows])
    from betpredict.experimental.cards import CardModel

    yc = CardModel(conn)
    shares = h1_shares(conn)
    out = []
    for r in rows:
        share = shares.get(r["league_id"], shares[None])
        lh, la, gsrc = goal_lambdas(r["lh"], r["la"], mkt_lams.get(r["id"]))
        ps: Dict[str, float] = model_p(lh, la, share) if lh is not None else {}
        if ps:
            ps["BB_H13x2_O15"] = ps["H13x2"]  # 1-3 în fiecare repriză ⇒ ≥ 2 goluri: identic cu H13x2
        mean, src = cm.mean(r["league_id"], r["home_id"], r["away_id"])
        if src == "global":
            bsd = _bsd_corner_mean(conn, r["id"])
            if bsd:
                mean, src = bsd, "bsd"
        if mean:
            ps.update(cm.probs(mean))
        ymh, yma, ysrc = yc.means(r["league_id"], r["home_id"], r["away_id"])
        if ymh is not None:
            ps.update(CardModel.probs(ymh, yma))
        offers = offer_now(conn, r["id"], r["home_name"], r["away_name"])
        tp = team_p(lh, la, ymh, yma, share)
        if lh is not None and la is not None:  # 1–4 & R1 Sub 4.5: doar echipa favorită (așa a fost verificată pe istoric)
            tp.pop("BB_AG14_U45" if lh >= la else "BB_HG14_U45", None)
        # un Bet Builder intră doar dacă toate picioarele lui sunt în oferta Superbet (unele meciuri n-au R1 Sub 4.5
        # sau echipa Sub 4.5, ori sunt blocate): altfel biletul nu se poate pune
        for side in ("H", "A"):
            if f"{side}U45" not in offers or "H1U45" not in offers:
                tp.pop(f"BB_{side}G14_U45", None)
            if "H1U35" not in offers:
                tp.pop(f"BB_{side}G13_U35", None)
        ps.update({k: v for k, v in tp.items() if k in offers or BB_ANCHOR.get(k) in offers})
        if not offers:
            continue
        for k, p in ps.items():
            price, est = offers.get(k), False
            if k in BB_LEGS and not all(leg in offers for leg in BB_LEGS[k]):
                continue  # un picior lipsește sau e blocat pe Superbet
            if k in BB_KEYS and price is None:
                price, est = _bb_price(k, ps, offers), True
            show_fair = price is None and mean and k in (*CORNER_KEYS, "H1CLT5", "H1C56", "H1C7P")
            if not show_fair and not (k in BB_KEYS or (price and band[0] <= price <= band[1])):
                continue
            if est and price is None:
                est = False
            cornerish = k in CORNER_KEYS or k in ("H1U65", "CU145") or k.startswith("BB_C") or k.startswith("BB_H1C") or k.startswith("H1C")
            out.append({"match_id": r["id"], "league_id": r["league_id"], "key": k, "p": p, "odds": price,
                        "est": bool(est and price), "edge": p * price - 1 if price else None,
                        "kickoff_utc": r["kickoff_utc"], "home": r["home_name"], "away": r["away_name"],
                        "src": src if cornerish else f"cartonașe ({ysrc})" if k in CARD_KEYS else gsrc,
                        "corner_mean": round(mean, 2) if mean else None, "h1_share": round(share, 3)})
    return out


# Predicțiile robotului principal care intră în biletele mixte. Pe rezultatele reale cu cote Superbet (octombrie 2026,
# doar cele „sănătoase”): 1X2 +20% (35), GG +22% (21), egal-returnat +15% (23); Peste/Sub −11,6% (308) și șansă dublă
# −14,7% (28) au pierdut, deci nu mai intră.
ROBOT_MARKETS = {("1x2", 0.0), ("draw_no_bet", 0.0), ("btts", 0.0)}


def robot_key(market: str, line: float, sel: str) -> str:
    return f"R:{market}:{line:g}:{sel}"


def is_robot(key: str) -> bool:
    return key.startswith("R:")


def label(key: str) -> str:
    """Eticheta selecției: piețele Stil din LABELS, cele ale robotului principal din robot/markets.py."""
    if is_robot(key):
        _, market, line, sel = key.split(":")
        from betpredict.robot.markets import label_ro

        ln = float(line)
        name = {"1x2": "Final", "double_chance": "Șansă dublă", "draw_no_bet": "Egal = pariu returnat",
                "btts": "Ambele marchează", "over_under": "Total goluri"}.get(market, market)
        return f"{name} {label_ro(market, ln, sel)}"
    return LABELS.get(key, key)


def robot_candidates(conn: sqlite3.Connection, now: datetime, horizon_h: int) -> List[Dict[str, Any]]:
    """Predicțiile robotului principal (1X2, șansă dublă, Peste/Sub, GG) cu preț Superbet, pentru biletele mixte.
    Doar cele pe care robotul le consideră sănătoase (calibrare, segment, mișcarea cotei); un singur rând pe selecție."""
    lo, hi = canon_utc(now.isoformat()), canon_utc((now + timedelta(hours=horizon_h)).isoformat())
    try:
        rows = conn.execute(
            """SELECT p.match_id, p.market, p.line, p.selection, p.p_calibrated, p.p_model, p.reasons_json, p.created_at,
                      m.kickoff_utc, m.home_name, m.away_name, m.league_id
               FROM prediction p JOIN match m ON m.id = p.match_id
               WHERE m.kickoff_utc > ? AND m.kickoff_utc <= ? AND p.period='FT' AND p.result IS NULL
               ORDER BY p.created_at""", (lo, hi)).fetchall()
    except sqlite3.OperationalError:
        return []
    last: Dict[Tuple[int, str], Dict[str, Any]] = {}
    for r in rows:
        if (r["market"], float(r["line"] or 0)) not in ROBOT_MARKETS:
            continue
        try:
            js = json.loads(r["reasons_json"] or "{}")
        except ValueError:
            js = {}
        price = (js.get("odds_alt") or {}).get("superbet")
        p = r["p_calibrated"] if r["p_calibrated"] is not None else r["p_model"]
        k = robot_key(r["market"], float(r["line"] or 0), r["selection"])
        if not js.get("healthy") or not price or price <= 1 or p is None:
            last.pop((r["match_id"], k), None)  # cea mai nouă versiune nu mai e bună: nu folosim una veche
            continue
        last[(r["match_id"], k)] = {"match_id": r["match_id"], "league_id": r["league_id"], "key": k, "p": float(p),
                                    "odds": float(price), "est": False, "edge": float(p) * float(price) - 1,
                                    "kickoff_utc": r["kickoff_utc"], "home": r["home_name"], "away": r["away_name"],
                                    "src": "robotul principal", "corner_mean": None, "h1_share": None}
    return list(last.values())


# Absenți (API-Football, meciurile din următoarele 24 de ore): un pariu pe o echipă (marchează, 1–3 / 1–4 goluri,
# câștigă, egal-returnat) iese dacă echipa are cu cel puțin ABS_GAP absenți mai mulți decât adversarul. Nu se numără cei
# scoși de mult din lot („Off the roster”, „Inactive”): sunt deja în cote.
ABS_GAP = 3
ABS_LONG = ("off the roster", "inactive")
TEAM_SIDE = {"HO05": "home", "HO15": "home", "HG13": "home", "BB_HG13_U35": "home", "BB_HG14_U45": "home",
             "R:1x2:0:HOME": "home", "R:draw_no_bet:0:HOME": "home",
             "AO05": "away", "AO15": "away", "AG13": "away", "BB_AG13_U35": "away", "BB_AG14_U45": "away",
             "R:1x2:0:AWAY": "away", "R:draw_no_bet:0:AWAY": "away"}


# Cotele mărite cu EV pozitiv au ieșit pe plus pe rezultatele reale (+30% pe 61, 11–16.10.2026): pe fiecare bilet Stil
# intră cel mult una, în locul celor mai slabe selecții (cota rămâne în bandă), și fiecare cotă mărită pe un singur bilet.
BOOST_PER_TICKET = 1
# Fiecare bilet Stil cu cotă mărită are și un geamăn fără ea (aceleași selecții de dinainte de înlocuire): auditul le compară.
BOOST_TWIN = True
TWIN_SUFFIX = " · fără cotă mărită"
# Biletele lungi: varianta sistem recomandată (N−1 din N). Pe istoric (1–4 & R1 Sub 4.5, 683 de bilete de 20): 19/20 plătește
# de ~4× mai des decât biletul întreg (5–9% din bilete față de 1,4–2%), cu același câștig așteptat.
SYSTEM_MIN_LEGS = 12


def _boost_pool(conn: sqlite3.Connection, now: datetime) -> List[Dict[str, Any]]:
    try:
        from betpredict.ingest.boosts import today_doc

        return [b for b in today_doc(conn, now)["boosts"]
                if (b.get("ev") or -1) > 0 and b.get("reliable") and not b.get("suspect") and b.get("price") and b.get("p_fair")]
    except Exception:  # noqa: BLE001  (fără tabelul cotelor mărite)
        return []


def _with_boost(legs: List[Dict[str, Any]], boosts: List[Dict[str, Any]], used: set, used_match: Dict[int, int],
                lo_n: int, band: Tuple[float, float]) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """O cotă mărită +EV în locul celor mai slabe selecții (cele mai multe șanse pierdute pe unitate de cotă)."""
    mids = {c["match_id"] for c in legs}
    for b in boosts:
        uid = (b["match_id"], b["label"])
        if uid in used or b["match_id"] in mids or used_match.get(b["match_id"], 0) >= MAX_TICKETS_PER_MATCH:
            continue
        keep = sorted(legs, key=_cost)  # cele mai eficiente întâi
        # iese cea mai slabă selecție cât timp biletul rămâne de la cota minimă a benzii: cota mărită ia locul mai
        # multor selecții, deci biletul are mai puține meciuri la aceeași cotă (șansă mai mare)
        while len(keep) > max(lo_n - 1, 1) and math.prod(c["odds"] for c in keep[:-1]) * b["price"] >= band[0]:
            keep.pop()
        total = math.prod(c["odds"] for c in keep) * b["price"]
        if band[0] <= total <= band[1] * 1.04:
            return keep, b
    return legs, None


# o selecție citită cu mult înainte de ultima citire a meciului a dispărut între timp din ofertă (blocată sau scoasă):
# rândul rămâne în sb_offer cu prețul vechi, dar nu se mai poate pune
OFFER_STALE_MIN = 20


def offer_now(conn: sqlite3.Connection, match_id: int, home: str, away: str, names: bool = False) -> Dict[str, Any]:
    """Piețele Stil (și picioarele Bet Builder-elor) din oferta Superbet de acum a meciului: cheie → cotă
    (cu ``names``: cheie → (piața, selecția) exact cum le scrie Superbet, pentru biletul precompletat)."""
    rows = conn.execute("SELECT market_name, outcome, price, observed_at FROM sb_offer WHERE match_id=?", (match_id,)).fetchall()
    if not rows:
        return {}
    last = max(r[3] or "" for r in rows)
    try:
        lim = canon_utc((datetime.fromisoformat(last.replace("Z", "+00:00")) - timedelta(minutes=OFFER_STALE_MIN)).isoformat())
    except ValueError:
        lim = ""
    out: Dict[str, float] = {}
    for mname, outcome, price, seen in rows:
        if (seen or "") < lim:
            continue
        key = MARKETS.get((mname, outcome)) or team_market(mname, outcome, home, away)
        if key:
            out[key] = (mname, outcome) if names else price
    return out


def bb_legs(key: str) -> Tuple[str, ...]:
    """Picioarele unui Bet Builder (piețele simple din care îl compui pe Superbet)."""
    return BB_LEGS.get(key) or {"BB_HG14_U45": ("HO05", "HU45", "H1U45"), "BB_AG14_U45": ("AO05", "AU45", "H1U45"),
                                "BB_HG13_U35": ("HG13", "H1U35"), "BB_AG13_U35": ("AG13", "H1U35")}.get(key, ())


def playable(conn: sqlite3.Connection, match_id: int, key: str, home: str, away: str) -> Tuple[bool, Optional[float]]:
    """Se mai poate pune selecția pe Superbet acum? (și cota ei de acum, unde Superbet o publică direct)."""
    offers = offer_now(conn, match_id, home, away)
    if not offers:
        return True, None  # fără ofertă citită (meci început, ligă fără detalii): nu știm, nu semnalăm
    if key in BB_KEYS:
        return all(l in offers for l in bb_legs(key)), None
    if is_robot(key):
        return True, None  # piețele principale se verifică din cotele robotului
    return key in offers, offers.get(key)


def absences(conn: sqlite3.Connection) -> Dict[int, Tuple[int, int]]:
    """Absenții de scurtă durată pe meci: (gazde, oaspeți), din ``af_injury``."""
    out: Dict[int, Tuple[int, int]] = {}
    try:
        rows = conn.execute("SELECT match_id, players_json FROM af_injury").fetchall()
    except sqlite3.OperationalError:
        return out
    for mid, pj in rows:
        try:
            players = json.loads(pj or "[]")
        except ValueError:
            continue
        cnt = {"home": 0, "away": 0}
        for pl in players:
            if (pl.get("reason") or "").strip().lower() in ABS_LONG or pl.get("type") == "Questionable":
                continue
            if pl.get("side") in cnt:
                cnt[pl["side"]] += 1
        out[mid] = (cnt["home"], cnt["away"])
    return out


def drop_absent(cands: List[Dict[str, Any]], abs_: Dict[int, Tuple[int, int]]) -> Tuple[List[Dict[str, Any]], int]:
    keep, n = [], 0
    for c in cands:
        side = TEAM_SIDE.get(c["key"])
        a = abs_.get(c["match_id"])
        if side and a:
            mine, other = (a[0], a[1]) if side == "home" else (a[1], a[0])
            if mine - other >= ABS_GAP:
                n += 1
                continue
        keep.append(c)
    return keep, n


MUST_REBUILD = (BEST_NAME, BEST_SAFE_NAME, "Combo R1 0.5 & meci 1.5", "Goluri 1–3", "R1 cornere interval 3-6")


def _prod(legs: Sequence[Dict[str, Any]]) -> float:
    return math.prod(c["odds"] for c in legs) if legs else 1.0


def _assemble(pool: Sequence[Dict[str, Any]], lo_n: int, hi_n: int, max_per_key: Optional[int],
               odds_lo: float = ODDS_LO, odds_hi: float = ODDS_HI, max_per_league: int = MAX_PER_LEAGUE,
               max_per_family: Optional[int] = None, efficient: bool = False) -> Optional[List[Dict[str, Any]]]:
    """Cea mai mare șansă de verde în bandă. O selecție în plus scade șansa, deci nu se lungește un bilet deja valid."""
    hard = odds_hi * (ODDS_HI_HARD / ODDS_HI)
    items = list(pool)
    E = 0.0
    if efficient:
        # biletul spre o cotă țintă: contează câtă șansă pierzi pentru fiecare bucată de cotă câștigată,
        # nu doar șansa selecției (altfel ar lua numai cote de 1.15 și n-ar ajunge niciodată la 80)
        items.sort(key=_cost)
        E = _cost(items[min(9, len(items) - 1)]) if items else 0.0
    if max_per_key is not None:
        # cu limită pe piață: din fiecare piață doar primele câteva rezerve, altfel cele 40 de locuri ar fi luate de o
        # singură piață și limita ar face biletul imposibil
        seen_k: Dict[str, int] = {}
        kept = []
        for c in items:
            seen_k[c["key"]] = seen_k.get(c["key"], 0) + 1
            if seen_k[c["key"]] <= max_per_key + 5:
                kept.append(c)
        items = kept
    items = items[:40]
    if not items:
        return None
    beam: List[Tuple[frozenset, float, float]] = [(frozenset(), 1.0, 1.0)]
    best: Optional[Tuple[float, int, float, frozenset]] = None
    for _ in range(hi_n):
        nxt: List[Tuple[float, frozenset, float, float]] = []
        seen = set()
        for state, prod, pj in beam:
            chosen = [items[i] for i in state]
            in_t = {c["match_id"] for c in chosen}
            per_key: Dict[str, int] = {}
            per_lg: Dict[Any, int] = {}
            per_fam: Dict[str, int] = {}
            for c in chosen:
                per_key[c["key"]] = per_key.get(c["key"], 0) + 1
                per_fam[family(c["key"])] = per_fam.get(family(c["key"]), 0) + 1
                lid = c.get("league_id")
                if lid is not None:
                    per_lg[lid] = per_lg.get(lid, 0) + 1
            for i, c in enumerate(items):
                if i in state or c["match_id"] in in_t:
                    continue
                lid = c.get("league_id")
                if lid is not None and per_lg.get(lid, 0) >= max_per_league:
                    continue
                if max_per_key is not None and per_key.get(c["key"], 0) >= max_per_key:
                    continue
                if c["key"] in CARD_KEYS and sum(per_key.get(k, 0) for k in CARD_KEYS) >= CARD_PER_TICKET:
                    continue
                if max_per_family is not None and per_fam.get(family(c["key"]), 0) >= max_per_family:
                    continue
                new_prod = prod * c["odds"]
                if new_prod > hard:
                    continue
                ns = state | {i}
                if ns in seen:
                    continue
                seen.add(ns)
                new_p = pj * (c.get("p_rank") or c["p"] or 0.0)
                if len(ns) >= lo_n and odds_lo <= new_prod <= hard:
                    cand = (new_p, -len(ns), new_prod, ns)
                    if best is None or cand[:2] > best[:2]:
                        best = cand
                    continue
                nxt.append((new_p, ns, new_prod, new_p))
        if not nxt:
            break
        if efficient:  # starea cea mai bună = șansa estimată la final, dacă restul cotei vine cu eficiența obișnuită
            nxt.sort(key=lambda x: -(math.log(max(x[0], 1e-12)) + E * math.log(x[2])))
        else:
            nxt.sort(key=lambda x: -x[0])
        beam = [(s, pr, p) for _, s, pr, p in nxt[:24]]
    if best is None:
        return None
    return [items[i] for i in best[3]]


def wave_keys(legs: Dict[str, Dict[str, Any]]) -> List[str]:
    """Tipurile cu cel puțin WAVE_MIN_N selecții decontate și ROI peste zero, cele mai bune întâi."""
    hot = [k for k, v in legs.items() if (v.get("n") or 0) >= WAVE_MIN_N and (v.get("roi_single") or 0) > WAVE_MIN_ROI]
    hot.sort(key=lambda k: -(legs[k].get("roi_single") or 0))
    return hot


def active_specs(hot: Sequence[str]) -> Tuple:
    """Fără istoric: toate rețetele. Cu istoric: doar piețele pe val, plus un bilet mixt."""
    hot_set = set(hot)
    if not hot_set:
        return TICKETS
    specs = []
    if len(hot) >= 2:
        specs.append(("Pe val", tuple(hot), 4, 12, "p", (1.15, 1.80)))
    for name, keys, lo, hi, order, band in TICKETS:
        if name == "Mix Supersocial":
            continue
        keep = tuple(k for k in keys if k in hot_set)
        if not keep:
            continue
        if keep == tuple(keys):
            specs.append((name, keep, lo, hi, order, band))
        elif len(keep) == 1:
            specs.append((f"Pe val · {label(keep[0])}", keep, lo, hi, order, band))
        else:
            specs.append((f"Pe val · {name}", keep, lo, hi, order, band))
    return tuple(specs)


def _pending_wave(conn: sqlite3.Connection, today: date) -> Optional[Tuple[str, ...]]:
    """Semnătura piețelor folosite la biletele pending de azi. None = nu există bilete pending."""
    rows = conn.execute(
        "SELECT notes FROM ticket WHERE day=? AND variant=? AND status='pending'",
        (today.isoformat(), VARIANT)).fetchall()
    if not rows:
        return None
    sigs = set()
    for r in rows:
        try:
            notes = json.loads(r[0] or "{}")
        except ValueError:
            notes = {}
        sigs.add(tuple(sorted(notes.get("wave_keys") or [])))
    if len(sigs) != 1:
        return ("*",)
    return sigs.pop()


def _odds_outside(conn: sqlite3.Connection, today: date) -> bool:
    """Biletele pending cu cota în afara benzii lor se refac. Cel de 4–5 (Pe val scurt) se înlocuiește."""
    rows = conn.execute(
        "SELECT total_odds, notes FROM ticket WHERE day=? AND variant=? AND status='pending'",
        (today.isoformat(), VARIANT)).fetchall()
    for odds, raw in rows:
        try:
            notes = json.loads(raw or "{}")
        except ValueError:
            notes = {}
        stil = notes.get("stil")
        if notes.get("short") or stil == "Pe val scurt":
            return True
        if notes.get("slip") == "supersocial" or stil == "Supersocial":
            if odds < SUPERS_ODDS[0] or odds > SUPERS_ODDS[1] * 1.04:
                return True
        elif stil in SPEC_ODDS:
            if odds < SPEC_ODDS[stil][0] or odds > SPEC_ODDS[stil][1] * 1.04:
                return True
        elif odds < ODDS_LO or odds > ODDS_HI_HARD:
            return True
    return False


STALE_EDGE = -0.05


BB_TEAM_KEYS = BB_KEYS  # toate Bet Builder-ele: fără un picior în ofertă, biletul nu se mai poate pune


def _stale_tickets(conn: sqlite3.Connection, today: date, cands: Sequence[Dict[str, Any]], now: datetime) -> List[Tuple[int, str]]:
    """Biletele de azi încă neîncepute în care o selecție a ajuns clar sub cotă cu estimarea de acum (alt λ, altă cotă,
    o corecție învățată): se refac. Cele cu un meci deja început rămân, ca să nu dispară un bilet aflat în joc."""
    cur = {(c["match_id"], c["key"]): c.get("edge") for c in cands}
    start = canon_utc(now.isoformat())
    try:
        paused = {r[0] for r in conn.execute("SELECT mkey FROM market_state WHERE status='paused'")}
    except sqlite3.OperationalError:
        paused = set()
    out = []
    for t in conn.execute("SELECT id, notes FROM ticket WHERE day=? AND variant=? AND status='pending'", (today.isoformat(), VARIANT)).fetchall():
        legs = conn.execute("""SELECT tl.match_id, tl.selection, m.kickoff_utc FROM ticket_leg tl JOIN match m ON m.id=tl.match_id
                               WHERE tl.ticket_id=?""", (t["id"],)).fetchall()
        if not legs or any(l["kickoff_utc"] <= start for l in legs):
            continue
        bad = [l for l in legs if cur.get((l["match_id"], l["selection"])) is not None and cur[(l["match_id"], l["selection"])] < STALE_EDGE]
        # Bet Builder pe echipă care nu mai e în oferta Superbet (un picior blocat sau scos): biletul nu se mai poate pune
        bad += [l for l in legs if l["selection"] in BB_TEAM_KEYS and (l["match_id"], l["selection"]) not in cur]
        try:
            name = json.loads(t["notes"] or "{}").get("stil")
        except ValueError:
            name = None
        if name in TIER_NAMES:
            # treptele mari / lanțul: cu ≤ 75 min înainte de primul meci, o selecție scoasă de echipele confirmate sau de
            # mișcarea Pinnacle (nu mai e între candidați) reface biletul
            first = min(l["kickoff_utc"] for l in legs)
            if first <= canon_utc((now + timedelta(minutes=LINEUP_REBUILD_MIN)).isoformat()):
                bad += [l for l in legs if (l["match_id"], l["selection"]) not in cur]
        # reguli noi aplicate și biletelor deja publicate (neîncepute): prea multe cartonașe, piețe pauzate, cartonașe scoase de poartă
        cards = [l for l in legs if l["selection"] in CARD_KEYS]
        if len(cards) > CARD_PER_TICKET:
            bad += cards
        bad += [l for l in legs if l["selection"] in paused]
        bad += [l for l in cards if (l["match_id"], l["selection"]) not in cur]
        if bad:
            out.append((t["id"], name))
    return out


def _needs_rebuild(existing: set, cands: List[Dict[str, Any]], specs: Sequence[Tuple]) -> bool:
    """Reface biletele doar dacă slipul lipsă chiar încape în banda 80–200. Altfel s-ar șterge în fiecare oră."""
    for name, keys, lo_n, hi_n, _order, band in specs:
        if name in existing:
            continue
        if name not in MUST_REBUILD and name not in ("Pe val", "Supersocial") and not str(name).startswith("Pe val"):
            continue
        floor = _floor(name)
        pool = _priced_pool(cands, keys, band, floor)
        cap = _key_cap(keys)
        odds_lo, odds_hi = _odds_band(name)
        best = name.startswith(BEST_NAME)
        if _assemble(_by_green(pool), lo_n, hi_n, cap, odds_lo, odds_hi, MAX_PER_LEAGUE, BEST_PER_FAMILY if best else None, efficient=best):
            return True
    return False


def family(key: str) -> str:
    if is_robot(key):
        return "goluri" if ":over_under:" in key or ":btts:" in key else "rezultat"
    if key in CARD_KEYS:
        return "cartonase"
    if key in CORNER_KEYS or key in ("H1U65", "CU145", "H1CLT5", "H1C56", "H1C7P") or key.startswith(("BB_C", "BB_H1C", "H1C")):
        return "cornere"
    return "goluri"


def _floor(name: str) -> Optional[float]:
    if name == "Supersocial":
        return SUPERS_EDGE
    if name in HIST_FLOOR:
        return HIST_FLOOR[name]
    return BEST_MIN_EDGE if name.startswith(BEST_NAME) else None


def _odds_band(name: str) -> Tuple[float, float]:
    if STIL_COMPACT:
        return next((b for n, b, _lo, _hi in STIL_TIERS if n == name), STIL_ODDS)
    return SUPERS_ODDS if name == "Supersocial" else SPEC_ODDS.get(name, (ODDS_LO, ODDS_HI))


def _cost(c: Dict[str, Any]) -> float:
    """Șansă pierdută pe unitate de cotă: −ln(p) / ln(cotă). Mai mic = mai eficient."""
    p = c.get("p_rank") or c.get("p") or 0.0
    o = c.get("odds") or 1.0
    if p <= 0 or o <= 1.0:
        return 99.0
    return -math.log(p) / math.log(o)


MIN_TICKET_EV = -0.15  # sub atât (EV realist: cote fără marjă × corecția învățată) biletul nu se mai publică


def proven(key: str, lift: Dict[str, Dict[str, float]]) -> bool:
    """Piață cu destule rezultate reale și care intră cel puțin cât promite cota."""
    lf = lift.get(key)
    return bool(lf and lf["n"] >= LIFT_MIN_N and lf["lift"] >= 1.0)


def _ticket_ev(legs: Sequence[Dict[str, Any]], lift: Dict[str, Dict[str, float]]) -> float:
    return math.prod(realistic_p(c, lift) for c in legs) * math.prod(c["odds"] for c in legs) - 1


def _key_cap(keys: Sequence[str]) -> Optional[int]:
    if "*" in keys:
        return BEST_PER_KEY
    return MAX_PER_KEY if len(keys) > 2 else (12 if len(keys) > 1 else None)


def _by_green(pool: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Cea mai mare șansă de verde: șansa combinată model + cotă, apoi avantajul față de cotă."""
    return sorted(pool, key=lambda c: (-(c.get("p_rank") or c["p"] or 0.0), -(c["edge"] or -1.0)))


def _logit(p: float) -> float:
    p = min(0.995, max(0.005, p))
    return math.log(p / (1 - p))


def rank_p(c: Dict[str, Any], lift: Dict[str, Dict[str, float]]) -> float:
    """Șansa după care se ordonează selecțiile: modelul și cota Superbet, cu greutăți egale (logit)."""
    if not c.get("odds") or not c.get("p"):
        return c.get("p") or 0.0
    w = RANK_W_FAMILY.get(family(c["key"]), RANK_W)
    z = w * _logit(c["p"]) + (1 - w) * _logit(realistic_p(c, lift))
    return 1 / (1 + math.exp(-z))


def suspect(c: Dict[str, Any]) -> bool:
    return (c.get("edge") or 0.0) > EDGE_SUSPECT


def _priced_pool(cands: Sequence[Dict[str, Any]], keys: Sequence[str], band: Tuple[float, float], min_edge: Optional[float] = None) -> List[Dict[str, Any]]:
    out = []
    for c in cands:
        if not c.get("odds") or (c["key"] not in keys and "*" not in keys) or not (band[0] <= c["odds"] <= band[1]) or c.get("edge") is None:
            continue
        floor = min_edge if min_edge is not None else (CORNER_MIN_EDGE if c["key"] in CORNER_KEYS or c["key"] in BB_KEYS else MIN_EDGE)
        # avantajul se judecă pe șansa combinată (cotă + rezultate reale + puțin model), nu pe model singur
        e = c["p_rank"] * c["odds"] - 1 if c.get("p_rank") else c["edge"]
        if e < floor or suspect(c):
            continue
        if "*" in keys and (c.get("est") or c["key"] in BB_KEYS):
            continue  # alegerea robotului: doar prețuri reale Superbet
        out.append(c)
    return out


def lineup_info(conn: sqlite3.Connection, ids: Sequence[int]) -> Dict[int, Tuple[int, int]]:
    """Indisponibili (accidentați/suspendați) din echipele de start confirmate: (gazde, oaspeți). Doar status «confirmed»."""
    out: Dict[int, Tuple[int, int]] = {}
    if not ids:
        return out
    q = ",".join("?" for _ in ids)
    try:
        rows = conn.execute(f"SELECT match_id, context_json FROM match_context WHERE match_id IN ({q})", list(ids)).fetchall()
    except sqlite3.OperationalError:
        return out
    for mid, cj in rows:
        try:
            lu = (json.loads(cj or "{}") or {}).get("lineups") or {}
        except ValueError:
            continue
        if lu.get("status") != "confirmed" or not isinstance(lu.get("unavailable"), dict):
            continue
        un = lu["unavailable"]
        # doar titularii importanți contează (imp ≥ KEY_IMP din minutele/golurile recente); o absență oarecare nu mișcă nimic
        def _key(side: str) -> int:
            return sum(1 for pl in (un.get(side) or []) if isinstance(pl, dict) and (pl.get("imp") or 0) >= KEY_IMP)
        out[mid] = (_key("home"), _key("away"))
    return out


def pinnacle_drift(conn: sqlite3.Connection, ids: Sequence[int]) -> Dict[int, float]:
    """Pinnacle Peste 2.5: cota acum ÷ cota la deschidere − 1 (negativ = cota a scăzut, piața vine spre goluri)."""
    from betpredict.store import repo

    out: Dict[int, float] = {}
    if not ids:
        return out
    try:
        now = repo.latest_odds(conn, list(ids), source="bsd:pinnacle")
        q = ",".join("?" for _ in ids)
        rows = conn.execute(f"""SELECT match_id, decimal FROM odds_open WHERE source='bsd:pinnacle' AND market='over_under'
                                     AND line=2.5 AND outcome='OVER' AND match_id IN ({q})""", list(ids)).fetchall()
    except sqlite3.OperationalError:
        return out
    for mid, dec in rows:
        cur = ((now.get(mid) or {}).get("over_under_2.5") or {}).get("OVER")
        if cur and dec and dec > 1:
            out[mid] = cur / dec - 1
    return out


def signal_filter(conn: sqlite3.Connection, cands: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Echipe confirmate + mișcarea Pinnacle: scoate selecțiile slăbite, preferă (șansă ×1.02) pe cele spre care vine piața."""
    ids = sorted({c["match_id"] for c in cands})
    lu, dr = lineup_info(conn, ids), pinnacle_drift(conn, ids)
    out, st = [], {"lineup": 0, "drift": 0, "shortened": 0}
    for c in cands:
        k, mid = c["key"], c["match_id"]
        side = TEAM_SIDE.get(k)
        if mid in lu:
            h, a = lu[mid]
            weak = (side == "home" and h - a >= LINEUP_SIDE_GAP) or (side == "away" and a - h >= LINEUP_SIDE_GAP) \
                or (side is None and k in GOAL_UP_KEYS and h + a >= LINEUP_TOTAL_MAX)
            if weak:
                st["lineup"] += 1
                continue
        d = dr.get(mid)
        if d is not None and k in GOAL_UP_KEYS:
            if d > DRIFT_OUT:
                st["drift"] += 1
                continue
            if d < DRIFT_IN and c.get("p_rank"):
                c = {**c, "p_rank": min(0.99, c["p_rank"] * DRIFT_BONUS), "shortened": round(d, 3)}
                st["shortened"] += 1
        out.append(c)
    return out, st


def build_chain(pool: Sequence[Dict[str, Any]], now: datetime) -> Optional[List[List[Dict[str, Any]]]]:
    """«Lanț pe ore»: 3–4 bilete mici succesive (cota 3.2–6 fiecare); câștigul unei trepte intră ca miză în următoarea.
    Fiecare treaptă începe după ce meciurile treptei anterioare s-au jucat. Total ≥ 100 dintr-o singură miză."""
    t0 = now + timedelta(minutes=LINEUP_REBUILD_MIN)
    items = sorted((c for c in pool if c.get("odds")), key=lambda c: c["kickoff_utc"])
    steps: List[List[Dict[str, Any]]] = []
    used: set = set()
    start = canon_utc(t0.isoformat())
    while len(steps) < CHAIN_STEPS[1]:
        avail = [c for c in items if c["kickoff_utc"] >= start and c["match_id"] not in used]
        if not avail:
            break
        first = datetime.fromisoformat(avail[0]["kickoff_utc"].replace("Z", "+00:00"))
        win_end = canon_utc((first + timedelta(minutes=90)).isoformat())
        window = [c for c in avail if c["kickoff_utc"] <= win_end]
        legs = _assemble(_by_green(window), 1, 3, None, CHAIN_STEP_ODDS[0], CHAIN_STEP_ODDS[1], 4, None)
        if not legs:  # fereastra prea mică: mutăm începutul după primul meci
            start = canon_utc((first + timedelta(minutes=1)).isoformat())
            continue
        steps.append(legs)
        used |= {c["match_id"] for c in legs}
        last = max(datetime.fromisoformat(c["kickoff_utc"].replace("Z", "+00:00")) for c in legs)
        start = canon_utc((last + timedelta(minutes=CHAIN_GAP_MIN)).isoformat())
    if len(steps) < CHAIN_STEPS[0]:
        return None
    total = math.prod(_prod(s) for s in steps)
    return steps if total >= CHAIN_MIN_TOTAL else None


def positive_keys(conn: sqlite3.Connection, min_n: int = STIL_POS_MIN_N) -> List[str]:
    """Piețele Stil cu ROI pozitiv pe selecțiile decontate (preț Superbet real), cel puțin ``min_n`` rezultate."""
    _ensure_track(conn)
    out = []
    for k, n, ret in conn.execute("""SELECT mkey, COUNT(*), SUM(CASE WHEN result='won' THEN odds ELSE 0 END) FROM ss_track
                                     WHERE result IN ('won','lost') AND odds > 1 GROUP BY mkey"""):
        if k in STIL_BANNED or is_robot(k) or n < min_n:
            continue
        roi = (ret or 0.0) / n - 1
        if roi > 0:
            out.append((roi, k))
    keys = [k for _, k in sorted(out, reverse=True)]
    return keys if len(keys) >= 2 else [k for k in STIL_DEFAULT_KEYS if k not in STIL_BANNED]


def stil_specs(specs: Sequence[Tuple], allowed: Sequence[str]) -> List[Tuple]:
    """Rețetele Stil restrânse la piețele permise, cu 3–6 selecții și cotă 2.5–25."""
    ok = set(allowed) - STIL_BANNED
    out, seen = [], set()
    for name, keys, _lo, _hi, order, band in specs:
        keep = tuple(ok) if "*" in keys else tuple(k for k in keys if k in ok)
        if not keep or name in seen:
            continue
        seen.add(name)
        out.append((name, keep, STIL_LEGS[0], STIL_LEGS[1], order, band))
    return out


def ensure_pont_stil(conn: sqlite3.Connection, day: date, kind: str, variant: str, band: Tuple[float, float],
                     now: Optional[datetime] = None) -> int:
    """Pontul zilei din piețele Stil cu ROI pozitiv: o selecție cu cotă Superbet reală în bandă, fără EV suspect,
    avantaj ≥ 0 pe șansa combinată (model + cotă + rezultate), cea mai mare șansă. 0 dacă nu există."""
    from betpredict.store import repo

    now = now or datetime.now(timezone.utc)
    allowed = set(positive_keys(conn))
    lift = key_lift(conn)
    start = canon_utc(now.isoformat())
    from betpredict.timeutil import ro_day_bounds_utc

    lo_utc, hi_utc = ro_day_bounds_utc(day)
    best = None
    for c in apply_lift(calibrate_cards(candidates(conn, now, 36), card_calibration(conn)), lift, league_lift(conn, lift)):
        if c["key"] not in allowed or not c.get("odds") or c.get("est") or c["key"] in BB_KEYS or suspect(c):
            continue
        if not (band[0] <= c["odds"] <= band[1]) or c["kickoff_utc"] <= start or not (lo_utc <= c["kickoff_utc"] < hi_utc):
            continue
        pr = rank_p(c, lift)
        if pr * c["odds"] - 1 < 0:
            continue
        if best is None or pr > best[0]:
            best = (pr, c)
    if not best:
        return 0
    pr, c = best
    notes = {"honest": True, "pont": True, "stil": "Pontul zilei", "paper": True,
             "reasons": [f"Pontul zilei din piețele Stil cu ROI pozitiv: {label(c['key'])} · cotă {c['odds']:.2f}",
                         f"Șansă realistă {pr:.1%} · EV {pr * c['odds'] - 1:+.1%}. Robotul principal n-are azi nicio piață pe plus."]}
    with conn:
        cur = conn.execute(
            """INSERT INTO ticket (kind, variant, created_by, target_odds, total_odds, p_ticket, ev, stake, status, created_at, notes, day)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (kind, variant, "robot", round(c["odds"], 2), round(c["odds"], 2), round(pr, 6), round(pr * c["odds"] - 1, 4), 1.0, "pending",
             repo.now_iso(), json.dumps(notes, ensure_ascii=False), day.isoformat()))
        conn.execute("INSERT INTO ticket_leg (ticket_id, prediction_id, match_id, market, selection, odds, odds_source) VALUES (?,?,?,?,?,?,?)",
                     (cur.lastrowid, None, c["match_id"], "ss|0", c["key"], c["odds"], "superbet"))
    return 1


def card_calibration(conn: sqlite3.Connection) -> Dict[str, float]:
    """Pe piața de cartonașe: factorul cu care se înmulțește șansa modelului = câștigate reale ÷ șansa medie promisă,
    micșorat spre 1 cu CARD_CAL_K. Ex.: Sub 5.5 promitea 95%, a intrat 81% → ≈0.87."""
    _ensure_track(conn)
    out: Dict[str, float] = {}
    for k, n, w, mp in conn.execute("""SELECT mkey, COUNT(*), SUM(result='won'), AVG(p) FROM ss_track
                                        WHERE result IN ('won','lost') GROUP BY mkey"""):
        if k not in CARD_KEYS or n < CARD_CAL_MIN_N or not mp:
            continue
        out[k] = round((w + CARD_CAL_K * mp) / (n * mp + CARD_CAL_K * mp), 4)
    return out


def calibrate_cards(cands: List[Dict[str, Any]], cal: Dict[str, float]) -> List[Dict[str, Any]]:
    for c in cands:
        f = cal.get(c["key"])
        if f and c.get("p"):
            c["p_uncal"] = c["p"]
            c["p"] = min(0.99, max(0.01, c["p"] * f))
            if c.get("odds"):
                c["edge"] = c["p"] * c["odds"] - 1
    return cands


def build(conn: sqlite3.Connection, today: date, now: Optional[datetime] = None, replace: bool = False) -> Dict[str, Any]:
    from betpredict.store import repo

    now = now or datetime.now(timezone.utc)
    conn.execute(SCHEMA)
    rep: Dict[str, Any] = {"snapshot_rows": snapshot(conn, now)}
    existing = {json.loads(r[0] or "{}").get("stil") for r in conn.execute(
        "SELECT notes FROM ticket WHERE day=? AND variant=? AND status!='replaced'", (today.isoformat(), VARIANT))}
    have = bool(existing)
    try:  # cartonașe/cornere/pauză din football-data pe meciurile deja legate (istoric pentru modele)
        from betpredict.ingest.footballdata import fill_match_stats

        fill_match_stats(conn)
    except sqlite3.OperationalError:
        pass  # fără tabelul football-data
    _health = market_health(conn, now)
    _paused = {k for k, v in _health.items() if v["status"] == "paused"}
    rep["paused_markets"] = sorted(_paused)
    raw = card_gate(calibrate_cards(candidates(conn, now, HORIZON_H), card_calibration(conn))) + robot_candidates(conn, now, HORIZON_H)
    raw = [c for c in raw if c.get("key") not in _paused]
    rep["tracked"] = track(conn, raw, now)
    raw, rep["dropped_absences"] = drop_absent(raw, absences(conn))
    lift = key_lift(conn)
    cands = [{**c, "p_rank": rank_p(c, lift)} for c in apply_lift(raw, lift, league_lift(conn, lift))]
    cands, rep["signals"] = signal_filter(conn, cands)  # echipe confirmate + mișcarea Pinnacle
    rep["repriced_pending"] = refresh_pending(conn, lift)
    hot = wave_keys(live_stats(conn)["legs"])
    specs = list(active_specs(hot))
    if hot:
        specs.append(("Supersocial", tuple(hot), 6, 16, "p", (1.15, 2.20)))
        # pe lângă piețele pe val, și rețetele din catalog: piețele dovedite slabe (corecție sub LIFT_DROP) au ieșit deja
        # din candidați (apply_lift), deci rămân doar cele neutre sau peste cotă. Altfel, cu o singură piață pe val, ziua avea un bilet.
        have_names = {s[0] for s in specs}
        specs += [t for t in TICKETS if t[0] not in have_names and t[0] != "Mix Supersocial"]
    if STIL_COMPACT:
        allowed = positive_keys(conn)
        rep["allowed_keys"] = allowed
        specs = stil_specs(specs, allowed)
        specs += [(n, tuple(k for k in allowed if k not in STIL_BANNED), lo, hi, "p", (1.15, 2.20)) for n, _b, lo, hi in STIL_TIERS]
    stale = _stale_tickets(conn, today, cands, now)
    if stale:
        with conn:
            conn.executemany("UPDATE ticket SET status='replaced' WHERE id=?", [(i,) for i, _ in stale])
        existing -= {n for _, n in stale}
        rep["stale_replaced"] = len(stale)
    # O schimbare în lista „pe val” nu mai reface biletele: rezultatele noi o mișcă aproape la fiecare rulare, iar
    # biletele se schimbau din oră în oră (notificări „bilete noi” repetate, bilete jucate care dispăreau din listă).
    # Un bilet se reface doar dacă o selecție a lui a ajuns clar sub cotă (_stale_tickets) sau cota iese din bandă.
    obsolete = existing - {s[0] for s in specs} if hot else set()
    if obsolete:  # rețete care nu mai există azi: se înlocuiesc doar biletele lor încă neîncepute, nu toate
        start = canon_utc(now.isoformat())
        with conn:
            for t in conn.execute("SELECT id, notes FROM ticket WHERE day=? AND variant=? AND status='pending'",
                                  (today.isoformat(), VARIANT)).fetchall():
                if json.loads(t["notes"] or "{}").get("stil") not in obsolete:
                    continue
                if conn.execute("""SELECT 1 FROM ticket_leg tl JOIN match m ON m.id=tl.match_id
                                   WHERE tl.ticket_id=? AND m.kickoff_utc <= ?""", (t["id"], start)).fetchone():
                    continue
                conn.execute("UPDATE ticket SET status='replaced' WHERE id=?", (t["id"],))
        existing = {json.loads(r[0] or "{}").get("stil") for r in conn.execute(
            "SELECT notes FROM ticket WHERE day=? AND variant=? AND status!='replaced'", (today.isoformat(), VARIANT))}
    if not replace and _odds_outside(conn, today):
        replace = True
    if STIL_COMPACT and not replace and conn.execute(
            """SELECT 1 FROM ticket t WHERE t.day=? AND t.variant=? AND t.status='pending'
               AND (SELECT COUNT(*) FROM ticket_leg tl WHERE tl.ticket_id=t.id) > ?
               AND COALESCE(json_extract(t.notes, '$.stil'), '') NOT LIKE 'Stil %+%'""",
            (today.isoformat(), VARIANT, STIL_LEGS[1] + BOOST_PER_TICKET)).fetchone():
        replace = True  # bilete vechi de 10–22 selecții: se refac cele neîncepute pe regula 3–6
    # un slip lipsă se adaugă lângă cele existente (mai jos), fără să le înlocuiască pe toate
    if have and not replace and all(t[0] in existing for t in specs) and (not STIL_COMPACT or CHAIN_NAME in existing):
        rep["skipped_existing"] = True
        rep["wave"] = hot
        return rep
    skip_names = set() if replace else set(existing)
    rep["candidates"] = len(cands)
    rep["wave"] = hot
    rep["lift"] = {k: v["lift"] for k, v in lift.items() if v["n"] >= LIFT_MIN_N}
    used_match: Dict[int, int] = {}
    used_sel: set = set()
    made = []
    boosts = _boost_pool(conn, now)
    used_boost: set = set()
    with conn:
        if have and replace:
            # se refac doar biletele fără niciun meci început: unul aflat în joc nu dispare de sub ochii celui care l-a jucat
            conn.execute("""UPDATE ticket SET status='replaced' WHERE day=? AND variant=? AND status='pending'
                            AND NOT EXISTS (SELECT 1 FROM ticket_leg tl JOIN match m ON m.id=tl.match_id
                                            WHERE tl.ticket_id=ticket.id AND m.kickoff_utc <= ?)""",
                         (today.isoformat(), VARIANT, canon_utc(now.isoformat())))
            for r in conn.execute("SELECT notes FROM ticket WHERE day=? AND variant=? AND status='pending'", (today.isoformat(), VARIANT)):
                skip_names.add(json.loads(r[0] or "{}").get("stil"))
        # selecțiile biletelor de azi rămase (publicate sau aflate în joc) contează la controlul suprapunerii
        for r in conn.execute("""SELECT tl.match_id, tl.selection FROM ticket_leg tl JOIN ticket t ON t.id=tl.ticket_id
                                 WHERE t.day=? AND t.variant=? AND t.status!='replaced'""", (today.isoformat(), VARIANT)):
            used_sel.add((r[0], r[1]))
            used_match[r[0]] = used_match.get(r[0], 0) + 1
        def _save(name: str, supers: bool, legs: List[Dict[str, Any]], boost: Optional[Dict[str, Any]], arm: Optional[str]) -> None:
            count = arm != "fără"  # geamănul repetă biletul original: nu ocupă locurile altor bilete pe meci
            total = math.prod(c["odds"] for c in legs) * (boost["price"] if boost else 1.0)
            p_model = math.prod(c.get("p_model", c["p"]) for c in legs) * (boost["p_fair"] if boost else 1.0)
            # șansa publicată: realistă, nu a modelului
            p = math.prod(realistic_p(c, lift) for c in legs) * (boost["p_fair"] if boost else 1.0)
            leg_p = {f"{c['match_id']}|{c['key']}": round(realistic_p(c, lift), 5) for c in legs}
            if boost:
                leg_p[f"{boost['match_id']}|{boost['label']}"] = round(boost["p_fair"], 5)
            n_all = len(legs) + (1 if boost else 0)
            n_est = sum(1 for c in legs if c.get("est"))
            notes = {"experimental": True, "paper": True, "risk_acknowledged": True, "stil": name, "wave": bool(hot),
                     "p_model": round(p_model, 6), "leg_p": leg_p,
                     **({"system_pick": n_all - 1} if n_all >= SYSTEM_MIN_LEGS else {}),
                     **({"boost_test": arm, "twin": arm == "fără"} if arm else {}),
                     **({"boost": {"label": boost["label"], "price": boost["price"], "ev": boost["ev"]}} if boost else {}),
                     "wave_keys": list(hot), "slip": "supersocial" if supers else "lung",
                     "label": ("Stil Supersocial" + (TWIN_SUFFIX if arm == "fără" else "")) if supers else f"Stil Supersocial · {name}",
                     "reasons": [f"Stil Supersocial · {name} · {n_all} selecții din 7 zile, cotă {total:.0f}."
                                 + (f" Include o cotă mărită Superbet cu EV {boost['ev']:+.0%} în locul celor mai slabe selecții." if boost else ""),
                                 (f"Amestec din toate piețele: cele mai sigure selecții după model și cota Superbet împreună, fiecare cu avantaj de cel puțin "
                                  f"{BEST_MIN_EDGE:.0%}, cel mult {BEST_PER_KEY} din aceeași piață, un meci o singură dată."
                                  if name.startswith(BEST_NAME) else
                                  "Cotă de la 20 în sus. Selecțiile sunt din piețele pe val; avantajul poate fi ușor negativ, altfel biletul rămâne la cotă 4."),
                                 f"Șansă realistă {p:.2%} · EV {p * total - 1:+.0%} (din cote, corectate cu rezultatele reale pe piață). "
                                 f"Modelul singur ar spune {p_model:.2%}.",
                                 f"Paper. Miza {STAKE_U:.2f}u."
                                 + (" Bet Builder e estimat, nu e prețul copiat." if n_est else "")]}
            cur = conn.execute(
                """INSERT INTO ticket (kind, variant, created_by, target_odds, total_odds, p_ticket, ev, stake, status, created_at, notes, day)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (KIND, VARIANT, "robot", round(total, 2), round(total, 2), round(p, 6), round(p * total - 1, 4), STAKE_U, "pending",
                 repo.now_iso(), json.dumps(notes, ensure_ascii=False), today.isoformat()))
            for c in sorted(legs, key=lambda c: c["kickoff_utc"]):
                conn.execute("INSERT INTO ticket_leg (ticket_id, prediction_id, match_id, market, selection, odds, odds_source) VALUES (?,?,?,?,?,?,?)",
                             (cur.lastrowid, None, c["match_id"], "ss|0", c["key"], c["odds"], "bb_est" if c.get("est") else "superbet"))
                if count:
                    used_sel.add((c["match_id"], c["key"]))
                    used_match[c["match_id"]] = used_match.get(c["match_id"], 0) + 1
            if boost:
                conn.execute("INSERT INTO ticket_leg (ticket_id, prediction_id, match_id, market, selection, odds, odds_source) VALUES (?,?,?,?,?,?,?)",
                             (cur.lastrowid, None, boost["match_id"], "boost|0", boost["label"], boost["price"], "superbet"))
                used_boost.add((boost["match_id"], boost["label"]))
                used_match[boost["match_id"]] = used_match.get(boost["match_id"], 0) + 1
            made.append({"name": name, "legs": n_all, "boost": bool(boost), "odds": round(total, 2), "p": round(p, 5), "ev": round(p * total - 1, 3),
                         "ev_model": round(p_model * total - 1, 3)})

        for name, keys, lo_n, hi_n, _order, band in specs:
            if name in skip_names:
                continue
            supers = name == "Supersocial"
            pool = _priced_pool(cands, keys, band, _floor(name))
            pool = [c for c in pool if (c["match_id"], c["key"]) not in used_sel and used_match.get(c["match_id"], 0) < MAX_TICKETS_PER_MATCH]
            cap = None if name in TIER_NAMES else _key_cap(keys)  # treptele mari: fără limită pe piață (un meci tot o singură dată)
            odds_band = _odds_band(name)
            legs = None
            best = name.startswith(BEST_NAME)

            def _make(src, fam=BEST_PER_FAMILY if best else None):
                for league_cap in (2, MAX_PER_LEAGUE):
                    got = _assemble(_by_green(src), lo_n, hi_n, cap, odds_band[0], odds_band[1], league_cap,
                                    fam, efficient=best or name in HIST_FLOOR or name in TIER_NAMES)
                    if got:
                        return got
                return None

            legs = None
            if name in TIER_NAMES and name != CHAIN_NAME and STIL_TIER_EV_FIRST:
                gkeys = tuple(sorted({c["key"] for c in cands if c["key"] not in STIL_BANNED}))
                epool = [c for c in _priced_pool(cands, gkeys, band, None)
                         if (c["match_id"], c["key"]) not in used_sel and used_match.get(c["match_id"], 0) < MAX_TICKETS_PER_MATCH
                         and 0 <= (c.get("p", 0) * c.get("odds", 0) - 1) <= EDGE_SUSPECT]
                legs = _make(epool)
                if legs:
                    rep.setdefault("tier_ev_first", []).append(name)
            if not legs:
                legs = _make(pool)
            if (not legs or _ticket_ev(legs, lift) < MIN_TICKET_EV) and best:
                # alegerea robotului: a doua încercare doar cu piețele dovedite pe rezultatele reale; acolo limita pe
                # familie nu mai e nevoie (protejează de un model greșit, iar aici decid rezultatele reale), rămâne
                # limita de 3 pe piață
                legs = _make([c for c in pool if proven(c["key"], lift)], None)
            if not legs and name in TIER_NAMES and name != CHAIN_NAME and STIL_TIER_GLOBAL:
                # treptele 100+/500+/1000+: dacă piețele pe plus nu ajung la cotă, se scanează toată oferta cotată
                # (toate piețele cu model: goluri, reprize, cornere, cartonașe, BB), tot cu EV suspect exclus
                gkeys = tuple(sorted({c["key"] for c in cands if c["key"] not in STIL_BANNED}))
                gpool = [c for c in _priced_pool(cands, gkeys, band, None)
                         if (c["match_id"], c["key"]) not in used_sel and used_match.get(c["match_id"], 0) < MAX_TICKETS_PER_MATCH
                         and (c.get("p", 0) * c.get("odds", 0) - 1) <= EDGE_SUSPECT]
                legs = _make(gpool)
                if legs:
                    rep.setdefault("tier_global", []).append(name)
            if not legs:
                continue
            if _ticket_ev(legs, lift) < MIN_TICKET_EV and name not in HIST_FLOOR and name not in TIER_NAMES:
                rep.setdefault("skipped_ev", []).append({"name": name, "ev": round(_ticket_ev(legs, lift), 3)})
                continue  # după cote (corectate cu rezultatele reale) biletul pierde clar: nu se publică
            legs0 = list(legs)
            boost = None
            if boosts and BOOST_PER_TICKET:
                legs, boost = _with_boost(legs, boosts, used_boost, used_match, lo_n, odds_band)
            _save(name, supers, legs, boost, "cu" if boost and BOOST_TWIN else None)
            if boost and BOOST_TWIN and f"{name}{TWIN_SUFFIX}" not in skip_names:
                # geamănul: același bilet fără cota mărită (selecțiile de dinainte de înlocuire), ca să se vadă care merge
                _save(f"{name}{TWIN_SUFFIX}", supers, legs0, None, "fără")
        if STIL_COMPACT and CHAIN_NAME not in skip_names:
            pool = [c for c in _priced_pool(cands, tuple(allowed), (1.15, 2.20), None)
                    if (c["match_id"], c["key"]) not in used_sel and used_match.get(c["match_id"], 0) < MAX_TICKETS_PER_MATCH]
            steps = build_chain(pool, now)
            if steps:
                _save(CHAIN_NAME, False, [c for st in steps for c in st], None, None)
                tid = conn.execute("SELECT MAX(id) FROM ticket").fetchone()[0]
                notes = json.loads(conn.execute("SELECT notes FROM ticket WHERE id=?", (tid,)).fetchone()[0])
                desc = [f"Treapta {i + 1}: " + ", ".join(f"{c['home']}–{c['away']} {label(c['key'])} @{c['odds']:.2f}" for c in st)
                        + f" · cotă {_prod(st):.2f}" for i, st in enumerate(steps)]
                notes["chain"] = [[f"{c['match_id']}|{c['key']}" for c in st] for st in steps]
                notes["reasons"] = [f"Lanț pe ore: {len(steps)} bilete mici unul după altul; tot câștigul unei trepte intră ca miză în "
                                    f"următoarea. O singură miză, cotă totală {math.prod(_prod(st) for st in steps):.0f}. "
                                    "Te poți opri după orice treaptă câștigată (încasezi ce ai)."] + desc + notes["reasons"][2:]
                conn.execute("UPDATE ticket SET notes=? WHERE id=?", (json.dumps(notes, ensure_ascii=False), tid))
    rep["tickets"] = made
    return rep


def won(sel: str, r: Dict[str, Any]) -> bool:
    if is_robot(sel):
        from betpredict.robot.markets import settle_selection

        _, market, line, s = sel.split(":")
        return settle_selection(market, float(line), s, r["fthg"], r["ftag"]) == "won"
    if sel in CARD_KEYS:
        yh, ya = r["yh"], r["ya"]
        y = yh + ya
        return {"YC35": y > 3, "YC45": y > 4, "YCU45": y <= 4, "YCU55": y <= 5, "BOTH15": yh >= 2 and ya >= 2,
                "HY15": yh >= 2, "AY15": ya >= 2, "HY25": yh >= 3, "AY25": ya >= 3}[sel]
    if sel in ("HG13", "AG13", "BB_HG13_U35", "BB_AG13_U35", "BB_HG14_U45", "BB_AG14_U45"):
        g = r["fthg"] if sel in ("HG13", "BB_HG13_U35", "BB_HG14_U45") else r["ftag"]
        hi = 4 if "14" in sel else 3
        return 1 <= g <= hi and (not sel.startswith("BB_") or r["hthg"] + r["htag"] <= hi)
    if sel in ("HO05", "HO15", "AO05", "AO15"):
        g = r["fthg"] if sel[0] == "H" else r["ftag"]
        return g > (0 if sel.endswith("05") else 1)
    if sel == "BB_C65_U145":
        t = (r.get("hc") or 0) + (r.get("ac") or 0)
        return 7 <= t <= 14
    if sel == "BB_H1C25_U65":
        t = (r.get("hc1") or 0) + (r.get("ac1") or 0)
        return 3 <= t <= 6
    if sel == "BB_H13x2_O15":
        return _won("H13x2", r)
    if sel == "CU145":
        return r["hc"] + r["ac"] <= 14
    if sel in ("H1U65", "H1CLT5", "H1C56", "H1C7P"):
        t = r["hc1"] + r["ac1"]
        return {"H1U65": t <= 6, "H1CLT5": t <= 4, "H1C56": 5 <= t <= 6, "H1C7P": t >= 7}[sel]
    if sel in CORNER_KEYS:
        if sel.startswith("H1C"):
            return r["hc1"] + r["ac1"] > {"H1C25": 2, "H1C35": 3}[sel]
        return r["hc"] + r["ac"] > {"C65": 6, "C75": 7, "C85": 8, "C95": 9}[sel]
    return _won(sel, r)


def today_doc(conn: sqlite3.Connection, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Predicții pe piețele Stil Supersocial: șansa modelului vs prețul Superbet (EV), pentru toate meciurile cu ofertă."""
    now = now or datetime.now(timezone.utc)
    rows = []
    for c in calibrate_cards(candidates(conn, now, 36), card_calibration(conn)):
        fair = round(1 / c["p"], 2) if c["p"] > 0 else None
        rows.append({**c, "label": label(c["key"]), "p": round(c["p"], 4), "fair_odds": fair,
                     "edge": None if c["edge"] is None else round(c["edge"], 4), "bb": c["key"] in BB_KEYS,
                     "group": GROUP.get(c["key"], "altele"), "suspect": bool(c.get("odds") and suspect(c))})
    rows.sort(key=lambda r: -r["p"])
    return {"generated_at": canon_utc(now.isoformat()), "count": len(rows), "matches": len({r["match_id"] for r in rows}),
            "note": "Intervalul 3-6 la cornere pe prima repriză nu e în oferta publică. Superbet are «Prima repriză - Interval cornere»: <5, 5-6, 7+. Cota 3-6 e estimată din Peste 2.5 și Sub 6.5.",
            "rows": rows}


GEN_MIN_ODDS, GEN_MIN_P = 1.03, 0.35


def generator_doc(conn: sqlite3.Connection, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Selecțiile Stil pentru generatorul din aplicație (următoarele 3 zile), compact: șansa realistă, cota Superbet,
    grupa și piața Superbet (cu id-uri), ca biletul generat să se deschidă precompletat."""
    from betpredict.publish.outputs import _sb_pick

    now = now or datetime.now(timezone.utc)
    lift = key_lift(conn)
    names_by: Dict[int, Dict[str, Any]] = {}
    rows = []
    for c in candidates(conn, now, 72):
        if is_robot(c["key"]) or not c.get("odds") or c["odds"] < GEN_MIN_ODDS:
            continue
        p = realistic_p(c, lift)
        if p < GEN_MIN_P:
            continue
        if c["match_id"] not in names_by:
            names_by[c["match_id"]] = offer_now(conn, c["match_id"], c["home"], c["away"], names=True)
        nm = names_by[c["match_id"]]
        r: Dict[str, Any] = {"m": c["match_id"], "k": c["key"], "g": GROUP.get(c["key"], "altele"),
                             "p": round(p, 4), "o": c["odds"], **({"e": 1} if c.get("est") else {})}
        if c["key"] in BB_KEYS:
            steps = [nm.get(k) for k in bb_legs(c["key"])]
            if all(steps):
                r["bs"] = [f"{m}: {o}" for m, o in steps]
                r["bp"] = [_sb_pick(conn, c["match_id"], m, o) for m, o in steps]
        elif c["key"] in nm:
            r["pk"] = _sb_pick(conn, c["match_id"], *nm[c["key"]])
        rows.append(r)
    return {"generated_at": canon_utc(now.isoformat()), "labels": {k: label(k) for k in {r["k"] for r in rows}}, "rows": rows}


def corners_consistent(m: Any) -> bool:
    """Cornerele din prima repriză nu pot depăși totalul pe meci (pe echipă). Fără total pe meci nu avem cu ce compara."""
    ft_h, ft_a, ht_h, ht_a = m["corners_home"], m["corners_away"], m["corners_ht_home"], m["corners_ht_away"]
    if None in (ft_h, ft_a, ht_h, ht_a):
        return True
    return ht_h <= ft_h and ht_a <= ft_a


BAD_CORNERS_SQL = """m.corners_home IS NOT NULL AND m.corners_ht_home IS NOT NULL
                     AND (m.corners_ht_home > m.corners_home OR m.corners_ht_away > m.corners_away)"""


def _settle_result(sel: str, m: Any, too_old: str) -> Optional[str]:
    """won / lost / void, sau None dacă încă nu se poate deconta (meci neterminat, cornere lipsă)."""
    from betpredict.ingest.normalize import VOID_STATUSES

    if m["status"] in VOID_STATUSES:
        return "void"
    if m["status"] != "finished" or m["ft_home"] is None or m["ht_home"] is None:
        return None
    if is_robot(sel) and sel.startswith("R:draw_no_bet:") and m["ft_home"] is not None and m["ft_home"] == m["ft_away"] \
            and m["status"] == "finished":
        return "void"  # egal = pariu returnat
    need_ht = sel.startswith("H1C") or sel in ("BB_H1C25_U65", "H1U65")
    need_ft = sel in CORNER_KEYS or sel in ("BB_C65_U145", "CU145")
    if (need_ft and (m["corners_home"] is None or m["corners_away"] is None)) or (need_ht and (m["corners_ht_home"] is None or m["corners_ht_away"] is None)):
        return "void" if m["kickoff_utc"] < too_old else None  # după 4 zile fără cornere: anulat
    if sel in CARD_KEYS and (m["cards_home"] is None or m["cards_away"] is None):
        return "void" if m["kickoff_utc"] < too_old else None  # după 4 zile fără cartonașe: anulat
    if need_ht and not corners_consistent(m):
        return "void" if m["kickoff_utc"] < too_old else None  # date de cornere contradictorii: nu învățăm din ele
    r = {"fthg": m["ft_home"], "ftag": m["ft_away"], "hthg": m["ht_home"], "htag": m["ht_away"],
         "hc": m["corners_home"], "ac": m["corners_away"], "hc1": m["corners_ht_home"], "ac1": m["corners_ht_away"],
         "yh": m["cards_home"], "ya": m["cards_away"]}
    return "won" if won(sel, r) else "lost"


def settle_track(conn: sqlite3.Connection) -> int:
    """Decontează selecțiile urmărite (``ss_track``) cu aceleași reguli ca biletele."""
    from betpredict.ingest.corners import ensure as ensure_corners

    ensure_corners(conn)
    from betpredict.ingest.cards import ensure as ensure_cards

    ensure_cards(conn)
    _ensure_track(conn)
    too_old = canon_utc((datetime.now(timezone.utc) - timedelta(days=4)).isoformat())
    # rezultate deja trecute din date de cornere contradictorii: le refacem cu regula de mai jos (devin anulate)
    conn.execute(f"""UPDATE ss_track SET result=NULL WHERE result IN ('won','lost')
                     AND (mkey LIKE 'H1C%' OR mkey IN ('H1U65', 'BB_H1C25_U65'))
                     AND match_id IN (SELECT m.id FROM match m WHERE {BAD_CORNERS_SQL})""")
    n = 0
    for l in conn.execute(
            """SELECT s.match_id, s.mkey, m.status, m.ft_home, m.ft_away, m.ht_home, m.ht_away, m.corners_home, m.corners_away,
                      m.corners_ht_home, m.corners_ht_away, m.cards_home, m.cards_away, m.kickoff_utc
               FROM ss_track s JOIN match m ON m.id = s.match_id WHERE s.result IS NULL""").fetchall():
        try:
            res = _settle_result(l["mkey"], l, too_old)
        except (KeyError, TypeError):
            res = None  # piață fără regulă de decontare: rămâne nedecontată
        if res is None:
            continue
        conn.execute("UPDATE ss_track SET result=? WHERE match_id=? AND mkey=?", (res, l["match_id"], l["mkey"]))
        n += 1
    return n


def settle_legs(conn: sqlite3.Connection) -> int:
    """Decontare reală a selecțiilor Stil Supersocial din scorul final + pauză (void la meci anulat/amânat)."""
    from betpredict.ingest.normalize import VOID_STATUSES

    from betpredict.ingest.corners import ensure as ensure_corners

    ensure_corners(conn)
    from betpredict.ingest.cards import ensure as ensure_cards

    ensure_cards(conn)
    too_old = canon_utc((datetime.now(timezone.utc) - timedelta(days=4)).isoformat())
    n = 0
    for l in conn.execute(
            """SELECT tl.rowid rid, tl.selection, m.status, m.ft_home, m.ft_away, m.ht_home, m.ht_away, m.corners_home, m.corners_away,
                      m.corners_ht_home, m.corners_ht_away, m.cards_home, m.cards_away, m.kickoff_utc
               FROM ticket_leg tl JOIN match m ON m.id = tl.match_id WHERE tl.market='ss|0' AND tl.result IS NULL""").fetchall():
        if l["status"] in VOID_STATUSES:
            res = "void"
        else:
            try:
                res = _settle_result(l["selection"], l, too_old)
            except (KeyError, TypeError):
                res = None
            if res is None:
                continue
        conn.execute("UPDATE ticket_leg SET result=? WHERE rowid=?", (res, l["rid"]))
        n += 1
    return n


def key_lift(conn: sqlite3.Connection) -> Dict[str, Dict[str, float]]:
    """Pe piață: câștigate reale ÷ câștigate promise de cotă (Σ 1/cotă), micșorat spre LIFT_PRIOR.
    1.10 = intră cu 10% mai des decât spune cota; 0.90 = mai rar. Fiecare meci × piață contează o singură dată."""
    from betpredict.ingest.corners import ensure as ensure_corners

    ensure_corners(conn)
    _ensure_track(conn)
    # toate selecțiile urmărite (preț Superbet real) + selecțiile de pe bilete care nu sunt în urmărire (ex. Bet Builder estimat)
    rows = conn.execute("""SELECT selection, COUNT(*) n, SUM(w) w, SUM(1.0 / o) e, COUNT(DISTINCT d) days FROM (
                             SELECT match_id, mkey AS selection, result='won' AS w, odds AS o, substr(kickoff_utc, 1, 10) AS d FROM ss_track
                             WHERE result IN ('won','lost') AND odds > 1
                             UNION ALL
                             SELECT tl.match_id, tl.selection, MAX(tl.result='won'), AVG(tl.odds),
                                    (SELECT substr(m.kickoff_utc, 1, 10) FROM match m WHERE m.id = tl.match_id) FROM ticket_leg tl
                             WHERE tl.market='ss|0' AND tl.result IN ('won','lost') AND tl.odds > 1
                               AND NOT EXISTS (SELECT 1 FROM ss_track s WHERE s.match_id=tl.match_id AND s.mkey=tl.selection AND s.result IN ('won','lost'))
                               AND NOT ((tl.selection LIKE 'H1C%' OR tl.selection IN ('H1U65', 'BB_H1C25_U65'))
                                        AND tl.match_id IN (SELECT m.id FROM match m WHERE """ + BAD_CORNERS_SQL + """))
                             GROUP BY tl.match_id, tl.selection)
                           GROUP BY selection""").fetchall()
    out: Dict[str, Dict[str, float]] = {}
    for r in rows:
        n, w, e = r[1], r[2] or 0, r[3] or 0.0
        if not n or e <= 0:
            continue
        # rezultatele din aceeași zi nu sunt independente (o zi cu multe goluri ridică toate piețele de goluri):
        # cel mult LIFT_PER_DAY rezultate „cântăresc” pe zi, restul doar confirmă proporția
        n_eff = min(n, LIFT_PER_DAY * max(1, r[4] or 1))
        if n_eff < n:
            k = n_eff / n
            n, w, e = n_eff, w * k, e * k
        m = e / n  # șansa medie promisă de cotă
        lift = (w + LIFT_K * LIFT_PRIOR * m) / (e + LIFT_K * m)
        h = w / n
        se = math.sqrt(max(h * (1 - h), 0.01) / (n + LIFT_K)) / m  # eroarea standard a raportului (aproximativ)
        out[r[0]] = {"n": n, "hit": round(h, 3), "implied": round(m, 3), "lift": round(lift, 3), "se": round(se, 3)}
    # CLV: prețul când l-am văzut prima dată ÷ prețul de la start − 1. Pozitiv = piața a ajuns la noi (cota a scăzut).
    # Apare înainte de rezultat, deci arată mai repede dacă piața e prețuită greșit.
    for k, n, clv in conn.execute("""SELECT mkey, COUNT(*), AVG(odds_first / odds - 1) FROM ss_track
                                     WHERE odds_first IS NOT NULL AND odds > 1 AND kickoff_utc <= ? GROUP BY mkey""",
                                  (canon_utc(datetime.now(timezone.utc).isoformat()),)):
        out.setdefault(k, {"n": 0, "hit": 0.0, "implied": 0.0, "lift": LIFT_PRIOR}).update({"clv_n": n, "clv": round(clv, 4)})
    return out


MARGIN = 1.05  # marja tipică Superbet pe aceste piețe: șansa corectă ≈ (1/cotă) / 1.05


def realistic_p(c: Dict[str, Any], lift: Dict[str, Dict[str, float]]) -> float:
    """Șansa realistă a unei selecții: cota fără marjă × corecția învățată pe piață (dacă are destule rezultate).
    Nu folosește modelul: biletul alege tocmai selecțiile unde modelul vede mai mult decât cota, deci erorile lui
    s-ar înmulți pe 10–20 de selecții (EV „model” de +100% pe bilete cu 1–3% șanse)."""
    base = (1.0 / c["odds"]) / MARGIN
    lf = lift.get(c["key"])
    if lf and lf["n"] >= LIFT_MIN_N:
        # prudent: peste 1 se ia marginea de jos (corecție − 2 erori standard, ~95%), pentru că pe un bilet de 10–20
        # selecții din aceeași piață o corecție supraestimată se înmulțește (R1O15: 1.11 pe 45 de rezultate → „16% la cota 21”)
        lv = lf["lift"] if lf["lift"] <= 1 else max(1.0, lf["lift"] - 2 * lf.get("se", 0.0))
        base *= lv / LIFT_PRIOR
    return min(0.99, base * (c.get("league_f") or 1.0))


def refresh_pending(conn: sqlite3.Connection, lift: Dict[str, Dict[str, float]]) -> int:
    """Recalculează șansa și EV-ul afișate ale biletelor Stil încă în joc, cu regula de acum (cotă fără marjă ×
    corecția prudentă). Selecțiile, cotele și miza nu se ating: se schimbă doar estimarea arătată."""
    n = 0
    with conn:
        for t in conn.execute("SELECT id, total_odds, notes FROM ticket WHERE variant=? AND status='pending'", (VARIANT,)).fetchall():
            legs = conn.execute("SELECT match_id, market, selection, odds FROM ticket_leg WHERE ticket_id=?", (t["id"],)).fetchall()
            if not legs or any(not l["odds"] or l["odds"] <= 1 for l in legs):
                continue
            try:
                notes = json.loads(t["notes"] or "{}")
            except ValueError:
                notes = {}
            lp = notes.get("leg_p") or {}
            p = math.prod((lp.get(f"{l['match_id']}|{l['selection']}") or 1 / l["odds"]) if l["market"] == "boost|0"
                          else realistic_p({"key": l["selection"], "odds": l["odds"]}, lift) for l in legs)
            total = t["total_odds"]
            rs = notes.get("reasons") or []
            pm = notes.get("p_model")
            line = (f"Șansă realistă {p:.2%} · EV {p * total - 1:+.0%} (din cote, corectate cu rezultatele reale pe piață)."
                    + (f" Modelul singur ar spune {pm:.2%}." if pm else ""))
            if len(rs) >= 3:
                rs[2] = line
                notes["reasons"] = rs
            conn.execute("UPDATE ticket SET p_ticket=?, ev=?, notes=? WHERE id=?",
                         (round(p, 6), round(p * total - 1, 4), json.dumps(notes, ensure_ascii=False), t["id"]))
            n += 1
    return n


# Corecția pe piață × ligă: cât intră piața într-o ligă față de cum intră peste tot. Micșorată puternic spre 1 (LEAGUE_K
# câștiguri „fictive” la medie), folosită doar de la LEAGUE_MIN_N rezultate și plafonată: cu puține date nu schimbă nimic.
LEAGUE_K = 30.0
LEAGUE_MIN_N = 30
LEAGUE_CAP = (0.85, 1.15)


def league_lift(conn: sqlite3.Connection, lift: Dict[str, Dict[str, float]]) -> Dict[Tuple[str, Any], Tuple[float, int]]:
    _ensure_track(conn)
    out: Dict[Tuple[str, Any], Tuple[float, int]] = {}
    try:
        rows = conn.execute("""SELECT s.mkey, m.league_id, COUNT(*) n, SUM(s.result='won') w, SUM(1.0 / s.odds) e
                               FROM ss_track s JOIN match m ON m.id=s.match_id
                               WHERE s.result IN ('won','lost') AND s.odds > 1 AND m.league_id IS NOT NULL
                               GROUP BY s.mkey, m.league_id""").fetchall()
    except sqlite3.OperationalError:
        return out
    for k, lg, n, w, e in rows:
        if n < LEAGUE_MIN_N or not e:
            continue
        exp = e * ((lift.get(k) or {}).get("lift") or LIFT_PRIOR)  # câștigate dacă liga ar fi ca piața peste tot
        f = ((w or 0) + LEAGUE_K) / (exp + LEAGUE_K)
        out[(k, lg)] = (max(LEAGUE_CAP[0], min(LEAGUE_CAP[1], f)), n)
    return out


def apply_lift(cands: List[Dict[str, Any]], lift: Dict[str, Dict[str, float]],
               league: Optional[Dict[Tuple[str, Any], Tuple[float, int]]] = None) -> List[Dict[str, Any]]:
    """Șansa folosită la bilete = șansa modelului × corecția pieței (× corecția pe ligă, dacă are destule rezultate).
    Piețele cu destule rezultate și sub LIFT_DROP ies."""
    out = []
    for c in cands:
        lf = lift.get(c["key"])
        if lf and lf["n"] >= LIFT_MIN_N:
            if lf["lift"] < LIFT_DROP:
                continue
            p = min(0.99, c["p"] * lf["lift"])
            c = {**c, "p_model": c["p"], "p": p, "lift": lf["lift"], "edge": p * c["odds"] - 1 if c.get("odds") else c.get("edge")}
        lg = (league or {}).get((c["key"], c.get("league_id")))
        if lg:
            p = min(0.99, c["p"] * lg[0])
            c = {**c, "p": p, "league_f": lg[0], "edge": p * c["odds"] - 1 if c.get("odds") else c.get("edge")}
        out.append(c)
    return out


def live_stats(conn: sqlite3.Connection) -> Dict[str, Any]:
    out: Dict[str, Dict[str, Any]] = {}
    for t in conn.execute("SELECT status, stake, payout, notes FROM ticket WHERE variant=? AND status!='replaced'", (VARIANT,)):
        name = json.loads(t["notes"] or "{}").get("stil", "?")
        r = out.setdefault(name, {"n": 0, "won": 0, "lost": 0, "pending": 0, "staked_u": 0.0, "profit_u": 0.0})
        r["n"] += 1
        st = t["status"] if t["status"] in ("won", "lost") else "pending"
        r[st] += 1
        if st != "pending":
            r["staked_u"] = round(r["staked_u"] + (t["stake"] or 0), 2)
            r["profit_u"] = round(r["profit_u"] + (t["payout"] or 0) - (t["stake"] or 0), 2)
    # o selecție (meci × piață) pusă pe mai multe bilete e un singur rezultat, nu câte unul pe bilet
    legs = conn.execute("""SELECT selection, COUNT(*) n, SUM(w) w, AVG(o) o FROM (
                             SELECT match_id, selection, MAX(result='won') w, AVG(odds) o FROM ticket_leg
                             WHERE market='ss|0' AND result IN ('won','lost') GROUP BY match_id, selection)
                           GROUP BY selection""").fetchall()
    legs = {r["selection"]: {"n": r["n"], "won": r["w"], "hit": round(r["w"] / r["n"], 3), "avg_odds": round(r["o"], 2),
                             "roi_single": round(r["w"] / r["n"] * r["o"] - 1, 3)} for r in legs}
    hot = wave_keys(legs)
    return {"tickets": out, "legs": legs, "lift": key_lift(conn), "lift_min_n": LIFT_MIN_N, "lift_drop": LIFT_DROP,
            "wave": [{"key": k, "label": label(k), **legs[k]} for k in hot],
            "wave_min_n": WAVE_MIN_N, "wave_min_roi": WAVE_MIN_ROI}


def history_doc(conn: sqlite3.Connection, days: int = 14, now: Optional[datetime] = None, top: int = 40) -> Dict[str, Any]:
    """Istoricul selecțiilor Supersocial urmărite, pe zile (ora României): totaluri, pe piață și cele mai sigure
    selecții cu rezultatul. ROI la 1 unitate pe selecție, la ultimul preț Superbet dinainte de start."""
    from betpredict.timeutil import ro_date_of

    _ensure_track(conn)
    now = now or datetime.now(timezone.utc)
    lo = canon_utc((now - timedelta(days=days + 1)).isoformat())
    rows = conn.execute(
        """SELECT s.match_id, s.mkey, s.kickoff_utc, s.p, s.odds, s.result, m.home_name, m.away_name, m.ft_home, m.ft_away,
                  m.corners_home, m.corners_away
           FROM ss_track s JOIN match m ON m.id = s.match_id WHERE s.kickoff_utc >= ? AND s.kickoff_utc <= ?""",
        (lo, canon_utc(now.isoformat()))).fetchall()
    by_day: Dict[str, List[Any]] = {}
    for r in rows:
        d = ro_date_of(r["kickoff_utc"])
        if d:
            by_day.setdefault(d.isoformat(), []).append(r)

    def agg(rs: Sequence[Any]) -> Dict[str, Any]:
        st = [r for r in rs if r["result"] in ("won", "lost")]
        w = sum(1 for r in st if r["result"] == "won")
        prof = sum((r["odds"] - 1) if r["result"] == "won" else -1.0 for r in st)
        return {"n": len(rs), "won": w, "lost": len(st) - w, "void": sum(1 for r in rs if r["result"] == "void"),
                "pending": sum(1 for r in rs if r["result"] is None),
                "win_rate": round(w / len(st), 4) if st else None,
                "implied": round(sum(1 / r["odds"] for r in st) / len(st), 4) if st else None,
                "roi": round(prof / len(st), 4) if st else None}

    out = []
    for d in sorted(by_day, reverse=True)[:days]:
        rs = by_day[d]
        keys: Dict[str, List[Any]] = {}
        for r in rs:
            keys.setdefault(r["mkey"], []).append(r)
        best = sorted([r for r in rs if r["result"] in ("won", "lost", "void")], key=lambda r: -r["p"])[:top]
        out.append({
            "date": d, **agg(rs),
            "markets": sorted(({"key": k, "label": label(k), **agg(v)} for k, v in keys.items()), key=lambda x: -x["n"]),
            "top": [{"match_id": r["match_id"], "home": r["home_name"], "away": r["away_name"], "key": r["mkey"],
                     "label": label(r["mkey"]), "p": round(r["p"], 4), "odds": r["odds"], "result": r["result"],
                     "score": f"{r['ft_home']}-{r['ft_away']}" if r["ft_home"] is not None else None,
                     "corners": (r["corners_home"] + r["corners_away"]) if r["corners_home"] is not None and r["corners_away"] is not None else None}
                    for r in best],
        })
    return {"generated_at": canon_utc(now.isoformat()), "days": out}
