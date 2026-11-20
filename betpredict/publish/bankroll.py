"""Banca și performanța celor trei produse de bază, de la noul început (``TICKETS_RESET_AT``).

Produse: biletul de ~10 (``acca_super``/``s10``), biletele lungi (``acca_super``/``s100``…``s10000``) și piramida
de cotă 2 (``pyramid``/``p120`` + seriile din ``pyramid120_run``/``pyramid120_step``).

Pe produs: bilete decontate, câștigate față de așteptat (suma șanselor publicate), ROI la miză egală cu SuperBonus (și fără),
profit pe zile, scăderea maximă (drawdown), seriile cele mai lungi, CLV pe selecții (cota luată față de închidere) și
calibrarea selecțiilor (șansa estimată față de rata ieșită, pe intervale).

Simulatorul de bancă (Monte Carlo) folosește șansele măsurate, nu un avantaj presupus: șansa pe bilet pornește din șansa
publicată, corectată cu raportul ieșit/estimat pe selecții (micșorat spre 0.97, adică marja reală a casei), apoi
actualizată cu biletele decontate (Beta). Fiecare drum din simulare trage propria șansă din această distribuție, deci
intervalele includ și incertitudinea despre șansă, nu doar norocul.
"""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from betpredict.builder.super_tickets import TICKETS_RESET_AT
from betpredict.timeutil import canon_utc

PRODUCTS: Tuple[Tuple[str, str, str, Tuple[str, ...]], ...] = (
    ("s10", "Cotă ~10", "acca_super", ("s10",)),
    ("long", "Bilete lungi", "acca_super", ("s100", "s500", "s1000", "s5000", "s10000")),
    ("pyr2", "Piramidă cotă 2", "pyramid", ("p120",)),
)
# Valori de pornire când nu există încă bilete (din analizele anterioare, nu din dorințe):
# ~10: P(câștig) realist 8–9%; lungi: cotă ~3.000 cu bonus ~+80% și 22 de selecții la 0.97 din prețul corect (~−45%); piramida: 2 selecții 1.30–1.55 ≈ cotă 2, ~47%.
FALLBACK = {"s10": {"p": 0.085, "pay": 10.8, "legs": 7, "per_day": 1.5},
            "long": {"p": 0.0001, "pay": 5400.0, "legs": 22, "per_day": 3.0},
            "pyr2": {"p": 0.47, "pay": 2.0, "legs": 2, "per_day": 1.0}}
LEG_RATIO_PRIOR = 0.97   # selecțiile ies, în medie, cu ~3% sub șansa „onestă” (marja Superbet la 1.30–1.65)
LEG_RATIO_STRENGTH = 300  # câte selecții „imaginare” are prima estimare
TICKET_PRIOR_MIN = 20     # câte bilete „imaginare” are șansa de pornire (cel puțin 5 câștiguri așteptate la lungi)
BUCKETS = ((0.0, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0001))
PLANS = (
    {"id": "prudent", "label": "Prudent", "s10": 0.01, "long": 0.005, "pyr2": 0.02},
    {"id": "fara_lungi", "label": "Fără bilete lungi", "s10": 0.01, "long": 0.0, "pyr2": 0.02},
    {"id": "activ", "label": "Activ", "s10": 0.02, "long": 0.005, "pyr2": 0.03},
)
HORIZON_DAYS = 30
PATHS = 2000


def _since(now: datetime) -> str:
    return TICKETS_RESET_AT if (canon_utc(now.isoformat()) or "") >= TICKETS_RESET_AT else ""


def _notes(s: Optional[str]) -> Dict[str, Any]:
    try:
        v = json.loads(s or "{}")
        return v if isinstance(v, dict) else {}
    except (TypeError, ValueError):
        return {}


def _tickets(conn: sqlite3.Connection, kind: str, variants: Sequence[str], since: str) -> List[Dict[str, Any]]:
    q = ",".join("?" * len(variants))
    rows = conn.execute(
        f"""SELECT id, variant, status, total_odds, p_ticket, notes, day, created_at, settled_at, clv FROM ticket
            WHERE kind=? AND variant IN ({q}) AND status NOT IN ('replaced','void') AND created_at>=?
            ORDER BY COALESCE(settled_at, created_at), id""", (kind, *variants, since)).fetchall()
    out = []
    for r in rows:
        n = _notes(r[5])
        odds = float(r[3] or 0)
        pay = float(n.get("payout_bonus") or odds or 0)
        out.append({"id": r[0], "variant": r[1], "status": r[2], "odds": odds, "pay": pay, "p": float(r[4] or 0),
                    "day": r[6] or (r[7] or "")[:10], "settled_at": r[8], "clv": r[9]})
    return out


