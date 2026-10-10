"""Piramida zilnică ~2.00: 1–4 evenimente, reinvestire totală, retrageri parțiale (paper tracker)."""

from __future__ import annotations

import itertools
import json
import math
import sqlite3
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from betpredict.builder.pool import Cand, load_pool, ticket_probability
from betpredict.store import repo

# v4 (research §5): edge ≥ 3%, preferă single-uri (o dublă plătește marja de 2 ori), retragere 50% din profit după
# fiecare câștig, plafon 4 pași (apoi se reia de la miza de bază), pauză 1 zi după 2 pierderi la rând.
RULES: Dict[str, Any] = {
    "target_odds": 2.0, "band": [1.85, 2.2], "max_legs": 3, "min_p": 0.48, "min_ev": 0.03,
    "start_bank": 100.0, "withdraw_steps": [], "withdraw_pct": 0.0, "profit_withdraw_pct": 0.5,
    "max_steps": 4, "pause_after_losses": 2, "leg_penalty": 0.03,
    "target_multiple": 8, "target_withdraw_pct": 0.5,
}


def best_combos(pool: List[Cand], rules=RULES, top: int = 24) -> List[Tuple[List[Cand], float]]:
    lo, hi = rules["band"]
    # probabilitate prudentă (model tras spre piață), ca EV-ul piramidei să nu fie supraestimat
    cands = [c for c in pool if c.healthy and c.grade in ("A", "B") and c.p >= 0.55 and c.p_adj >= 0.55 and 1.15 <= c.odds <= hi]
    best_per_match: Dict[int, Cand] = {}
    for c in cands:
        if c.match_id not in best_per_match or c.p_adj * c.odds > best_per_match[c.match_id].p_adj * best_per_match[c.match_id].odds:
            best_per_match[c.match_id] = c
    cands = sorted(best_per_match.values(), key=lambda c: c.p_adj, reverse=True)[:top]
    out: List[Tuple[List[Cand], float]] = []
    for k in range(1, rules["max_legs"] + 1):
        for combo in itertools.combinations(cands, k):
            o = math.prod(c.odds for c in combo)
            if lo <= o <= hi:
                out.append((list(combo), ticket_probability(list(combo), adjusted=True)))
    # v4: scor = p − 3 pp pe fiecare selecție în plus (single-urile câștigă la egalitate)
    out.sort(key=lambda x: x[1] - rules.get("leg_penalty", 0.0) * (len(x[0]) - 1), reverse=True)
    return out


def pick_pyramid(pool: List[Cand], rules=RULES) -> Dict[str, Any]:
    combos = best_combos(pool, rules)
    if not combos:
        return {"status": "no_bet", "reason": "Nicio combinație de 1–4 selecții sigure în intervalul de cotă 1.85–2.20.", "main": None, "alternatives": []}
    # v4: prima combinație care trece de edge ≥ 3% (în ordinea scorului)
    ok = [(l, p) for l, p in combos if p * math.prod(c.odds for c in l) - 1 >= rules["min_ev"] and p >= rules["min_p"]]
    main, p_main = ok[0] if ok else combos[0]
    o_main = math.prod(c.odds for c in main)
    ev = p_main * o_main - 1
    if p_main < rules["min_p"] or ev < rules["min_ev"]:
        return {"status": "no_bet", "main": None, "alternatives": [],
                "reason": f"Azi fără piramidă: cea mai bună combinație are p={p_main:.0%}, EV={ev:+.1%} (minim p≥{rules['min_p']:.0%}, edge≥{rules['min_ev']:.0%}). Zilele fără piramidă cresc șansa reală a seriei."}
    used = {c.match_id for c in main}
    alts = []
    for legs, p in combos[1:]:
        if used & {c.match_id for c in legs}:
            continue
        if p < rules["min_p"] * 0.95:
            break
        alts.append((legs, p))
        used |= {c.match_id for c in legs}
        if len(alts) == 2:
            break
    return {"status": "pick", "reason": f"Combinație p={p_main:.0%}, EV={ev:+.1%}", "main": (main, p_main), "alternatives": alts}


def _insert_ticket(conn, legs: List[Cand], p: float, variant: str, day: date, created: str) -> int:
    total = math.prod(c.odds for c in legs)
    cur = conn.execute(
        """INSERT INTO ticket (kind, variant, created_by, target_odds, total_odds, p_ticket, ev, stake, status, created_at, notes, day)
           VALUES ('pyramid',?, 'robot', 2.0, ?, ?, ?, 1.0, 'pending', ?, ?, ?)""",
        (variant, round(total, 2), round(p, 6), round(p * total - 1, 4), created,
         json.dumps({"reasons": [f"{len(legs)} selecții, p={p:.0%}"]}, ensure_ascii=False), day.isoformat()),
    )
    tid = cur.lastrowid
    for c in legs:
        conn.execute("INSERT INTO ticket_leg (ticket_id, prediction_id, match_id, market, selection, odds, odds_source) VALUES (?,?,?,?,?,?,?)",
                     (tid, c.prediction_id, c.match_id, f"{c.market}|{c.line:g}", c.selection, c.odds, getattr(c, "odds_source", None)))
    return tid


