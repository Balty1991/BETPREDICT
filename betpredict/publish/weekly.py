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
    rec = [r for r in rows if is_recommended(r["p_calibrated"], r["odds_shown"], r["ev"], r["grade"], True, _rtop(r))]
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
                        "profit": round(r["profit"] or 0, 2), "staked": round(r["staked"] or 0, 2), "roi_pct": round(100 * (r["profit"] or 0) / r["staked"], 1) if r["staked"] else None,
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


def _frac(pct: Optional[float]) -> Optional[float]:
    return None if pct is None else round(pct / 100.0, 4)


def contract_report(d: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """``api/report/weekly.json`` (``betpredict.report.weekly.v1``, docs/data-contract.md §11) — citit de aplicația Android.

    Publicat doar când săptămâna are ceva decontat (altfel 404, tolerat): nu notificăm rapoarte goale."""
    p = d["blocks"]["pick"]
    decided = (p.get("won") or 0) + (p.get("lost") or 0)
    tk = d.get("tickets") or []
    t_dec = sum(t["won"] + t["lost"] for t in tk)
    if not decided and not t_dec:
        return None
    roi, wr = _frac(p.get("roi_pct")), p.get("win_rate")
    if decided:
        head = (f"Săptămână {'pe plus' if (roi or 0) > 0 else 'pe minus' if (roi or 0) < 0 else 'pe zero'}: "
                f"ROI {(roi or 0) * 100:+.1f}%, {round((wr or 0) * 100)}% câștigate")
    else:
        head = f"Bilanț bilete: {sum(t['won'] for t in tk)}/{t_dec} câștigate"
    if p.get("clv_n"):
        head += f", CLV {p['clv_avg'] * 100:+.1f}%"
    hl: List[str] = []
    if decided:
        hl.append(f"Pick-uri: {p['won']}/{decided} câștigate, profit {p.get('profit') or 0:+.2f}u")
    rec = d["blocks"]["recomandate"]
    if (rec.get("won") or 0) + (rec.get("lost") or 0):
        hl.append(f"Recomandate: ROI {_pct(rec.get('roi_pct'))}, {rec['won']}/{rec['won'] + rec['lost']} câștigate")
    if t_dec:
        prof = sum(t["profit"] for t in tk)
        hl.append(f"Bilete: {sum(t['won'] for t in tk)}/{t_dec} câștigate, profit {prof:+.2f}u")
    segs = d.get("segments") or {}
    if segs.get("off") or segs.get("boost"):
        hl.append(f"Focus: {len(segs.get('boost') or [])} segmente întărite, {len(segs.get('off') or [])} oprite")
    if d.get("changes"):
        hl.append(f"Robotul a făcut {len(d['changes'])} ajustări după reantrenare")
    t_pyr = [t for t in tk if t["kind"] == "pyramid"]
    t_acc = [t for t in tk if t["kind"] != "pyramid"]

    def tsum(ts):
        st = sum(t.get("staked") or 0 for t in ts)
        return {"n": sum(t["n"] for t in ts), "won": sum(t["won"] for t in ts), "lost": sum(t["lost"] for t in ts),
                "roi": round(sum(t["profit"] for t in ts) / st, 4) if st else None}
    recs = []
    for m in d.get("worst_markets") or []:
        if (m.get("roi_pct") or 0) < 0:
            recs.append(f"Atenție la piața {m['key']}: ROI {_pct(m['roi_pct'])} săptămâna aceasta")
    for m in d.get("best_markets") or []:
        if (m.get("roi_pct") or 0) > 0:
            recs.append(f"Piața {m['key']} a mers bine: ROI {_pct(m['roi_pct'])}")
    return {
        "schema": "betpredict.report.weekly.v1", "week": d["id"], "period": {"from": d["from"], "to": d["to"]},
        "generated_at": d["generated_at"], "headline": head[:120], "highlights": [h[:80] for h in hl[:5]],
        "summary": {"predictions": {"n": p.get("n") or (p.get("won", 0) + p.get("lost", 0) + p.get("void", 0) + p.get("pending", 0)),
                                    "won": p.get("won") or 0, "lost": p.get("lost") or 0, "winrate": wr, "roi": roi,
                                    "clv": p.get("clv_avg")},
                    "tickets": tsum(t_acc), "pyramid": tsum(t_pyr)},
        "recommendations": recs[:4],
    }


def publish_weekly(conn: sqlite3.Connection, out_root: Path, today: date) -> None:
    from betpredict.publish.day import write_json

    doc = weekly_doc(conn, today)
    write_json(out_root / "api" / "stats" / "weekly.json", doc)
    rep = contract_report(doc["latest"]) if doc.get("latest") else None
    if rep:
        write_json(out_root / "api" / "report" / "weekly.json", rep)


def _rtop(r) -> bool:
    import json as _j
    try:
        return bool(_j.loads(r["reasons_json"] or "{}").get("top", True))
    except (ValueError, KeyError, IndexError, TypeError):
        return True
