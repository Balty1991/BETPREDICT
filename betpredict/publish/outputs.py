"""Bilete, piramidă, statistici, învățare, meta → ``api/``."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from betpredict import __version__
from betpredict.builder.pyramid import RULES
from betpredict.builder.tickets import VARIANTS
from betpredict.publish.day import write_json
from betpredict.publish.robot import MODEL_LABEL
from betpredict.robot import MODEL_VERSION, STATS_SINCE
from betpredict.robot.markets import label_ro, market_key
from betpredict.store import repo

KIND_NOTES = {
    "acca_safe": "Bilet sigur (cotă ~2/3/5): favoriți clari la cote 1.20–1.40; se publică zilnic, chiar și cu EV ușor negativ (marcat).",
    "acca_50": "Bilet de cotă ~50: șansă realistă ~1,5–3%.",
    "acca_100": "Bilet de cotă ~100: șansă realistă ~0,7–1,5%.",
    "acca_500": "Bilet de cotă ~500+: șansă realistă ~0,1–0,3%. Loterie cu fundament — mizează mic.",
}


from betpredict.robot.engine import BOOKMAKER_LABEL  # noqa: E402


INFO_ONLY_KINDS = frozenset({"acca_50", "acca_100", "acca_500", "acca_1000", "acca_boost"})


def _sb_pick(conn: sqlite3.Connection, match_id: int, market: str, outcome: str) -> Dict[str, Any]:
    """Piața și selecția Superbet + id-urile ei (``ref``), ca biletul precompletat să nu depindă de citirea ofertei din telefon."""
    try:
        r = conn.execute("SELECT ref FROM sb_offer WHERE match_id=? AND market_name=? AND outcome=?", (match_id, market, outcome)).fetchone()
    except sqlite3.OperationalError:
        r = None
    return {"market": market, "outcome": outcome, **({"ref": r[0]} if r and r[0] else {})}


# Piețele Robotului principal în oferta Superbet: id-ul pieței și numele selecției (ca în aplicație).
SB_ROBOT = {"1x2": 547, "double_chance": 531, "draw_no_bet": 555, "btts": 539, "over_under": 200734}


def _robot_pick(conn: sqlite3.Connection, match_id: int, market: str, line: Optional[float], sel: str) -> Optional[Dict[str, Any]]:
    mid = SB_ROBOT.get(market)
    if not mid:
        return None
    try:
        rows = conn.execute("SELECT market_name, outcome, ref FROM sb_offer WHERE match_id=? AND market_id=? ORDER BY rowid",
                            (match_id, mid)).fetchall()
    except sqlite3.OperationalError:
        return None
    if market == "1x2":
        want = {"HOME": "1", "DRAW": "X", "AWAY": "2"}.get(sel)
    elif market == "double_chance":
        want = sel
    elif market == "btts":
        want = "Da" if sel == "YES" else "Nu"
    elif market == "over_under":
        want = f"{'Peste' if sel == 'OVER' else 'Sub'} {line:g}" if line is not None else None
    else:  # egal = pariu returnat: întâi gazdele, apoi oaspeții
        pick = rows[0] if sel == "HOME" and rows else rows[1] if sel == "AWAY" and len(rows) > 1 else None
        return {"market": pick[0], "outcome": pick[1], **({"ref": pick[2]} if pick[2] else {})} if pick else None
    r = next((r for r in rows if r[1].strip() == want), None) if want else None
    return {"market": r[0], "outcome": r[1], **({"ref": r[2]} if r[2] else {})} if r else None


def ticket_json(conn: sqlite3.Connection, t: sqlite3.Row, with_reasons: bool = True) -> Dict[str, Any]:
    legs = conn.execute(
        """SELECT tl.*, p.p_calibrated, p.grade, p.line, p.market AS pmarket, m.kickoff_utc, m.home_name, m.away_name,
                  m.ft_home, m.ft_away, l.name AS league_name,
                  (SELECT ext_id FROM ext_event x WHERE x.match_id = tl.match_id AND x.source = 'superbet') AS sb_event_id
           FROM ticket_leg tl LEFT JOIN prediction p ON p.id = tl.prediction_id
           LEFT JOIN match m ON m.id = tl.match_id LEFT JOIN league l ON l.id = m.league_id
           WHERE tl.ticket_id = ? ORDER BY m.kickoff_utc""",
        (t["id"],),
    ).fetchall()
    out_legs = []
    eff = 1.0
    settled = 0
    # Re-prețuire pentru AFIȘARE: biletele încă în joc arată cota Superbet curentă (jucabilă) pe fiecare
    # selecție nedecontată; cota publicată rămâne în DB și în ``odds_published`` → statisticile nu se schimbă.
    pending = t["status"] == "pending"
    sb: Dict[int, Dict[str, Dict[str, float]]] = {}
    if pending:
        try:
            sb = repo.latest_odds(conn, sorted({l["match_id"] for l in legs if l["match_id"] and not l["result"]}), source="superbet")
        except sqlite3.Error:
            sb = {}
    play_total = 1.0
    repriced = False
    for l in legs:
        market, _, line_s = (l["market"] or "").partition("|")
        line = float(line_s) if line_s else (l["line"] or 0.0)
        res = l["result"]
        if res:
            settled += 1
        eff *= 1.0 if res == "void" else l["odds"]
        o_play, src_play = l["odds"], l["odds_source"]
        if pending and not res and src_play != "superbet":
            o_sb = ((sb.get(l["match_id"]) or {}).get(market_key(market, line)) or {}).get(l["selection"])
            if o_sb and o_sb > 1.0:
                o_play, src_play, repriced = o_sb, "superbet", True
        play_total *= 1.0 if res == "void" else o_play
        out_legs.append({
            "prediction_id": l["prediction_id"], "match_id": l["match_id"], "kickoff_utc": l["kickoff_utc"],
            "sb_event_id": l["sb_event_id"],
            "superbet_url": _sb_url(l["home_name"], l["away_name"], l["sb_event_id"]) if l["sb_event_id"] else None,
            "league": l["league_name"] or "Ligă necunoscută", "home": l["home_name"], "away": l["away_name"],
            "market": market, "line": line or None, "selection": l["selection"], "label": label_ro(market, line, l["selection"]),
            "odds": o_play, "odds_published": l["odds"], "odds_source_published": l["odds_source"],
            "p": l["p_calibrated"], "grade": l["grade"], "result": res,
            "odds_source": src_play, "bookmaker": BOOKMAKER_LABEL.get(src_play or "bsd_consensus") if o_play else None,
            "closing_odds": l["closing_odds"],
            "score": f"{l['ft_home']}-{l['ft_away']}" if l["ft_home"] is not None else None,
        })
    notes = {}
    try:
        notes = json.loads(t["notes"] or "{}")
    except ValueError:
        pass
    from betpredict.builder.v4tickets import LEG_SHRINK, LOTTERY_VALIDATED, TICKET_EV_CAP

    try:  # absenți de scurtă durată (API-Football), unde îi avem
        from betpredict.experimental.supersocial import absences

        ab = absences(conn)
    except Exception:  # noqa: BLE001
        ab = {}
    for x in out_legs:
        a_ = ab.get(x["match_id"])
        x["absences"] = {"home": a_[0], "away": a_[1]} if a_ and (a_[0] or a_[1]) else None
    if pending:  # piețele Robotului principal (și în biletele Stil, „R:1x2:0:HOME”): id-urile Superbet pentru biletul precompletat
        for x in out_legs:
            if x["result"]:
                continue
            if x["market"] in SB_ROBOT:
                pk = _robot_pick(conn, x["match_id"], x["market"], x["line"], x["selection"])
            elif x["market"] == "ss" and str(x["selection"]).startswith("R:"):
                _, m_, ln_, sel_ = x["selection"].split(":")
                pk = _robot_pick(conn, x["match_id"], m_, float(ln_), sel_)
            else:
                continue
            if pk:
                x["sb_pick"] = pk
    if pending:  # cotele mărite: piața și selecția exact ca în oferta Superbet, pentru biletul precompletat
        for x in out_legs:
            if x["market"] != "boost" or x["result"]:
                continue
            sel = x["selection"] or ""
            name = sel.replace("Super Cota ", "SC-") if sel.startswith("Super Cota ") else sel
            try:
                row = conn.execute("SELECT market_name, name, ref FROM sb_boost WHERE match_id=? AND name=? ORDER BY last_seen DESC LIMIT 1",
                                   (x["match_id"], name)).fetchone()
            except sqlite3.OperationalError:
                row = None
            if row and row[0]:
                x["sb_pick"] = {"market": row[0], "outcome": row[1], **({"ref": row[2]} if row[2] else {})}
    if pending and t["kind"] in ("acca_stil", "acca_seg"):  # se mai poate pune fiecare selecție pe Superbet, și la ce cotă
        try:
            from betpredict.experimental.supersocial import BB_KEYS, bb_legs, offer_now, playable
            from datetime import datetime as _dt, timezone as _tz

            now_s = _dt.now(_tz.utc).isoformat()[:19] + "Z"
            for x in out_legs:
                if x["result"] or x["market"] != "ss" or not x["kickoff_utc"] or x["kickoff_utc"] <= now_s:
                    continue
                ok, now_p = playable(conn, x["match_id"], x["selection"], x["home"], x["away"])
                if not ok:
                    x["unavailable"] = True
                elif now_p and x["odds"] and abs(now_p / x["odds"] - 1) >= 0.10:
                    x["odds_now"] = now_p
                if not ok:
                    continue
                names = offer_now(conn, x["match_id"], x["home"], x["away"], names=True)
                if x["selection"] in BB_KEYS:  # Bet Builder: ce bifezi în meci, cu numele de pe Superbet
                    steps = [names.get(k) for k in bb_legs(x["selection"])]
                    if all(steps):
                        x["bb_steps"] = [f"{m}: {o}" for m, o in steps]
                        x["bb_picks"] = [_sb_pick(conn, x["match_id"], m, o) for m, o in steps]
                elif x["selection"] in names:  # selecție simplă: intră direct în biletul precompletat
                    x["sb_pick"] = _sb_pick(conn, x["match_id"], *names[x["selection"]])
        except Exception:  # noqa: BLE001
            pass
    lp = notes.get("leg_p") or {}
    if lp:  # Stil Supersocial: șansa realistă pe selecție (pentru variantele sistem), salvată la construirea biletului
        for x in out_legs:
            if x["p"] is None:
                x["p"] = lp.get(f"{x['match_id']}|{x['selection']}")
    lottery = bool(notes.get("lottery"))
    sys_k = int((notes.get("backtest") or {}).get("system") or notes.get("system") or 0)
    risk_ack = lottery or bool(notes.get("risk_acknowledged")) or t["kind"] in ("acca_value", "acca_double")
    p_t, ev_t = t["p_ticket"], t["ev"]
    if lottery and p_t is not None and "p_raw" not in notes:  # bilete create înainte de corecție: aplicăm corecția la afișare
        p_t = p_t * LEG_SHRINK ** max(1, len(out_legs))
        ev_t = p_t * (t["total_odds"] or 0) - 1
    if ev_t is not None:
        ev_t = round(min(TICKET_EV_CAP, ev_t), 4)
    if p_t is not None:
        p_t = round(p_t, 6)
    d: Dict[str, Any] = {
        "id": t["id"], "kind": t["kind"], "variant": t["variant"],
        "variant_label": VARIANTS.get(t["variant"], {"principal": "Principal", "alternativa": "Alternativă", "multi_zi": "Multi-zi"}.get(t["variant"], t["variant"])),
        "created_by": t["created_by"], "date": t["day"], "created_at": t["created_at"],
        "target_odds": t["target_odds"],
        # total_odds = cota JUCABILĂ acum (Superbet unde există); total_odds_published = cota la publicare (statistici)
        "total_odds": round(play_total, 2) if repriced else t["total_odds"], "total_odds_published": t["total_odds"],
        "repriced": repriced,
        "bookmakers": sorted({x["bookmaker"] for x in out_legs if x["bookmaker"]}), "p_ticket": p_t, "ev": ev_t, "p_ticket_raw": notes.get("p_raw", t["p_ticket"]) if lottery else None,
        "status": t["status"], "payout": t["payout"], "settled_legs": settled, "legs_count": len(out_legs),
        "effective_odds": round((t["payout"] or 0) / t["stake"], 2) if sys_k and t["status"] in ("won", "lost") and t["stake"] else round(eff, 2),
        "system": sys_k or None, "system_label": f"sistem {len(out_legs) - sys_k}/{len(out_legs)}" if sys_k else None, "legs": out_legs,
        "stake_units": _stake_units(t),
        "clv": t["clv"] if "clv" in t.keys() else None,
        "safe": t["kind"] == "acca_safe",
        # EV<0 (sau bilet sigur) = doar informativ, nu se recomandă la joc
        # Alin (11.10): biletele de valoare/loterie/super sunt jucabile cu risc asumat (EV realist afișat); sigurul rămâne informativ
        # audit 17.10: 0 din 27 la cotele 50/100/500 și la biletele cu cote mărite → doar informative (urmărite, decontate)
        "informational": t["kind"] in INFO_ONLY_KINDS or (t["kind"] == "pyramid" and not (t["variant"] or "").startswith(("pmici", "pr5", "pr10"))) or t["kind"] == "acca_safe" or (not risk_ack and bool(notes.get("informational")
                         or (t["kind"] or "").startswith("acca_") and ev_t is not None and ev_t < 0)),
        "risk_acknowledged": risk_ack, "backtest": notes.get("backtest"),
        # v4: coș de statistici + variante sistem Superbet (k/n) cu tabel de câștig la 0/1/2 ratări
        "bucket": ticket_bucket(t["kind"], t["variant"], notes),
        "lottery": lottery,
        "system_pick": notes.get("system_pick"),
        "systems": (_systems_for([{**l, "p": (l.get("p") or 0) * LEG_SHRINK} for l in out_legs], _stake_units(t))
                    if lottery and "p_raw" not in notes else None) or notes.get("systems") or _systems_for(out_legs, _stake_units(t)),
    }
    if lottery:
        d["variant_label"] = "Loterie · miză mică" + (" · multi-zi" if t["variant"] == "multi_zi" else "")
    if notes.get("pattern"):
        d["variant_label"] = notes.get("label") or "Tiparul 80%+"
    if notes.get("segments"):
        d["variant_label"] = notes.get("label") or "Meciuri potrivite"
    if notes.get("stil"):
        d["variant_label"] = notes.get("label") or "Stil Supersocial"
        d["experimental"] = True
    if notes.get("soft_draw"):
        d["variant_label"] = notes.get("label") or "Egaluri Superbet"
        d["experimental"] = True
        d["soft_events"] = notes.get("events") or []
    if notes.get("super"):
        d["variant_label"] = "Super bilet · " + ((notes.get("backtest") or {}).get("label") or "")
    trk = {"principal": "2.00", "p140": "1.40", "pmici": "mici", "pr5": "r5", "pr10": "r10"}.get(t["variant"] or "") if t["kind"] == "pyramid" else None
    if trk and t["status"] == "pending":  # instrucțiunea zilei (folosită și de notificări)
        a = _pyr_action(conn, trk, t["id"]) or {}
        d["pyr_track"], d["pyr_action"], d["pyr_action_text"] = trk, a.get("short"), " ".join(x for x in (a.get("text"), a.get("today")) if x)
    if with_reasons:
        d["reasons"] = notes.get("reasons", [])
    return d


def ticket_bucket(kind: Optional[str], variant: Optional[str], notes: Optional[Dict[str, Any]] = None) -> str:
    kind = kind or ""
    if kind == "pyramid":
        v = variant or ""
        return ("Piramidă 1.40" if v.startswith("p140") else "Piramidă Ligi mici" if v.startswith("pmici") else "Piramidă ~5" if v.startswith("pr5")
            else "Piramidă ~10" if v.startswith("pr10") else "Piramidă")
    if kind == "acca_soft" or (notes or {}).get("soft_draw"):
        return "Egaluri Superbet"
    if kind == "acca_safe":
        return "Sigur (informativ)"
    if kind == "acca_double":
        return "Dublu de valoare"
    if kind == "acca_value":
        return "Valoare"
    if (notes or {}).get("lottery") or (variant or "").startswith("loterie"):
        return "Loterie"
    if kind == "acca_stil" or (variant or "") == "stil_supersocial":
        return "Pe val"
    if kind == "acca_80":
        return "Tiparul 80%+"
    if kind == "acca_seg":
        return "Meciuri potrivite"
    if kind.startswith("acca_"):
        return "Acumulator"
    return "Altele"


def _systems_for(legs: List[Dict[str, Any]], stake: Optional[float]) -> List[Dict[str, Any]]:
    if len(legs) < 3 or any(not l.get("odds") or not l.get("p") for l in legs):
        return []
    from betpredict.builder.system import system_variants

    return system_variants([l["odds"] for l in legs], [min(0.99, l["p"]) for l in legs], stake if stake else 1.0)


def _stake_units(t) -> Optional[float]:
    """Miză sugerată în unități (1u = 1% din bancă): ¼ Kelly plafonat. Piramida: plafon 2u (bancă separată)."""
    from betpredict.builder.tickets import suggested_stake

    kind = t["kind"] or ""
    if kind.startswith("acca_"):
        return t["stake"] if t["stake"] is not None else None
    if kind == "pyramid" and t["p_ticket"] and t["total_odds"]:
        return suggested_stake(t["p_ticket"], t["total_odds"], 2.0)
    return None


def exposure_report(tickets: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Suprapunerea biletelor active: câte bilete cad dacă pică o singură selecție.

    Adaugă pe fiecare bilet ``overlap`` (câte alte bilete au cel puțin o selecție comună) și ``shared_legs``."""
    from betpredict.builder.tickets import MAX_TICKETS_PER_SELECTION

    active = [t for t in tickets if t.get("status") == "pending"]
    by_sel: Dict[Any, List[Dict[str, Any]]] = {}
    for t in active:
        for l in t["legs"]:
            key = l.get("prediction_id") or f"{l['match_id']}|{l['market']}|{l['selection']}"
            by_sel.setdefault(key, []).append(t)
    shared_pairs = set()
    for t in tickets:
        others = {o["id"] for l in t["legs"] for o in by_sel.get(l.get("prediction_id") or f"{l['match_id']}|{l['market']}|{l['selection']}", []) if o["id"] != t["id"]}
        t["overlap"] = len(others)
        t["shared_legs"] = sum(1 for l in t["legs"] if len(by_sel.get(l.get("prediction_id") or f"{l['match_id']}|{l['market']}|{l['selection']}", [])) > 1)
        for o in others:
            shared_pairs.add(tuple(sorted((str(t["id"]), str(o)))))
    top = []
    for key, ts in sorted(by_sel.items(), key=lambda kv: -len(kv[1])):
        if len(ts) < 2:
            break
        leg = next(l for l in ts[0]["legs"] if (l.get("prediction_id") or f"{l['match_id']}|{l['market']}|{l['selection']}") == key)
        top.append({"prediction_id": leg.get("prediction_id"), "label": leg["label"], "home": leg["home"], "away": leg["away"],
                    "kickoff_utc": leg["kickoff_utc"], "tickets": len(ts), "ticket_ids": [t["id"] for t in ts],
                    "stake_units": round(sum(t.get("stake_units") or 0 for t in ts), 2)})
    n = len(active)
    worst = max((len(v) for v in by_sel.values()), default=0)
    return {"max_tickets_per_selection": MAX_TICKETS_PER_SELECTION, "tickets": n, "selections": len(by_sel),
            "max_tickets_on_one_selection": worst, "shared_pairs": len(shared_pairs),
            "pairs_total": n * (n - 1) // 2, "independent_tickets": sum(1 for t in active if not t.get("overlap")),
            "top": top[:15]}


