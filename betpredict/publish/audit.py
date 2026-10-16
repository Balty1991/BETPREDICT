"""Auditul piețelor, refăcut la fiecare rulare (``api/stats/audit.json``): ce câștigă și ce pierde pe cotele reale Superbet.

- Stil Supersocial: fiecare piață urmărită (``ss_track``), ROI la ultima cotă dinainte de start, corecția învățată și ce
  face Robotul cu ea (scoasă din bilete, dovedită, în bilete, prea puține rezultate), plus cât se mișcă cota până la start;
- robotul principal: predicțiile „sănătoase” cu cotă Superbet, pe piață, și dacă intră în biletele mixte;
- cotele mărite: cu EV pozitiv față de restul;
- biletele Stil cu o cotă mărită în ele față de cele fără (bilete câștigate, ROI, cât intră selecțiile)."""

from __future__ import annotations

import json
import sqlite3
from statistics import median
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _roi(rows: List[Any], odds_i: int, won_i: int) -> Optional[float]:
    if not rows:
        return None
    return round(sum(r[odds_i] for r in rows if r[won_i]) / len(rows) - 1, 4)


def _stil(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    from betpredict.experimental import supersocial as SS

    try:
        rows = conn.execute("""SELECT mkey, odds, odds_first, result='won' FROM ss_track
                               WHERE result IN ('won','lost') AND odds > 1""").fetchall()
    except sqlite3.OperationalError:
        return []
    lift = SS.key_lift(conn)
    by: Dict[str, List[Any]] = {}
    for r in rows:
        by.setdefault(r[0], []).append(r)
    out = []
    for k, rs in by.items():
        lf = lift.get(k) or {}
        n_l = lf.get("n") or 0
        if n_l < SS.LIFT_MIN_N:
            status = "puține rezultate"
        elif lf["lift"] < SS.LIFT_DROP:
            status = "scoasă din bilete"
        elif SS.proven(k, lift):
            status = "dovedită"
        else:
            status = "în bilete"
        drift = [r[1] / r[2] - 1 for r in rs if r[2] and r[2] > 1]
        out.append({"key": k, "label": SS.label(k), "family": SS.family(k), "n": len(rs),
                    "win_rate": round(sum(1 for r in rs if r[3]) / len(rs), 4),
                    "avg_odds": round(sum(r[1] for r in rs) / len(rs), 3), "roi": _roi(rs, 1, 3),
                    "lift": round(lf["lift"], 3) if lf.get("lift") else None, "status": status,
                    "drift": round(median(drift), 4) if drift else None, "_drifts": drift})
    out.sort(key=lambda x: -(x["roi"] if x["roi"] is not None else -9))
    return out


def _robot(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    from betpredict.experimental.supersocial import ROBOT_MARKETS

    mix = {m for m, _ in ROBOT_MARKETS}
    by: Dict[str, List[Any]] = {}
    try:
        rows = conn.execute("SELECT market, result, reasons_json FROM prediction WHERE result IN ('won','lost') AND period='FT'").fetchall()
    except sqlite3.OperationalError:
        return []
    for m, res, rj in rows:
        try:
            js = json.loads(rj or "{}")
        except ValueError:
            continue
        pr = (js.get("odds_alt") or {}).get("superbet")
        if not js.get("healthy") or not pr or pr <= 1:
            continue
        by.setdefault(m, []).append((pr, res == "won"))
    out = [{"market": m, "n": len(v), "win_rate": round(sum(1 for x in v if x[1]) / len(v), 4),
            "avg_odds": round(sum(x[0] for x in v) / len(v), 3), "roi": _roi(v, 0, 1), "in_mix": m in mix}
           for m, v in by.items()]
    out.sort(key=lambda x: -(x["roi"] if x["roi"] is not None else -9))
    return out


def _boosts(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    out = []
    for name, cond in (("Cote mărite cu EV pozitiv", "ev > 0 AND method NOT LIKE 'incert%'"),
                       ("Cote mărite cu EV negativ", "ev <= 0"), ("Super Cotă", "kind='super_cota'")):
        try:
            rs = conn.execute(f"SELECT price, result='won' FROM sb_boost WHERE result IN ('won','lost') AND {cond}").fetchall()
        except sqlite3.OperationalError:
            return []
        if rs:
            out.append({"name": name, "n": len(rs), "win_rate": round(sum(1 for r in rs if r[1]) / len(rs), 4),
                        "avg_odds": round(sum(r[0] for r in rs) / len(rs), 3), "roi": _roi(rs, 0, 1)})
    return out


def _boost_split(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Biletele Stil decontate, separat cu / fără cotă mărită. Câștigurile la cote mari sunt rare, deci pe lângă ROI arătăm
    și cât intră selecțiile (stabil și pe puține bilete)."""
    from betpredict.experimental.supersocial import KIND

    try:
        rows = conn.execute("""SELECT t.id, t.status, t.total_odds, l.market, l.result FROM ticket t JOIN ticket_leg l ON l.ticket_id=t.id
                               WHERE t.kind=? AND t.status IN ('won','lost')""", (KIND,)).fetchall()
    except sqlite3.OperationalError:
        return []
    tk: Dict[int, Dict[str, Any]] = {}
    for tid, st, odds, mkt, res in rows:
        t = tk.setdefault(tid, {"won": st == "won", "odds": odds or 0, "boost": False, "legs": [], "boost_won": None})
        if mkt == "boost|0":
            t["boost"] = True
            t["boost_won"] = res == "won" if res in ("won", "lost") else None
        elif res in ("won", "lost"):
            t["legs"].append(res == "won")
    out = []
    for name, flag in (("Cu cotă mărită", True), ("Fără cotă mărită", False)):
        ts = [t for t in tk.values() if t["boost"] == flag]
        if not ts:
            continue
        legs = [x for t in ts for x in t["legs"]]
        bw = [t["boost_won"] for t in ts if t["boost_won"] is not None]
        out.append({"name": name, "n": len(ts), "won": sum(1 for t in ts if t["won"]),
                    "win_rate": round(sum(1 for t in ts if t["won"]) / len(ts), 4),
                    "avg_odds": round(sum(t["odds"] for t in ts) / len(ts), 2),
                    "roi": round(sum(t["odds"] for t in ts if t["won"]) / len(ts) - 1, 4),
                    "avg_legs": round(sum(len(t["legs"]) + t["boost"] for t in ts) / len(ts), 1),
                    "leg_win_rate": round(sum(legs) / len(legs), 4) if legs else None,
                    "boost_win_rate": round(sum(bw) / len(bw), 4) if bw else None})
    return out


def audit_doc(conn: sqlite3.Connection, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    stil = _stil(conn)
    drifts = [d for x in stil for d in x.pop("_drifts") if abs(d) < 0.5]  # peste 50%: altă linie / eroare de preț
    if drifts:
        moved = sum(1 for d in drifts if abs(d) >= 0.02) / len(drifts)
        up = sum(1 for d in drifts if d >= 0.02) / len(drifts)
        timing = (f"Până la start, {moved:.0%} din selecțiile Stil își schimbă cota Superbet cu 2% sau mai mult, dar la fel "
                  f"de des în sus ({up:.0%}) ca în jos (în medie {sum(drifts) / len(drifts):+.1%}): nu câștigi jucând mai "
                  "devreme sau mai târziu. Cotele mărite dispar repede: acolo joacă imediat.")
    else:
        timing = None
    return {"schema": "betpredict.audit.v1", "generated_at": now.isoformat()[:19] + "Z", "stil": stil, "robot": _robot(conn),
            "boosts": _boosts(conn), "boost_split": _boost_split(conn), "timing": timing,
            "note": "ROI la 1 unitate pe selecție, la cota Superbet reală. Robotul scoate singur din bilete piețele care intră "
                    "constant sub cotă și le pune întâi pe cele dovedite peste cotă."}
