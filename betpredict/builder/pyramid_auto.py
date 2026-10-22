"""Piramide automate: instrucțiunea zilei (miză + ce faci cu banii) și auto-învățarea regulii de retragere.

Regula de retragere a fiecărei piramide pornește de la cea mai bună variantă din backtest (campion) și e reevaluată
periodic pe pașii urmăriți live (campion / challenger, cu gărzi): schimbăm doar dacă există destui pași decontați
și challenger-ul e mai bun pe ambele jumătăți ale istoricului live, cu o marjă clară."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from betpredict.builder import pyramid as P
from betpredict.builder import pyramid_risk as R
from betpredict.store import repo

TRACKS: Dict[str, Dict[str, Any]] = {
    "2.00": {"prefix": "pyramid", "key": "pyramid.day.", "rules": P.RULES, "name": "Piramida 2.00"},
    "1.20": {"prefix": "pyramid120", "key": P.KEY_120, "rules": P.RULES_120, "name": "Piramida 1.20"},
    "1.40": {"prefix": "pyramid140", "key": P.KEY_140, "rules": P.RULES_140, "name": "Piramida 1.40"},
    "1.60": {"prefix": "pyramid160", "key": P.KEY_160, "rules": P.RULES_160, "name": "Piramida 1.60"},
    "boost": {"prefix": "pyramidboost", "key": P.KEY_BOOST, "rules": P.RULES_BOOST, "name": "Piramida Cote mărite"},
    "mici": {"prefix": "pyramidmici", "key": P.KEY_MICI, "rules": P.RULES_MICI, "name": "Piramida Ligi mici"},
    "r5": {"prefix": "pyramidr5", "key": R.KEY_R5, "rules": R.RULES_R5, "name": "Piramida ~5"},
    "r10": {"prefix": "pyramidr10", "key": R.KEY_R10, "rules": R.RULES_R10, "name": "Piramida ~10"},
}
# variante de retragere încercate ca challenger: (procent din profit retras la fiecare pas, plafon de pași „ia tot”)
CHALLENGERS: List[Tuple[float, int]] = [(0.25, 999), (0.5, 999), (0.75, 999), (1.0, 999), (0.0, 3), (0.0, 4), (0.0, 5), (0.0, 7), (0.5, 4)]
MIN_STEPS = 40          # gardă: minim pași decontați live înainte de orice schimbare
MIN_GAIN = 0.20         # gardă: challenger-ul trebuie să bată campionul cu ≥20% din suma investită
STATE_KEY = "pyramid.rule."


def effective_rules(conn: sqlite3.Connection, track: str) -> Dict[str, Any]:
    """Regulile din cod. Retragerea nu se mai schimbă singură: ce găsește ``review`` e doar o propunere (``suggestion``)."""
    return dict(TRACKS[track]["rules"])


def suggestion(conn: sqlite3.Connection, track: str) -> Optional[Dict[str, Any]]:
    raw = repo.get_state(conn, STATE_KEY + track)
    return json.loads(raw) if raw else None


def advance_all(conn: sqlite3.Connection) -> Dict[str, Any]:
    out = {}
    for t, cfg in TRACKS.items():
        P.ensure_track_tables(conn, cfg["prefix"]) if t != "2.00" else None
        out[t] = P.advance_pyramid(conn, rules=effective_rules(conn, t), run_t=f"{cfg['prefix']}_run", step_t=f"{cfg['prefix']}_step")
    return out


def _lei(x: float) -> str:
    return f"{x:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".") + " lei"


def action(conn: sqlite3.Connection, track: str, today_ticket_id: Optional[int]) -> Dict[str, Any]:
    """Ce faci azi: miza de azi + instrucțiunea pentru banii din pasul anterior."""
    cfg = TRACKS[track]
    pre = cfg["prefix"]
    rules = effective_rules(conn, track)
    start = float(rules["start_bank"])
    last = conn.execute(f"""SELECT s.*, r.status AS rstatus, r.current_bank AS rbank, r.current_step AS rstep FROM {pre}_step s
                            JOIN {pre}_run r ON r.id = s.run_id WHERE s.result IS NOT NULL ORDER BY s.date DESC, s.run_id DESC LIMIT 1""").fetchone()
    today = conn.execute(f"SELECT bank_before, step_no FROM {pre}_step WHERE ticket_id=?", (today_ticket_id,)).fetchone() if today_ticket_id else None
    stake = today["bank_before"] if today else None
    step = today["step_no"] if today else None
    if last is None:
        kind, text = "start", f"Pornește piramida cu {_lei(start)}."
    elif last["result"] == "lost":
        kind, text = "restart", f"Pasul {last['step_no']} a pierdut. Repornești de la treapta 1 cu {_lei(start)}."
    elif last["rstatus"] == "completed":
        kind, text = "take_all", f"Ai ajuns la pasul {last['step_no']}, ultimul: încasezi {_lei(last['withdrawn'] or 0)} și repornești cu {_lei(start)}."
    elif (last["withdrawn"] or 0) > 0:
        kind, text = "withdraw", f"Retrage {_lei(last['withdrawn'])} acum și reinvestește {_lei(last['bank_after'] or 0)}."
    elif last["result"] == "won" and last["step_no"] >= rules.get("suggest_at", 99):
        b = last["bank_after"] or 0
        kind = "suggest"
        text = (f"{last['step_no']} câștiguri la rând. Propunere: poți încasa acum {_lei(b)} (profit {_lei(b - start)}) și reporni cu "
                f"{_lei(start)}, sau continui și reinvestești tot pe biletul de azi. Alegi tu.")
    else:
        kind, text = "reinvest", f"Reinvestește tot: {_lei(last['bank_after'] or 0)} pe biletul de azi."
    today_txt = (f"Azi: pasul {step}, miză {_lei(stake)}." if stake is not None else "Azi nu se joacă: pauză, banii rămân pe loc.")
    pw, cap = rules.get("profit_withdraw_pct", 0.0), rules.get("max_steps", 999)
    sa = rules.get("suggest_at")
    rule_txt = (f"Regula: retragi {int(round(pw * 100))}% din profit la fiecare pas câștigat" if pw else "Regula: reinvestești tot")
    rule_txt += f"; maximum {cap} pași, apoi încasezi și repornești" if cap < 100 else ""
    rule_txt += f". De la pasul {sa} îți propunem să încasezi (cel mai bun punct din backtest), dar decizia e a ta." if sa else "."
    out = {"kind": kind, "text": text, "today": today_txt, "stake": stake, "step": step, "rule": rule_txt, "max_steps": cap,
           "short": {"start": "Pornește", "restart": "Repornește", "take_all": "Ia tot și repornește", "withdraw": "Retrage acum",
                     "reinvest": "Reinvestește", "suggest": "Încasezi sau continui?"}[kind]}
    if kind == "suggest":
        out["cashout"] = round(last["bank_after"] or 0, 2)
    return out


def _sim(seq: List[Tuple[float, bool]], pw: float, cap: int, stake: float = 10.0) -> Tuple[float, float]:
    bank, inv, back, cur = stake, stake, 0.0, 0
    for o, won in seq:
        if won:
            cur += 1
            prof = bank * (o - 1)
            back += prof * pw
            bank += prof * (1 - pw)
            if cur >= cap:
                back += bank; bank, cur = stake, 0; inv += stake
        else:
            bank, cur = stake, 0; inv += stake
    return back + bank - inv, inv


def review(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Campion / challenger pe pașii live decontați. Schimbă regula doar cu gărzi (≥40 pași, mai bun pe ambele jumătăți)."""
    out = {}
    for t, cfg in TRACKS.items():
        pre = cfg["prefix"]
        if t != "2.00":
            P.ensure_track_tables(conn, pre)
        seq = [(r["odds"], r["result"] == "won") for r in conn.execute(
            f"SELECT odds, result FROM {pre}_step WHERE result IN ('won','lost') AND odds IS NOT NULL ORDER BY date, run_id, step_no")]
        cur = effective_rules(conn, t)
        champ = (cur.get("profit_withdraw_pct", 0.0), cur.get("max_steps", 999))
        info: Dict[str, Any] = {"steps": len(seq), "champion": {"withdraw": champ[0], "cap": champ[1]}, "changed": False}
        if len(seq) < MIN_STEPS:
            info["note"] = f"Prea puțini pași live ({len(seq)}/{MIN_STEPS}) — regula rămâne cea din backtest."
            out[t] = info
            continue
        h = len(seq) // 2
        halves = (seq[:h], seq[h:])
        cn = [_sim(x, *champ) for x in halves]
        best = None
        for ch in CHALLENGERS:
            if ch == champ:
                continue
            r = [_sim(x, *ch) for x in halves]
            if all(r[i][0] - cn[i][0] >= MIN_GAIN * max(r[i][1], cn[i][1]) for i in range(2)):
                gain = sum(r[i][0] - cn[i][0] for i in range(2))
                if best is None or gain > best[1]:
                    best = (ch, gain)
        if best:
            ch = best[0]
            # doar propunere (nu se aplică singură): vezi ``suggestion``
            repo.set_state(conn, STATE_KEY + t, json.dumps({"profit_withdraw_pct": ch[0], "max_steps": ch[1], "steps": len(seq),
                                                             "since": repo.now_iso(), "previous": list(champ)}))
            conn.commit()
            info.update({"changed": True, "new": {"withdraw": ch[0], "cap": ch[1]}})
        out[t] = info
    return out