def pick_of_day(tickets: List[Dict[str, Any]]) -> Optional[Any]:
    """„Biletul zilei”: biletul dedicat „biletul_zilei” (~5, 4–6 selecții sigure); altfel cea mai mare șansă cu EV > −5%
    dintre valoare/dublu/Super în curs; altfel cel mai bun EV."""
    c = [t for t in tickets if t.get("status") == "pending" and (t["kind"] in ("acca_value", "acca_double") or t.get("variant") == "super")]
    for t in c:
        if (t.get("variant") or "").startswith("biletul_zilei"):
            return t["id"]
    if not c:
        return None
    ev = lambda t: t.get("ev") if t.get("ev") is not None else -9  # noqa: E731
    ok = [t for t in c if ev(t) > -0.05]
    return (max(ok, key=lambda t: t.get("p_ticket") or 0) if ok else max(c, key=ev))["id"]


def publish_tickets(conn: sqlite3.Connection, out_root: Path, days: List[date], today: date) -> None:
    for d in days:
        ts = conn.execute("SELECT * FROM ticket WHERE day=? AND kind LIKE 'acca_%' AND status!='replaced' ORDER BY target_odds, id",
                          (d.isoformat(),)).fetchall()
        tj = [ticket_json(conn, t) for t in ts]
        payload = {"schema": "betpredict.tickets.v1", "date": d.isoformat(), "targets": [50, 100, 500], "safe_targets": [2, 3, 5],
                   "tickets": tj, "pick_id": pick_of_day(tj),
                   "notes": [KIND_NOTES[k] for k in ("acca_safe", "acca_50", "acca_100", "acca_500")]}
        write_json(out_root / "api" / "tickets" / f"{d.isoformat()}.json", payload)
        if d == today:
            write_json(out_root / "api" / "tickets" / "today.json", payload)
    try:
        from betpredict.builder.soft_draw import events_doc

        write_json(out_root / "api" / "soft_draw.json", events_doc(conn))
    except Exception:  # noqa: BLE001 — rubrica nu oprește publicarea biletelor
        pass
    upcoming_days = [d for d in days if d >= today]
    if upcoming_days:
        rows = conn.execute(
            "SELECT * FROM ticket WHERE day>=? AND day<=? AND kind LIKE 'acca_%' AND created_by='robot' AND status!='replaced' "
            "ORDER BY day, CASE WHEN variant='multi_zi' THEN 1 ELSE 0 END, target_odds, id",
            (upcoming_days[0].isoformat(), upcoming_days[-1].isoformat())).fetchall()
        tickets = [ticket_json(conn, t) for t in rows]
        expo = exposure_report(tickets)
        write_json(out_root / "api" / "tickets" / "upcoming.json",
                   {"schema": "betpredict.tickets_upcoming.v1", "from": upcoming_days[0].isoformat(), "to": upcoming_days[-1].isoformat(),
                    "tickets": tickets, "exposure": expo})
    since = max((today - timedelta(days=90)).isoformat(), STATS_SINCE)  # doar Robotul 3.0
    hist = conn.execute("SELECT * FROM ticket WHERE day >= ? AND status!='replaced' ORDER BY day DESC, target_odds, id", (since,)).fetchall()
    write_json(out_root / "api" / "tickets" / "history.json",
               {"schema": "betpredict.tickets_history.v1", "tickets": [ticket_json(conn, t, with_reasons=False) for t in hist]})


