"""Analiza pe meci (``api/match/<id>.json``): ce spune prețul Superbet, cât e marja, ce spun datele, de ce o selecție
e recomandată sau evitată și ce riscuri are meciul.

Doar meciurile cu ofertă Superbet din următoarele 3 zile. Șansa „corectă” vine din prețurile Superbet fără marjă
(perechile Peste/Sub și 1X2 normalizate); istoricul (ligă, forma echipelor, H2H) e doar context: nu promite avantaj,
iar o diferență mare față de preț apare ca notă, nu ca plus inventat (verificat: n-a prezis rezultatul).
"""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from betpredict.timeutil import RO_TZ, canon_utc, parse_utc, ro_date_of

SCHEMA = "betpredict.match_analysis.v1"
HORIZON_DAYS = 3
FORM_N = 6            # ultimele rezultate afișate
RATE_N = 10           # meciuri pe echipă pentru ratele de goluri pe reprize
H2H_N = 6
H2H_YEARS = 6
LEAGUE_DAYS = 365
LEAGUE_MIN_N = 60     # sub atât profilul ligii e „date puține”
FORM_MIN_N = 4
SHRINK_LEAGUE = 50    # liga → media generală (meciuri echivalente)
SHRINK_TEAMS = 12     # echipele → profilul ligii
CONTRADICT_PP = 0.08  # istoricul diferă de prețul corect cu ≥ 8 puncte → notă (fără efect pe recomandare)
HIGH_OVERROUND = 0.08
NIGHT_TO_HOUR_RO = 10

H2 = "A doua repriză - Total goluri"
H1 = "Prima repriză - Total goluri"
FT = "Total goluri"

# cheie → (etichetă, piața Superbet, ieșirea, cum se calculează șansa corectă)
MARKETS: Dict[str, Tuple[str, str, str, Tuple]] = {
    "H2G13": ("Repriza 2: 1–3 goluri", "A doua repriză - Interval goluri", "1-3", ("diff", H2, 0.5, 3.5)),
    "H2G12": ("Repriza 2: 1–2 goluri", "A doua repriză - Interval goluri", "1-2", ("diff", H2, 0.5, 2.5)),
    "H1U15": ("Repriza 1: sub 1.5 goluri", H1, "Sub 1.5", ("under", H1, 1.5)),
    "OVER": ("Peste 1.5 goluri", FT, "Peste 1.5", ("over", FT, 1.5)),
    "YES": ("Ambele marchează (GG)", "Ambele echipe marchează (GG)", "Da", ("pair", "Ambele echipe marchează (GG)", "Da", "Nu")),
    "HOME": ("1 · câștigă gazda", "Final", "1", ("1x2", "1")),
    "DRAW": ("X · egal", "Final", "X", ("1x2", "X")),
    "AWAY": ("2 · câștigă oaspeții", "Final", "2", ("1x2", "2")),
}
ORDER = list(MARKETS)
# Constatări generale (arhivă + închideri Superbet) pentru piețele care nu sunt în lista recomandată la cota curentă.
AVOID_NOTE = {
    "YES": "GG: pe Superbet −4.5% la închidere, 36% intrate față de 54% așteptat pe biletele de ~10.",
    "DRAW": "Egalul intră doar unde ligă are tipar pe 7 sezoane (ex. Serie B 2.60–3.40); altfel marja de ~15% la cote 2.4–4 e prea mare.",
}


# ---------------------------------------------------------------- prețuri


DEVIG = "power"  # „power”: Σ (1/cotă)^k = 1 — marja apasă mai mult pe cotele mari (favorit–outsider); „prop”: proporțional


def devig(prices: Sequence[float]) -> Optional[List[float]]:
    """Șansele fără marjă pentru ieșirile unei piețe complete (metoda din ``DEVIG``)."""
    if not prices or any(not x or x <= 1 for x in prices):
        return None
    imp = [1 / x for x in prices]
    tot = sum(imp)
    if DEVIG != "power" or tot <= 1:
        return [q / tot for q in imp]
    lo, hi = 1.0, 6.0
    for _ in range(60):
        k = (lo + hi) / 2
        if sum(q ** k for q in imp) > 1:
            lo = k
        else:
            hi = k
    ps = [q ** hi for q in imp]
    t = sum(ps)
    return [q / t for q in ps]


