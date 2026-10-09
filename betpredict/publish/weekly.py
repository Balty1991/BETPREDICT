"""Raportul săptămânal (luni, după reantrenare): ROI, rată de câștig, CLV, ce a schimbat Robotul.

Publicat în ``api/stats/weekly.json`` = {"latest": raport, "history": [rezumate]}. ``latest.notify``
(id unic pe săptămână) e semnalul pentru aplicație: o notificare pe raport nou.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from betpredict.store import repo

KEY_PREFIX = "weekly.report."
HISTORY = 12


def week_id(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def _pct(x: Optional[float]) -> str:
    return "—" if x is None else f"{x:+.1f}%"


def build_weekly(conn: sqlite3.Connection, run_day: date) -> Dict[str, Any]:
    """Săptămâna încheiată înainte de ``run_day`` (luni → lunea–duminica precedentă)."""
    from betpredict.robot import MODEL_VERSION, is_recommended
    from betpredict.robot.markets import market_key
    from betpredict.segments import segment_action  # noqa: F401  (documentare)
    from betpredict.learn import _short
    from betpredict.stats import _agg, _group

    start = run_day - timedelta(days=7)
    end = run_day - timedelta(days=1)
    rows = conn.execute(
        """SELECT p.*, m.league_id, l.name AS league_name FROM prediction p JOIN match m ON m.id = p.match_id
           LEFT JOIN league l ON l.id = m.league_id
           WHERE p.model_version = ? AND p.shown_on_page = 'predictii' AND p.day >= ? AND p.day <= ?""",
        (MODEL_VERSION, start.isoformat(), end.isoformat())).fetchall()
    rec = [r for r in rows if is_recommended(r["p_calibrated"], r["odds_shown"], r["ev"], r["grade"])]
    picks = [r for r in rows if r["is_pick"]]
    blocks = {"toate": _agg(rows), "pick": _agg(picks), "recomandate": _agg(rec), "valoare": _agg([r for r in rows if (r["ev"] or 0) > 0])}
    by_market = [g for g in _group(picks + [r for r in rec if not r["is_pick"]], lambda r: market_key(r["market"], r["line"] or 0.0))
                 if (g["won"] + g["lost"]) >= 5]
    by_market.sort(key=lambda g: -(g["roi_pct"] or -999))
    tickets = []
    for r in conn.execute(
        """SELECT kind, COUNT(*) n, SUM(status='won') won, SUM(status='lost') lost, SUM(status='pending') pending,
                  SUM(CASE WHEN status IN ('won','lost') THEN COALESCE(payout,0) - stake ELSE 0 END) profit,
                  SUM(CASE WHEN status IN ('won','lost') THEN stake ELSE 0 END) staked, AVG(clv) clv, COUNT(clv) clv_n
           FROM ticket WHERE created_by='robot' AND status != 'replaced' AND day >= ? AND day <= ? GROUP BY kind ORDER BY kind""",
        (start.isoformat(), end.isoformat())):
        tickets.append({"kind": r["kind"], "n": r["n"], "won": r["won"] or 0, "lost": r["lost"] or 0, "pending": r["pending"] or 0,
                        "profit": round(r["profit"] or 0, 2), "roi_pct": round(100 * (r["profit"] or 0) / r["staked"], 1) if r["staked"] else None,
                        "clv_avg": round(r["clv"], 4) if r["clv"] is not None else None, "clv_n": r["clv_n"]})
    sb = sum(1 for r in picks if (r["odds_taken_source"] or r["odds_source"]) == "superbet")
    changes = []
    for r in conn.execute(
        """SELECT run_at, change_type, market, league_id, before, after, evidence_json FROM learning_log
           WHERE change_type NOT IN ('legacy_performance_snapshot') AND run_at >= ? ORDER BY id DESC LIMIT 40""",
        ((run_day - timedelta(days=6)).isoformat(),)):
        ev = json.loads(r["evidence_json"] or "{}") or {}
        changes.append({"type": r["change_type"], "market": r["market"], "league_id": r["league_id"],
                        "before": _short(r["before"]), "after": _short(r["after"]), "why": ev.get("why"), "run_at": r["run_at"]})
    from betpredict.learn import _short  # noqa: F401
    from betpredict.robot.params import load_params

    segs = (load_params(conn).get("segments") or {})
    seg_list = [{"key": k, **v} for k, v in segs.items()]
    p = blocks["pick"]
    prev = get_report(conn, week_id(start - timedelta(days=7)))
    prev_p = (prev or {}).get("blocks", {}).get("pick", {})
    title = f"Raport săptămânal {start.strftime('%d.%m')}–{end.strftime('%d.%m')}"
    decided = (p.get("won") or 0) + (p.get("lost") or 0)
    body_parts = []
    if decided:
        body_parts.append(f"Pick-uri: {p['won']}/{decided} câștigate, ROI {_pct(p.get('roi_pct'))}")
    if p.get("clv_n"):
        body_parts.append(f"CLV {p['clv_avg'] * 100:+.1f}% ({p['clv_n']})")
    body_parts.append(f"{len(changes)} ajustări ale Robotului" if changes else "fără ajustări ale Robotului")
    doc = {
        "schema": "betpredict.weekly.v1", "id": week_id(start), "from": start.isoformat(), "to": end.isoformat(),
        "generated_at": repo.now_iso(), "title": title,
        "blocks": blocks, "tickets": tickets,
        "best_markets": by_market[:3], "worst_markets": list(reversed(by_market[-3:])) if len(by_market) > 3 else [],
        "superbet_share": round(sb / len(picks), 3) if picks else None,
        "vs_previous": {"roi_pct": [prev_p.get("roi_pct"), p.get("roi_pct")], "clv_avg": [prev_p.get("clv_avg"), p.get("clv_avg")]} if prev else None,
        "changes": changes,
        "change_counts": _counts(changes),
        "segments": {"off": [s for s in seg_list if s.get("action") == "off"], "boost": [s for s in seg_list if s.get("action") == "boost"]},
        "notify": {"id": f"weekly-{week_id(start)}", "title": title, "body": " · ".join(body_parts)},
    }
    return doc


def _counts(changes: List[Dict[str, Any]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for c in changes:
        out[c["type"]] = out.get(c["type"], 0) + 1
    return out


def get_report(conn: sqlite3.Connection, wid: str) -> Optional[Dict[str, Any]]:
    raw = repo.get_state(conn, KEY_PREFIX + wid)
    return json.loads(raw) if raw else None


def save_weekly(conn: sqlite3.Connection, run_day: date) -> Dict[str, Any]:
    doc = build_weekly(conn, run_day)
    with conn:
        repo.set_state(conn, KEY_PREFIX + doc["id"], json.dumps(doc, ensure_ascii=False, default=str))
    return doc


def weekly_doc(conn: sqlite3.Connection, today: date) -> Dict[str, Any]:
    keys = [r[0] for r in conn.execute("SELECT key FROM ingest_state WHERE key LIKE ? ORDER BY key DESC", (KEY_PREFIX + "%",))]
    if not keys:  # primul raport: săptămâna încheiată cel mai recent
        save_weekly(conn, today)  # ultimele 7 zile încheiate (până ieri)
        keys = [r[0] for r in conn.execute("SELECT key FROM ingest_state WHERE key LIKE ? ORDER BY key DESC", (KEY_PREFIX + "%",))]
    docs = [json.loads(repo.get_state(conn, k)) for k in keys[:HISTORY]]
    hist = [{"id": d["id"], "from": d["from"], "to": d["to"], "title": d["title"],
             "pick": {k: d["blocks"]["pick"].get(k) for k in ("won", "lost", "win_rate", "roi_pct", "profit", "clv_avg", "clv_n")},
             "changes": len(d.get("changes") or [])} for d in docs]
    return {"schema": "betpredict.weekly_index.v1", "latest": docs[0] if docs else None, "history": hist}


def publish_weekly(conn: sqlite3.Connection, out_root: Path, today: date) -> None:
    from betpredict.publish.day import write_json

    write_json(out_root / "api" / "stats" / "weekly.json", weekly_doc(conn, today))
