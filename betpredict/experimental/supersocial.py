"""„Stil Supersocial”: slipurile lui Stefan M. (Superbet), prețuri reale Superbet.

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
H1_SHARE = 0.446  # prior; h1_shares() îl înlocuiește cu frecvența măsurată
H1_PRIOR_N = 200.0
MIN_LEGS, MAX_LEGS = 10, 22
# Oferta din care alege: 7 zile. Cota finală 80–200. Se oprește la prima combinație validă,
# pentru că fiecare selecție în plus scade șansa ca biletul să iasă verde.
HORIZON_H = 24 * 7
ODDS_LO, ODDS_HI = 80.0, 200.0
ODDS_HI_HARD = ODDS_HI * 1.04
BAND = (1.20, 2.20)
MIN_EDGE = -0.08
MAX_TICKETS_PER_MATCH = 2
MAX_PER_LEAGUE = 4
MAX_PER_KEY = 5  # biletele cu mai mult de 2 piețe: cel mult 5 selecții din aceeași piață
# (nume piață Superbet, rezultat) → cheie
MARKETS: Dict[Tuple[str, str], str] = {
    ("Interval goluri", "2-4"): "G24", ("Interval goluri", "2-5"): "G25", ("Interval goluri", "1-3"): "G13",
    ("Gol marcat în ambele reprize", "Da"): "R1R2",
    ("Total goluri prima repriză & Total goluri a doua repriză", "Peste 0.5 & Peste 0.5"): "R1R2",
    ("Total goluri prima repriză & Total goluri", "Peste 0.5 & Peste 1.5"): "R1O15",
    ("Interval goluri în fiecare repriză", "1-3"): "H13x2",
    ("Total cornere", "Peste 6.5"): "C65", ("Total cornere", "Peste 7.5"): "C75",
    ("Total cornere", "Peste 8.5"): "C85", ("Total cornere", "Peste 9.5"): "C95",
    ("Prima repriză - Interval cornere", "3-6"): "BB_H1C25_U65", ("Prima repriză - Interval cornere", "3 - 6"): "BB_H1C25_U65",
    ("Interval cornere prima repriză", "3-6"): "BB_H1C25_U65",
    ("Prima repriză - Interval cornere", "<5"): "H1CLT5", ("Prima repriză - Interval cornere", "5-6"): "H1C56",
    ("Prima repriză - Interval cornere", "7+"): "H1C7P",
    ("Prima repriză - Total cornere", "Peste 2.5"): "H1C25", ("Prima repriză - Total cornere", "Peste 3.5"): "H1C35",
    ("Prima repriză - Total cornere", "Sub 6.5"): "H1U65",
    ("Total cornere", "Sub 14.5"): "CU145",
}
LABELS = {"G24": "Interval goluri 2-4", "G25": "Interval goluri 2-5", "G13": "Interval goluri 1-3",
          "R1R2": "Gol în fiecare repriză (R1 Peste 0.5 & R2 Peste 0.5)", "R1O15": "Combo R1 Peste 0.5 & meci Peste 1.5",
          "H13x2": "Interval 1-3 goluri în fiecare repriză",
          "C65": "Cornere Peste 6.5", "C75": "Cornere Peste 7.5", "C85": "Cornere Peste 8.5", "C95": "Cornere Peste 9.5",
          "H1C25": "R1 Cornere Peste 2.5", "H1C35": "R1 Cornere Peste 3.5",
          "H1CLT5": "R1 Cornere sub 5", "H1C56": "R1 Cornere 5-6", "H1C7P": "R1 Cornere 7+",
          "BB_C65_U145": "BB Cornere Peste 6.5 & Sub 14.5", "BB_H1C25_U65": "R1 Cornere interval 3-6",
          "BB_H13x2_O15": "BB 1-3 goluri în fiecare repriză & Peste 1.5"}
# grupe pentru filtrul Predicții (tip piață → sub-chipuri pe piață)
GROUP = {"H13x2": "reprize", "R1R2": "reprize", "BB_H13x2_O15": "reprize", "R1O15": "combo",
         "G13": "interval", "G24": "interval", "G25": "interval", "C65": "cornere", "C75": "cornere", "C85": "cornere",
         "C95": "cornere", "BB_C65_U145": "cornere", "H1C25": "r1_cornere", "H1C35": "r1_cornere",
         "H1CLT5": "r1_cornere", "H1C56": "r1_cornere", "H1C7P": "r1_cornere", "BB_H1C25_U65": "r1_cornere"}
CORNER_KEYS = ("C65", "C75", "C85", "C95", "H1C25", "H1C35")
BB_KEYS = ("BB_C65_U145", "BB_H1C25_U65", "BB_H13x2_O15")
BB_ANCHOR = {"BB_C65_U145": "C65", "BB_H1C25_U65": "H1C25", "BB_H13x2_O15": "H13x2"}
BIAS = {"R1R2": 0.018, "H13x2": 0.024, "R1O15": 0.012, "G24": 0.008, "G25": 0.009, "G13": 0.0}
# (nume, piețe, min, max, ordonare, banda) — slipurile lui Stefan, apoi intervalul 2–4/2–5
TICKETS = (
    ("Combo R1 0.5 & meci 1.5", ("R1O15",), 10, 12, "p", (1.15, 1.60)),
    ("Goluri 1–3", ("G13",), 10, 12, "edge", BAND),
    ("R1 cornere interval 3-6", ("BB_H1C25_U65",), 7, 12, "p", (1.30, 2.10)),
    ("Cornere 6.5/7.5", ("C65", "C75"), 10, 22, "p", (1.15, 1.45)),
    ("Cornere prima repriză", ("H1C25", "H1C35"), 10, 22, "p", (1.12, 1.60)),
    ("1–3 în fiecare repriză", ("H13x2",), 10, 22, "p", (1.65, 1.95)),
    ("Peste 0.5 ambele reprize", ("R1R2",), 10, 22, "p", (1.40, 1.65)),
    ("BB cornere 6.5 și sub 14.5", ("BB_C65_U145",), 10, 22, "p", (1.20, 1.70)),
    ("BB 1–3 reprize și peste 1.5", ("BB_H13x2_O15",), 10, 22, "p", (1.65, 2.05)),
    ("Goluri 2–4 / 2–5", ("G24", "G25"), 10, 15, "edge", BAND),
    ("Mix Supersocial", ("G24", "G25", "G13", "R1R2", "R1O15", "H13x2", "C65", "C75", "H1C25"), 10, 15, "edge", BAND),
)
CORNER_MIN_EDGE = -0.06
# Piețe „pe val”: intră la bilete doar după suficiente rezultate și ROI pozitiv.
# n=1 (un meci norocos) nu ajunge. Fără istoric decontat rămâne catalogul experimental.
WAVE_MIN_N = 15

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


def _scaled(price: Optional[float], p_leg: Optional[float], p_combo: Optional[float]) -> Optional[float]:
    if not price or not p_leg or not p_combo or p_combo <= 0:
        return None
    return price * p_leg / p_combo


def _bb_price(key: str, ps: Dict[str, float], offers: Dict[str, float]) -> Optional[float]:
    """Cota combinației din liniile Superbet (ambele capete, dacă există), nu un preț copiat."""
    legs = {"BB_H1C25_U65": ("H1C25", "H1U65"), "BB_C65_U145": ("C65", "CU145")}.get(key)
    if legs is None:
        anchor = BB_ANCHOR.get(key)
        legs = (anchor,) if anchor else ()
    vals = [v for leg in legs if (v := _scaled(offers.get(leg), ps.get(leg), ps.get(key)))]
    if not vals:
        return None
    g = math.exp(sum(math.log(v) for v in vals) / len(vals))
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


def candidates(conn: sqlite3.Connection, now: datetime, horizon_h: int = 60, band=(1.01, 50.0)) -> List[Dict[str, Any]]:
    from betpredict.experimental.corners import CornerModel

    lo, hi = canon_utc(now.isoformat()), canon_utc((now + timedelta(hours=horizon_h)).isoformat())
    rows = conn.execute(
        """SELECT m.id, m.kickoff_utc, m.home_name, m.away_name, m.league_id, m.home_id, m.away_id,
                  mm.lambda_home lh, mm.lambda_away la
           FROM match m LEFT JOIN match_model mm ON mm.match_id = m.id
           WHERE m.kickoff_utc > ? AND m.kickoff_utc <= ?""", (lo, hi)).fetchall()
    cm = CornerModel(conn)
    shares = h1_shares(conn)
    out = []
    for r in rows:
        share = shares.get(r["league_id"], shares[None])
        ps: Dict[str, float] = model_p(r["lh"], r["la"], share) if r["lh"] is not None else {}
        if ps:
            ps["BB_H13x2_O15"] = ps["H13x2"]  # 1-3 în fiecare repriză ⇒ ≥ 2 goluri: identic cu H13x2
        mean, src = cm.mean(r["league_id"], r["home_id"], r["away_id"])
        if src == "global":
            bsd = _bsd_corner_mean(conn, r["id"])
            if bsd:
                mean, src = bsd, "bsd"
        if mean:
            ps.update(cm.probs(mean))
        offers = {MARKETS[(o["market_name"], o["outcome"])]: o["price"] for o in conn.execute(
            "SELECT market_name, outcome, price FROM sb_offer WHERE match_id=?", (r["id"],)) if (o["market_name"], o["outcome"]) in MARKETS}
        if not offers:
            continue
        for k, p in ps.items():
            price, est = offers.get(k), False
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
                        "src": src if cornerish else "goluri (λ robot)",
                        "corner_mean": round(mean, 2) if mean else None, "h1_share": round(share, 3)})
    return out


MUST_REBUILD = ("Combo R1 0.5 & meci 1.5", "Goluri 1–3", "R1 cornere interval 3-6")


def _prod(legs: Sequence[Dict[str, Any]]) -> float:
    return math.prod(c["odds"] for c in legs) if legs else 1.0


def _assemble(pool: Sequence[Dict[str, Any]], lo_n: int, hi_n: int, max_per_key: Optional[int]) -> Optional[List[Dict[str, Any]]]:
    """Ține produsul cotelor în [80, 200]. Nu adaugă o selecție care sare de bandă dacă biletul e deja valid."""
    chosen: List[Dict[str, Any]] = []
    per_key: Dict[str, int] = {}
    per_lg: Dict[Any, int] = {}
    in_t: set = set()

    def can_add(c: Dict[str, Any]) -> bool:
        if c["match_id"] in in_t:
            return False
        lid = c.get("league_id")
        if lid is not None and per_lg.get(lid, 0) >= MAX_PER_LEAGUE:
            return False
        if max_per_key is not None and per_key.get(c["key"], 0) >= max_per_key:
            return False
        return True

    def add(c: Dict[str, Any]) -> None:
        chosen.append(c)
        in_t.add(c["match_id"])
        per_key[c["key"]] = per_key.get(c["key"], 0) + 1
        lid = c.get("league_id")
        if lid is not None:
            per_lg[lid] = per_lg.get(lid, 0) + 1

    def remove(c: Dict[str, Any]) -> None:
        chosen.remove(c)
        in_t.discard(c["match_id"])
        per_key[c["key"]] -= 1
        lid = c.get("league_id")
        if lid is not None:
            per_lg[lid] = max(0, per_lg.get(lid, 0) - 1)

    for c in pool:
        if len(chosen) >= hi_n:
            break
        if not can_add(c):
            continue
        prod = _prod(chosen)
        nxt = prod * c["odds"]
        if len(chosen) >= lo_n and prod >= ODDS_LO and nxt > ODDS_HI:
            break
        if nxt > ODDS_HI_HARD:
            continue
        if nxt > ODDS_HI and len(chosen) + 1 > lo_n:
            continue
        add(c)
        if len(chosen) >= lo_n and _prod(chosen) >= ODDS_LO:
            break
    if _prod(chosen) < ODDS_LO:
        used = {(c["match_id"], c["key"]) for c in chosen}
        rest = sorted((c for c in pool if (c["match_id"], c["key"]) not in used), key=lambda c: c["odds"])
        for alt in rest:
            if _prod(chosen) >= ODDS_LO or not chosen:
                break
            i = min(range(len(chosen)), key=lambda i: chosen[i]["odds"])
            old = chosen[i]
            if alt["odds"] <= old["odds"]:
                continue
            remove(old)
            if can_add(alt) and _prod(chosen) * alt["odds"] <= ODDS_HI_HARD:
                add(alt)
            else:
                add(old)
    prod = _prod(chosen)
    if len(chosen) < lo_n or prod < ODDS_LO or prod > ODDS_HI_HARD:
        return None
    return chosen


def wave_keys(legs: Dict[str, Dict[str, Any]]) -> List[str]:
    """Tipurile cu cel puțin WAVE_MIN_N selecții decontate și ROI peste zero, cele mai bune întâi."""
    hot = [k for k, v in legs.items() if (v.get("n") or 0) >= WAVE_MIN_N and (v.get("roi_single") or 0) > 0]
    hot.sort(key=lambda k: -(legs[k].get("roi_single") or 0))
    return hot


def active_specs(hot: Sequence[str]) -> Tuple:
    """Fără istoric: toate rețetele. Cu istoric: doar piețele pe val, plus un bilet mixt."""
    hot_set = set(hot)
    if not hot_set:
        return TICKETS
    specs = []
    if len(hot) >= 2:
        specs.append(("Pe val", tuple(hot), 10, 15, "p", (1.15, 1.80)))
    for name, keys, lo, hi, order, band in TICKETS:
        if name == "Mix Supersocial":
            continue
        keep = tuple(k for k in keys if k in hot_set)
        if not keep:
            continue
        if keep == tuple(keys):
            specs.append((name, keep, lo, hi, order, band))
        elif len(keep) == 1:
            specs.append((f"Pe val · {LABELS.get(keep[0], name)}", keep, lo, hi, order, band))
        else:
            specs.append((f"Pe val · {name}", keep, lo, hi, order, band))
    return tuple(specs)


def _odds_outside(conn: sqlite3.Connection, today: date) -> bool:
    """Biletele pending cu cota în afara benzii se refac, altfel rămân cele de 500–1800."""
    return conn.execute(
        "SELECT 1 FROM ticket WHERE day=? AND variant=? AND status='pending' AND (total_odds < ? OR total_odds > ?) LIMIT 1",
        (today.isoformat(), VARIANT, ODDS_LO, ODDS_HI_HARD)).fetchone() is not None


def _needs_rebuild(existing: set, cands: List[Dict[str, Any]], specs: Sequence[Tuple]) -> bool:
    """Reface biletele doar dacă slipul lipsă chiar încape în banda 80–200. Altfel s-ar șterge în fiecare oră."""
    for name, keys, lo_n, hi_n, _order, band in specs:
        if name in existing:
            continue
        if name not in MUST_REBUILD and name != "Pe val" and not str(name).startswith("Pe val"):
            continue
        pool = _priced_pool(cands, keys, band)
        cap = MAX_PER_KEY if len(keys) > 2 else (12 if len(keys) > 1 else None)
        if _assemble(_by_green(pool), lo_n, hi_n, cap):
            return True
    return False


def _by_green(pool: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Cea mai mare șansă de verde: probabilitatea selecției, apoi avantajul față de cotă."""
    return sorted(pool, key=lambda c: (-(c["p"] or 0.0), -(c["edge"] or -1.0)))