def build_pyramid_day(conn: sqlite3.Connection, day: date, now: Optional[datetime] = None, replace: bool = False) -> Dict[str, Any]:
    key = f"pyramid.day.{day.isoformat()}"
    prev = repo.get_state(conn, key)
    if prev and not replace and json.loads(prev).get("status") == "pick":
        return {"skipped_existing": True}
    pause = _pause_reason(conn, day)
    res = {"status": "no_bet", "reason": pause, "main": None, "alternatives": []} if pause else pick_pyramid(load_pool(conn, day, now))
    created = repo.now_iso()
    state: Dict[str, Any] = {"status": res["status"], "reason": res["reason"], "main": None, "alternatives": [], "rules": "v4"}
    if res["status"] == "pick":
        p0 = res["main"][1]
        state["streak_odds"] = {str(k): round(p0 ** k, 4) for k in range(1, RULES["max_steps"] + 1)}  # șansa estimată a seriei de N
    with conn:
        if res["status"] == "pick":
            legs, p = res["main"]
            state["main"] = _insert_ticket(conn, legs, p, "principal", day, created)
            state["alternatives"] = [_insert_ticket(conn, l, pp, "alternativa", day, created) for l, pp in res["alternatives"]]
            run = _active_run(conn, day)
            step_no = (conn.execute("SELECT COALESCE(MAX(step_no), 0) FROM pyramid_step WHERE run_id=?",
                                    (run["id"],)).fetchone()[0]) + 1
            conn.execute(
                "INSERT OR IGNORE INTO pyramid_step (run_id, step_no, date, ticket_id, stake, odds, bank_before) VALUES (?,?,?,?,?,?,?)",
                (run["id"], step_no, day.isoformat(), state["main"], run["current_bank"],
                 round(math.prod(c.odds for c in legs), 2), run["current_bank"]),
            )
        repo.set_state(conn, key, json.dumps(state, ensure_ascii=False))
    return state


def _pause_reason(conn: sqlite3.Connection, day: date) -> Optional[str]:
    """Pauză 1 zi după 2 pierderi la rând (ultima decontată ieri sau azi)."""
    from datetime import timedelta

    rows = conn.execute("SELECT status, day FROM ticket WHERE kind='pyramid' AND variant='principal' AND status IN ('won','lost') "
                        "AND day < ? ORDER BY day DESC LIMIT ?", (day.isoformat(), RULES["pause_after_losses"])).fetchall()
    if len(rows) == RULES["pause_after_losses"] and all(r["status"] == "lost" for r in rows) and rows[0]["day"] >= (day - timedelta(days=1)).isoformat():
        return f"Pauză azi: {RULES['pause_after_losses']} pierderi la rând — verificăm calibrarea înainte de un nou pas."
    return None


def _active_run(conn: sqlite3.Connection, day: date) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM pyramid_run WHERE status='active' ORDER BY id DESC LIMIT 1").fetchone()
    if row:
        return row
    conn.execute("INSERT INTO pyramid_run (start_date, start_bank, status, current_step, current_bank, rule_json) VALUES (?,?,?,?,?,?)",
                 (day.isoformat(), RULES["start_bank"], "active", 0, RULES["start_bank"], json.dumps(RULES)))
    return conn.execute("SELECT * FROM pyramid_run WHERE status='active' ORDER BY id DESC LIMIT 1").fetchone()


def advance_pyramid(conn: sqlite3.Connection) -> Dict[str, int]:
    """Aplică rezultatele biletelor principale pe run-ul curent (reinvestire + retrageri)."""
    stats = {"steps": 0}
    with conn:
        steps = conn.execute(
            """SELECT s.*, t.status AS tstatus, t.payout, t.total_odds FROM pyramid_step s JOIN ticket t ON t.id = s.ticket_id
               WHERE s.result IS NULL AND t.status != 'pending' ORDER BY s.date"""
        ).fetchall()
        for s in steps:
            run = conn.execute("SELECT * FROM pyramid_run WHERE id=?", (s["run_id"],)).fetchone()
            bank = run["current_bank"]
            withdrawn = 0.0
            if run["status"] != "active":
                # pas creat înainte ca run-ul să se încheie: doar îl consemnăm
                conn.execute("UPDATE pyramid_step SET result=? WHERE run_id=? AND step_no=?",
                             (s["tstatus"], s["run_id"], s["step_no"]))
            elif s["tstatus"] == "lost":
                conn.execute("UPDATE pyramid_step SET result='lost', bank_after=0 WHERE run_id=? AND step_no=?", (s["run_id"], s["step_no"]))
                conn.execute("UPDATE pyramid_run SET status='lost', current_bank=0 WHERE id=?", (run["id"],))
            else:
                mult = (s["payout"] or 1.0)  # stake 1 → payout = multiplicatorul (void → 1)
                bank = round(bank * mult, 2)
                step = run["current_step"] + (1 if s["tstatus"] == "won" else 0)
                status = "active"
                if s["tstatus"] == "won":  # v4: retragem 50% din profitul pasului
                    withdrawn = round(max(0.0, bank - run["current_bank"]) * RULES.get("profit_withdraw_pct", 0.0), 2)
                    if step in RULES.get("withdraw_steps", []):
                        withdrawn += round((bank - withdrawn) * RULES["withdraw_pct"], 2)
                if s["tstatus"] == "won" and step >= RULES.get("max_steps", 99):  # plafon de pași: încasăm și reluăm
                    withdrawn = round(bank, 2)
                    status = "completed"
                if bank - withdrawn >= RULES["start_bank"] * RULES["target_multiple"]:
                    withdrawn += round((bank - withdrawn) * RULES["target_withdraw_pct"], 2)
                    status = "completed"
                bank = round(bank - withdrawn, 2)
                conn.execute("UPDATE pyramid_step SET result=?, bank_after=?, withdrawn=? WHERE run_id=? AND step_no=?",
                             (s["tstatus"], bank, withdrawn, s["run_id"], s["step_no"]))
                conn.execute("UPDATE pyramid_run SET current_step=?, current_bank=?, withdrawn_total=withdrawn_total+?, status=? WHERE id=?",
                             (step, bank, withdrawn, status, run["id"]))
            stats["steps"] += 1
    return stats