def _pair_p(offer: Dict[Tuple[str, str], float], market: str, a: str, b: str) -> Tuple[Optional[float], Optional[float]]:
    """Șansa fără marjă pentru ``a`` dintr-o piață cu două ieșiri și marja (overround) pieței."""
    pa, pb = offer.get((market, a)), offer.get((market, b))
    ps = devig([pa, pb]) if pa and pb else None
    if ps is None:
        return None, None
    return ps[0], 1 / pa + 1 / pb - 1


def fair_prob(offer: Dict[Tuple[str, str], float], how: Tuple) -> Tuple[Optional[float], Optional[float]]:
    """(șansa corectă, marja pieței de bază) pentru o regulă din ``MARKETS``; (None, None) când lipsesc prețurile."""
    kind = how[0]
    if kind in ("over", "under"):
        _k, mk, line = how
        p, ov = _pair_p(offer, mk, f"Peste {line}", f"Sub {line}")
        if p is None:
            return None, None
        return (p if kind == "over" else 1 - p), ov
    if kind == "diff":
        _k, mk, lo, hi = how
        p_lo, ov_lo = _pair_p(offer, mk, f"Peste {lo}", f"Sub {lo}")
        p_hi, ov_hi = _pair_p(offer, mk, f"Peste {hi}", f"Sub {hi}")
        if p_lo is None or p_hi is None:
            return None, None
        return max(0.0, p_lo - p_hi), (ov_lo + ov_hi) / 2
    if kind == "pair":
        _k, mk, a, b = how
        return _pair_p(offer, mk, a, b)
    if kind == "1x2":
        prices = [offer.get(("Final", o)) for o in ("1", "X", "2")]
        ps = devig(prices)  # type: ignore[arg-type]
        if ps is None:
            return None, None
        return ps[("1", "X", "2").index(how[1])], sum(1 / x for x in prices) - 1  # type: ignore[operator]
    return None, None


# ---------------------------------------------------------------- istoric


def _outcomes(hg: int, ag: int, hh: Optional[int], ha: Optional[int]) -> Dict[str, Optional[int]]:
    """Care piețe ar fi intrat la un scor dat (None = lipsește pauza)."""
    t = hg + ag
    ht = None if hh is None or ha is None else hh + ha
    h2 = None if ht is None else t - ht
    return {
        "H2G13": None if h2 is None else int(1 <= h2 <= 3),
        "H2G12": None if h2 is None else int(1 <= h2 <= 2),
        "H1U15": None if ht is None else int(ht <= 1),
        "OVER": int(t >= 2), "YES": int(hg > 0 and ag > 0),
        "HOME": int(hg > ag), "DRAW": int(hg == ag), "AWAY": int(hg < ag),
    }