def _priced_pool(cands: Sequence[Dict[str, Any]], keys: Sequence[str], band: Tuple[float, float]) -> List[Dict[str, Any]]:
    out = []
    for c in cands:
        if not c.get("odds") or c["key"] not in keys or not (band[0] <= c["odds"] <= band[1]) or c.get("edge") is None:
            continue
        min_e = CORNER_MIN_EDGE if c["key"] in CORNER_KEYS or c["key"] in BB_KEYS else MIN_EDGE
        if c["edge"] < min_e:
            continue
        out.append(c)
    return out


def build(conn: sqlite3.Connection, today: date, now: Optional[datetime] = None, replace: bool = False) -> Dict[str, Any]:
    from betpredict.store import repo

    now = now or datetime.now(timezone.utc)
    conn.execute(SCHEMA)
    rep: Dict[str, Any] = {"snapshot_rows": snapshot(conn, now)}
    existing = {json.loads(r[0] or "{}").get("stil") for r in conn.execute(
        "SELECT notes FROM ticket WHERE day=? AND variant=? AND status!='replaced'", (today.isoformat(), VARIANT))}
    have = bool(existing)
    cands = candidates(conn, now, HORIZON_H)
    hot = wave_keys(live_stats(conn)["legs"])
    specs = active_specs(hot)
    if hot and existing and not existing <= {s[0] for s in specs}:
        replace = True  # încă sunt bilete din piețe care nu mai sunt pe val
    if not replace and _odds_outside(conn, today):
        replace = True
    if not replace and _needs_rebuild(existing, cands, specs):
        replace = True  # slipurile cerute au destule selecții, dar sloturile sunt ocupate de biletele vechi
    if have and not replace and all(t[0] in existing for t in specs):
        rep["skipped_existing"] = True
        rep["wave"] = hot
        return rep
    skip_names = set() if replace else existing
    rep["candidates"] = len(cands)
    rep["wave"] = hot
    used_match: Dict[int, int] = {}
    used_sel: set = set()
    made = []
    with conn:
        if have and replace:
            conn.execute("UPDATE ticket SET status='replaced' WHERE day=? AND variant=? AND status='pending'", (today.isoformat(), VARIANT))
        if not replace:  # selecțiile biletelor de azi deja publicate contează la controlul suprapunerii
            for r in conn.execute("""SELECT tl.match_id, tl.selection FROM ticket_leg tl JOIN ticket t ON t.id=tl.ticket_id
                                     WHERE t.day=? AND t.variant=? AND t.status!='replaced'""", (today.isoformat(), VARIANT)):
                used_sel.add((r[0], r[1]))
                used_match[r[0]] = used_match.get(r[0], 0) + 1
        for name, keys, lo_n, hi_n, _order, band in specs:
            if name in skip_names:
                continue
            pool = _priced_pool(cands, keys, band)
            pool = [c for c in pool if (c["match_id"], c["key"]) not in used_sel and used_match.get(c["match_id"], 0) < MAX_TICKETS_PER_MATCH]
            cap = MAX_PER_KEY if len(keys) > 2 else (12 if len(keys) > 1 else None)
            legs = _assemble(_by_green(pool), lo_n, hi_n, cap)
            if not legs:
                continue
            total = math.prod(c["odds"] for c in legs)
            p = math.prod(c["p"] for c in legs)
            n_est = sum(1 for c in legs if c.get("est"))
            notes = {"experimental": True, "paper": True, "risk_acknowledged": True, "stil": name, "wave": bool(hot),
                     "label": f"Stil Supersocial · {name}",
                     "reasons": [f"Stil Supersocial · {name} · {len(legs)} selecții din 7 zile, cotă {total:.0f}.",
                                 "Doar tipuri cu cel puțin 15 rezultate și ROI peste zero. Meciurile sunt alese după șansa modelului, apoi avantajul față de cota Superbet." if hot
                                 else "Oprit la prima combinație din 80–200: șansa de verde e mai mare decât la un bilet mai lung.",
                                 f"Șansă model {p:.2%} · EV model {p * total - 1:+.0%}",
                                 "Paper, miză mică. Bet Builder e estimat din cota Superbet a piciorului, nu e prețul copiat." if n_est
                                 else "Paper, miză mică. Cotele sunt cele Superbet."]}
            cur = conn.execute(
                """INSERT INTO ticket (kind, variant, created_by, target_odds, total_odds, p_ticket, ev, stake, status, created_at, notes, day)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (KIND, VARIANT, "robot", round(total, 2), round(total, 2), round(p, 6), round(p * total - 1, 4), STAKE_U, "pending",
                 repo.now_iso(), json.dumps(notes, ensure_ascii=False), today.isoformat()))
            for c in sorted(legs, key=lambda c: c["kickoff_utc"]):
                conn.execute("INSERT INTO ticket_leg (ticket_id, prediction_id, match_id, market, selection, odds, odds_source) VALUES (?,?,?,?,?,?,?)",
                             (cur.lastrowid, None, c["match_id"], "ss|0", c["key"], c["odds"], "bb_est" if c.get("est") else "superbet"))
                used_sel.add((c["match_id"], c["key"]))
                used_match[c["match_id"]] = used_match.get(c["match_id"], 0) + 1
            made.append({"name": name, "legs": len(legs), "odds": round(total, 2), "ev_model": round(p * total - 1, 3)})
    rep["tickets"] = made
    return rep


def won(sel: str, r: Dict[str, Any]) -> bool:
    if sel == "BB_C65_U145":
        t = (r.get("hc") or 0) + (r.get("ac") or 0)
        return 7 <= t <= 14
    if sel == "BB_H1C25_U65":
        t = (r.get("hc1") or 0) + (r.get("ac1") or 0)
        return 3 <= t <= 6
    if sel == "BB_H13x2_O15":
        return _won("H13x2", r)
    if sel in CORNER_KEYS:
        if sel.startswith("H1C"):
            return r["hc1"] + r["ac1"] > {"H1C25": 2, "H1C35": 3}[sel]
        return r["hc"] + r["ac"] > {"C65": 6, "C75": 7, "C85": 8, "C95": 9}[sel]
    return _won(sel, r)


def today_doc(conn: sqlite3.Connection, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Predicții pe piețele Stil Supersocial: șansa modelului vs prețul Superbet (EV), pentru toate meciurile cu ofertă."""
    now = now or datetime.now(timezone.utc)
    rows = []
    for c in candidates(conn, now, 36):
        fair = round(1 / c["p"], 2) if c["p"] > 0 else None
        rows.append({**c, "label": LABELS.get(c["key"], c["key"]), "p": round(c["p"], 4), "fair_odds": fair,
                     "edge": None if c["edge"] is None else round(c["edge"], 4), "bb": c["key"] in BB_KEYS,
                     "group": GROUP.get(c["key"], "altele")})
    rows.sort(key=lambda r: -r["p"])
    return {"generated_at": canon_utc(now.isoformat()), "count": len(rows), "matches": len({r["match_id"] for r in rows}),
            "note": "Intervalul 3-6 la cornere pe prima repriză nu e în oferta publică. Superbet are «Prima repriză - Interval cornere»: <5, 5-6, 7+. Cota 3-6 e estimată din Peste 2.5 și Sub 6.5.",
            "rows": rows}


def settle_legs(conn: sqlite3.Connection) -> int:
    """Decontare reală a selecțiilor Stil Supersocial din scorul final + pauză (void la meci anulat/amânat)."""
    from betpredict.ingest.normalize import VOID_STATUSES

    from betpredict.ingest.corners import ensure as ensure_corners

    ensure_corners(conn)
    n = 0
    for l in conn.execute(
            """SELECT tl.rowid rid, tl.selection, m.status, m.ft_home, m.ft_away, m.ht_home, m.ht_away, m.corners_home, m.corners_away,
                      m.corners_ht_home, m.corners_ht_away, m.kickoff_utc
               FROM ticket_leg tl JOIN match m ON m.id = tl.match_id WHERE tl.market='ss|0' AND tl.result IS NULL""").fetchall():
        if l["status"] in VOID_STATUSES:
            res = "void"
        elif l["status"] == "finished" and l["ft_home"] is not None and l["ht_home"] is not None:
            sel = l["selection"]
            need_ht = sel.startswith("H1C") or sel == "BB_H1C25_U65"
            need_ft = sel in CORNER_KEYS or sel == "BB_C65_U145"
            if (need_ft and (l["corners_home"] is None or l["corners_away"] is None)) or (need_ht and (l["corners_ht_home"] is None or l["corners_ht_away"] is None)):
                # cornerele lipsesc: așteptăm; după 4 zile → anulat (fără date de decontare)
                if l["kickoff_utc"] < canon_utc((datetime.now(timezone.utc) - timedelta(days=4)).isoformat()):
                    res = "void"
                else:
                    continue
            else:
                r = {"fthg": l["ft_home"], "ftag": l["ft_away"], "hthg": l["ht_home"], "htag": l["ht_away"],
                     "hc": l["corners_home"], "ac": l["corners_away"], "hc1": l["corners_ht_home"], "ac1": l["corners_ht_away"]}
                res = "won" if won(sel, r) else "lost"
        else:
            continue
        conn.execute("UPDATE ticket_leg SET result=? WHERE rowid=?", (res, l["rid"]))
        n += 1
    return n


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
    legs = conn.execute("""SELECT selection, COUNT(*) n, SUM(result='won') w, AVG(odds) o FROM ticket_leg
                           WHERE market='ss|0' AND result IN ('won','lost') GROUP BY selection""").fetchall()
    legs = {r["selection"]: {"n": r["n"], "won": r["w"], "hit": round(r["w"] / r["n"], 3), "avg_odds": round(r["o"], 2),
                             "roi_single": round(r["w"] / r["n"] * r["o"] - 1, 3)} for r in legs}
    hot = wave_keys(legs)
    return {"tickets": out, "legs": legs,
            "wave": [{"key": k, "label": LABELS.get(k, k), **legs[k]} for k in hot],
            "wave_min_n": WAVE_MIN_N}
