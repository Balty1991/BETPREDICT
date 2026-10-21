"""Biletele Robotului din „Meciuri potrivite”: selecțiile de azi care cad într-un profil de meci pe plus (vezi ``lab.segments``).

Două bilete pe zi, cu meciuri diferite: ~5 (3–6 selecții, cel mult 1.90 pe selecție) și ~20 (6–16 selecții, cel mult 1.80),
din cele mai sigure selecții potrivite — mai multe cote mici în loc de cote mari riscante. Urmărite pe hârtie (miză 0.1u),
ca să vedem pe rezultate reale dacă profilurile chiar merg."""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from betpredict.store import repo

KIND = "acca_seg"
TARGETS = ((5.0, 3, 6, 1.90, "potrivite5"), (20.0, 6, 16, 1.80, "potrivite20"))
MAX_PER_LEAGUE = 2
STAKE_U = 0.1


def _pick(pool: List[Dict[str, Any]], target: float, n_min: int, n_max: int, cap: float, banned: set) -> Optional[List[Dict[str, Any]]]:
    legs: List[Dict[str, Any]] = []
    leagues: Dict[Any, int] = {}
    floor = target ** (1 / n_max) * 0.97  # cota minimă pe selecție ca ținta să se poată atinge cu cel mult n_max selecții
    for c in sorted(pool, key=lambda c: (-c["p"], -c.get("rank", 0))):
        if not floor <= c["odds"] <= cap or c["match_id"] in banned or any(l["match_id"] == c["match_id"] for l in legs):
            continue
        if leagues.get(c["league_id"], 0) >= MAX_PER_LEAGUE:
            continue
        total = math.prod(l["odds"] for l in legs) * c["odds"]
        if total > target * 1.3 and len(legs) >= n_min:
            continue
        legs.append(c)
        leagues[c["league_id"]] = leagues.get(c["league_id"], 0) + 1
        if math.prod(l["odds"] for l in legs) >= target and len(legs) >= n_min:
            return legs
        if len(legs) >= n_max:
            break
    return legs if len(legs) >= n_min and math.prod(l["odds"] for l in legs) >= target * 0.8 else None


def build(conn: sqlite3.Connection, today: date, now: Optional[datetime] = None, rows: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    have = conn.execute("SELECT COUNT(*) FROM ticket WHERE kind=? AND day=? AND status!='replaced'", (KIND, today.isoformat())).fetchone()[0]
    if have:
        return {"skipped_existing": have}
    if rows is None:
        from betpredict.lab.segments import doc

        rows = doc(conn, now)["today"]
    until = (today + timedelta(days=2)).isoformat()
    pool = [r for r in rows if (r.get("kickoff_utc") or "") < until]
    made, banned = [], set()
    with conn:
        for target, n_min, n_max, cap, variant in TARGETS:
            legs = _pick(pool, target, n_min, n_max, cap, banned)
            if not legs:
                continue
            total = math.prod(l["odds"] for l in legs)
            p = math.prod(l["p"] for l in legs)
            prof = sorted({l["profile"] for l in legs})
            notes = {"label": f"Meciuri potrivite · cotă ~{target:g}", "segments": True, "paper": True, "risk_acknowledged": True,
                     "reasons": [f"{len(legs)} selecții din meciurile potrivite: fiecare cade într-un profil de meci care a ieșit pe plus "
                                 "la cota Superbet în ambele jumătăți ale istoricului.",
                                 "Profiluri: " + "; ".join(prof[:6]) + ("…" if len(prof) > 6 else ""),
                                 f"Șansa Robotului pentru tot biletul: {p:.1%} · cotă {total:.2f}. Miză {STAKE_U:g}u (urmărit pe hârtie)."]}
            cur = conn.execute(
                """INSERT INTO ticket (kind, variant, created_by, target_odds, total_odds, p_ticket, ev, stake, status, created_at, notes, day)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (KIND, variant, "robot", target, round(total, 2), round(p, 6), round(p * total - 1, 4), STAKE_U, "pending",
                 repo.now_iso(), json.dumps(notes, ensure_ascii=False), today.isoformat()))
            for l in sorted(legs, key=lambda l: l["kickoff_utc"]):
                if l["market"] == "ss":
                    conn.execute("INSERT INTO ticket_leg (ticket_id, prediction_id, match_id, market, selection, odds, odds_source) VALUES (?,?,?,?,?,?,?)",
                                 (cur.lastrowid, None, l["match_id"], "ss|0", l["selection"], l["odds"], "superbet"))
                else:
                    conn.execute("INSERT INTO ticket_leg (ticket_id, prediction_id, match_id, market, selection, odds, odds_source) VALUES (?,?,?,?,?,?,?)",
                                 (cur.lastrowid, l.get("prediction_id"), l["match_id"], f"{l['market']}|{l['line']:g}", l["selection"], l["odds"], "superbet"))
                banned.add(l["match_id"])
            made.append({"target": target, "legs": len(legs), "odds": round(total, 2), "p": round(p, 4)})
    return {"pool": len(pool), "tickets": made}
