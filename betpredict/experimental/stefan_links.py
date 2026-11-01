"""Biletele lui Ștefan din linkurile de share Superbet (``data/stefan_links.txt`` + issue-uri „Bilet Ștefan” ale lui Alin).

Fluxul: link onelink → HTML cu ``deep_link_sub1`` (JSON base64: ticket_id, user_name) → API-ul public Supersocial
``content-preview/.../public/ticket?ticket_id=`` (status 1 activ, 3 pierdut, 7 câștigat, 8 cashout; cotă, selecții).
Politicos: linkul se rezolvă o singură dată (cache în DB), apoi cel mult o cerere pe bilet pe rulare și doar cât e activ.
"""
from __future__ import annotations

import base64
import json
import os
import re
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

LINKS_PATH = Path(__file__).resolve().parents[2] / "data" / "stefan_links.txt"
SNAPSHOT_PATH = Path(__file__).resolve().parents[2] / "data" / "stefan_share_snapshots.json"
UA = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"
TICKET_API = "https://social-front-default-production.freetls.fastly.net/default/content-preview/rosuperbetsport/public/ticket?ticket_id="
ISSUES_API = "https://api.github.com/repos/Balty1991/BETPREDICT/issues?state=all&per_page=50&creator=Balty1991"
STATUS = {1: "pending", 3: "lost", 7: "won", 8: "cashout"}
TID_RE = re.compile(r"^[0-9A-Z]{3,5}-[A-Z0-9]{4,10}$")  # ex. 8939-BBNST0, 892O-SS3X1N (litera O)
LINK_RE = re.compile(r"https?://(?:superbet\.onelink\.me|[a-z0-9.-]*superbet\.ro)/\S+", re.I)

# piața Superbet (nume + selecție, ca în bilet) → cheia noastră
MARKETS = {("Bet Builder", "Peste 0.5;Peste 1.5"): "BB_H1O05_O15", ("Total goluri", "Peste 1.5"): "O15", ("Total goluri", "Peste 2.5"): "O25",
           ("Prima repriză - Total goluri", "Peste 0.5"): "H1O05"}

TABLE = """CREATE TABLE IF NOT EXISTS stefan_sb (
  ticket_id TEXT PRIMARY KEY, link TEXT, user_name TEXT, first_seen TEXT, fetched_at TEXT, status INTEGER, doc TEXT)"""
LINKS = "CREATE TABLE IF NOT EXISTS stefan_sb_link (link TEXT PRIMARY KEY, ticket_id TEXT, resolved_at TEXT)"


