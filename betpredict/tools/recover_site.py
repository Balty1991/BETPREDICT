"""Recuperarea zilelor pierdute (24.10 dimineața → 27.10 seara) din ultima publicare bună a site-ului.

27.10.2026 20:15 UTC: o descărcare întreruptă a bazei a pornit pipeline-ul pe o bază goală, care a suprascris baza din
release. Baza s-a restaurat din copia din 24.10 ~05:00 UTC; ce s-a întâmplat între timp există doar în fișierele publicate
pe site la 27.10 20:14 UTC (commit gh-pages 61be7b6), copiate în ``data/recovery/2026-10-27``:

- biletele (``api/tickets/*.json``): cele lipsă se adaugă cu id-ul lor de atunci, cele existente își primesc rezultatul;
- piramidele (``api/pyramid/state*.json``): seriile și treptele din 25–27.10, cu banca recalculată din cote;
- biletele și treptele făcute de pipeline după restaurare (id-uri care s-ar suprapune) se mută la id-uri noi, iar treptele
  de azi se pun la capătul seriei recuperate.

Rulează o singură dată (marcaj în ``ingest_state``)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

from betpredict.store import repo

SNAP = Path(__file__).resolve().parents[2] / "data" / "recovery" / "2026-10-27"
MARK = "recovery.site.2026-10-27"
LOST_FROM = "2026-10-24T04:51:00"   # după ultimul bilet din copia restaurată
SITE_AT = "2026-10-27T20:14:00"     # ultima publicare bună
NEW_FROM = "2026-10-28"             # zilele construite după restaurare
TRACKS = {"2.00": "pyramid", "1.20": "pyramid120", "1.40": "pyramid140", "1.60": "pyramid160", "boost": "pyramidboost",
          "mici": "pyramidmici", "r5": "pyramidr5", "r10": "pyramidr10", "r100": "pyramidr100"}


def _site_tickets(snap: Path) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    files = sorted((snap / "tickets").glob("*.json"))
    files = [f for f in files if f.name == "history.json"] + [f for f in files if f.name != "history.json"]
    for f in files:  # zilele după istoric: au starea cea mai nouă
        for t in json.loads(f.read_text(encoding="utf-8")).get("tickets") or []:
            out[t["id"]] = t
    return out


def _market(l: Dict[str, Any]) -> str:
    line = l.get("line")
    return f"{l['market']}|{0 if line is None else float(line):g}"


def _notes(t: Dict[str, Any]) -> Dict[str, Any]:
    n: Dict[str, Any] = {"label": t.get("variant_label") or t.get("variant"), "recovered": "2026-10-27",
                         "reasons": t.get("reasons") or []}
    for k in ("lottery", "safe", "informational", "risk_acknowledged", "paper", "experimental"):
        if t.get(k):
            n[k] = True
    b = t.get("bucket") or ""
    if t["kind"] == "acca_test":
        n.update(test=True, mono=True, paper=True)
    elif t["kind"] == "acca_mono":
        n.update(mono=True, paper=True)
    elif t["kind"] == "acca_seg":
        n.update(segments=True, paper=True)
    if b.startswith("Loterie"):
        n["lottery"] = True
    if t["kind"] == "acca_boost":
        n["boost"] = True
    return n


def _remap_new(conn: sqlite3.Connection, site_ids: set, prefixes: List[str]) -> int:
    """Biletele făcute după restaurare care au un id folosit atunci se mută la id-uri libere (cu toate referințele)."""
    clash = [r[0] for r in conn.execute("SELECT id FROM ticket WHERE created_at >= ? ORDER BY id", (NEW_FROM,)) if r[0] in site_ids]
    if not clash:
        return 0
    nxt = max(max(site_ids), conn.execute("SELECT MAX(id) FROM ticket").fetchone()[0] or 0) + 1
    mp = {}
    for old in clash:
        mp[old] = nxt
        nxt += 1
    for old, new in mp.items():
        conn.execute("UPDATE ticket SET id=? WHERE id=?", (new, old))
        conn.execute("UPDATE ticket_leg SET ticket_id=? WHERE ticket_id=?", (new, old))
        for pre in prefixes:
            conn.execute(f"UPDATE {pre}_step SET ticket_id=? WHERE ticket_id=?", (new, old))
    # biletul zilei din starea piramidelor („main”)
    for key, val in conn.execute("SELECT key, value FROM ingest_state WHERE key LIKE 'pyramid%.day.%' AND key >= ?", ("",)).fetchall():
        try:
            st = json.loads(val)
        except (TypeError, ValueError):
            continue
        if isinstance(st, dict) and st.get("main") in mp:
            st["main"] = mp[st["main"]]
            conn.execute("UPDATE ingest_state SET value=? WHERE key=?", (json.dumps(st, ensure_ascii=False), key))
    return len(mp)


def _tickets(conn: sqlite3.Connection, site: Dict[int, Dict[str, Any]]) -> Dict[str, int]:
    have = {r[0]: r[1] for r in conn.execute("SELECT id, status FROM ticket")}
    stake_of = {(r[0], r[1]): r[2] for r in conn.execute("SELECT kind, variant, stake FROM ticket WHERE stake IS NOT NULL ORDER BY id")}
    stake_kind = {r[0]: r[1] for r in conn.execute("SELECT kind, stake FROM ticket WHERE stake IS NOT NULL ORDER BY id")}
    added = updated = 0
    for tid, t in sorted(site.items()):
        if tid in have:
            if have[tid] == "pending" and t["status"] != "pending":
                conn.execute("UPDATE ticket SET status=?, payout=? WHERE id=?", (t["status"], t.get("payout"), tid))
                updated += 1
            for l in t["legs"]:
                if l.get("result"):
                    conn.execute("UPDATE ticket_leg SET result=? WHERE ticket_id=? AND match_id=? AND selection=? AND result IS NULL",
                                 (l["result"], tid, l["match_id"], l["selection"]))
            continue
        if (t.get("created_at") or "") < LOST_FROM:
            continue  # nu era în fereastra pierdută: nu-l re-creăm
        if (t.get("date") or "") >= NEW_FROM and conn.execute(
                "SELECT 1 FROM ticket WHERE kind=? AND variant IS ? AND day=? AND status!='replaced'", (t["kind"], t["variant"], t["date"])).fetchone():
            continue  # zilele de după restaurare au deja biletele lor: nu le dublăm
        stake = 1.0 if t["kind"] == "pyramid" else stake_of.get((t["kind"], t["variant"]), stake_kind.get(t["kind"], 0.1))
        conn.execute(
            """INSERT INTO ticket (id, kind, variant, created_by, target_odds, total_odds, p_ticket, ev, stake, status, payout,
                                   created_at, notes, day, clv) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (tid, t["kind"], t["variant"], t.get("created_by") or "robot", t.get("target_odds"),
             t.get("total_odds_published") or t.get("total_odds"), t.get("p_ticket_raw") or t.get("p_ticket"), t.get("ev"), stake,
             t["status"], t.get("payout"), t.get("created_at"), json.dumps(_notes(t), ensure_ascii=False), t.get("date"), t.get("clv")))
        for l in t["legs"]:
            conn.execute("""INSERT INTO ticket_leg (ticket_id, prediction_id, match_id, market, selection, odds, result, odds_source, closing_odds)
                            VALUES (?,?,?,?,?,?,?,?,?)""",
                         (tid, None, l["match_id"], _market(l), l["selection"], l.get("odds_published") or l.get("odds"),
                          l.get("result"), l.get("odds_source_published") or l.get("odds_source"), l.get("closing_odds")))
            if l["market"] == "boost" and not l.get("result"):  # ca decontarea cotelor mărite s-o găsească
                sel = l["selection"]
                kind, name = ("super_cota", sel.replace("Super Cota ", "SC-")) if sel.startswith("Super Cota ") else ("core", sel)
                conn.execute("""INSERT OR IGNORE INTO sb_boost (match_id, uid, kind, market_name, name, price, first_seen, last_seen, method)
                                VALUES (?,?,?,?,?,?,?,?,?)""",
                             (l["match_id"], f"recovered:{tid}:{name}", kind, None, name, l.get("odds"), t.get("created_at"),
                              t.get("created_at"), "recuperat"))
        added += 1
    return {"added": added, "updated": updated}


