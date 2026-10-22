"""Piramida zilnică ~2.00: 1–4 evenimente, reinvestire totală, retrageri parțiale (paper tracker)."""

from __future__ import annotations

import itertools
import json
import math
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from betpredict.builder.pool import Cand, load_pool, ticket_probability
from betpredict.store import repo
from betpredict.timeutil import canon_utc


def one_league_each(combo) -> bool:
    """Meciurile din aceeași ligă, în aceeași zi, nu sunt independente. Un bilet ia o singură ligă o dată."""
    ids = [c.league_id for c in combo]
    known = [i for i in ids if i is not None]
    return len(known) == len(set(known))


# v4 (research §5): edge ≥ 3%, preferă single-uri (o dublă plătește marja de 2 ori), pauză 1 zi după 2 pierderi la rând.
# Fără retragere automată: piramida merge până la 7 pași reinvestind tot; de la pasul „suggest_at” (cel mai bun punct de
# încasare din backtest) aplicația doar PROPUNE retragerea, decizia e a ta (cererea lui Alin, 21.10.2026).
RULES: Dict[str, Any] = {
    "target_odds": 2.0, "band": [1.85, 2.2], "max_legs": 3, "min_p": 0.45, "min_ev": -0.06,
    "start_bank": 100.0, "withdraw_steps": [], "withdraw_pct": 0.0, "profit_withdraw_pct": 0.0,
    "max_steps": 7, "suggest_at": 4, "pause_after_losses": 2, "leg_penalty": 0.03,
    "target_multiple": 10**9, "target_withdraw_pct": 0.0,
    "leg_max": 1.40,  # cel mult 1.40 pe selecție (cererea lui Alin, 22.10.2026): ~2.00 din 2–3 selecții sigure
}


def best_combos(pool: List[Cand], rules=RULES, top: int = 24) -> List[Tuple[List[Cand], float]]:
    lo, hi = rules["band"]
    # probabilitate prudentă (model tras spre piață), ca EV-ul piramidei să nu fie supraestimat
    leg_hi = min(hi, rules.get("leg_max", hi))
    leg_lo = max(1.15, lo ** (1 / rules["max_legs"]) * 0.97)
    cands = [c for c in pool if c.playable and c.grade in ("A", "B") and c.p >= 0.55 and c.p_honest >= 0.50 and leg_lo <= c.odds <= leg_hi]
    best_per_match: Dict[int, Cand] = {}
    for c in cands:
        if c.match_id not in best_per_match or c.ev_honest > best_per_match[c.match_id].ev_honest:
            best_per_match[c.match_id] = c
    cands = sorted(best_per_match.values(), key=lambda c: c.p_honest, reverse=True)[:top]
    out: List[Tuple[List[Cand], float]] = []
    for k in range(1, rules["max_legs"] + 1):
        for combo in itertools.combinations(cands, k):
            if not one_league_each(combo):
                continue
            o = math.prod(c.odds for c in combo)
            if lo <= o <= hi:
                out.append((list(combo), math.prod(c.p_honest for c in combo)))  # p onest (blend spre piață)
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
    return {"status": "pick", "reason": f"Combinație p realist={p_main:.0%}, EV realist={ev:+.1%}" + (" — urmărire pe hârtie (EV ≤ 0)" if ev <= 0 else ""), "main": (main, p_main), "alternatives": alts}


def _tuned_rules() -> Dict[str, Any]:
    from betpredict.selflearn import tuned

    return {**RULES, "min_p": tuned("pyramid", "min_p", RULES["min_p"])}  # auto-tuning zilnic (selflearn)