def _get(url: str, timeout: int = 20, headers: Optional[Dict[str, str]] = None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ro-RO,ro;q=0.9", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 — doar URL-uri fixe / linkuri Superbet
        return r.read()


def parse_share(html: str) -> Optional[Dict[str, Any]]:
    """JSON-ul din ``deep_link_sub1`` (URL-encoded, cu \\u escape-uri) din pagina onelink."""
    s = html.replace("\\u003D", "=").replace("\\u003d", "=").replace("\\u0026", "&").replace("\\/", "/")
    m = re.search(r"deep_link_sub1(?:=|%3D)([A-Za-z0-9+/=%_-]+)", s)
    if not m:
        return None
    raw = urllib.parse.unquote(m.group(1)).replace("-", "+").replace("_", "/")
    raw += "=" * (-len(raw) % 4)
    try:
        d = json.loads(base64.b64decode(raw).decode("utf-8", "replace"))
    except (ValueError, json.JSONDecodeError):
        return None
    return d if isinstance(d, dict) and d.get("ticket_id") else None


def read_links(path: Path = LINKS_PATH) -> List[str]:
    out: List[str] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                out.append(line.split()[0])
    except OSError:
        pass
    try:  # issue-uri „Bilet Ștefan” deschise din aplicație de Alin: linkul sau ticket_id-ul din titlu/corp
        tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        hdr = {"Accept": "application/vnd.github+json", **({"Authorization": f"Bearer {tok}"} if tok else {})}
        req = urllib.request.Request(ISSUES_API, headers={"User-Agent": "betpredict", **hdr})
        with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
            for it in json.loads(r.read()):
                if "tefan" not in (it.get("title") or ""):
                    continue  # doar issue-urile „Bilet Ștefan” deschise de Alin
                txt = f"{it.get('title') or ''}\n{it.get('body') or ''}"
                out += LINK_RE.findall(txt) + [w for w in re.findall(r"\b[0-9]{3}[0-9A-Z]{0,2}-[A-Z0-9]{4,10}\b", txt)]
    except Exception:  # noqa: BLE001 — fără GitHub, rămân linkurile din fișier
        pass
    seen, uniq = set(), []
    for x in out:
        x = x.rstrip(").,;")
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def leg_key(market: str, odd: str) -> str:
    return MARKETS.get((market or "", odd or ""), f"SB:{market}:{odd}")


def _ensure(conn: sqlite3.Connection) -> None:
    conn.execute(TABLE)
    conn.execute(LINKS)
    for col, typ in (("fetch_error", "TEXT"),):
        try:
            conn.execute(f"ALTER TABLE stefan_sb ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass


def load_snapshots(path: Path = SNAPSHOT_PATH) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    data.setdefault("tickets", {})
    data.setdefault("errors", {})
    return data


def save_snapshots(data: Dict[str, Any], path: Path = SNAPSHOT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _remember(tid: str, payload: Optional[Dict[str, Any]], error: Optional[str], stamp: str, path: Path) -> None:
    """Keep the first full ticket document. A later 404 must not erase it."""
    data = load_snapshots(path)
    if payload is not None:
        data["tickets"][tid] = payload
        data["errors"].pop(tid, None)
    elif error:
        data["errors"][tid] = {"error": error, "at": stamp}
    save_snapshots(data, path)


def sync(conn: sqlite3.Connection, links: Optional[List[str]] = None, fetch: Callable[[str], bytes] = _get,
         now: Optional[datetime] = None, max_calls: int = 30, snapshot_path: Optional[Path] = None) -> Dict[str, Any]:
    """Rezolvă linkurile noi (o dată) și reîncarcă biletele active (o cerere pe bilet). Întoarce contoarele.

    The full Superbet payload is stored on the first successful fetch. Failed fetches (geo-block, 404 after
    settlement) stay visible in ``errors`` and do not wipe a snapshot we already have.
    """
    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    path = snapshot_path or SNAPSHOT_PATH
    _ensure(conn)
    snaps = load_snapshots(path)
    links = read_links() if links is None else links
    calls, new, upd = 0, 0, 0
    errors: List[Dict[str, str]] = []
    for link in links:
        if calls >= max_calls:
            break
        if TID_RE.match(link):
            tid, user = link, None
        else:
            row = conn.execute("SELECT ticket_id FROM stefan_sb_link WHERE link=?", (link,)).fetchone()
            if row:
                continue  # rezolvat deja: biletul se reîncarcă mai jos, dacă e activ
            calls += 1
            try:
                d = parse_share(fetch(link).decode("utf-8", "replace"))
            except Exception as exc:  # noqa: BLE001
                errors.append({"link": link, "error": f"{type(exc).__name__}: {exc}"})
                continue
            if not d:
                errors.append({"link": link, "error": "linkul nu conține ticket_id"})
                continue
            tid, user = d["ticket_id"], d.get("user_name")
            conn.execute("INSERT OR REPLACE INTO stefan_sb_link VALUES (?,?,?)", (link, tid, stamp))
        if conn.execute("SELECT 1 FROM stefan_sb WHERE ticket_id=?", (tid,)).fetchone() is None:
            conn.execute("INSERT INTO stefan_sb (ticket_id, link, user_name, first_seen, status) VALUES (?,?,?,?,NULL)",
                         (tid, None if TID_RE.match(link) else link, user, stamp))
            new += 1
        cached = snaps["tickets"].get(tid)
        if cached and conn.execute("SELECT doc FROM stefan_sb WHERE ticket_id=?", (tid,)).fetchone()[0] is None:
            t = cached.get("ticket") or cached
            conn.execute("UPDATE stefan_sb SET doc=?, status=COALESCE(status, ?), fetch_error=NULL WHERE ticket_id=?",
                         (json.dumps(cached, ensure_ascii=False), (t or {}).get("status"), tid))
    for tid, st in conn.execute("SELECT ticket_id, status FROM stefan_sb WHERE status IS NULL OR status = 1").fetchall():
        if calls >= max_calls:
            break
        calls += 1
        try:
            doc = json.loads(fetch(TICKET_API + urllib.parse.quote(tid)))
        except Exception as exc:  # noqa: BLE001
            msg = f"{type(exc).__name__}: {exc}"
            errors.append({"ticket_id": tid, "error": msg})
            conn.execute("UPDATE stefan_sb SET fetch_error=?, fetched_at=? WHERE ticket_id=?", (msg, stamp, tid))
            _remember(tid, None, msg, stamp, path)
            continue
        if not isinstance(doc, dict) or not (doc.get("ticket") or doc.get("selections")):
            msg = "răspuns fără bilet (posibil 404 după decontare sau blocaj regional)"
            errors.append({"ticket_id": tid, "error": msg})
            conn.execute("UPDATE stefan_sb SET fetch_error=? WHERE ticket_id=?", (msg, tid))
            _remember(tid, None, msg, stamp, path)
            continue
        t = doc.get("ticket") or doc
        user = (doc.get("user") or {}).get("username")
        conn.execute(
            "UPDATE stefan_sb SET fetched_at=?, status=?, doc=?, fetch_error=NULL, user_name=COALESCE(user_name, ?) WHERE ticket_id=?",
            (stamp, t.get("status"), json.dumps(doc, ensure_ascii=False), user, tid))
        _remember(tid, doc, None, stamp, path)
        upd += 1
    conn.commit()
    return {"calls": calls, "new": new, "updated": upd, "errors": errors}


def _unwrap(doc: Any) -> Dict[str, Any]:
    if isinstance(doc, dict) and isinstance(doc.get("ticket"), dict):
        return doc["ticket"]
    return doc if isinstance(doc, dict) else {}


def tickets(conn: sqlite3.Connection, snapshot_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Biletele din DB (sau din snapshot-ul salvat la prima citire) în formatul ``data/stefan_tickets.json``."""
    path = snapshot_path or SNAPSHOT_PATH
    snaps = load_snapshots(path)
    try:
        _ensure(conn)
        rows = conn.execute(
            "SELECT ticket_id, link, user_name, first_seen, fetched_at, status, doc, fetch_error FROM stefan_sb ORDER BY first_seen"
        ).fetchall()
    except sqlite3.Error:
        rows = []
    seen = set()
    out = []

    def _one(tid, link, user, first, fetched, st, doc, err):
        if tid in snaps["tickets"] and not doc:
            doc = json.dumps(snaps["tickets"][tid], ensure_ascii=False)
        if not doc:
            err = err or (snaps["errors"].get(tid) or {}).get("error")
            return {"id": f"sb-{tid}", "source": "superbet", "ticket_id": tid, "link": link, "user": user,
                    "posted": (first or "")[:10], "status_shown": "unavailable", "fetch_error": err or "biletul nu a putut fi citit",
                    "total_odds": None, "legs_total": 0, "more_hidden": 0, "sb": None, "legs": []}
        raw = json.loads(doc)
        t = _unwrap(raw)
        sels = t.get("selections") or []
        return {"id": f"sb-{tid}", "source": "superbet", "ticket_id": tid, "link": link, "user": user, "posted": (first or "")[:10],
                "status_shown": STATUS.get(st or 0, "pending"), "fetch_error": err,
                "total_odds": t.get("coefficient"), "legs_total": t.get("number_of_selections") or len(sels),
                "more_hidden": 0, "sb": {"status": st, "win_count": t.get("win_count"), "lost_count": t.get("lost_count"),
                                         "active_count": t.get("active_count"), "copies": t.get("number_of_copies"), "fetched_at": fetched},
                "legs": [{"home": s.get("team1_name"), "away": s.get("team2_name"), "market": leg_key(s.get("market_name"), s.get("odd_name")),
                          "sb_market": f"{s.get('market_name')}: {s.get('odd_name')}", "odds": s.get("odd_coefficient"), "kickoff": None,
                          "result_shown": None} for s in sels]}

    for row in rows:
        tid = row[0]
        seen.add(tid)
        out.append(_one(*row))
    for tid, payload in snaps["tickets"].items():
        if tid in seen:
            continue
        out.append(_one(tid, None, (payload.get("user") or {}).get("username"), None, None,
                        (payload.get("ticket") or {}).get("status"), json.dumps(payload), None))
    for tid, err in snaps["errors"].items():
        if tid in seen or tid in snaps["tickets"]:
            continue
        out.append(_one(tid, None, None, None, None, None, None, err.get("error") if isinstance(err, dict) else str(err)))
    return out