def publish_pyramid(conn: sqlite3.Connection, out_root: Path, today: date) -> None:
    from betpredict.builder.pyramid import KEY_140, RULES_140, ensure_140_tables

    _publish_pyramid_track(conn, out_root, today, "pyramid.day.", "pyramid_run", "pyramid_step", RULES, "state.json", "pyramid.json", "2.00")
    ensure_140_tables(conn)
    _publish_pyramid_track(conn, out_root, today, KEY_140, "pyramid140_run", "pyramid140_step", RULES_140,
                           "state_140.json", "pyramid_140.json", "1.40")
    from betpredict.builder.pyramid import KEY_MICI, RULES_MICI, ensure_track_tables

    ensure_track_tables(conn, "pyramidmici")
    _publish_pyramid_track(conn, out_root, today, KEY_MICI, "pyramidmici_run", "pyramidmici_step", RULES_MICI,
                           "state_mici.json", "pyramid_mici.json", "mici")
    from betpredict.builder.pyramid_risk import KEY_R5, KEY_R10, RULES_R5, RULES_R10

    for pre, key, rules, tr in (("pyramidr5", KEY_R5, RULES_R5, "r5"), ("pyramidr10", KEY_R10, RULES_R10, "r10")):
        ensure_track_tables(conn, pre)
        _publish_pyramid_track(conn, out_root, today, key, f"{pre}_run", f"{pre}_step", rules, f"state_{tr}.json", f"pyramid_{tr}.json", tr)