def _insert_ticket(conn, legs: List[Cand], p: float, variant: str, day: date, created: str, target: float = 2.0) -> int:
    total = math.prod(c.odds for c in legs)
    cur = conn.execute(
        """INSERT INTO ticket (kind, variant, created_by, target_odds, total_odds, p_ticket, ev, stake, status, created_at, notes, day)
           VALUES ('pyramid',?, 'robot', ?, ?, ?, ?, 1.0, 'pending', ?, ?, ?)""",
        (variant, target, round(total, 2), round(p, 6), round(p * total - 1, 4), created,
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
    res = {"status": "no_bet", "reason": pause, "main": None, "alternatives": []} if pause else pick_pyramid(load_pool(conn, day, now), _tuned_rules())
    created = repo.now_iso()
    state: Dict[str, Any] = {"status": res["status"], "reason": res["reason"], "main": None, "alternatives": [], "rules": "v4"}
    if res["status"] == "pick":
        p0 = res["main"][1]
        state["streak_odds"] = {str(k): round(p0 ** k, 4) for k in range(1, RULES["max_steps"] + 1)}  # șansa estimată a seriei de N
    with conn:
        if res["status"] == "pick":
            legs, p = res["main"]
            state["main"] = _insert_ticket(conn, legs, p, "principal", day, created)
            # o singură variantă: cea mai bună (alternativele doar încurcau alegerea)
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


def advance_pyramid(conn: sqlite3.Connection, rules: Optional[Dict[str, Any]] = None,
                    run_t: str = "pyramid_run", step_t: str = "pyramid_step") -> Dict[str, int]:
    R = rules or RULES
    """Aplică rezultatele biletelor principale pe run-ul curent (reinvestire + retrageri)."""
    stats = {"steps": 0}
    with conn:
        steps = conn.execute(
            f"""SELECT s.*, t.status AS tstatus, t.payout, t.total_odds FROM {step_t} s JOIN ticket t ON t.id = s.ticket_id
               WHERE s.result IS NULL AND t.status != 'pending' ORDER BY s.date"""
        ).fetchall()
        for s in steps:
            run = conn.execute(f"SELECT * FROM {run_t} WHERE id=?", (s["run_id"],)).fetchone()
            bank = run["current_bank"]
            withdrawn = 0.0
            if run["status"] != "active":
                # pas creat înainte ca run-ul să se încheie: doar îl consemnăm
                conn.execute(f"UPDATE {step_t} SET result=? WHERE run_id=? AND step_no=?",
                             (s["tstatus"], s["run_id"], s["step_no"]))
            elif s["tstatus"] == "lost":
                conn.execute(f"UPDATE {step_t} SET result='lost', bank_after=0 WHERE run_id=? AND step_no=?", (s["run_id"], s["step_no"]))
                conn.execute(f"UPDATE {run_t} SET status='lost', current_bank=0 WHERE id=?", (run["id"],))
            else:
                mult = (s["payout"] or 1.0)  # stake 1 → payout = multiplicatorul (void → 1)
                bank = round(bank * mult, 2)
                step = run["current_step"] + (1 if s["tstatus"] == "won" else 0)
                status = "active"
                if s["tstatus"] == "won":  # v4: retragem 50% din profitul pasului
                    withdrawn = round(max(0.0, bank - run["current_bank"]) * R.get("profit_withdraw_pct", 0.0), 2)
                    if step in R.get("withdraw_steps", []):
                        withdrawn += round((bank - withdrawn) * R["withdraw_pct"], 2)
                if s["tstatus"] == "won" and step >= R.get("max_steps", 99):  # plafon de pași: încasăm și reluăm
                    withdrawn = round(bank, 2)
                    status = "completed"
                if bank - withdrawn >= R["start_bank"] * R["target_multiple"]:
                    withdrawn += round((bank - withdrawn) * R["target_withdraw_pct"], 2)
                    status = "completed"
                bank = round(bank - withdrawn, 2)
                conn.execute(f"UPDATE {step_t} SET result=?, bank_after=?, withdrawn=? WHERE run_id=? AND step_no=?",
                             (s["tstatus"], bank, withdrawn, s["run_id"], s["step_no"]))
                conn.execute(f"UPDATE {run_t} SET current_step=?, current_bank=?, withdrawn_total=withdrawn_total+?, status=? WHERE id=?",
                             (step, bank, withdrawn, status, run["id"]))
            stats["steps"] += 1
    return stats


# Pornire curată (cererea lui Alin, 22.10.2026): seriile active se închid („reset”), biletul de azi devine treapta 1 a unei
# serii noi, iar recordul se numără de la pornire. O singură dată pe pistă (marcaj în ingest_state).
RESET_ID = "2026-10-22"
RESET_TRACKS = ("pyramid120", "pyramid140", "pyramid160", "pyramidboost")


def reset_tracks(conn: sqlite3.Connection, day: date, rules_by_prefix: Dict[str, Dict[str, Any]], reset_id: str = RESET_ID) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for pre, rules in rules_by_prefix.items():
        key = f"pyramid.reset.{pre}.{reset_id}"
        ensure_track_tables(conn, pre)
        if repo.get_state(conn, key):
            continue
        with conn:
            pend = conn.execute(f"""SELECT s.* FROM {pre}_step s JOIN {pre}_run r ON r.id=s.run_id
                                    WHERE r.status='active' AND s.result IS NULL AND s.date=?""", (day.isoformat(),)).fetchone()
            n = conn.execute(f"UPDATE {pre}_run SET status='reset' WHERE status='active'").rowcount
            if pend:
                start = float(rules["start_bank"])
                cur = conn.execute(f"INSERT INTO {pre}_run (start_date, start_bank, status, current_step, current_bank, rule_json) VALUES (?,?,?,?,?,?)",
                                   (day.isoformat(), start, "active", 0, start, json.dumps(rules)))
                conn.execute(f"DELETE FROM {pre}_step WHERE run_id=? AND step_no=?", (pend["run_id"], pend["step_no"]))
                conn.execute(f"INSERT INTO {pre}_step (run_id, step_no, date, ticket_id, stake, odds, bank_before) VALUES (?,?,?,?,?,?,?)",
                             (cur.lastrowid, 1, pend["date"], pend["ticket_id"], start, pend["odds"], start))
            repo.set_state(conn, key, json.dumps({"at": repo.now_iso(), "closed_runs": n, "moved_today": bool(pend)}))
        out[pre] = {"closed_runs": n, "today_is_step_1": bool(pend)}
    return out


# ───────────────────────── Piramida 1.40 (paralelă, stare separată) ─────────────────────────
# Metoda lui Alin (a ajuns manual la pasul 17): 1–4 dintre cele mai sigure selecții, din meciuri diferite, până la cota ~1.40.
# Prioritate = șansa maximă de a trece pasul (nu EV-ul), corectată cu cât de des a intrat de fapt fiecare piață.
# Reinvestire totală, reluare de la banca de start după o pierdere; retragerea e doar propusă.
# Backtest football-data (2020–2026), cota pe selecție ≤ 1.40: UN SINGUR MECI (1.35–1.40, ≥ 65%) e cel mai bun —
# 72% pași câștigați, serie medie 2.6, record 17 — față de 1–2 selecții (71%) și 2 selecții (67%). Când nu există un
# meci potrivit, rezervă: 2 selecții. Scopul: cât mai mulți pași verzi la rând (recordul lui Alin: 17).
RULES_140: Dict[str, Any] = {
    "target_odds": 1.40, "band": [1.35, 1.45], "max_legs": 1, "fallback_legs": 2, "min_leg_p": 0.65, "min_p": 0.62,
    "min_ev": -0.15, "leg_odds": [1.04, 1.40], "drift_max": 0.05, "start_bank": 100.0, "profit_withdraw_pct": 0.0,
    "withdraw_steps": [], "withdraw_pct": 0.0, "max_steps": 20, "suggest_at": 4,  # backtest: „ia tot după 4” = cel mai bun
    "target_multiple": 10**9, "target_withdraw_pct": 0.0,
    "pause_after_losses": 0, "variant": "p140", "alt_variant": "p140_alt",
}
KEY_140 = "pyramid140.day."

# ~1.20: UN SINGUR MECI la cota 1.16–1.25 (≥ 75%); rezervă 2 selecții. Întâi căutăm un meci la care cota a SCĂZUT cu
# ≥ 2% de la deschidere (piața confirmă); dacă nu există, regula de bază. Backtest 2020–2026: 83.5% pași câștigați (bază
# 81%), serie medie 5.0 (bază 4.2), record 47; stabil pe ambele jumătăți (2020–23: 83.2% vs 80.7%, 2023–26: 84.1% vs 81.3%).
# La 1.40 și 1.60 același filtru nu se ține pe ambele jumătăți, deci nu îl folosim acolo.
RULES_120: Dict[str, Any] = {
    **RULES_140, "target_odds": 1.20, "band": [1.16, 1.25], "max_legs": 1, "fallback_legs": 2, "min_leg_p": 0.75, "min_p": 0.72,
    "prefer_drift": -0.02,
    "leg_odds": [1.04, 1.25], "max_steps": 30, "suggest_at": 10, "variant": "p120", "alt_variant": "p120_alt",
}
KEY_120 = "pyramid120.day."
# ~1.60: 2 selecții de cel mult 1.40 (≥ 70%). Backtest: 60% pași câștigați, record 13 (3 selecții: 59%, 2–3: 60.5%).
RULES_160: Dict[str, Any] = {
    **RULES_140, "target_odds": 1.60, "band": [1.52, 1.70], "max_legs": 2, "fallback_legs": None, "min_leg_p": 0.70, "min_p": 0.50,
    "leg_odds": [1.05, 1.40], "max_steps": 15, "suggest_at": 4, "variant": "p160", "alt_variant": "p160_alt",
}
KEY_160 = "pyramid160.day."
REL_MIN_P, REL_PRIOR = 0.70, 200   # corecția pe piață: predicțiile decontate cu șansă ≥ 70%, micșorată (200 pseudo-selecții)


# ───────────── cotele mărite Superbet: singura sursă de EV pozitiv măsurată pe rezultate reale ─────────────
# 11–21.10.2026: cotele mărite obișnuite (nu Super Cota) 74 decontate, 51% intrate, ROI +34%; evaluate sigur, cu EV > 0
# și cota 1.40–3.20: 30 decontate, 70% intrate, ROI +75%, ofertă în 9 din 11 zile (modelul le dă ~50%, intră 70%).
# Super Cota: ROI −12% (nu le folosim). Prețul e subvenționat de Superbet (marketing). Eșantion mic: urmărit zilnic.
BOOST_MIN_P = 0.40


def boost_cands(conn: sqlite3.Connection, day: date, now: Optional[datetime] = None, super_cota: bool = False) -> List[Cand]:
    """Cotele mărite obișnuite ale zilei (ora României), evaluate sigur (piață/model), cu EV > 0 și nesuspecte.
    ``super_cota``: rezerva — Super Cota cu EV > 0 și șansă ≥ 50% (11–21.10: 14 decontate, 71% intrate, ROI +9.5%)."""
    from zoneinfo import ZoneInfo

    from betpredict.ingest.boosts import EV_SUSPECT

    now = now or datetime.now(timezone.utc)
    ro = ZoneInfo("Europe/Bucharest")
    lo = max(now, datetime(day.year, day.month, day.day, tzinfo=ro).astimezone(timezone.utc))
    hi = datetime(day.year, day.month, day.day, tzinfo=ro).astimezone(timezone.utc) + timedelta(days=1)
    try:
        rows = conn.execute(
            """SELECT b.match_id, b.name, b.price, b.p_fair, b.ev, m.kickoff_utc, m.home_name, m.away_name, m.league_id, l.name league
               FROM sb_boost b JOIN match m ON m.id=b.match_id LEFT JOIN league l ON l.id=m.league_id
               WHERE (b.kind = 'super_cota') = ? AND b.ev > 0 AND b.ev <= ? AND b.p_fair >= ? AND b.result IS NULL
                 AND (b.method LIKE 'piață%' OR b.method LIKE 'model%') AND m.kickoff_utc > ? AND m.kickoff_utc <= ?
                 AND b.last_seen >= ?""",
            (1 if super_cota else 0, EV_SUSPECT, max(BOOST_MIN_P, 0.50) if super_cota else BOOST_MIN_P,
             canon_utc((lo + timedelta(minutes=10)).isoformat()), canon_utc(hi.isoformat()),
             canon_utc((now - timedelta(hours=8)).isoformat()))).fetchall()
    except sqlite3.Error:
        return []
    return [Cand(None, r["match_id"], r["league_id"], r["league"], r["kickoff_utc"], r["home_name"], r["away_name"], "boost", 0.0,
                 (f"Super Cota {r['name'].replace('SC-', '')}" if super_cota else r["name"]), float(r["price"]), float(r["p_fair"]), float(r["ev"]), "A", 80, True, p_market=float(r["p_fair"]),
                 odds_source="superbet") for r in rows]


def reliability(conn: sqlite3.Connection) -> Dict[Tuple[str, float, str], float]:
    """Pe piață × linie × selecție: (intrate − șanse promise) / (n + 200) pe predicțiile decontate cu șansă ≥ 70%.
    Pozitiv = piața intră mai des decât spune Robotul (o preferăm în piramide), negativ = mai rar."""
    out: Dict[Tuple[str, float, str], float] = {}
    try:
        rows = conn.execute("""SELECT market, line, selection, COUNT(*), SUM(CASE WHEN result='won' THEN 1.0 ELSE 0 END) - SUM(p_calibrated)
                               FROM prediction WHERE result IN ('won','lost') AND p_calibrated >= ? GROUP BY market, line, selection""",
                            (REL_MIN_P,)).fetchall()
    except sqlite3.Error:
        return out
    for m, ln, sel, n, d in rows:
        out[(m, float(ln or 0), sel)] = (d or 0.0) / (n + REL_PRIOR)
    return out


def q_leg(c: Cand, rel: Optional[Dict[Tuple[str, float, str], float]]) -> float:
    """Șansa folosită la alegere: cea onestă + corecția pieței din rezultate."""
    return max(0.01, min(0.99, c.p_honest + (rel or {}).get((c.market, float(c.line or 0), c.selection), 0.0)))


def ensure_track_tables(conn: sqlite3.Connection, prefix: str) -> None:
    conn.executescript(
        f"""CREATE TABLE IF NOT EXISTS {prefix}_run (
             id INTEGER PRIMARY KEY AUTOINCREMENT, start_date TEXT NOT NULL, start_bank REAL NOT NULL,
             status TEXT NOT NULL DEFAULT 'active', current_step INTEGER NOT NULL DEFAULT 0, current_bank REAL NOT NULL,
             withdrawn_total REAL NOT NULL DEFAULT 0, rule_json TEXT);
           CREATE TABLE IF NOT EXISTS {prefix}_step (
             run_id INTEGER NOT NULL REFERENCES {prefix}_run(id) ON DELETE CASCADE, step_no INTEGER NOT NULL,
             date TEXT NOT NULL, ticket_id INTEGER REFERENCES ticket(id), stake REAL, odds REAL, result TEXT,
             bank_before REAL, bank_after REAL, withdrawn REAL DEFAULT 0, PRIMARY KEY (run_id, step_no));"""
    )


def ensure_140_tables(conn: sqlite3.Connection) -> None:
    ensure_track_tables(conn, "pyramid140")


def _leg_ok_140(c: Cand, r=RULES_140) -> bool:
    lo, hi = r["leg_odds"]
    if not (c.playable and lo <= c.odds <= hi and c.p_honest >= r["min_leg_p"]):
        return False
    if c.drift is not None and c.drift > r["drift_max"]:  # cota a crescut >5% de la deschidere
        return False
    return not getattr(c, "price_suspect", False)


def best_combos_140(pool: List[Cand], rules=RULES_140, top: int = 30, rel: Optional[Dict] = None) -> List[Tuple[List[Cand], float]]:
    """Combinațiile din banda de cotă, după șansa comună maximă. Din fiecare meci intră până la 3 selecții (nu doar cea
    mai sigură, care are de obicei cota cea mai mică), dar pe bilet un meci apare o singură dată."""
    lo, hi = rules["band"]
    # cota minimă pe selecție ca banda să se poată atinge cu cel mult max_legs selecții (altfel cele mai sigure 30 au
    # toate cota ~1.05–1.15 și la 1.60 nu iese nicio combinație)
    floor = lo ** (1 / rules["max_legs"]) * 0.97
    per_match: Dict[int, List[Cand]] = {}
    for c in pool:
        if _leg_ok_140(c, rules) and floor <= c.odds <= hi:
            per_match.setdefault(c.match_id, []).append(c)
    allc: List[Cand] = []
    for cs in per_match.values():
        cs.sort(key=lambda c: (q_leg(c, rel), c.odds_source == "superbet"), reverse=True)
        allc.extend(cs[:3])
    cands = sorted(allc, key=lambda c: q_leg(c, rel), reverse=True)[:top]
    out: List[Tuple[List[Cand], float]] = []
    for k in range(1, rules["max_legs"] + 1):
        for combo in itertools.combinations(cands, k):
            if len({c.match_id for c in combo}) < k or not one_league_each(combo):
                continue
            o = math.prod(c.odds for c in combo)
            if lo <= o <= hi:
                out.append((list(combo), math.prod(q_leg(c, rel) for c in combo)))
    # prioritate: șansa comună maximă; la egalitate (0.1 pp) cote Superbet, apoi EV
    out.sort(key=lambda x: (round(x[1], 3), sum(c.odds_source == "superbet" for c in x[0]),
                            x[1] * math.prod(c.odds for c in x[0]) - 1), reverse=True)
    return out


def pick_pyramid_140(pool: List[Cand], rules=RULES_140, rel: Optional[Dict] = None) -> Dict[str, Any]:
    pd = rules.get("prefer_drift")
    if pd is not None:  # întâi meciurile la care piața a împins cota în jos; altfel regula de bază
        steam = [c for c in pool if c.drift is not None and c.drift <= pd]
        r = pick_pyramid_140(steam, {**rules, "prefer_drift": None}, rel) if steam else None
        if r and r["status"] == "pick":
            r["reason"] += f" · cota a scăzut cu cel puțin {abs(pd):.0%} de la deschidere (piața confirmă)"
            return r
        rules = {**rules, "prefer_drift": None}
    combos = [(l, p) for l, p in best_combos_140(pool, rules, rel=rel)
              if p >= rules["min_p"] and p * math.prod(c.odds for c in l) - 1 >= rules["min_ev"]]
    if not combos and rules.get("fallback_legs"):  # niciun meci singur potrivit azi: rezerva cu mai multe selecții
        rules = {**rules, "max_legs": rules["fallback_legs"]}
        combos = [(l, p) for l, p in best_combos_140(pool, rules, rel=rel)
                  if p >= rules["min_p"] and p * math.prod(c.odds for c in l) - 1 >= rules["min_ev"]]
    t = f"{rules['target_odds']:.2f}"
    if not combos:
        lo, hi = rules["band"]
        return {"status": "no_bet", "main": None, "alternatives": [],
                "reason": f"Azi fără Piramida {t}: nicio combinație de 1–{rules['max_legs']} selecții cu șanse ≥{rules['min_leg_p']:.0%} "
                          f"fiecare în cota {lo:g}–{hi:g}."}
    main, p_main = combos[0]
    used = {c.match_id for c in main}
    alts = []
    for legs, p in combos[1:]:
        if used & {c.match_id for c in legs}:
            continue
        alts.append((legs, p))
        used |= {c.match_id for c in legs}
        if len(alts) == 2:
            break
    ev = p_main * math.prod(c.odds for c in main) - 1
    return {"status": "pick", "main": (main, p_main), "alternatives": alts,
            "reason": f"{len(main)} {'selecție sigură' if len(main) == 1 else 'selecții sigure'}, șansă {p_main:.0%} (corectată cu cât intră "
                      f"piața de fapt), EV {ev:+.1%}"}


def _build_track_day(conn: sqlite3.Connection, day: date, now: Optional[datetime], replace: bool, prefix: str, key_prefix: str,
                     rules: Dict[str, Any], picker, label: str) -> Dict[str, Any]:
    ensure_track_tables(conn, prefix)
    key = f"{key_prefix}{day.isoformat()}"
    prev = repo.get_state(conn, key)
    if prev and not replace and json.loads(prev).get("status") == "pick":
        return {"skipped_existing": True}
    res = picker(load_pool(conn, day, now), rules)
    k = int(rules.get("pause_after_losses") or 0)
    if k and res["status"] == "pick":
        from datetime import timedelta

        last = conn.execute("SELECT status, day FROM ticket WHERE kind='pyramid' AND variant=? AND status IN ('won','lost') AND day < ? "
                            "ORDER BY day DESC LIMIT ?", (rules["variant"], day.isoformat(), k)).fetchall()
        if len(last) == k and all(r["status"] == "lost" for r in last) and last[0]["day"] >= (day - timedelta(days=1)).isoformat():
            # pauză automată o zi după k pierderi la rând (ziua următoare reia de la treapta 1)
            res = {"status": "pause", "reason": f"Pauză azi: {k} pierderi la rând. Reluăm mâine de la treapta 1."}
    created = repo.now_iso()
    state: Dict[str, Any] = {"status": res["status"], "reason": res["reason"], "main": None, "alternatives": [], "rules": label}
    with conn:
        if res["status"] == "pick":
            legs, p = res["main"]
            state["main"] = _insert_ticket(conn, legs, p, rules["variant"], day, created, rules["target_odds"])
            # o singură variantă: cea mai bună (alternativele doar încurcau alegerea)
            run = conn.execute(f"SELECT * FROM {prefix}_run WHERE status='active' ORDER BY id DESC LIMIT 1").fetchone()
            if not run:
                conn.execute(f"INSERT INTO {prefix}_run (start_date, start_bank, status, current_step, current_bank, rule_json) VALUES (?,?,?,?,?,?)",
                             (day.isoformat(), rules["start_bank"], "active", 0, rules["start_bank"], json.dumps(rules)))
                run = conn.execute(f"SELECT * FROM {prefix}_run WHERE status='active' ORDER BY id DESC LIMIT 1").fetchone()
            step_no = conn.execute(f"SELECT COALESCE(MAX(step_no), 0) FROM {prefix}_step WHERE run_id=?", (run["id"],)).fetchone()[0] + 1
            conn.execute(f"INSERT OR IGNORE INTO {prefix}_step (run_id, step_no, date, ticket_id, stake, odds, bank_before) VALUES (?,?,?,?,?,?,?)",
                         (run["id"], step_no, day.isoformat(), state["main"], run["current_bank"],
                          round(math.prod(c.odds for c in legs), 2), run["current_bank"]))
        repo.set_state(conn, key, json.dumps(state, ensure_ascii=False))
    return state


def _safe_picker(conn: sqlite3.Connection, day: date, now: Optional[datetime]):
    """Întâi o combinație care conține o cotă mărită cu EV > 0 (dacă se potrivește în bandă), altfel regula piramidei."""
    rel = reliability(conn)
    boosts = boost_cands(conn, day, now)

    def pick(pool, r):
        if boosts:
            combos = [(l, p) for l, p in best_combos_140(pool + boosts, {**r, "max_legs": max(r["max_legs"], 1)}, rel=rel)
                      if any(c.market == "boost" for c in l) and p >= r["min_p"]]
            if combos:
                legs, p = combos[0]
                return {"status": "pick", "main": (legs, p), "alternatives": [],
                        "reason": f"Cotă mărită Superbet cu EV pozitiv în banda piramidei: șansă {p:.0%}, EV {p * math.prod(c.odds for c in legs) - 1:+.1%}"}
        return pick_pyramid_140(pool, r, rel)
    return pick


def build_pyramid_140_day(conn: sqlite3.Connection, day: date, now: Optional[datetime] = None, replace: bool = False) -> Dict[str, Any]:
    return _build_track_day(conn, day, now, replace, "pyramid140", KEY_140, RULES_140, _safe_picker(conn, day, now), "p140")


def build_pyramid_120_day(conn: sqlite3.Connection, day: date, now: Optional[datetime] = None, replace: bool = False) -> Dict[str, Any]:
    return _build_track_day(conn, day, now, replace, "pyramid120", KEY_120, RULES_120, _safe_picker(conn, day, now), "p120")


# Piramida „Cote mărite +EV”: un singur pariu pe zi, cota mărită obișnuită cu EV > 0 și cea mai mare șansă (≥ 40%),
# cota 1.25–3.20. Singura piramidă cu EV pozitiv pe pas în datele reale (vezi mai sus). Serii scurte, dar fiecare pas e pe plus.
RULES_BOOST: Dict[str, Any] = {
    **RULES_140, "target_odds": 2.0, "band": [1.25, 3.20], "max_legs": 1, "fallback_legs": None, "min_leg_p": BOOST_MIN_P,
    "min_p": BOOST_MIN_P, "min_ev": 0.0, "leg_odds": [1.25, 3.20], "max_steps": 10, "suggest_at": 3, "prefer_drift": None,
    "variant": "pboost", "alt_variant": "pboost_alt",
}
KEY_BOOST = "pyramidboost.day."


def pick_pyramid_boost(pool: List[Cand], rules=RULES_BOOST) -> Dict[str, Any]:
    cands = sorted([c for c in pool if c.market == "boost" and rules["leg_odds"][0] <= c.odds <= rules["leg_odds"][1]],
                   key=lambda c: (c.p, c.ev), reverse=True)
    if not cands:
        return {"status": "no_bet", "main": None, "alternatives": [],
                "reason": "Azi fără Piramida Cote mărite: nicio cotă mărită obișnuită cu EV pozitiv (cota 1.25–3.20). Pauza nu rupe seria."}
    c = cands[0]
    return {"status": "pick", "main": ([c], c.p), "alternatives": [],
            "reason": f"Cota mărită {c.selection} @{c.odds:.2f}: șansă {c.p:.0%}, EV {c.ev:+.1%} (prețul Superbet peste șansa reală)"}


def build_pyramid_boost_day(conn: sqlite3.Connection, day: date, now: Optional[datetime] = None, replace: bool = False) -> Dict[str, Any]:
    """Întâi cotele mărite obișnuite cu EV > 0; dacă azi nu există, rezerva: Super Cota cu EV > 0 și șansă ≥ 50%."""
    boosts = boost_cands(conn, day, now)

    def pick(_pool, r):
        res = pick_pyramid_boost(boosts, r)
        if res["status"] != "pick":
            res2 = pick_pyramid_boost(boost_cands(conn, day, now, super_cota=True), r)
            if res2["status"] == "pick":
                res2["reason"] += " · rezervă: azi nu e nicio cotă mărită obișnuită cu EV pozitiv"
                return res2
        return res
    return _build_track_day(conn, day, now, replace, "pyramidboost", KEY_BOOST, RULES_BOOST, pick, "pboost")


def build_pyramid_160_day(conn: sqlite3.Connection, day: date, now: Optional[datetime] = None, replace: bool = False) -> Dict[str, Any]:
    return _build_track_day(conn, day, now, replace, "pyramid160", KEY_160, RULES_160, _safe_picker(conn, day, now), "p160")


def advance_pyramid_140(conn: sqlite3.Connection) -> Dict[str, int]:
    ensure_140_tables(conn)
    return advance_pyramid(conn, rules=RULES_140, run_t="pyramid140_run", step_t="pyramid140_step")


# ───────────────────────── Piramida 2.00 Ligi mici (paralelă, stare separată) ─────────────────────────
# Din grila de backtest: 2–3 favoriți 1X2 din League One / League Two / National League, cotă totală ~2.00, cote în creștere
# permise. Reinvestire totală până la 9 pași; de la 7 câștiguri la rând (cel mai bun în backtest) încasarea e propusă.
SMALL_LEAGUES = {"league one", "league two", "national league"}
RULES_MICI: Dict[str, Any] = {
    "target_odds": 2.0, "band": [1.85, 2.2], "min_legs": 2, "max_legs": 3, "min_leg_p": 0.50, "leg_odds": [1.15, 1.40],
    "start_bank": 100.0, "profit_withdraw_pct": 0.0, "withdraw_steps": [], "withdraw_pct": 0.0, "max_steps": 9, "suggest_at": 7,
    "target_multiple": 10**9, "target_withdraw_pct": 0.0, "pause_after_losses": 2, "variant": "pmici", "alt_variant": "pmici_alt",
    "leagues": sorted(SMALL_LEAGUES),
}
KEY_MICI = "pyramidmici.day."


def _leg_ok_mici(c: Cand, r=RULES_MICI) -> bool:
    lo, hi = r["leg_odds"]
    return (c.playable and (c.league or "").strip().lower() in SMALL_LEAGUES and c.market == "1x2"
            and c.selection in ("HOME", "AWAY") and lo <= c.odds <= hi and c.p_honest >= r["min_leg_p"]
            and not getattr(c, "price_suspect", False))


def pick_pyramid_mici(pool: List[Cand], rules=RULES_MICI) -> Dict[str, Any]:
    lo, hi = rules["band"]
    per_match: Dict[int, Cand] = {}
    for c in pool:
        if not _leg_ok_mici(c, rules):
            continue
        b = per_match.get(c.match_id)
        key = (c.odds_source == "superbet", c.p_honest)  # preferăm cota Superbet
        if b is None or key > (b.odds_source == "superbet", b.p_honest):
            per_match[c.match_id] = c
    cands = sorted(per_match.values(), key=lambda c: c.p_honest, reverse=True)[:20]
    combos: List[Tuple[List[Cand], float]] = []
    for k in range(rules["min_legs"], rules["max_legs"] + 1):
        for combo in itertools.combinations(cands, k):
            if not one_league_each(combo):
                continue
            if lo <= math.prod(c.odds for c in combo) <= hi:
                combos.append((list(combo), math.prod(c.p_honest for c in combo)))
    combos.sort(key=lambda x: (round(x[1], 3), sum(c.odds_source == "superbet" for c in x[0])), reverse=True)
    if not combos:
        return {"status": "no_bet", "main": None, "alternatives": [],
                "reason": "Azi fără Piramida Ligi mici: nu sunt 2–3 favoriți din League One / League Two / National League pentru cota ~2.00."}
    main, p_main = combos[0]
    used = {c.match_id for c in main}
    alts = []
    for legs, p in combos[1:]:
        if used & {c.match_id for c in legs}:
            continue
        alts.append((legs, p)); used |= {c.match_id for c in legs}
        if len(alts) == 2:
            break
    ev = p_main * math.prod(c.odds for c in main) - 1
    return {"status": "pick", "main": (main, p_main), "alternatives": alts,
            "reason": f"{len(main)} favoriți din ligi mici, șansă realistă {p_main:.0%}, EV {ev:+.1%}"}


def build_pyramid_mici_day(conn: sqlite3.Connection, day: date, now: Optional[datetime] = None, replace: bool = False) -> Dict[str, Any]:
    return _build_track_day(conn, day, now, replace, "pyramidmici", KEY_MICI, RULES_MICI, pick_pyramid_mici, "pmici")


def advance_pyramid_mici(conn: sqlite3.Connection) -> Dict[str, int]:
    ensure_track_tables(conn, "pyramidmici")
    return advance_pyramid(conn, rules=RULES_MICI, run_t="pyramidmici_run", step_t="pyramidmici_step")