def league_profiles(conn: sqlite3.Connection, now: datetime, league_ids: Iterable[int]) -> Tuple[Dict[int, Dict[str, Any]], Dict[str, Any]]:
    """Profilul de goluri pe reprize al ligilor (ultimele ``LEAGUE_DAYS`` zile) și media tuturor ligilor."""
    since = canon_utc((now - timedelta(days=LEAGUE_DAYS)).isoformat())
    at = canon_utc(now.isoformat())
    acc: Dict[Any, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    wanted = set(league_ids)
    for lg, hg, ag, hh, ha in conn.execute(
            "SELECT league_id, ft_home, ft_away, ht_home, ht_away FROM match WHERE kickoff_utc>=? AND kickoff_utc<? "
            "AND ft_home IS NOT NULL AND ft_away IS NOT NULL", (since, at)):
        for key in ("*", lg) if lg in wanted else ("*",):
            a = acc[key]
            a["n"] += 1
            a["goals"] += hg + ag
            if hh is not None and ha is not None:
                a["n_ht"] += 1
                a["h1"] += hh + ha
                a["h2"] += hg + ag - hh - ha
            for k, v in _outcomes(hg, ag, hh, ha).items():
                if v is not None:
                    a[k] += v
                    a[f"n_{k}"] += 1
    glob = _profile(acc.get("*"), None)
    return {lg: _profile(acc[lg], glob) for lg in wanted if lg in acc}, glob


def _profile(a: Optional[Dict[str, float]], glob: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not a or not a.get("n"):
        return {"n": 0, "n_ht": 0, "rates": {}, "raw": {}}
    n, nh = int(a["n"]), int(a.get("n_ht", 0))
    raw = {k: a[k] / a[f"n_{k}"] for k in ORDER if a.get(f"n_{k}")}
    rates = {}
    for k in ORDER:
        if not a.get(f"n_{k}"):
            continue
        g = (glob or {}).get("rates", {}).get(k)
        rates[k] = (a[k] + SHRINK_LEAGUE * g) / (a[f"n_{k}"] + SHRINK_LEAGUE) if g is not None else raw[k]
    return {"n": n, "n_ht": nh, "avg_goals": round(a["goals"] / n, 2),
            "h1_avg": round(a["h1"] / nh, 2) if nh else None, "h2_avg": round(a["h2"] / nh, 2) if nh else None,
            "h2_share": round(a["h2"] / (a["h1"] + a["h2"]), 3) if nh and a["h1"] + a["h2"] else None,
            "rates": {k: round(v, 4) for k, v in rates.items()}, "raw": {k: round(v, 4) for k, v in raw.items()}}


def team_history(conn: sqlite3.Connection, team_ids: Iterable[int], now: datetime) -> Dict[int, List[sqlite3.Row]]:
    """Meciurile terminate ale echipelor (cel mai nou primul), dintr-o singură citire a tabelei."""
    ids = sorted({int(t) for t in team_ids if t is not None})
    out: Dict[int, List[Any]] = defaultdict(list)
    if not ids:
        return out
    since = canon_utc((now - timedelta(days=365 * H2H_YEARS)).isoformat())
    wanted = set(ids)
    for r in conn.execute(
            "SELECT m.id, m.kickoff_utc, m.home_id, m.away_id, m.home_name, m.away_name, m.ft_home, m.ft_away, m.ht_home, m.ht_away, "
            "l.name AS league FROM match m LEFT JOIN league l ON l.id=m.league_id "
            "WHERE m.kickoff_utc>=? AND m.ft_home IS NOT NULL AND m.ft_away IS NOT NULL ORDER BY m.kickoff_utc DESC", (since,)):
        for side in (r[2], r[3]):
            if side in wanted:
                out[side].append(r)
    return out


def _form(team_id: Optional[int], rows: Sequence, before: str) -> Dict[str, Any]:
    past = [r for r in rows if r[1] < before]
    last = []
    w = d = l = gf = ga = 0
    for r in past[:FORM_N]:
        home = r[2] == team_id
        f, a = (r[6], r[7]) if home else (r[7], r[6])
        res = "W" if f > a else "D" if f == a else "L"
        w, d, l = w + (res == "W"), d + (res == "D"), l + (res == "L")
        gf, ga = gf + f, ga + a
        last.append({"date": (r[1] or "")[:10], "opponent": r[5] if home else r[4], "venue": "H" if home else "A",
                     # scorul din perspectiva echipei (goluri date–primite), ca rezultatul V/E/Î să se citească direct
                     "score": f"{f}-{a}",
                     "ht": (f"{r[8]}-{r[9]}" if home else f"{r[9]}-{r[8]}") if r[8] is not None and r[9] is not None else None,
                     "result": res, "league": r[10]})
    played = len(last)
    rates: Dict[str, Any] = {}
    sample = [r for r in past[:RATE_N]]
    for k in ("H2G13", "H2G12", "H1U15", "OVER", "YES"):
        vals = [v for v in (_outcomes(r[6], r[7], r[8], r[9])[k] for r in sample) if v is not None]
        if vals:
            rates[k] = {"hit": sum(vals), "n": len(vals)}
    res_s = [("W" if (r[6] > r[7]) == (r[2] == team_id) and r[6] != r[7] else "D" if r[6] == r[7] else "L") for r in sample]
    rates["WIN"] = {"hit": res_s.count("W"), "n": len(res_s)}
    rates["LOSS"] = {"hit": res_s.count("L"), "n": len(res_s)}
    rates["DRAW"] = {"hit": res_s.count("D"), "n": len(res_s)}
    h1 = [r[8] + r[9] for r in sample if r[8] is not None and r[9] is not None]
    h2 = [r[6] + r[7] - r[8] - r[9] for r in sample if r[8] is not None and r[9] is not None]
    return {"played": played, "last": last, "w": w, "d": d, "l": l, "gf": gf, "ga": ga,
            "ppm": round((3 * w + d) / played, 2) if played else None,
            "h1_avg": round(sum(h1) / len(h1), 2) if h1 else None, "h2_avg": round(sum(h2) / len(h2), 2) if h2 else None,
            "rates": rates}


def _h2h(home_id: Optional[int], away_id: Optional[int], rows: Sequence, before: str) -> Dict[str, Any]:
    meet = [r for r in rows if r[1] < before and {r[2], r[3]} == {home_id, away_id}][:H2H_N]
    hw = sum(1 for r in meet if (r[6] > r[7] and r[2] == home_id) or (r[7] > r[6] and r[3] == home_id))
    dr = sum(1 for r in meet if r[6] == r[7])
    goals = [r[6] + r[7] for r in meet]
    return {"n": len(meet), "home_wins": hw, "draws": dr, "away_wins": len(meet) - hw - dr,
            "avg_goals": round(sum(goals) / len(goals), 2) if goals else None,
            "over15": sum(1 for g in goals if g >= 2), "btts": sum(1 for r in meet if r[6] > 0 and r[7] > 0),
            "recent": [{"date": (r[1] or "")[:10], "home": r[4], "away": r[5], "score": f"{r[6]}-{r[7]}",
                        "ht": f"{r[8]}-{r[9]}" if r[8] is not None and r[9] is not None else None} for r in meet]}


def data_estimate(key: str, league: Optional[Dict[str, Any]], glob: Dict[str, Any], fh: Dict[str, Any], fa: Dict[str, Any]) -> Optional[float]:
    """Estimarea din date: profilul ligii (micșorat spre media generală), ajustat cu ultimele meciuri ale celor două echipe."""
    base = ((league or {}).get("rates") or {}).get(key, glob.get("rates", {}).get(key))
    if base is None:
        return None
    if key in ("HOME", "AWAY", "DRAW"):
        a, b = {"HOME": ("WIN", "LOSS"), "AWAY": ("LOSS", "WIN"), "DRAW": ("DRAW", "DRAW")}[key]
        parts = [fh["rates"].get(a), fa["rates"].get(b)]
    else:
        parts = [fh["rates"].get(key), fa["rates"].get(key)]
    hit = sum(p["hit"] for p in parts if p)
    n = sum(p["n"] for p in parts if p)
    return (hit + SHRINK_TEAMS * base) / (n + SHRINK_TEAMS)


# ---------------------------------------------------------------- analiza


def _ro_hour(ts: str) -> Optional[int]:
    dt = parse_utc(ts)
    return dt.astimezone(RO_TZ).hour if dt else None


def risk_flags(league: Optional[str], is_cup: bool, kickoff: str, fh: Dict[str, Any], fa: Dict[str, Any],
               prof: Optional[Dict[str, Any]], has_pin: bool) -> List[Dict[str, str]]:
    from betpredict.builder.super_tickets import INTL

    out: List[Dict[str, str]] = []
    if INTL.search(league or ""):
        out.append({"code": "intl", "level": "high",
                    "text": "Meci internațional sau amical: pe Superbet, selecțiile recomandate au ieșit −8% aici, față de +6% la cluburi."})
    h = _ro_hour(kickoff)
    if h is not None and h < NIGHT_TO_HOUR_RO:
        out.append({"code": "night", "level": "high",
                    "text": f"Start la {h:02d}:{(parse_utc(kickoff).astimezone(RO_TZ).minute):02d} ora României (noaptea): selecțiile de noapte au intrat 43% față de 69% cât era de așteptat."})
    if is_cup:
        out.append({"code": "cup", "level": "medium", "text": "Meci de cupă: rotații și motivație diferită; istoricul de campionat spune mai puțin."})
    thin = []
    if fh["played"] < FORM_MIN_N or fa["played"] < FORM_MIN_N:
        thin.append(f"forma are {fh['played']}/{fa['played']} meciuri")
    if not prof or prof.get("n_ht", 0) < LEAGUE_MIN_N:
        thin.append(f"liga are {(prof or {}).get('n_ht', 0)} meciuri cu scor la pauză în ultimul an")
    if thin:
        out.append({"code": "thin", "level": "medium", "text": "Date puține: " + ", ".join(thin) + ". Estimările din istoric sunt aproape de media generală."})
    if not has_pin:
        out.append({"code": "no_ref", "level": "low", "text": "Fără referință Pinnacle pentru 1X2: prețul se compară doar cu sine (fără marjă)."})
    return out


def _rec_set(conn: sqlite3.Connection, now: datetime) -> Dict[Tuple[int, str], Any]:
    """Selecțiile pe care Robotul le-ar folosi acum (aceeași sursă ca ``api/recommended.json``)."""
    from betpredict.builder import super_tickets as S

    soon = canon_utc((now + timedelta(minutes=5)).isoformat())
    out: Dict[Tuple[int, str], Any] = {}
    for c in S.load_recommended(conn, now):
        if c.market == "bb" or (c.kickoff_utc or "") <= soon or not S.leg_ok(c):
            continue
        if (c.match_id, c.selection) not in out or c.odds > out[(c.match_id, c.selection)].odds:
            out[(c.match_id, c.selection)] = c
    return out


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def analyse_market(key: str, offer: Dict[Tuple[str, str], float], rec: Optional[Any], est: Optional[float], pin: Optional[float],
                   live: Dict[Any, Dict[str, Any]], league_id: Optional[int], flags: Sequence[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    from betpredict.builder import super_tickets as S

    label, mn, oc, how = MARKETS[key]
    price = offer.get((mn, oc))
    if not price or price <= 1:
        return None
    fair, ov = fair_prob(offer, how)
    spec = S.REC.get((mn, oc))
    lspec = S.LEAGUE_REC.get((league_id, oc)) if mn == "Final" else None
    st = live.get((mn, oc)) if spec else None
    row: Dict[str, Any] = {
        "key": key, "label": label, "price": round(price, 3), "implied_p": round(1 / price, 4),
        "fair_p": round(fair, 4) if fair is not None else None, "fair_odds": round(1 / fair, 2) if fair else None,
        "overround": round(ov, 4) if ov is not None else None,
        "margin": round(1 - price * fair, 4) if fair else None,  # cât pierzi față de prețul corect, la cota asta
        "data_p": round(est, 4) if est is not None else None,
        "pinnacle_p": round(pin, 4) if pin is not None else None,
        "window": [spec[2], spec[3]] if spec else ([lspec[2], lspec[3]] if lspec else None),
        "measured": {"n": st["n"], "roi": st.get("roi"), "days": st.get("days"), "off": bool(st.get("off"))} if st and st.get("n") else None,
    }
    why: List[str] = []
    caution: List[str] = []
    if rec is not None:
        status = "recommended"
        if rec.grade == S.LEAGUE_GRADE and lspec:
            why.append(lspec[5] + ".")
        elif rec.grade == "P":
            why.append("Superbet plătește cel puțin prețul corect Pinnacle pentru acest meci.")
        else:
            why.append(S.SEL_WHY.get(key, "Piață recomandată în istoric."))
        if row["measured"] and row["measured"]["n"] >= 30 and row["measured"]["roi"] is not None:
            m = row["measured"]
            why.append(f"Ultimele {m['days']} de zile pe Superbet: {m['roi']:+.0%} pe {m['n']} selecții la cota de închidere.")
        if price >= S.LONG_MIN_ODDS:
            why.append("De la 1.35 intră la SuperBonus pe biletele lungi.")
        row["p_robot"] = round(rec.p_honest, 4)
    else:
        status = "avoid"
        win = row["window"]
        if st and st.get("off"):
            why.append(f"Piața e scoasă de pe bilete: {st['roi']:+.0%} pe {st['n']} selecții în ultimele {st['days']} de zile.")
        elif win and price < win[0]:
            why.append(f"Cota {price:.2f} e sub fereastra măsurată {win[0]:.2f}–{win[1]:.2f}: la cote mici marja Superbet ia tot avantajul.")
        elif win and price > win[1]:
            why.append(f"Cota {price:.2f} e peste fereastra măsurată {win[0]:.2f}–{win[1]:.2f}: în afara ei piața n-a ieșit pe plus.")
        elif pin is not None and price * pin < S.PIN_MIN_RATIO:
            why.append(f"Superbet plătește sub prețul corect Pinnacle (corect ≈ {1 / pin:.2f}).")
        elif win:
            why.append("Marja pe selecție e prea mare la cota asta sau selecția nu trece filtrele Robotului.")
        if key in AVOID_NOTE:
            why.append(AVOID_NOTE[key])
        if not why:
            why.append("Nu face parte din piețele recomandate la această cotă.")
    if ov is not None and ov >= HIGH_OVERROUND:
        caution.append(f"Marja pieței e mare ({ov:.1%}).")
    if est is not None and fair is not None and abs(est - fair) >= CONTRADICT_PP:
        # verificat pe 1.572 de selecții la închiderea Superbet (13–19.11): diferența asta n-a prezis rezultatul → doar context
        row["data_note"] = (f"Istoricul (liga + ultimele meciuri) dă {_fmt_pct(est)}, prețul {_fmt_pct(fair)}. Diferența asta n-a prezis "
                            "rezultatul la cotele de închidere, deci e doar context, nu avantaj.")
    if status == "recommended" and (caution or any(f["level"] == "high" for f in flags)):
        status = "caution"
        if any(f["level"] == "high" for f in flags):
            caution.append("Meciul are un risc mare (vezi riscurile de mai jos).")
    row.update(status=status, why=why, caution=caution)
    return row


def _verdict(markets: List[Dict[str, Any]], flags: Sequence[Dict[str, str]]) -> str:
    rec = [m for m in markets if m["status"] == "recommended"]
    cau = [m for m in markets if m["status"] == "caution"]
    if rec:
        best = max(rec, key=lambda m: m.get("p_robot") or m.get("fair_p") or 0)
        txt = f"Recomandat: {best['label']} la {best['price']:.2f}"
        if best.get("fair_p"):
            txt += f" (șansă corectă {_fmt_pct(best['fair_p'])})"
        return txt + ". Una câte una nu sunt sigure: rostul lor e pe bilete, cu SuperBonus."
    if cau:
        return f"Doar cu atenție: {cau[0]['label']} la {cau[0]['price']:.2f}. " + (cau[0]["caution"][0] if cau[0]["caution"] else "")
    if any(f["level"] == "high" for f in flags):
        return "Niciun pariu recomandat: meciul are un risc mare și nicio piață nu trece filtrele."
    return "Niciun pariu recomandat pe acest meci: prețurile sunt sub fereastra unde piețele au ieșit la zero sau pe plus."


def build_all(conn: sqlite3.Connection, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    from betpredict.builder import super_tickets as S
    from betpredict.builder.rec_monitor import market_stats

    now = now or datetime.now(timezone.utc)
    lo = canon_utc(now.isoformat())
    hi = canon_utc((now + timedelta(days=HORIZON_DAYS)).isoformat())
    ms = conn.execute(
        "SELECT m.id, m.kickoff_utc, m.home_id, m.away_id, m.home_name, m.away_name, m.league_id, m.status, "
        "l.name AS league, COALESCE(l.is_cup, 0) AS is_cup FROM match m LEFT JOIN league l ON l.id=m.league_id "
        "WHERE m.kickoff_utc>? AND m.kickoff_utc<=? AND m.id IN (SELECT DISTINCT match_id FROM sb_offer) "
        "AND COALESCE(m.status, 'notstarted') NOT IN ('finished', 'canceled', 'cancelled', 'postponed') ORDER BY m.kickoff_utc, m.id",
        (lo, hi)).fetchall()
    if not ms:
        return []
    ids = [m[0] for m in ms]
    offers: Dict[int, Dict[Tuple[str, str], float]] = defaultdict(dict)
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        for mid, mn, oc, p in conn.execute(
                f"SELECT match_id, market_name, outcome, price FROM sb_offer WHERE match_id IN ({','.join('?' * len(chunk))}) "
                f"AND market_name IN ({','.join('?' * len({v[1] for v in MARKETS.values()} | {H2, H1, FT}))})",
                (*chunk, *sorted({v[1] for v in MARKETS.values()} | {H2, H1, FT}))):
            offers[mid][(mn, oc)] = float(p)
    profs, glob = league_profiles(conn, now, {m[6] for m in ms if m[6] is not None})
    hist = team_history(conn, [x for m in ms for x in (m[2], m[3])], now)
    try:
        recs = _rec_set(conn, now)
    except Exception:  # noqa: BLE001 — fără lista recomandată, analiza rămâne descriptivă
        recs = {}
    try:
        live = market_stats(conn, S.REC, (1.40, 1.60), now)
    except Exception:  # noqa: BLE001
        live = {}
    try:
        pins = S.pin_fair(conn, ids, now)
    except Exception:  # noqa: BLE001
        pins = {}
    docs = []
    for m in ms:
        mid, ko, hid, aid = m[0], m[1], m[2], m[3]
        fh = _form(hid, hist.get(hid, []) if hid is not None else [], ko)
        fa = _form(aid, hist.get(aid, []) if aid is not None else [], ko)
        prof = profs.get(m[6])
        has_pin = any((mid, k) in pins for k in ("HOME", "DRAW", "AWAY"))
        flags = risk_flags(m[8], bool(m[9]), ko, fh, fa, prof, has_pin)
        markets = []
        for key in ORDER:
            row = analyse_market(key, offers.get(mid, {}), recs.get((mid, key)), data_estimate(key, prof, glob, fh, fa),
                                 pins.get((mid, key)), live, m[6], flags)
            if row:
                markets.append(row)
        rank = {"recommended": 0, "caution": 1, "avoid": 2}
        markets.sort(key=lambda r: (rank[r["status"]], ORDER.index(r["key"])))
        h2h = _h2h(hid, aid, hist.get(hid, []) if hid is not None else [], ko)
        day = ro_date_of(ko)
        docs.append({
            "schema": SCHEMA, "generated_at": canon_utc(now.isoformat()),
            "match": {"id": mid, "kickoff_utc": ko, "day": day.isoformat() if day else None, "home": m[4], "away": m[5],
                      "league": m[8], "league_id": m[6], "intl": any(f["code"] == "intl" for f in flags),
                      "night": any(f["code"] == "night" for f in flags)},
            "verdict": _verdict(markets, flags),
            "markets": markets,
            "form": {"home": fh, "away": fa},
            "h2h": h2h,
            "league_profile": {**{k: v for k, v in (prof or {"n": 0, "n_ht": 0}).items() if k != "raw"},
                               "days": LEAGUE_DAYS, "all": {k: glob.get(k) for k in ("n", "avg_goals", "h1_avg", "h2_avg", "h2_share", "rates")}},
            "risk": flags,
            "note": "Șansa corectă = prețurile Superbet fără marjă. Istoricul e context, nu un avantaj: o selecție e recomandată "
                    "doar dacă piața ei a ieșit la zero sau pe plus la cotele reale, în fereastra ei de cote.",
        })
    return docs


def publish_match_analysis(conn: sqlite3.Connection, out_root: Path, now: Optional[datetime] = None) -> int:
    """Scrie ``api/match/<id>.json`` pentru meciurile cu ofertă Superbet din următoarele 3 zile și ``api/match/index.json``;
    șterge fișierele meciurilor care nu mai sunt în fereastră. Întoarce câte meciuri au fost scrise."""
    from betpredict.publish.day import write_json

    now = now or datetime.now(timezone.utc)
    docs = build_all(conn, now)
    folder = Path(out_root) / "api" / "match"
    keep = set()
    for d in docs:
        p = write_json(folder / f"{d['match']['id']}.json", d)
        keep.add(p.name)
    if folder.exists():
        for f in folder.glob("*.json"):
            if re.fullmatch(r"\d+\.json", f.name) and f.name not in keep:
                f.unlink()
    write_json(folder / "index.json", {
        "schema": "betpredict.match_analysis_index.v1", "generated_at": canon_utc(now.isoformat()), "count": len(docs),
        "matches": [{"id": d["match"]["id"], "day": d["match"]["day"], "kickoff_utc": d["match"]["kickoff_utc"],
                     "home": d["match"]["home"], "away": d["match"]["away"], "league": d["match"]["league"],
                     "recommended": [m["key"] for m in d["markets"] if m["status"] == "recommended"],
                     "risk": [f["code"] for f in d["risk"]]} for d in docs]})
    return len(docs)