def _publish_pyramid_track(conn, out_root: Path, today: date, key: str, run_t: str, step_t: str, rules: Dict[str, Any],
                           fname: str, wname: str, track: str) -> None:
    raw = repo.get_state(conn, f"{key}{today.isoformat()}")
    st = json.loads(raw) if raw else {"status": "no_bet", "reason": "Încă nu s-a generat propunerea zilei.", "main": None, "alternatives": []}

    def tk(tid: Optional[int]):
        if not tid:
            return None
        row = conn.execute("SELECT * FROM ticket WHERE id=?", (tid,)).fetchone()
        return ticket_json(conn, row) if row else None

    run = conn.execute(f"SELECT * FROM {run_t} ORDER BY id DESC LIMIT 1").fetchone()
    history = []
    for k in conn.execute("SELECT key, value FROM ingest_state WHERE key LIKE ? ORDER BY key DESC LIMIT 120", (key + '%',)):
        v = json.loads(k["value"])
        t = conn.execute("SELECT * FROM ticket WHERE id=?", (v.get("main"),)).fetchone() if v.get("main") else None
        history.append({"date": k["key"].rsplit(".", 1)[1], "status": v.get("status"), "ticket_id": v.get("main"),
                        "odds": t["total_odds"] if t else None, "p": t["p_ticket"] if t else None,
                        "result": t["status"] if t else None})
    runs = []
    for r in conn.execute(f"SELECT * FROM {run_t} ORDER BY id DESC LIMIT 50"):
        mx = conn.execute(f"SELECT MAX(bank_after), MAX(date) FROM {step_t} WHERE run_id=?", (r["id"],)).fetchone()
        runs.append({"id": r["id"], "start_date": r["start_date"], "end_date": mx[1] if r["status"] != "active" else None,
                     "steps": r["current_step"], "max_bank": mx[0], "withdrawn": r["withdrawn_total"], "status": r["status"],
                     "bank": r["current_bank"]})
    # probabilitatea reală de a ajunge la pasul k (din run-urile încheiate + cel activ)
    reach = []
    steps_reached = [r["steps"] for r in runs]
    if steps_reached:
        for k in range(1, max(steps_reached + [1]) + 1):
            reach.append({"step": k, "p": round(sum(1 for s in steps_reached if s >= k) / len(steps_reached), 3)})
    payload = {
        "schema": "betpredict.pyramid.v1", "date": today.isoformat(), "track": track, "rules": _eff_rules(conn, track, rules),
        "today": {"status": st.get("status"), "reason": st.get("reason"), "main": tk(st.get("main")),
                  "alternatives": [x for x in (tk(a) for a in st.get("alternatives", [])) if x]},
        "run": ({"id": run["id"], "start_date": run["start_date"], "status": run["status"], "step": run["current_step"],
                 "bank": run["current_bank"], "start_bank": run["start_bank"], "withdrawn": run["withdrawn_total"]} if run else None),
        "history": history, "runs": runs, "reach_probability": reach,
        "action": _pyr_action(conn, track, st.get("main")),
        **({"backtest": _pyr_backtest()} if track == "1.40" else {"backtest": _pyr_backtest("pyramid_mici_backtest.json")} if track == "mici" else {}),
        "grid": _pyr_grid(track) if track in ("2.00", "1.40") else None,
        **({"backtest": (_pyr_backtest("pyramid_risk_backtest.json") or {}).get(track)} if track in ("r5", "r10") else {}),
    }
    write_json(out_root / "api" / "pyramid" / fname, payload)
    m = payload["today"]["main"] or {}
    r = payload["run"] or {}
    write_json(out_root / "api" / "widget" / wname, {**widget_pyramid(conn, today, payload["today"], m, r, step_t, track),
                                                     "action": (payload["action"] or {}).get("short"), "action_text": (payload["action"] or {}).get("text"),
                                                     "stake_today": (payload["action"] or {}).get("stake")})


