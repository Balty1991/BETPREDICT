"""v4: Bet Builder informativ + piețe noi experimentale + SuperAvantaj (din simularea comună a meciului).

Publicat în ``api/builder/<zi>.json`` (vezi docs/data-contract.md §14). Nimic de aici nu intră în recomandări
sau bilete: piețele noi și combinațiile sunt EXPERIMENTALE până la ≥ 300 de selecții decontate cu CLV pozitiv.
Sugestiile se salvează în ``bb_suggestion`` și se decontează după meci (unde datele permit)."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from betpredict.model import sim as SIM
from betpredict.store import repo
from betpredict.timeutil import canon_utc, ro_day_bounds_utc

VALUE_MARGIN = 1.05      # joacă doar dacă cota Superbet ≥ 1/p × 1.05
MIN_P, MAX_P = 0.25, 0.85
TOP_COMBOS = 6

# combinații proprii (când Superbet nu are preț public): șabloane în textul Superbet, cu FAV = favorita modelului
TEMPLATES = [
    ("Peste 1.5 goluri; Peste 0.5 goluri în prima repriză", ()),
    ("FAV câştigă sau egal; Peste 1.5 goluri", ()),
    ("FAV câştigă; Peste 1.5 goluri", ()),
    ("FAV peste 0.5 goluri; Sub 4.5 goluri", ()),
    ("Peste 1.5 goluri; Peste 0.5 goluri în prima repriză; HTC3-6", ()),
    ("FAV câştigă sau egal; Sub 3.5 goluri", ()),
    ("Ambele echipe marchează; Peste 2.5 goluri", ()),
    ("Peste 8.5 cornere; Peste 1.5 goluri", ()),
]

EXTRA_SB = {  # piața experimentală → (nume piață Superbet, format rezultat)
    "team_total_home": ("Total goluri {home}", "Peste {line}"),
    "team_total_away": ("Total goluri {away}", "Peste {line}"),
    "ht_over_under": ("Prima repriză - Total goluri", "Peste {line}"),
    "h2_over_under": ("A doua repriză - Total goluri", "Peste {line}"),
    "corners_over_under": ("Total cornere", "Peste {line}"),
}
EXTRA_LABEL = {
    "team_total_home": "Gazde peste {line} goluri", "team_total_away": "Oaspeți peste {line} goluri",
    "ht_over_under": "Prima repriză peste {line}", "h2_over_under": "Repriza 2 peste {line}",
    "corners_over_under": "Cornere peste {line}", "ht_corners_over_under": "Cornere pauză peste {line}",
    "half_most_goals": "Repriza cu cele mai multe goluri: {sel}",
}
HALF_SEL = {"FIRST": "Repriza 1", "EQUAL": "Egalitate", "SECOND": "Repriza 2"}


def _ht_corners_range(lo: int, hi: int):
    return (f"ht_corners_{lo}_{hi}", lambda S: ((S["ch1"] + S["ca1"]) >= lo) & ((S["ch1"] + S["ca1"]) <= hi))


def _legs_for(text: str, home: str, away: str, fav: str) -> Optional[List[Tuple[str, Any]]]:
    out = []
    for part in [x.strip() for x in text.replace("FAV", fav).split(";")]:
        if part == "HTC3-6":
            out.append(_ht_corners_range(3, 6))
            continue
        p = SIM.parse_leg(part, home, away)
        if p is None:
            return None
        out.append(p)
    return out


def _corners_prior(conn: sqlite3.Connection, mid: int) -> Tuple[Tuple[float, float], str]:
    pts = [(r[0], r[1]) for r in conn.execute(
        "SELECT line, probability FROM provider_prediction WHERE source='bsd' AND match_id=? AND market='total_corners' AND selection='OVER'", (mid,))]
    sb = {}
    for r in conn.execute("SELECT outcome, price FROM sb_offer WHERE match_id=? AND market_name='Total cornere'", (mid,)):
        sb[r[0]] = r[1]
    for k, v in list(sb.items()):
        if k.startswith("Peste "):
            ln = k.split()[1]
            u = sb.get(f"Sub {ln}")
            if u:
                po = (1 / v) / (1 / v + 1 / u)
                pts.append((float(ln), po))
                pts.append((float(ln), po))  # piața Superbet cântărește dublu față de BSD
    if not pts:
        return SIM.DEFAULT_CORNERS, "implicit"
    return SIM.fit_corners(pts), ("bsd+superbet" if sb else "bsd")


def _fmt(x: float) -> str:
    return f"{x:g}"


def match_builder(conn: sqlite3.Connection, m: sqlite3.Row, lh: float, la: float) -> Dict[str, Any]:
    home, away = m["home_name"] or "", m["away_name"] or ""
    corners, csrc = _corners_prior(conn, m["id"])
    S = SIM.simulate(lh, la, corners, seed=int(m["id"]) % 100000)
    offer = {(r["market_name"], r["outcome"]): r["price"] for r in conn.execute(
        "SELECT market_name, outcome, price FROM sb_offer WHERE match_id=?", (m["id"],))}
    # piețe experimentale (din simulare) + cota Superbet unde există
    extra = []
    for key, p in SIM.extra_markets(S).items():
        mk, line, sel = key.split("|")
        sbn = EXTRA_SB.get(mk)
        o = None
        if sbn and sel == "OVER":
            o = offer.get((sbn[0].format(home=home, away=away), sbn[1].format(line=line)))
        if mk == "half_most_goals":
            o = offer.get(("Repriza cu cele mai multe goluri", HALF_SEL[sel]))
        extra.append({"key": key, "market": mk, "line": float(line), "selection": sel,
                      "label": EXTRA_LABEL[mk].format(line=line, sel=HALF_SEL.get(sel, sel)), "p": p,
                      "fair_odds": round(1 / p, 2) if p > 0.01 else None, "sb_odds": o,
                      "ev": round(p * o - 1, 4) if o else None, "experimental": True})
    # combinații: întâi cele cu preț public Superbet (Bet Builder predefinit + piețe combinate), apoi șabloanele proprii
    combos: List[Dict[str, Any]] = []
    for (mn, oc), price in offer.items():
        if not (mn.startswith(("1X2 & ", "Șansă dublă & ", "Total goluri & GG", "Total goluri prima repriză & Total goluri"))
                or ";" in oc or mn == oc):
            continue
        legs = SIM.parse_combo(mn, oc, home, away)
        if not legs:
            continue
        p = SIM.joint(S, legs)
        if not (MIN_P <= p <= MAX_P):
            continue
        combos.append({"label": oc if ";" in oc or mn == oc else f"{mn}: {oc}", "legs": [k for k, _ in legs],
                       "superbet": {"market": mn, "outcome": oc}, "p": round(p, 4), "fair_odds": round(1 / p, 2),
                       "min_odds": round(VALUE_MARGIN / p, 2), "sb_odds": price, "ev": round(p * price - 1, 4),
                       "value": price >= VALUE_MARGIN / p, "source": "superbet"})
    fav = home if lh >= la else away
    for tpl, _ in TEMPLATES:
        legs = _legs_for(tpl, home, away, fav)
        if not legs:
            continue
        p = SIM.joint(S, legs)
        if not (MIN_P <= p <= MAX_P):
            continue
        indep = float(np.prod([f(S).mean() for _, f in legs]))
        combos.append({"label": tpl.replace("FAV", fav).replace("HTC3-6", "3–6 cornere la pauză"), "legs": [k for k, _ in legs],
                       "superbet": None, "p": round(p, 4), "fair_odds": round(1 / p, 2), "min_odds": round(VALUE_MARGIN / p, 2),
                       "sb_odds": None, "ev": None, "value": None, "source": "model",
                       "correlation_lift": round(p / indep, 3) if indep > 0 else None})
    combos.sort(key=lambda c: (c["value"] is True, c["ev"] if c["ev"] is not None else -1, c["p"]), reverse=True)
    sa = SIM.superavantaj(S)
    # Super Cotă (cotă mărită publică pe 1X2): EV cu probabilitatea simulării ancorate (fără SuperAvantaj — nu se aplică)
    super_cota = []
    for sel, key in (("SC-1", "h"), ("SC-X", "d"), ("SC-2", "a")):
        o = offer.get(("Final - Super Cota", sel))
        if not o:
            continue
        p = float((S["h"] > S["a"]).mean() if key == "h" else (S["h"] == S["a"]).mean() if key == "d" else (S["a"] > S["h"]).mean())
        super_cota.append({"selection": sel, "odds": o, "p": round(p, 4), "fair_odds": round(1 / p, 2) if p > 0 else None,
                           "ev": round(p * o - 1, 4), "value": p * o >= VALUE_MARGIN})
    return {"match_id": m["id"], "home": home, "away": away, "kickoff_utc": m["kickoff_utc"],
            "lambda_home": round(lh, 3), "lambda_away": round(la, 3), "corners": {"mu": corners[0], "k": corners[1], "source": csrc},
            "superavantaj": {"home_bonus": sa["home"], "away_bonus": sa["away"],
                             "note": "SuperAvantaj: pariul pe 1/2 e câștigător dacă echipa conduce cu 2 goluri oricând (nu se aplică pe cote mărite)"},
            "super_cota": super_cota,
            "extra_markets": extra, "combos": combos[:TOP_COMBOS], "experimental": True}


MARKET_WEIGHT = 0.7  # ca la p prudent: simularea e ancorată 70% în piață, 30% în model


def _pois_probs(lh: float, la: float) -> Tuple[float, float, float]:
    from math import exp, factorial

    ph = [exp(-lh) * lh ** i / factorial(i) for i in range(11)]
    pa = [exp(-la) * la ** i / factorial(i) for i in range(11)]
    hw = sum(ph[i] * pa[j] for i in range(11) for j in range(11) if i > j)
    dr = sum(ph[i] * pa[i] for i in range(11))
    o25 = 1 - sum(ph[i] * pa[j] for i in range(11) for j in range(11) if i + j <= 2)
    return hw, dr, o25


def _grid_probs(A: np.ndarray, B: np.ndarray):
    from scipy.stats import poisson

    g = np.arange(11)
    Ph, Pa = poisson.pmf(g[None, :], A[:, None]), poisson.pmf(g[None, :], B[:, None])
    L = (g[:, None] > g[None, :]).astype(float)
    U2 = ((g[:, None] + g[None, :]) <= 2).astype(float)
    return Ph @ L @ Pa.T, Ph @ Pa.T, 1 - Ph @ U2 @ Pa.T


def anchored_lambdas(conn: sqlite3.Connection, mid: int, lh: float, la: float) -> Tuple[float, float, str]:
    """λ-urile simulării ajustate ca P(1), P(X), P(Peste 2.5) să fie 0.7·piață + 0.3·model.
    Fără ancorare, orice dezacord model–piață pe 1X2 ar apărea fals ca „valoare” în combinații."""
    from betpredict.robot.engine import novig

    odds = {}
    for src in ("superbet", "bsd_consensus"):
        try:
            odds = repo.latest_odds(conn, [mid], source=src).get(mid) or {}
        except Exception:  # noqa: BLE001
            odds = {}
        if odds.get("1x2") and odds.get("over_under_2.5"):
            break
    x = novig(odds.get("1x2") or {}, ("HOME", "DRAW", "AWAY"))
    ou = novig(odds.get("over_under_2.5") or {}, ("OVER", "UNDER"))
    if not x or not ou:
        return lh, la, "model"
    mh, md, mo = _pois_probs(lh, la)
    w = MARKET_WEIGHT
    th, td, to = w * x["HOME"] + (1 - w) * mh, w * x["DRAW"] + (1 - w) * md, w * ou["OVER"] + (1 - w) * mo
    A, B = np.arange(0.15, 4.5, 0.04), np.arange(0.15, 4.0, 0.04)
    H, D, O = _grid_probs(A, B)
    E = (H - th) ** 2 + (D - td) ** 2 + (O - to) ** 2
    ia, ib = np.unravel_index(int(np.argmin(E)), E.shape)
    bl = (float(A[ia]), float(B[ib]))
    return bl[0], bl[1], "piață+model"


def build_day(conn: sqlite3.Connection, day: date, now: Optional[datetime] = None, track: bool = True) -> Dict[str, Any]:
    start, end = ro_day_bounds_utc(day)
    now_s = canon_utc((now or datetime.now(timezone.utc)).isoformat())
    rows = conn.execute(
        """SELECT m.*, mm.lambda_home, mm.lambda_away FROM match m JOIN match_model mm ON mm.match_id = m.id
           WHERE m.kickoff_utc >= ? AND m.kickoff_utc < ? AND mm.lambda_home IS NOT NULL ORDER BY m.kickoff_utc""",
        (start, end)).fetchall()
    out = []
    created = repo.now_iso()
    for m in rows:
        try:
            lh, la, anchor = anchored_lambdas(conn, m["id"], float(m["lambda_home"]), float(m["lambda_away"]))
            b = match_builder(conn, m, lh, la)
            b["anchor"] = anchor
        except Exception:  # noqa: BLE001 — un meci problematic nu oprește ziua
            continue
        out.append(b)
        if track and m["kickoff_utc"] > now_s:
            with conn:
                for c in b["combos"][:3]:
                    conn.execute(
                        "INSERT INTO bb_suggestion(match_id, day, legs_json, label, p_joint, fair_odds, min_odds, sb_price, ev, source, created_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(match_id, label) DO UPDATE SET p_joint=excluded.p_joint, "
                        "fair_odds=excluded.fair_odds, min_odds=excluded.min_odds, sb_price=excluded.sb_price, ev=excluded.ev "
                        "WHERE bb_suggestion.result IS NULL",
                        (m["id"], day.isoformat(), json.dumps({"legs": c["legs"], "superbet": c["superbet"], "template": c["label"] if c["source"] == "model" else None}, ensure_ascii=False),
                         c["label"], c["p"], c["fair_odds"], c["min_odds"], c["sb_odds"], c["ev"], c["source"], created))
    return {"schema": "betpredict.builder.v1", "date": day.isoformat(), "generated_at": created, "experimental": True,
            "rule": f"Joacă doar dacă Superbet dă cel puțin cota minimă (1/p × {VALUE_MARGIN}).", "matches": out}


def settle_suggestions(conn: sqlite3.Connection) -> Dict[str, int]:
    """Decontează sugestiile pe scorul final/pauză (cornerele doar dacă meciul are cornerele în DB)."""
    st = {"settled": 0}
    rows = conn.execute(
        """SELECT b.id, b.legs_json, b.label, b.source, m.home_name, m.away_name, m.ft_home, m.ft_away, m.ht_home, m.ht_away,
                  m.corners_home, m.corners_away FROM bb_suggestion b JOIN match m ON m.id = b.match_id
           WHERE b.result IS NULL AND m.ft_home IS NOT NULL""").fetchall()
    with conn:
        for r in rows:
            d = json.loads(r["legs_json"])
            keys = d.get("legs") or []
            if any(k.startswith(("ht_", "scores_both", "wins_a_half")) for k in keys) and r["ht_home"] is None:
                continue
            if any("corner" in k for k in keys) and r["corners_home"] is None:
                continue
            if any(k.startswith("leads_") for k in keys):
                continue  # momentul golurilor nu e în DB
            h1, a1 = (r["ht_home"] or 0), (r["ht_away"] or 0)
            S = {"h": np.array([r["ft_home"]]), "a": np.array([r["ft_away"]]), "h1": np.array([h1]), "a1": np.array([a1]),
                 "h2": np.array([r["ft_home"] - h1]), "a2": np.array([r["ft_away"] - a1]),
                 "ch": np.array([r["corners_home"] or 0]), "ca": np.array([r["corners_away"] or 0]),
                 "ch1": np.array([0]), "ca1": np.array([0])}
            sb = d.get("superbet")
            if sb:
                legs = SIM.parse_combo(sb["market"], sb["outcome"], r["home_name"] or "", r["away_name"] or "")
            else:
                legs = None  # șabloanele proprii: refacem din etichetă
                tpl = d.get("template")
                if tpl and "cornere la pauză" not in tpl:
                    legs = _legs_for(tpl, r["home_name"] or "", r["away_name"] or "", "")
            if not legs:
                continue
            won = bool(SIM.joint(S, legs) > 0.5)
            conn.execute("UPDATE bb_suggestion SET result=?, settled_at=? WHERE id=?", ("won" if won else "lost", repo.now_iso(), r["id"]))
            st["settled"] += 1
    return st


def builder_stats(conn: sqlite3.Connection) -> Dict[str, Any]:
    out = {}
    for src in ("superbet", "model"):
        rs = conn.execute("SELECT result, sb_price, p_joint FROM bb_suggestion WHERE source=? AND result IS NOT NULL", (src,)).fetchall()
        n = len(rs)
        won = sum(1 for r in rs if r["result"] == "won")
        priced = [r for r in rs if r["sb_price"]]
        profit = sum((r["sb_price"] - 1) if r["result"] == "won" else -1 for r in priced)
        out[src] = {"n": n, "won": won, "expected_won": round(sum(r["p_joint"] for r in rs), 1),
                    "priced_n": len(priced), "roi_pct": round(100 * profit / len(priced), 1) if priced else None}
    return {"experimental": True, **out}


def publish_builder(conn: sqlite3.Connection, out_root: Path, days: List[date], now: Optional[datetime] = None) -> None:
    from betpredict.publish.day import write_json

    for d in days:
        doc = build_day(conn, d, now)
        write_json(out_root / "api" / "builder" / f"{d.isoformat()}.json", doc)
        with conn:
            repo.set_state(conn, f"builder.doc.{d.isoformat()}", json.dumps(doc, ensure_ascii=False))
    write_json(out_root / "api" / "builder" / "stats.json", builder_stats(conn))
    write_index(out_root, days)


def write_index(out_root: Path, days: List[date]) -> None:
    from betpredict.publish.day import write_json

    write_json(out_root / "api" / "builder" / "index.json",
               {"schema": "betpredict.builder_index.v1", "days": [d.isoformat() for d in days],
                "generated_at": repo.now_iso()})


def republish_cached(conn: sqlite3.Connection, out_root: Path, days: List[date]) -> int:
    """Refresh: rescrie documentele Bet Builder calculate la rularea zilnică (fără recalcul)."""
    from betpredict.publish.day import write_json

    n = 0
    for d in days:
        raw = repo.get_state(conn, f"builder.doc.{d.isoformat()}")
        if raw:
            doc = json.loads(raw)
        else:  # fără cache (prima rulare după upgrade): calculăm o dată și salvăm
            doc = build_day(conn, d)
            with conn:
                repo.set_state(conn, f"builder.doc.{d.isoformat()}", json.dumps(doc, ensure_ascii=False))
        write_json(out_root / "api" / "builder" / f"{d.isoformat()}.json", doc)
        n += 1
    write_json(out_root / "api" / "builder" / "stats.json", builder_stats(conn))
    write_index(out_root, days)
    return n