def _legs(conn: sqlite3.Connection, ids: Sequence[int]) -> List[Dict[str, Any]]:
    if not ids:
        return []
    out: List[Dict[str, Any]] = []
    ids = list(ids)
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        q = ",".join("?" * len(chunk))
        rows = conn.execute(
            f"""SELECT l.ticket_id, l.odds, l.result, l.closing_odds, COALESCE(p.p_calibrated, p.p_model), t.p_ticket
                FROM ticket_leg l JOIN ticket t ON t.id=l.ticket_id LEFT JOIN prediction p ON p.id=l.prediction_id
                WHERE l.ticket_id IN ({q})""", chunk).fetchall()
        out += [{"tid": r[0], "odds": float(r[1] or 0), "result": r[2], "close": r[3], "p": r[4], "p_ticket": r[5]} for r in rows]
    # Selecțiile fără predicție legată: șansa biletului împărțită proporțional cu 1/cotă (așa a fost construit biletul).
    by_t: Dict[int, List[Dict[str, Any]]] = {}
    for l in out:
        by_t.setdefault(l["tid"], []).append(l)
    for legs in by_t.values():
        pt = legs[0]["p_ticket"]
        odds = [l["odds"] for l in legs if l["odds"] > 1]
        if pt and pt > 0 and len(odds) == len(legs):
            k = (pt * math.prod(odds)) ** (1 / len(legs))
            for l in legs:
                if l["p"] is None:
                    l["p"] = min(0.99, k / l["odds"])
    return out


def _streaks(seq: Sequence[bool]) -> Dict[str, int]:
    best_w = best_l = cur = 0
    cur_kind: Optional[bool] = None
    for x in seq:
        cur = cur + 1 if x == cur_kind else 1
        cur_kind = x
        if x:
            best_w = max(best_w, cur)
        else:
            best_l = max(best_l, cur)
    return {"win": best_w, "loss": best_l, "current": (cur if cur_kind else -cur) if cur_kind is not None else 0}


def max_drawdown(curve: Sequence[float]) -> float:
    """Cea mai mare scădere de la un vârf (în unități), pe profitul cumulat pornit de la 0."""
    peak, dd = 0.0, 0.0
    for v in curve:
        peak = max(peak, v)
        dd = max(dd, peak - v)
    return round(dd, 2)