def _eff_rules(conn: sqlite3.Connection, track: str, rules: Dict[str, Any]) -> Dict[str, Any]:
    from betpredict.builder.pyramid_auto import effective_rules

    try:
        return effective_rules(conn, track)
    except Exception:  # noqa: BLE001
        return rules


def _pyr_action(conn: sqlite3.Connection, track: str, tid: Optional[int]) -> Optional[Dict[str, Any]]:
    from betpredict.builder.pyramid_auto import action

    try:
        return action(conn, track, tid)
    except Exception as exc:  # noqa: BLE001
        return {"kind": "error", "text": str(exc)}


def _pyr_grid(track: str) -> Optional[Dict[str, Any]]:
    """Rezumatul grilei de variante (betpredict/lab/pyramid_grid.py) pentru piramida dată."""
    p = Path(__file__).resolve().parents[1] / "lab" / "pyramid_grid.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    x = d["pyramids"].get(track) or {}
    return {"matches": d["matches"], "split": d["split"], "tested": x.get("tested"), "both_positive": x.get("both_positive"),
            "test_positive_share": x.get("test_positive_share"), "baseline": x.get("baseline"), "top": x.get("top_by_train", [])[:5],
            "verdict": x.get("verdict")}


def _pyr_backtest(name: str = "pyramid140_backtest.json") -> Optional[Dict[str, Any]]:
    p = Path(__file__).resolve().parents[1] / "lab" / name
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def widget_pyramid(conn: sqlite3.Connection, today: date, td: Dict[str, Any], m: Dict[str, Any], r: Dict[str, Any],
                   step_t: str = "pyramid_step", track: str = "2.00") -> Dict[str, Any]:
    """Starea piramidei pentru widget. ``step`` = pași câștigați ÎNAINTEA biletului de azi (0-based: widget-ul afișează step+1);
    ``step_no`` = același pas, 1-based;
    după o pierdere run-ul e „lost”: ``restart`` = True, următorul pas e 1 cu banca de start."""
    step_row = conn.execute(f"SELECT step_no, bank_before, bank_after, result FROM {step_t} WHERE ticket_id=?",
                            (m.get("id"),)).fetchone() if m.get("id") else None
    run_status = r.get("status")
    restart = run_status in ("lost", "completed")
    return {
        "schema": "betpredict.widget_pyramid.v2", "track": track, "date": today.isoformat(), "status": td.get("status"),
        "reason": td.get("reason"), "odds": m.get("total_odds"), "p": m.get("p_ticket"), "legs": len(m.get("legs") or []),
        "result": m.get("status"),
        "step": (step_row["step_no"] - 1) if step_row else (0 if restart or not r else (r.get("step") or 0)),
        "step_no": step_row["step_no"] if step_row else (1 if restart or not r else (r.get("step") or 0) + 1),
        "stake_bank": step_row["bank_before"] if step_row else None,
        "bank": r.get("bank"), "run_status": run_status, "steps_won": r.get("step"),
        "restart": restart, "next_step": 1 if restart else (r.get("step") or 0) + 1,
        "next_bank": r.get("start_bank") if restart else r.get("bank"),
    }


