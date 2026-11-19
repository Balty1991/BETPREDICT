"""„Analiza zilei”: ce i-ar spune un analist bun pariorului în fiecare dimineață, din date (fără texte inventate).

Calitatea zilei (câte meciuri de cluburi, internaționale, noaptea), biletele de ~10 ale zilei și pasul piramidei, cum au mers
piețele recomandate în ultimele 30 de zile (``rec_monitor``), avertismente, cât să pui pe fiecare produs și ce a ieșit ieri.
Totul e cinstit: marja Superbet e reală, deci miza rămâne mică și nu se „recuperează” după o zi proastă.
→ ``api/brief/today.json``."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from betpredict.timeutil import RO_TZ, canon_utc, parse_utc, ro_day_bounds_utc, ro_today

SCHEMA = "betpredict.brief.v1"
WEEKDAYS = ("luni", "marți", "miercuri", "joi", "vineri", "sâmbătă", "duminică")
DAY_FROM_HOUR_RO = 10          # biletele se fac doar din meciurile de la 10:00 la 24:00 ora României
THIN_CLUB = 15                 # sub atâtea meciuri de cluburi ziua: zi slabă
RICH_CLUB = 40                 # de la atâtea (și destule selecții recomandate): zi bună
THIN_REC = 6                   # meciuri cu selecții recomandate azi, sub care biletul de ~10 iese greu
HOT_ROI, COLD_ROI, MIN_SHOW_N = 0.03, -0.03, 30
SHORT_P_REAL = 0.085           # șansa realistă a unui bilet de ~10 (8–9%, măsurat)
PCT = {"short": (0.01, 0.02), "long": 0.005, "pyramid_bank": 0.05, "day_cap": 0.05}


def _pct(v: Optional[float], d: int = 0, sign: bool = False) -> str:
    if v is None:
        return "—"
    s = f"{v * 100:+.{d}f}%" if sign else f"{v * 100:.{d}f}%"
    return s.replace(".", ",")


def _num(v: float, d: int = 2) -> str:
    return f"{v:,.{d}f}".replace(",", " ").replace(".", ",").replace(" ", ".")


def _n(k: int, one: str, many: str) -> str:
    return f"{k} {one if k == 1 else many}"


def _hour_ro(ts: str) -> Optional[int]:
    dt = parse_utc(ts)
    return dt.astimezone(RO_TZ).hour if dt else None


def _sel_label(sel: str) -> str:
    from betpredict.builder.super_tickets import SEL_LABEL

    if "|" in (sel or ""):
        return "Peste 0.5 goluri + peste 7.5 cornere"
    return SEL_LABEL.get(sel, sel)


# ---------------------------------------------------------------- calitatea zilei
def day_quality(conn: sqlite3.Connection, today: date, now: datetime) -> Dict[str, Any]:
    from betpredict.builder.super_tickets import INTL

    start, end = ro_day_bounds_utc(today)
    rows = conn.execute("""SELECT m.id, m.kickoff_utc, m.league_id, COALESCE(l.name,'') FROM match m LEFT JOIN league l ON l.id=m.league_id
                           WHERE m.kickoff_utc>=? AND m.kickoff_utc<?""", (start, end)).fetchall()
    club = [r for r in rows if not INTL.search(r[3])]
    intl = len(rows) - len(club)
    night = sum(1 for r in club if (_hour_ro(r[1]) or 0) < DAY_FROM_HOUR_RO)
    day_club = [r for r in club if (_hour_ro(r[1]) or 0) >= DAY_FROM_HOUR_RO]
    rec_matches = _rec_matches_today(conn, today, now)
    if len(day_club) < THIN_CLUB or (rec_matches is not None and rec_matches < THIN_REC):
        level, label = "slaba", "Zi slabă"
    elif len(day_club) >= RICH_CLUB and (rec_matches is None or rec_matches >= 15):
        level, label = "buna", "Zi bună"
    else:
        level, label = "normala", "Zi obișnuită"
    intl_break = intl >= 5 and intl >= len(club) * 0.5
    nl = len({r[2] for r in day_club})
    bits = [f"{_n(len(day_club), 'meci', 'meciuri')} de cluburi între 10 și 24"]
    if night:
        bits.append(f"{night} noaptea")
    if intl:
        bits.append(f"{intl} internațional/amical" if intl == 1 else f"{intl} internaționale/amicale")
    if rec_matches is not None:
        bits.append(f"{rec_matches} cu selecții recomandate")
    text = f"{label}: " + ", ".join(bits) + f", din {_n(nl, 'ligă', 'ligi')}."
    if intl_break:
        text += " Pauză internațională: puține meciuri de cluburi, iar la naționale cotele au ieșit mai prost (−8% față de +6%)."
    return {"level": level, "label": label, "club_day": len(day_club), "night": night, "intl": intl, "total": len(rows),
            "leagues": len({r[2] for r in day_club}), "rec_matches": rec_matches, "intl_break": intl_break, "text": text}


def _rec_matches_today(conn: sqlite3.Connection, today: date, now: datetime) -> Optional[int]:
    """Câte meciuri de cluburi de azi (10–24, încă neîncepute) au cel puțin o selecție recomandată jucabilă."""
    from betpredict.builder import super_tickets as S

    start, end = ro_day_bounds_utc(today)
    lo = max(canon_utc((parse_utc(start) + timedelta(hours=DAY_FROM_HOUR_RO)).isoformat()) or "", canon_utc(now.isoformat()) or "")
    try:
        cands = S.load_recommended(conn, now)
    except sqlite3.Error:
        return None
    return len({c.match_id for c in cands if lo <= (c.kickoff_utc or "") < end and not S.is_intl(c) and S.leg_ok(c)})


# ---------------------------------------------------------------- biletele zilei
def _legs(conn: sqlite3.Connection, tid: int) -> List[Dict[str, Any]]:
    rows = conn.execute("""SELECT l.selection, l.odds, l.result, m.home_name, m.away_name, m.kickoff_utc, COALESCE(g.name,'')
                           FROM ticket_leg l LEFT JOIN match m ON m.id=l.match_id LEFT JOIN league g ON g.id=m.league_id
                           WHERE l.ticket_id=? ORDER BY m.kickoff_utc""", (tid,)).fetchall()
    return [{"label": _sel_label(r[0]), "odds": round(r[1] or 0, 2), "result": r[2], "home": r[3], "away": r[4], "kickoff_utc": r[5],
             "league": r[6]} for r in rows]


def short_tickets(conn: sqlite3.Connection, today: date, now: datetime) -> Dict[str, Any]:
    from betpredict.builder import super_tickets as S
    from betpredict.store import repo

    since = S.TICKETS_RESET_AT if canon_utc(now.isoformat()) >= S.TICKETS_RESET_AT else ""
    rows = conn.execute("""SELECT id, total_odds, p_ticket, ev, status, notes FROM ticket WHERE kind=? AND variant IN ('s10')
                           AND day=? AND status!='replaced' AND created_at>=? ORDER BY id""", (S.KIND, today.isoformat(), since)).fetchall()
    out = []
    for r in rows:
        notes = json.loads(r[5] or "{}")
        legs = _legs(conn, r[0])
        kinds: Dict[str, int] = {}
        for x in legs:
            kinds[x["label"]] = kinds.get(x["label"], 0) + 1
        mix = ", ".join(f"{n}× {k}" for k, n in sorted(kinds.items(), key=lambda kv: -kv[1]))
        p = r[2] or 0.0
        first = min((x["kickoff_utc"] for x in legs if x["kickoff_utc"]), default=None)
        out.append({"id": r[0], "odds": round(r[1] or 0, 2), "payout": notes.get("payout_bonus"), "bonus": notes.get("superbonus"),
                    "p": round(p, 4), "ev": r[3], "status": r[4], "legs": legs, "n_legs": len(legs), "first_kickoff": first,
                    "why": [f"{len(legs)} selecții din piețele recomandate: {mix}.",
                            f"Șansa estimată {_pct(p, 1)}; realist ~{_pct(SHORT_P_REAL)} (cam 1 bilet din 12 iese). "
                            "Cele mai bune structuri: 5–7 selecții de 1,35–1,65."]})
    note = None
    if not out:
        try:
            st = json.loads(repo.get_state(conn, f"super.short.{today.isoformat()}") or "null")
        except (sqlite3.Error, ValueError):
            st = None
        note = (f"Azi nu e bilet de ~10: doar {st.get('matches', 0)} meciuri potrivite (cluburi, 10–24, piețe recomandate). "
                "Nu forțăm un bilet din meciuri slabe." if st else "Biletul de ~10 al zilei nu e încă generat.")
    long_rows = conn.execute("""SELECT variant, total_odds FROM ticket WHERE kind=? AND status='pending' AND variant NOT IN ('s10')
                                AND created_at>=?""", (S.KIND, since)).fetchall()
    by_v: Dict[str, int] = {}
    for v, _ in long_rows:
        by_v[v] = by_v.get(v, 0) + 1
    targets = ", ".join(f"{n}× ~{_num(float(v[1:]), 0)}" for v, n in sorted(by_v.items(), key=lambda kv: int(kv[0][1:]) if kv[0][1:].isdigit() else 0))
    return {"short": out, "short_note": note, "long_active": len(long_rows),
            "long_note": (f"{len(long_rows)} bilete lungi în joc ({targets}), cu SuperBonus." if long_rows else "Niciun bilet lung în joc acum.")}


def _short_streak(conn: sqlite3.Connection, now: datetime) -> int:
    """Câte bilete de ~10 la rând s-au pierdut (cele mai recente)."""
    from betpredict.builder import super_tickets as S

    n = 0  # faptic, și peste noul început al statisticilor
    for (st,) in conn.execute("SELECT status FROM ticket WHERE kind=? AND variant='s10' AND status IN ('won','lost') AND created_at<=? "
                              "ORDER BY COALESCE(settled_at, created_at) DESC, id DESC", (S.KIND, canon_utc(now.isoformat()))):
        if st != "lost":
            break
        n += 1
    return n


# ---------------------------------------------------------------- piramida cotă 2
def pyramid_state(conn: sqlite3.Connection, today: date) -> Dict[str, Any]:
    from betpredict.builder.pyramid import CORNER2_SINCE, KEY_120, RULES_CORNER2
    from betpredict.store import repo

    frac = float(RULES_CORNER2.get("stake_fraction") or 0.5)
    start_bank = float(RULES_CORNER2.get("start_bank") or 100.0)
    try:
        st = json.loads(repo.get_state(conn, f"{KEY_120}{today.isoformat()}") or "null") or {}
        run = conn.execute("SELECT status, current_step, current_bank, start_bank FROM pyramid120_run WHERE status!='reset' "
                           "AND start_date>=? ORDER BY rowid DESC LIMIT 1", (CORNER2_SINCE,)).fetchone()
        rec = conn.execute("SELECT MAX(current_step) FROM pyramid120_run WHERE status!='reset' AND start_date>=?", (CORNER2_SINCE,)).fetchone()
    except sqlite3.Error:
        st, run, rec = {}, None, None
    active = bool(run and run[0] == "active")
    step = (run[1] + 1) if active else 1
    bank = float(run[2]) if active else start_bank
    out: Dict[str, Any] = {"status": st.get("status") or "unknown", "reason": st.get("reason"), "step": step, "bank": round(bank, 2),
                           "stake": round(bank * frac, 2), "stake_fraction": frac, "restart": not active,
                           "last_run": run[0] if run else None, "record": (rec[0] or 0) if rec else 0, "ticket": None}
    tid = st.get("main")
    if tid:
        t = conn.execute("SELECT total_odds, p_ticket, status FROM ticket WHERE id=?", (tid,)).fetchone()
        if t:
            out["ticket"] = {"id": tid, "odds": round(t[0] or 0, 2), "p": round(t[1] or 0, 4), "status": t[2], "legs": _legs(conn, tid)}
    if out["ticket"]:
        tk = out["ticket"]
        out["text"] = (f"Pasul {step}: cotă {_num(tk['odds'])} din {len(tk['legs'])} meciuri de cluburi, șansă ~{_pct(tk['p'])}. "
                       f"Miza {_num(out['stake'])} din banca piramidei de {_num(bank)} (jumătate).")
    elif out["status"] == "no_bet":
        out["text"] = f"Azi pauză la piramidă (pasul {step} rămâne pentru o zi bună). " + (st.get("reason") or "")
    else:
        out["text"] = f"Propunerea de azi nu e încă generată. Următorul pas: {step}, banca {_num(bank)}."
    if not active and run and run[0] == "lost":
        out["text"] += " Seria trecută s-a pierdut: se repornește de la pasul 1 cu banca de start."
    return out


# ---------------------------------------------------------------- piețele recomandate
def market_board(conn: sqlite3.Connection, now: datetime) -> Dict[str, Any]:
    from betpredict.builder import super_tickets as S
    from betpredict.builder.rec_monitor import COMBO, DROP_ROI, MIN_N, market_stats

    live = market_stats(conn, S.REC, (1.40, 1.60), now)
    rows = []
    for key, v in live.items():
        label = "Peste 0.5 goluri + peste 7.5 cornere" if key == COMBO else S.SEL_LABEL.get(S.REC[key][1], key[1])
        if v.get("off"):
            state = "off"
        elif v["n"] < MIN_SHOW_N:
            state = "few"
        elif (v["roi"] or 0) >= HOT_ROI:
            state = "hot"
        elif (v["roi"] or 0) <= COLD_ROI:
            state = "cold"
        else:
            state = "flat"
        rows.append({"label": label, "n": v["n"], "hit": v["hit"], "roi": v["roi"], "state": state})
    order = {"hot": 0, "flat": 1, "cold": 2, "off": 3, "few": 4}
    rows.sort(key=lambda r: (order[r["state"]], -(r["roi"] or 0)))
    return {"days": 30, "rows": rows, "rule": f"Piața iese de pe bilete sub {_pct(DROP_ROI, 0, True)} pe cel puțin {MIN_N} selecții.",
            "note": "La cotele de închidere Superbet. 30 de zile sunt puține: e un semnal de urmărit, nu o garanție (ROI-ul recent se schimbă des)."}


# ---------------------------------------------------------------- ieri
def yesterday_recap(conn: sqlite3.Connection, today: date) -> Dict[str, Any]:
    from betpredict.builder import super_tickets as S
    from betpredict.builder.rec_monitor import settle

    y = today - timedelta(days=1)
    rows = conn.execute("""SELECT kind, variant, status, total_odds, notes, id FROM ticket WHERE day=? AND status!='replaced'
                           AND ((kind=? ) OR (kind='pyramid' AND variant='p120'))""", (y.isoformat(), S.KIND)).fetchall()
    lines: List[str] = []
    groups = (("~10", lambda r: r[0] == S.KIND and r[1] == "s10"), ("lungi", lambda r: r[0] == S.KIND and r[1] != "s10"),
              ("piramidă", lambda r: r[0] == "pyramid"))
    summary: Dict[str, Dict[str, int]] = {}
    for name, f in groups:
        g = [r for r in rows if f(r)]
        if not g:
            continue
        s = {"won": sum(r[2] == "won" for r in g), "lost": sum(r[2] == "lost" for r in g), "pending": sum(r[2] == "pending" for r in g)}
        summary[name] = s
        legs = conn.execute(f"SELECT SUM(result='won'), SUM(result IN ('won','lost')) FROM ticket_leg WHERE ticket_id IN ({','.join('?' * len(g))})",
                            [r[5] for r in g]).fetchone()
        parts = [f"{s['won']} câștigat" + ("e" if s["won"] != 1 else ""), f"{s['lost']} pierdut" + ("e" if s["lost"] != 1 else "")]
        if s["pending"]:
            parts.append(f"{s['pending']} în joc")
        best = max((float(json.loads(r[4] or "{}").get("payout_bonus") or r[3] or 0) for r in g if r[2] == "won"), default=None)
        txt = f"Bilete {name}: " + ", ".join(parts)
        if legs and legs[1]:
            txt += f"; selecții intrate {legs[0]}/{legs[1]}"
        if best:
            txt += f"; cel mai bun câștig cotă {_num(best)}"
        lines.append(txt + ".")
    # piețele recomandate ieri, la cotele de închidere
    start, end = ro_day_bounds_utc(y)
    mk: Dict[str, List[int]] = {}
    try:
        res = conn.execute("""SELECT s.market_name, s.outcome, MAX(s.price), m.ft_home, m.ft_away, m.ht_home, m.ht_away
                              FROM sb_offer_close s JOIN match m ON m.id=s.match_id
                              WHERE m.ft_home IS NOT NULL AND m.kickoff_utc>=? AND m.kickoff_utc<? GROUP BY s.match_id, s.market_name, s.outcome""",
                           (start, end)).fetchall()
    except sqlite3.OperationalError:
        res = []
    for mn, oc, price, fh, fa, hh, ha in res:
        spec = S.REC.get((mn, oc))
        if not spec or not price or not spec[2] <= price <= spec[3]:
            continue
        won = settle(mn, oc, fh, fa, hh, ha)
        if won is None:
            continue
        b = mk.setdefault(S.SEL_LABEL.get(spec[1], oc), [0, 0])
        b[0] += 1
        b[1] += int(won)
    markets = [{"label": k, "n": v[0], "won": v[1]} for k, v in sorted(mk.items(), key=lambda kv: -kv[1][0])]
    if markets:
        n, w = sum(m["n"] for m in markets), sum(m["won"] for m in markets)
        lines.append(f"Piețele recomandate ieri: {w}/{n} intrate ({_pct(w / n)}) la cotele lor.")
    if not lines:
        lines.append("Ieri nu s-a jucat niciun bilet al Robotului.")
    return {"date": y.isoformat(), "lines": lines, "tickets": summary, "markets": markets}


# ---------------------------------------------------------------- miza
def bankroll_advice(quality: Dict[str, Any], markets: Dict[str, Any], pyr: Dict[str, Any], tickets: Dict[str, Any], streak: int) -> List[Dict[str, Any]]:
    lo, hi = PCT["short"]
    careful = quality["level"] == "slaba" or quality.get("intl_break") or any(r["state"] in ("cold", "off") for r in markets["rows"])
    n_short = max(1, len(tickets["short"]))
    short_pct = lo if careful else hi
    per = short_pct / n_short
    out = [{"key": "short", "title": "Bilet de ~10", "pct": round(per, 4),
            "text": (f"{_pct(per, 1)} din bancă pe bilet" + (f" ({n_short} bilete, {_pct(short_pct, 0)} în total)" if n_short > 1 else "")
                     + (". Azi spre minim (1%): zi slabă sau piețe reci." if careful else ". Zi normală: până la 2% din bancă în total.")
                     + f" La 1.000 lei: {_num(1000 * per, 0)} lei.")},
           {"key": "long", "title": "Bilete lungi (1.000+)", "pct": PCT["long"],
            "text": f"{_pct(PCT['long'], 1)} pe bilet, cel mult 5 în joc ({_pct(PCT['long'] * 5, 1)} expunere). Sunt loterie cu SuperBonus: "
                    "rar ies, miza trebuie să fie una pe care o poți pierde liniștit."},
           {"key": "pyramid", "title": "Piramida cotă 2", "pct": None,
            "text": f"Bancă separată (~{_pct(PCT['pyramid_bank'])} din banca totală, 100 de unități la start). Pe fiecare pas jumătate din banca "
                    f"piramidei: azi pasul {pyr['step']}, miza {_num(pyr['stake'])} din {_num(pyr['bank'])} unități. "
                    "După o pierdere se repornește de la 100, nu se dublează."},
           {"key": "cap", "title": "Plafonul zilei", "pct": PCT["day_cap"],
            "text": f"Tot ce joci azi: cel mult {_pct(PCT['day_cap'])} din bancă. Marja casei e reală (~4–8% pe selecție la cotele astea): "
                    "pe termen lung câștigă doar disciplina mizei."}]
    if streak >= 3:
        out[0]["text"] += f" Ultimele {streak} bilete de ~10 s-au pierdut: la ~9% șansă e normal (se întâmplă în {_pct(0.915 ** streak)} din cazuri); nu mări miza."
    return out


# ---------------------------------------------------------------- avertismente
def risk_warnings(quality: Dict[str, Any], markets: Dict[str, Any], tickets: Dict[str, Any], pyr: Dict[str, Any], streak: int) -> List[str]:
    w: List[str] = []
    if quality["level"] == "slaba":
        w.append(f"Zi subțire: {_n(quality['club_day'], 'meci', 'meciuri')} de cluburi ziua. Mai puține bilete, nu bilete forțate.")
    if quality.get("intl_break"):
        w.append(f"{quality['intl']} meciuri internaționale/amicale: au ieșit sub cotă (−8%). Pe bilete intră cel mult 2, pe piramidă deloc.")
    if quality["night"]:
        w.append(f"{_n(quality['night'], 'meci', 'meciuri')} de cluburi noaptea (00–10 ora României) nu intră pe bilete: acolo selecțiile au intrat mult sub așteptări.")
    off = [r["label"] for r in markets["rows"] if r["state"] == "off"]
    if off:
        w.append("Scoase automat de pe bilete (pierd clar în 30 de zile): " + ", ".join(off) + ".")
    cold = [f"{r['label']} ({_pct(r['roi'], 0, True)})" for r in markets["rows"] if r["state"] == "cold"]
    if cold:
        w.append("Piețe reci, încă pe bilete: " + ", ".join(cold) + ". De urmărit.")
    for t in tickets["short"]:
        h = _hour_ro(t["first_kickoff"] or "")
        if h is not None and h < 13:
            w.append(f"Biletul de cotă {_num(t['odds'])} începe la {h}:00: joacă-l din timp.")
            break
    if streak >= 3:
        w.append(f"{streak} bilete de ~10 pierdute la rând: fără „recuperare” prin mize mai mari.")
    if pyr.get("ticket") is None and pyr.get("status") == "no_bet":
        w.append("Piramida stă azi: nu sunt două meciuri de cluburi potrivite. Pauza e regulă, nu pierdere.")
    return w


def _headline(quality: Dict[str, Any], tickets: Dict[str, Any], pyr: Dict[str, Any]) -> Tuple[str, str]:
    n = len(tickets["short"])
    parts = [quality["label"] + (" (pauză internațională)" if quality.get("intl_break") else "")]
    parts.append(f"{n} bilet{'e' if n != 1 else ''} de ~10" if n else "fără bilet de ~10")
    parts.append(f"piramida la pasul {pyr['step']}" if pyr.get("ticket") else "piramida în pauză")
    tone = "warn" if quality["level"] == "slaba" or not n else "good" if quality["level"] == "buna" else "ok"
    return ", ".join(parts) + ".", tone


def brief_doc(conn: sqlite3.Connection, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    now = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    today = ro_today(now)
    quality = day_quality(conn, today, now)
    tickets = short_tickets(conn, today, now)
    pyr = pyramid_state(conn, today)
    markets = market_board(conn, now)
    streak = _short_streak(conn, now)
    headline, tone = _headline(quality, tickets, pyr)
    return {"schema": SCHEMA, "generated_at": canon_utc(now.isoformat()), "date": today.isoformat(), "weekday": WEEKDAYS[today.weekday()],
            "headline": headline, "tone": tone, "quality": quality, "tickets": tickets, "pyramid": pyr, "markets": markets,
            "warnings": risk_warnings(quality, markets, tickets, pyr, streak),
            "bankroll": bankroll_advice(quality, markets, pyr, tickets, streak), "yesterday": yesterday_recap(conn, today),
            "short_loss_streak": streak,
            "disclaimer": "Analiză din date, fără garanții. Pariurile au marjă: joacă doar sume pe care ți le permiți să le pierzi."}


def publish_brief(conn: sqlite3.Connection, out_root: Path, now: Optional[datetime] = None) -> Path:
    from betpredict.publish.day import write_json

    return write_json(Path(out_root) / "api" / "brief" / "today.json", brief_doc(conn, now))
