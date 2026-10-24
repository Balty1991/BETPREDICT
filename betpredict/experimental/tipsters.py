"""Biletele tipsterilor din Supersocial, comparate cu robotul pe aceleași meciuri.

Biletele vin din ``betpredict/lab/tipsters.csv`` (transcrise din capturi). Pentru fiecare selecție căutăm meciul în baza
noastră (ziua + numele echipelor) și punem alături: ce șansă îi dădea robotul, cota Superbet pe care o vedea el și
cornerele din datele noastre. Așa se vede dacă un tipster are un plus real pe o piață sau doar biletele norocoase.
"""
from __future__ import annotations

import csv
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from zoneinfo import ZoneInfo

from betpredict.experimental.supersocial import LABELS, MARGIN, _ensure_track
from betpredict.timeutil import canon_utc

CSV_PATH = Path(__file__).resolve().parents[1] / "lab" / "tipsters.csv"
RO = ZoneInfo("Europe/Bucharest")
MIN_SIM = 0.65


def load(path: Path = CSV_PATH) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        lines = [ln for ln in f if ln.strip() and not ln.lstrip().startswith("#")]
    out = []
    for r in csv.DictReader(lines):
        try:
            kick = datetime.strptime(r["data_ora"].strip(), "%Y-%m-%d %H:%M").replace(tzinfo=RO).astimezone(timezone.utc)
            out.append({"ticket": r["bilet"].strip(), "tipster": r["tipster"].strip(), "kickoff": kick,
                        "home": r["gazde"].strip(), "away": r["oaspeti"].strip(), "key": r["cheie"].strip(),
                        "odds": float(r["cota"]), "result": r["rezultat"].strip().lower(),
                        "corners": int(r["cornere"]) if (r.get("cornere") or "").strip() else None})
        except (KeyError, ValueError):
            continue  # linie greșită: o sărim, nu oprim publicarea
    return out


def stat_kind(key: str) -> Optional[str]:
    """Ce înseamnă cifra de sub selecție pe bilet: cornere, șuturi sau goluri, după piață."""
    if key.startswith(("H1C", "BB_H1C")) or key in ("H1U65", "H1U75"):
        return "cornere R1"
    if key.startswith(("C", "BB_C")):
        return "cornere"
    if key.startswith("H1O"):
        return "goluri R1"
    return {"SHOTS": "șuturi", "O15": "goluri", "O25": "goluri", "R1O25": "goluri", "R1O15": "goluri"}.get(key)


def find_match(conn: sqlite3.Connection, home: str, away: str, kick: datetime) -> Optional[sqlite3.Row]:
    from betpredict.ingest.superbet import name_sim

    lo, hi = canon_utc((kick - timedelta(hours=3)).isoformat()), canon_utc((kick + timedelta(hours=3)).isoformat())
    best, score = None, 0.0
    for m in conn.execute("SELECT * FROM match WHERE kickoff_utc BETWEEN ? AND ?", (lo, hi)):
        a, b = name_sim(home, m["home_name"] or ""), name_sim(away, m["away_name"] or "")
        # o echipă sigură și cealaltă plauzibilă (în aceeași fereastră de 3 ore): „Willem II” ↔ „Willem II Tilburg”
        s = (a + b) / 2 if max(a, b) >= 0.9 and min(a, b) >= 0.3 else 0.0
        if s > score:
            best, score = m, s
    return best if score >= MIN_SIM else None


def report(conn: sqlite3.Connection, legs: Optional[Sequence[Dict[str, Any]]] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
    from betpredict.ingest.corners import ensure as ensure_corners

    ensure_corners(conn)
    _ensure_track(conn)
    legs = load() if legs is None else legs
    now = now or datetime.now(timezone.utc)
    tickets: Dict[str, Dict[str, Any]] = {}
    by_key: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"n": 0, "won": 0, "imp": 0.0, "rp": [], "seen": 0})
    checked, mismatch = 0, []
    for l in legs:
        m = find_match(conn, l["home"], l["away"], l["kickoff"])
        tr = conn.execute("SELECT p, odds FROM ss_track WHERE match_id=? AND mkey=?", (m["id"], l["key"])).fetchone() if m else None
        ours = None
        kind = stat_kind(l["key"])
        cols = {"cornere": ("corners_home", "corners_away"), "cornere R1": ("corners_ht_home", "corners_ht_away")}.get(kind or "")
        if cols and m is not None and m[cols[0]] is not None and m[cols[1]] is not None:
            ours = m[cols[0]] + m[cols[1]]
            if l["corners"] is not None:
                checked += 1
                if ours != l["corners"]:
                    mismatch.append({"home": l["home"], "away": l["away"], "their": l["corners"], "ours": ours})
        leg = {"home": l["home"], "away": l["away"], "kickoff_utc": canon_utc(l["kickoff"].isoformat()), "key": l["key"],
               "label": LABELS.get(l["key"], l["key"]), "odds": l["odds"], "result": l["result"],
               "match_id": m["id"] if m else None, "robot_p": round(tr["p"], 4) if tr else None,
               "robot_odds": tr["odds"] if tr else None, "corners": l["corners"], "corners_ours": ours, "stat": kind}
        t = tickets.setdefault(l["ticket"], {"id": l["ticket"], "tipster": l["tipster"], "date": l["kickoff"].astimezone(RO).date().isoformat(), "legs": []})
        t["legs"].append(leg)
        if l["result"] in ("won", "lost"):
            k = by_key[l["key"]]
            k["n"] += 1
            k["won"] += l["result"] == "won"
            k["imp"] += 1 / l["odds"] / MARGIN
            if tr:
                k["rp"].append(tr["p"])
        by_key[l["key"]]["seen"] += 1
    out_t = []
    for t in tickets.values():
        ls = t["legs"]
        res = [x["result"] for x in ls]
        status = "lost" if "lost" in res else "won" if all(r in ("won", "void") for r in res) else "pending"
        rp = [x["robot_p"] for x in ls if x["robot_p"] is not None]
        out_t.append({**t, "n": len(ls), "odds": round(math.prod(x["odds"] for x in ls if x["result"] != "void"), 2), "status": status,
                      "p_market": round(math.prod(1 / x["odds"] / MARGIN for x in ls if x["result"] != "void"), 5),
                      "p_robot": round(math.prod(rp), 5) if len(rp) == len(ls) else None,
                      "matched": sum(x["match_id"] is not None for x in ls), "robot_seen": len(rp)})
    out_t.sort(key=lambda t: t["date"], reverse=True)
    markets = []
    for key, k in sorted(by_key.items(), key=lambda kv: -kv[1]["n"]):
        n = k["n"]
        markets.append({"key": key, "label": LABELS.get(key, key), "n": n, "won": k["won"],
                        "hit": round(k["won"] / n, 3) if n else None, "implied": round(k["imp"] / n, 3) if n else None,
                        "robot_p": round(sum(k["rp"]) / len(k["rp"]), 3) if k["rp"] else None, "robot_n": len(k["rp"])})
    lost = sum(t["status"] == "lost" for t in out_t)
    return {"generated_at": canon_utc(now.isoformat()), "tickets": out_t, "markets": markets,
            "summary": {"tickets": len(out_t), "won": sum(t["status"] == "won" for t in out_t), "lost": lost,
                        "only_wins": bool(out_t) and lost == 0},
            "data_check": {"compared": checked, "mismatches": mismatch}}