def _pyramid(conn: sqlite3.Connection, st: Dict[str, Any], pre: str, site: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
    from betpredict.builder.pyramid import ensure_track_tables

    ensure_track_tables(conn, pre)
    runs = sorted(st.get("runs") or [], key=lambda r: r["id"])
    if not runs:
        return {"skipped": "fără serii"}
    rules = st.get("rules") or {}
    start_bank = float(rules.get("start_bank") or 100.0)
    # 1) treptele și seriile făcute după restaurare: le scoatem, le punem la loc la capăt
    post = [dict(r) for r in conn.execute(f"SELECT * FROM {pre}_step WHERE date >= ? ORDER BY date, step_no", (NEW_FROM,))]
    conn.execute(f"DELETE FROM {pre}_step WHERE date >= ?", (NEW_FROM,))
    site_run_ids = {r["id"] for r in runs}
    conn.execute(f"DELETE FROM {pre}_step WHERE run_id IN (SELECT id FROM {pre}_run WHERE start_date >= ?)", (NEW_FROM,))
    conn.execute(f"DELETE FROM {pre}_run WHERE start_date >= ?", (NEW_FROM,))
    # 2) seriile de atunci (cu id-urile lor)
    for r in runs:
        row = conn.execute(f"SELECT id FROM {pre}_run WHERE id=?", (r["id"],)).fetchone()
        if not row:
            conn.execute(f"INSERT INTO {pre}_run (id, start_date, start_bank, status, current_step, current_bank, withdrawn_total, rule_json) "
                         "VALUES (?,?,?,?,?,?,?,?)", (r["id"], r["start_date"], start_bank, "active", 0, start_bank, 0.0, json.dumps(rules)))
    # 3) treptele din 24–27.10 care lipsesc, pe seria activă atunci (cea mai nouă pornită până în ziua respectivă)
    added = 0
    for h in sorted((h for h in st.get("history") or [] if h.get("status") == "pick" and h.get("ticket_id")), key=lambda h: h["date"]):
        if h["date"] < "2026-10-24":
            continue
        cand = [r for r in runs if r["start_date"] <= h["date"]]
        if not cand:
            continue
        run_id = max(cand, key=lambda r: (r["start_date"], r["id"]))["id"]
        if conn.execute(f"SELECT 1 FROM {pre}_step WHERE run_id=? AND (date=? OR ticket_id=?)", (run_id, h["date"], h["ticket_id"])).fetchone():
            continue
        if not conn.execute("SELECT 1 FROM ticket WHERE id=?", (h["ticket_id"],)).fetchone():
            continue
        last = conn.execute(f"SELECT COALESCE(MAX(step_no), 0) FROM {pre}_step WHERE run_id=?", (run_id,)).fetchone()[0]
        conn.execute(f"INSERT INTO {pre}_step (run_id, step_no, date, ticket_id, stake, odds, result, bank_before, bank_after, withdrawn) "
                     "VALUES (?,?,?,?,NULL,?,NULL,NULL,NULL,0)", (run_id, last + 1, h["date"], h["ticket_id"], h.get("odds")))
        added += 1
    # 3b) banca pe fiecare treaptă a seriilor din fereastră, refăcută din cote și rezultate (cum le avea site-ul)
    res_of = {h["ticket_id"]: h.get("result") for h in st.get("history") or [] if h.get("ticket_id")}
    for r in runs:
        steps = conn.execute(f"SELECT step_no, ticket_id, odds, result FROM {pre}_step WHERE run_id=? ORDER BY step_no", (r["id"],)).fetchall()
        if not steps or not any(1 for x in conn.execute(f"SELECT 1 FROM {pre}_step WHERE run_id=? AND date >= '2026-10-24'", (r["id"],))):
            continue
        bank = start_bank
        for no, tid, odds, res in steps:
            sres = res_of.get(tid)
            res = res or (sres if sres in ("won", "lost", "void") else None)
            t = site.get(tid) or {}
            mult = t.get("payout") or odds or 1.0
            after = None if res is None else (0.0 if res == "lost" else round(bank * (mult if res == "won" else 1.0), 2))
            conn.execute(f"UPDATE {pre}_step SET stake=?, bank_before=?, result=?, bank_after=? WHERE run_id=? AND step_no=?",
                         (bank, bank, res, after, r["id"], no))
            if after is None:
                break
            bank = after
    # 4) starea seriilor exact ca atunci (o treaptă din 27.10 încă în joc se decontează la rularea asta)
    for r in runs:
        conn.execute(f"UPDATE {pre}_run SET status=?, current_step=?, current_bank=?, withdrawn_total=? WHERE id=?",
                     (r["status"], int(r.get("steps") or 0), float(r.get("bank") or 0.0), float(r.get("withdrawn") or 0.0), r["id"]))
    # 5) treptele de azi (făcute după restaurare) la capătul seriei active; dacă nu e niciuna activă, o serie nouă
    moved = 0
    for s in post:
        run = conn.execute(f"SELECT * FROM {pre}_run WHERE status='active' ORDER BY id DESC LIMIT 1").fetchone()
        if not run:
            conn.execute(f"INSERT INTO {pre}_run (start_date, start_bank, status, current_step, current_bank, rule_json) VALUES (?,?,?,?,?,?)",
                         (s["date"], start_bank, "active", 0, start_bank, json.dumps(rules)))
            run = conn.execute(f"SELECT * FROM {pre}_run WHERE status='active' ORDER BY id DESC LIMIT 1").fetchone()
        step_no = conn.execute(f"SELECT COALESCE(MAX(step_no), 0) FROM {pre}_step WHERE run_id=?", (run["id"],)).fetchone()[0] + 1
        bank = run["current_bank"]
        conn.execute(f"INSERT INTO {pre}_step (run_id, step_no, date, ticket_id, stake, odds, result, bank_before, bank_after, withdrawn) "
                     "VALUES (?,?,?,?,?,?,NULL,?,NULL,0)", (run["id"], step_no, s["date"], s["ticket_id"], bank, s["odds"], bank))
        moved += 1
    return {"steps_added": added, "today_moved": moved, "runs": len(site_run_ids)}


def recover(conn: sqlite3.Connection, snap: Path = SNAP, force: bool = False) -> Dict[str, Any]:
    if not snap.exists():
        return {"skipped": "fără copie"}
    if repo.get_state(conn, MARK) and not force:
        return {"skipped": "deja făcută"}
    n = conn.execute("SELECT COUNT(*) FROM ticket WHERE created_at < ?", (LOST_FROM,)).fetchone()[0]
    if n < 1000:
        return {"skipped": f"baza nu e cea restaurată ({n} bilete vechi)"}
    site = _site_tickets(snap)
    states = {}
    for f in sorted((snap / "pyramid").glob("state*.json")):
        st = json.loads(f.read_text(encoding="utf-8"))
        if st.get("track") in TRACKS:
            states[TRACKS[st["track"]]] = st
    from betpredict.builder.pyramid import ensure_track_tables

    for pre in states:
        ensure_track_tables(conn, pre)
    out: Dict[str, Any] = {}
    with conn:
        out["remapped"] = _remap_new(conn, set(site), list(states))
        out["tickets"] = _tickets(conn, site)
        out["pyramids"] = {pre: _pyramid(conn, st, pre, site) for pre, st in states.items()}
        repo.set_state(conn, MARK, json.dumps(out, ensure_ascii=False))
    return out