def calibration(legs: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    pts = [(float(l["p"]), 1.0 if l["result"] == "won" else 0.0) for l in legs
           if l.get("p") is not None and l.get("result") in ("won", "lost")]
    buckets = []
    for lo, hi in BUCKETS:
        b = [x for x in pts if lo <= x[0] < hi]
        if b:
            buckets.append({"lo": lo, "hi": min(hi, 1.0), "n": len(b), "pred": round(sum(x[0] for x in b) / len(b), 4),
                            "hit": round(sum(x[1] for x in b) / len(b), 4)})
    n = len(pts)
    return {"n": n, "buckets": buckets,
            "pred": round(sum(x[0] for x in pts) / n, 4) if n else None,
            "hit": round(sum(x[1] for x in pts) / n, 4) if n else None,
            "brier": round(sum((x[0] - x[1]) ** 2 for x in pts) / n, 4) if n else None,
            "ece": round(sum(b["n"] * abs(b["pred"] - b["hit"]) for b in buckets) / n, 4) if n else None}


def clv_stats(legs: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    xs = sorted(l["odds"] / float(l["close"]) - 1 for l in legs if l.get("close") and float(l["close"]) > 1 and l["odds"] > 1)
    if not xs:
        return {"n": 0, "avg": None, "median": None, "beat": None}
    return {"n": len(xs), "avg": round(sum(xs) / len(xs), 4), "median": round(xs[len(xs) // 2], 4),
            "beat": round(sum(1 for x in xs if x > 0) / len(xs), 4)}


def _pyramid_series(conn: sqlite3.Connection, since_day: str) -> Dict[str, Any]:
    try:
        runs = conn.execute("SELECT id, start_date, status, current_step, current_bank, start_bank FROM pyramid120_run "
                            "WHERE start_date>=? ORDER BY id", (since_day,)).fetchall()
        steps = conn.execute("SELECT run_id, step_no, result FROM pyramid120_step WHERE date>=? ORDER BY run_id, step_no",
                             (since_day,)).fetchall()
    except sqlite3.Error:
        return {"runs": 0, "best": 0, "current": 0, "lengths": []}
    won: Dict[int, int] = {}
    for rid, _no, res in steps:
        if res == "won":
            won[rid] = won.get(rid, 0) + 1
    lengths = [won.get(r[0], 0) for r in runs]
    active = [r for r in runs if r[2] == "active"]
    return {"runs": len(runs), "best": max(lengths, default=0), "current": won.get(active[-1][0], 0) if active else 0,
            "avg": round(sum(lengths) / len(lengths), 2) if lengths else None, "lengths": lengths[-20:]}


def _sim_inputs(pid: str, tickets: Sequence[Dict[str, Any]], legs: Sequence[Dict[str, Any]], days: int) -> Dict[str, Any]:
    fb = FALLBACK[pid]
    pub = [t for t in tickets if t["p"] > 0]
    p_model = sum(t["p"] for t in pub) / len(pub) if pub else fb["p"]
    pay = sum(t["pay"] for t in tickets if t["pay"] > 1) / max(1, sum(1 for t in tickets if t["pay"] > 1)) if any(t["pay"] > 1 for t in tickets) else fb["pay"]
    per_t: Dict[int, int] = {}
    for l in legs:
        per_t[l["tid"]] = per_t.get(l["tid"], 0) + 1
    n_legs = sum(per_t.values()) / len(per_t) if per_t else fb["legs"]
    settled = [l for l in legs if l.get("p") is not None and l.get("result") in ("won", "lost")]
    exp_w = sum(float(l["p"]) for l in settled)
    got_w = sum(1 for l in settled if l["result"] == "won")
    k = LEG_RATIO_STRENGTH
    ratio = (got_w + k * LEG_RATIO_PRIOR) / (exp_w + k) if settled else LEG_RATIO_PRIOR
    ratio = max(0.8, min(1.05, ratio))
    # EV pe bilet (șansa corectată × plata cu bonus), mediat; șansa folosită = (1 + EV) / plata medie (evită p̄ × plată̄)
    evs = [t["p"] * ratio ** per_t.get(t["id"], n_legs) * t["pay"] - 1 for t in pub if t["pay"] > 1]
    ev_adj = sum(evs) / len(evs) if evs else fb["p"] * fb["pay"] - 1
    if not evs:
        pay = fb["pay"]
    p0 = max(1e-7, min(0.95, (1 + ev_adj) / pay))
    done = [t for t in tickets if t["status"] in ("won", "lost")]
    w = sum(1 for t in done if t["status"] == "won")
    s = max(TICKET_PRIOR_MIN, 5.0 / p0)
    a, b = p0 * s + w, (1 - p0) * s + len(done) - w
    per_day = len(tickets) / days if tickets and days >= 3 else fb["per_day"]
    lim = {"s10": (1.0, 2.0), "long": (1.0, 5.0), "pyr2": (1.0, 1.0)}[pid]
    return {"p_model": round(p_model, 6), "leg_ratio": round(ratio, 4), "p_start": round(p0, 6), "alpha": round(a, 4), "beta": round(b, 4),
            "p_mean": round(a / (a + b), 6), "payout": round(pay, 2), "legs": round(n_legs, 1),
            "per_day": round(max(lim[0], min(lim[1], per_day)), 2), "ev": round(a / (a + b) * pay - 1, 4)}


def simulate(inputs: Dict[str, Dict[str, Any]], plan: Dict[str, Any], days: int = HORIZON_DAYS, paths: int = PATHS,
             seed: int = 7, pyr_cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Bancă 100 = 100%. Bilete de ~10 și lungi: miză = procent din banca curentă; piramida: o serie primește ``plan['pyr2']``
    din bancă, mizează ``stake_fraction`` din banca seriei la fiecare pas și se încasează la ``suggest_at`` pași sau la pierdere."""
    import numpy as np

    cfg = {"stake_fraction": 0.5, "suggest_at": 6, **(pyr_cfg or {})}
    rng = np.random.default_rng(seed)
    bank = np.full(paths, 100.0)
    p = {k: rng.beta(v["alpha"], v["beta"], size=paths) for k, v in inputs.items()}
    pyr_bank = np.zeros(paths)
    pyr_step = np.zeros(paths, dtype=int)
    peak = bank.copy()
    mdd = np.zeros(paths)
    fan = []
    # numărul de bilete pe zi: partea întreagă + încă unul cu probabilitatea părții fracționare
    for _ in range(days):
        for pid in ("s10", "long"):
            if pid not in inputs or not plan.get(pid):
                continue
            v = inputs[pid]
            base, frac = int(v["per_day"]), v["per_day"] - int(v["per_day"])
            n = base + (rng.random(paths) < frac)
            for j in range(int(n.max())):
                act = n > j
                stake = bank * plan[pid] * act
                win = rng.random(paths) < p[pid]
                bank = bank - stake + np.where(win, stake * v["payout"], 0.0)
        if "pyr2" in inputs and plan.get("pyr2"):
            v = inputs["pyr2"]
            new = pyr_step == 0
            alloc = np.where(new, bank * plan["pyr2"], 0.0)
            bank = bank - alloc
            pyr_bank = pyr_bank + alloc
            stake = pyr_bank * cfg["stake_fraction"]
            win = rng.random(paths) < p["pyr2"]
            pyr_bank = np.where(win, pyr_bank + stake * (v["payout"] - 1), pyr_bank - stake)
            pyr_step = np.where(win, pyr_step + 1, 0)
            cash = (~win) | (pyr_step >= cfg["suggest_at"])
            bank = bank + np.where(cash, pyr_bank, 0.0)
            pyr_bank = np.where(cash, 0.0, pyr_bank)
            pyr_step = np.where(cash, 0, pyr_step)
        total = bank + pyr_bank
        peak = np.maximum(peak, total)
        mdd = np.maximum(mdd, (peak - total) / peak)
        fan.append([round(float(x), 2) for x in np.percentile(total, [5, 25, 50, 75, 95])])
    total = bank + pyr_bank
    q = np.percentile(total, [5, 25, 50, 75, 95])
    return {"plan": plan["id"], "label": plan["label"], "stakes": {k: plan[k] for k in ("s10", "long", "pyr2")},
            "p5": round(float(q[0]), 1), "p25": round(float(q[1]), 1), "p50": round(float(q[2]), 1), "p75": round(float(q[3]), 1),
            "p95": round(float(q[4]), 1), "mean": round(float(total.mean()), 1),
            "p_profit": round(float((total > 100).mean()), 3), "p_down20": round(float((total < 80).mean()), 3),
            "mdd_median": round(float(np.median(mdd)), 3),
            # câte procente din bancă pierde/câștigă în medie fiecare produs pe orizont (miză × bilete × EV), fără compunere
            "ev_pct": {pid: round(plan[pid] * inputs[pid]["per_day"] * days * inputs[pid]["ev"] * 100, 1) for pid in ("s10", "long") if pid in inputs and plan.get(pid)},
            "fan": [{"day": i + 1, "p5": f[0], "p25": f[1], "p50": f[2], "p75": f[3], "p95": f[4]} for i, f in enumerate(fan)]}


def product_doc(conn: sqlite3.Connection, pid: str, label: str, kind: str, variants: Sequence[str], since: str,
                days_span: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    ts = _tickets(conn, kind, variants, since)
    done = [t for t in ts if t["status"] in ("won", "lost")]
    won = [t for t in done if t["status"] == "won"]
    legs = _legs(conn, [t["id"] for t in ts])
    done_ids = {t["id"] for t in done}
    curve, cum, cum_nb = [], 0.0, 0.0
    daily: Dict[str, Dict[str, float]] = {}
    for t in done:
        g = t["pay"] - 1 if t["status"] == "won" else -1.0
        cum += g
        cum_nb += (t["odds"] - 1) if t["status"] == "won" else -1.0
        curve.append(cum)
        d = daily.setdefault(t["day"], {"n": 0, "won": 0, "profit": 0.0})
        d["n"] += 1
        d["won"] += t["status"] == "won"
        d["profit"] += g
    run = 0.0
    by_day = []
    for day in sorted(daily):
        run += daily[day]["profit"]
        by_day.append({"day": day, "n": int(daily[day]["n"]), "won": int(daily[day]["won"]),
                       "profit": round(daily[day]["profit"], 2), "cum": round(run, 2)})
    n = len(done)
    exp = sum(t["p"] for t in done)
    leg_done = [l for l in legs if l["tid"] in done_ids or l.get("result") in ("won", "lost")]
    doc: Dict[str, Any] = {
        "id": pid, "label": label, "bets": n, "won": len(won), "lost": n - len(won), "pending": sum(1 for t in ts if t["status"] == "pending"),
        "hit": round(len(won) / n, 4) if n else None, "expected_hit": round(exp / n, 4) if n else None, "expected_wins": round(exp, 2),
        "profit": round(cum, 2), "roi": round(cum / n, 4) if n else None, "roi_no_bonus": round(cum_nb / n, 4) if n else None,
        "avg_odds": round(sum(t["odds"] for t in done) / n, 2) if n else None,
        "best": round(max((t["pay"] for t in won), default=0), 2) or None,
        "max_drawdown": max_drawdown(curve), "streaks": _streaks([t["status"] == "won" for t in done]),
        "by_day": by_day, "clv": clv_stats(legs), "calibration": calibration(leg_done),
        "legs_settled": sum(1 for l in legs if l.get("result") in ("won", "lost")),
        "legs_hit": round(sum(1 for l in legs if l.get("result") == "won") / max(1, sum(1 for l in legs if l.get("result") in ("won", "lost"))), 4)
        if any(l.get("result") in ("won", "lost") for l in legs) else None,
    }
    if pid == "pyr2":
        doc["series"] = _pyramid_series(conn, since[:10])
    return doc, _sim_inputs(pid, ts, legs, days_span)


def bankroll_doc(conn: sqlite3.Connection, now: Optional[datetime] = None, paths: int = PATHS) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    now = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    since = _since(now)
    start = datetime.fromisoformat(since.replace("Z", "+00:00")) if since else now
    days_span = max(1, int((now - start).total_seconds() // 86400) + 1)
    products, inputs = [], {}
    for pid, label, kind, variants in PRODUCTS:
        try:
            d, sim_in = product_doc(conn, pid, label, kind, variants, since, days_span)
        except sqlite3.Error:
            continue
        products.append(d)
        inputs[pid] = sim_in
    try:
        from betpredict.builder.pyramid import RULES_CORNER2

        pyr_cfg = {"stake_fraction": float(RULES_CORNER2.get("stake_fraction") or 0.5), "suggest_at": int(RULES_CORNER2.get("suggest_at") or 6)}
    except Exception:  # noqa: BLE001
        pyr_cfg = {"stake_fraction": 0.5, "suggest_at": 6}
    sims = [simulate(inputs, plan, paths=paths, pyr_cfg=pyr_cfg) for plan in PLANS] if inputs else []
    all_legs = sum(p["legs_settled"] for p in products)
    return {"generated_at": canon_utc(now.isoformat()), "since": since or None, "days": days_span, "products": products,
            "sim": {"horizon_days": HORIZON_DAYS, "paths": paths, "start_bank": 100, "inputs": inputs, "pyramid": pyr_cfg,
                    "plans": sims, "sample_small": sum(p["bets"] for p in products) < 60 or all_legs < 300},
            "notes": ["Miză egală de 1 unitate pe bilet; câștigul biletelor Robot include SuperBonusul.",
                      "Șansa din simulare = șansa publicată × (rata ieșită ÷ estimată pe selecții, micșorată spre 0.97) la puterea numărului de selecții, apoi actualizată cu biletele decontate.",
                      "Marja casei e inclusă: simularea nu presupune niciun avantaj."]}


def publish_bankroll(conn: sqlite3.Connection, out_root: Path, now: Optional[datetime] = None) -> Path:
    from betpredict.publish.day import write_json

    return write_json(Path(out_root) / "api" / "stats" / "bankroll.json", bankroll_doc(conn, now))