def publish_stats(conn: sqlite3.Connection, out_root: Path) -> None:
    from betpredict.learn import learning_doc
    from betpredict.stats import compute_stats

    docs = compute_stats(conn)
    for name, doc in docs.items():
        write_json(out_root / "api" / "stats" / f"{name}.json", doc)
    write_json(out_root / "api" / "stats" / "learning.json", learning_doc(conn))
    write_json(out_root / "api" / "lab" / "results.json", lab_doc(conn))


def lab_doc(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Rezultatele laboratorului + urmărirea live a „Super biletelor” pe strategie."""
    from betpredict.lab.superbilete import VARIANT, load_results

    doc = load_results()
    live: Dict[str, Dict[str, Any]] = {}
    for t in conn.execute("SELECT status, stake, payout, notes FROM ticket WHERE variant=? AND status!='replaced'", (VARIANT,)):
        try:
            name = (json.loads(t["notes"] or "{}").get("backtest") or {}).get("strategy") or "?"
        except ValueError:
            continue
        r = live.setdefault(name, {"n": 0, "won": 0, "lost": 0, "pending": 0, "staked_u": 0.0, "profit_u": 0.0})
        r["n"] += 1
        st = t["status"] if t["status"] in ("won", "lost") else "pending"
        r[st] += 1
        if st != "pending":
            r["staked_u"] += t["stake"] or 0
            r["profit_u"] += (t["payout"] or 0) - (t["stake"] or 0)  # plata reală (inclusiv sisteme pe combinații)
    doc["live"] = live
    from betpredict.experimental.supersocial import live_stats

    doc["stil_supersocial_live"] = live_stats(conn)
    return doc


def publish_meta(conn: sqlite3.Connection, out_root: Path, today: date, quota: Optional[Dict[str, Any]],
                 warnings: List[Any], step: str) -> None:
    last = json.loads(repo.get_state(conn, "meta.last_steps") or "{}")
    last[step] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with conn:
        repo.set_state(conn, "meta.last_steps", json.dumps(last))
    q = quota or {}
    degraded = bool(warnings) or bool(q.get("exhausted"))
    write_json(out_root / "api" / "meta.json", {
        "schema": "betpredict.meta.v1", "day": today.isoformat(), "model_version": MODEL_LABEL, "model_key": MODEL_VERSION, "app_version": __version__,
        "status": "degraded" if degraded else "ok",
        "quota": {k: q.get(k) for k in ("effective_remaining", "daily_quota", "exhausted")},
        "last_steps": last, "warnings": warnings[:20],
    })


def _sb_url(h, a, e):
    from betpredict.publish.day import superbet_url
    return superbet_url(h, a, e)
