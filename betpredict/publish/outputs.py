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


def ticket_json(conn: sqlite3.Connection, t: sqlite3.Row, with_reasons: bool = True) -> Dict[str, Any]:
    legs = conn.execute(
        """SELECT tl.*, p.p_calibrated, p.grade, p.line, p.market AS pmarket, m.kickoff_utc, m.home_name, m.away_name,
                  m.ft_home, m.ft_away, l.name AS league_name
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
    d: Dict[str, Any] = {
        "id": t["id"], "kind": t["kind"], "variant": t["variant"],
        "variant_label": VARIANTS.get(t["variant"], {"principal": "Principal", "alternativa": "Alternativă", "multi_zi": "Multi-zi"}.get(t["variant"], t["variant"])),
        "created_by": t["created_by"], "date": t["day"], "created_at": t["created_at"],
        "target_odds": t["target_odds"],
        # total_odds = cota JUCABILĂ acum (Superbet unde există); total_odds_published = cota la publicare (statistici)
        "total_odds": round(play_total, 2) if repriced else t["total_odds"], "total_odds_published": t["total_odds"],
        "repriced": repriced,
        "bookmakers": sorted({x["bookmaker"] for x in out_legs if x["bookmaker"]}), "p_ticket": t["p_ticket"], "ev": t["ev"],
        "status": t["status"], "payout": t["payout"], "settled_legs": settled, "legs_count": len(out_legs),
        "effective_odds": round(eff, 2), "legs": out_legs,
        "stake_units": _stake_units(t),
        "clv": t["clv"] if "clv" in t.keys() else None,
        "safe": t["kind"] == "acca_safe",
    }
    if with_reasons:
        d["reasons"] = notes.get("reasons", [])
    return d


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


def publish_tickets(conn: sqlite3.Connection, out_root: Path, days: List[date], today: date) -> None:
    for d in days:
        ts = conn.execute("SELECT * FROM ticket WHERE day=? AND kind LIKE 'acca_%' AND status!='replaced' ORDER BY target_odds, id",
                          (d.isoformat(),)).fetchall()
        payload = {"schema": "betpredict.tickets.v1", "date": d.isoformat(), "targets": [50, 100, 500], "safe_targets": [2, 3, 5],
                   "tickets": [ticket_json(conn, t) for t in ts],
                   "notes": [KIND_NOTES[k] for k in ("acca_safe", "acca_50", "acca_100", "acca_500")]}
        write_json(out_root / "api" / "tickets" / f"{d.isoformat()}.json", payload)
        if d == today:
            write_json(out_root / "api" / "tickets" / "today.json", payload)
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
    raw = repo.get_state(conn, f"pyramid.day.{today.isoformat()}")
    st = json.loads(raw) if raw else {"status": "no_bet", "reason": "Încă nu s-a generat propunerea zilei.", "main": None, "alternatives": []}

    def tk(tid: Optional[int]):
        if not tid:
            return None
        row = conn.execute("SELECT * FROM ticket WHERE id=?", (tid,)).fetchone()
        return ticket_json(conn, row) if row else None

    run = conn.execute("SELECT * FROM pyramid_run ORDER BY id DESC LIMIT 1").fetchone()
    history = []
    for k in conn.execute("SELECT key, value FROM ingest_state WHERE key LIKE 'pyramid.day.%' ORDER BY key DESC LIMIT 120"):
        v = json.loads(k["value"])
        t = conn.execute("SELECT * FROM ticket WHERE id=?", (v.get("main"),)).fetchone() if v.get("main") else None
        history.append({"date": k["key"].rsplit(".", 1)[1], "status": v.get("status"), "ticket_id": v.get("main"),
                        "odds": t["total_odds"] if t else None, "p": t["p_ticket"] if t else None,
                        "result": t["status"] if t else None})
    runs = []
    for r in conn.execute("SELECT * FROM pyramid_run ORDER BY id DESC LIMIT 50"):
        mx = conn.execute("SELECT MAX(bank_after), MAX(date) FROM pyramid_step WHERE run_id=?", (r["id"],)).fetchone()
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
        "schema": "betpredict.pyramid.v1", "date": today.isoformat(), "rules": RULES,
        "today": {"status": st.get("status"), "reason": st.get("reason"), "main": tk(st.get("main")),
                  "alternatives": [x for x in (tk(a) for a in st.get("alternatives", [])) if x]},
        "run": ({"id": run["id"], "start_date": run["start_date"], "status": run["status"], "step": run["current_step"],
                 "bank": run["current_bank"], "start_bank": run["start_bank"], "withdrawn": run["withdrawn_total"]} if run else None),
        "history": history, "runs": runs, "reach_probability": reach,
    }
    write_json(out_root / "api" / "pyramid" / "state.json", payload)


def publish_stats(conn: sqlite3.Connection, out_root: Path) -> None:
    from betpredict.learn import learning_doc
    from betpredict.stats import compute_stats

    docs = compute_stats(conn)
    for name, doc in docs.items():
        write_json(out_root / "api" / "stats" / f"{name}.json", doc)
    write_json(out_root / "api" / "stats" / "learning.json", learning_doc(conn))


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
