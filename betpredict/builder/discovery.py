"""Piețe noi, găsite singur: Robotul scanează zilnic toate piețele Superbet pe care le poate deconta (cheile Stil din
``supersocial.MARKETS``), pe cotele de închidere și rezultatele reale, doar meciuri de cluburi jucate ziua.

Pașii, cu reguli stricte (piețele alese doar după rezultatele recente pică de obicei după aceea):
1. **candidat → probă**: ≥ ``MIN_N`` selecții în ultimele ``WINDOW_DAYS`` zile, ROI ≥ ``MIN_ROI``, pe plus în ambele jumătăți
   ale perioadei și limita de jos a intervalului (Wilson 90%) peste ``MIN_LOW``;
2. **probă → activă**: abia după ce ține pasul pe meciurile de DUPĂ ce a fost găsită (≥ ``FWD_N`` selecții, ROI ≥ 0);
   numai piețele active intră în biletele Robotului (ca piețele recomandate, cu fereastra lor de cote);
3. **scoasă**: dacă în probă sau activă pierde peste ``DROP_ROI`` pe ≥ ``FWD_N`` selecții noi, sau pe toată perioada.
Starea se ține în tabela ``rec_discovery``; scanarea rulează o dată pe zi."""

from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from betpredict.timeutil import canon_utc

WINDOW_DAYS = 60
BANDS: Tuple[Tuple[float, float], ...] = ((1.25, 1.45), (1.45, 1.65))  # cotele biletelor (≤ 1.65: marjă mică)
MIN_N = 150
MIN_ROI = 0.03
MIN_LOW = -0.03          # limita de jos a ROI-ului (din intervalul Wilson 90% al ratei de intrare)
FWD_N = 80
DROP_ROI = -0.06
SKIP_PREFIX = ("YC", "BOTH")  # cartonașele: decontarea nu e verificată pe Superbet
Z90 = 1.645


def _ensure(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS rec_discovery (
        key TEXT NOT NULL, band_lo REAL NOT NULL, band_hi REAL NOT NULL, status TEXT NOT NULL, since TEXT NOT NULL,
        n INTEGER, roi REAL, low REAL, fwd_n INTEGER, fwd_roi REAL, updated_at TEXT,
        PRIMARY KEY (key, band_lo))""")


def _wilson_low(h: int, n: int, z: float = Z90) -> float:
    if not n:
        return 0.0
    p = h / n
    d = 1 + z * z / n
    return (p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d


def _day_club(league: Optional[str], kickoff: str) -> bool:
    from betpredict.builder.super_tickets import INTL, SHORT_FROM_HOUR_RO
    from zoneinfo import ZoneInfo

    if INTL.search(league or ""):
        return False
    try:
        h = datetime.fromisoformat(kickoff.replace("Z", "+00:00")).astimezone(ZoneInfo("Europe/Bucharest")).hour
    except ValueError:
        return False
    return h >= SHORT_FROM_HOUR_RO


def settled_rows(conn: sqlite3.Connection, now: datetime, days: int = WINDOW_DAYS) -> List[Tuple[str, str, float, bool]]:
    """(cheie, kickoff, cota de închidere, intrat) pentru piețele decontabile, meciuri de cluburi ziua, terminate."""
    from betpredict.experimental import supersocial as SS

    since = canon_utc((now - timedelta(days=days)).isoformat())
    too_old = canon_utc(now.isoformat())
    out = []
    try:
        cur = conn.cursor()
        cur.row_factory = sqlite3.Row
        cur.execute(
            """SELECT s.market_name, s.outcome, MAX(s.price) AS price, m.*, l.name AS league_name
               FROM sb_offer_close s JOIN match m ON m.id=s.match_id LEFT JOIN league l ON l.id=m.league_id
               WHERE m.status='finished' AND m.ft_home IS NOT NULL AND m.kickoff_utc>=? AND m.kickoff_utc<?
               GROUP BY s.match_id, s.market_name, s.outcome""", (since, too_old))
    except sqlite3.OperationalError:
        return out
    for r in cur:
        key = SS.MARKETS.get((r["market_name"], r["outcome"]))
        if not key or key.startswith(SKIP_PREFIX) or not r["price"] or not _day_club(r["league_name"], r["kickoff_utc"]):
            continue
        try:
            res = SS._settle_result(key, r, too_old)
        except (KeyError, TypeError, IndexError):
            res = None
        if res in ("won", "lost"):
            out.append((key, r["kickoff_utc"], float(r["price"]), res == "won"))
    return out


def _agg(rows: List[Tuple[str, float, bool]]) -> Dict[str, Any]:
    n = len(rows)
    if not n:
        return {"n": 0, "roi": None, "low": None}
    h = sum(1 for _, _, w in rows if w)
    ret = sum(p for _, p, w in rows if w)
    avg_price = sum(p for _, p, _ in rows) / n
    return {"n": n, "hits": h, "roi": ret / n - 1, "low": _wilson_low(h, n) * avg_price - 1}


def scan(conn: sqlite3.Connection, now: Optional[datetime] = None, rows=None) -> List[Dict[str, Any]]:
    """Statisticile fiecărei chei × fereastră de cote (toată perioada, cele două jumătăți)."""
    from betpredict.builder.super_tickets import REC

    now = now or datetime.now(timezone.utc)
    rows = rows if rows is not None else settled_rows(conn, now)
    rec_keys = {v[1] for v in REC.values() if v[0] == "ss"}
    by: Dict[Tuple[str, float, float], List[Tuple[str, float, bool]]] = {}
    for key, ko, price, won in rows:
        if key in rec_keys:
            continue
        for lo, hi in BANDS:
            if lo <= price < hi:
                by.setdefault((key, lo, hi), []).append((ko, price, won))
    out = []
    for (key, lo, hi), xs in by.items():
        xs.sort()
        mid = len(xs) // 2
        a, h1, h2 = _agg(xs), _agg(xs[:mid]), _agg(xs[mid:])
        out.append({"key": key, "lo": lo, "hi": hi, **a, "roi_h1": h1["roi"], "roi_h2": h2["roi"]})
    return out


def _is_candidate(s: Dict[str, Any]) -> bool:
    return (s["n"] >= MIN_N and (s["roi"] or -1) >= MIN_ROI and (s["roi_h1"] or -1) > 0 and (s["roi_h2"] or -1) > 0
            and (s["low"] or -1) >= MIN_LOW)


def update(conn: sqlite3.Connection, now: Optional[datetime] = None, rows=None) -> Dict[str, Any]:
    """Scanarea zilnică: candidați noi în probă, promovări în active, scoateri. Întoarce ce s-a schimbat."""
    now = now or datetime.now(timezone.utc)
    _ensure(conn)
    rows = rows if rows is not None else settled_rows(conn, now)
    stats = {(s["key"], s["lo"]): s for s in scan(conn, now, rows)}
    c2 = conn.cursor()
    c2.row_factory = sqlite3.Row
    state = {(r["key"], r["band_lo"]): dict(r) for r in c2.execute("SELECT * FROM rec_discovery")}
    stamp = canon_utc(now.isoformat())
    changes: Dict[str, List[str]] = {"proba": [], "activ": [], "scos": []}
    with conn:
        for k, s in stats.items():
            st = state.get(k)
            if st is None:
                if _is_candidate(s):
                    conn.execute("INSERT INTO rec_discovery (key, band_lo, band_hi, status, since, n, roi, low, fwd_n, fwd_roi, updated_at) "
                                 "VALUES (?,?,?,?,?,?,?,?,0,NULL,?)", (s["key"], s["lo"], s["hi"], "proba", stamp, s["n"], s["roi"], s["low"], stamp))
                    changes["proba"].append(f"{s['key']}@{s['lo']:.2f}")
                continue
            if st["status"] == "scos":
                continue
            fwd = _agg([(ko, p, w) for key, ko, p, w in rows if key == st["key"] and st["band_lo"] <= p < st["band_hi"] and ko >= st["since"]])
            status = st["status"]
            if fwd["n"] >= FWD_N and (fwd["roi"] or 0) < DROP_ROI or s["n"] >= MIN_N and (s["roi"] or 0) < MIN_LOW:
                status = "scos"
            elif status == "proba" and fwd["n"] >= FWD_N and (fwd["roi"] or -1) >= 0 and (s["roi"] or -1) >= 0:
                status = "activ"
            if status != st["status"]:
                changes[status].append(f"{st['key']}@{st['band_lo']:.2f}")
            conn.execute("UPDATE rec_discovery SET status=?, n=?, roi=?, low=?, fwd_n=?, fwd_roi=?, updated_at=? WHERE key=? AND band_lo=?",
                         (status, s["n"], s["roi"], s["low"], fwd["n"], fwd["roi"], stamp, st["key"], st["band_lo"]))
    return changes


def update_daily(conn: sqlite3.Connection, now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """O singură scanare pe zi (ora României)."""
    from betpredict.store import repo
    from betpredict.timeutil import ro_today

    now = now or datetime.now(timezone.utc)
    flag = f"discovery.day.{ro_today(now).isoformat()}"
    if repo.get_state(conn, flag):
        return None
    out = update(conn, now)
    repo.set_state(conn, flag, canon_utc(now.isoformat()))
    return out


def active_specs(conn: sqlite3.Connection) -> Dict[Tuple[str, str], tuple]:
    """Piețele active, în forma ``REC``: (piață Superbet, ieșire) → ("ss", cheie, cotă min, cotă max, ROI asumat 0)."""
    from betpredict.experimental import supersocial as SS

    try:
        act = conn.execute("SELECT key, band_lo, band_hi FROM rec_discovery WHERE status='activ'").fetchall()
    except sqlite3.OperationalError:
        return {}
    out: Dict[Tuple[str, str], tuple] = {}
    for key, lo, hi in act:
        for mo, k in SS.MARKETS.items():
            if k == key and mo not in out:
                out[mo] = ("ss", key, float(lo), float(hi), 0.0)
    return out


def doc(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Pentru UI: piețele găsite (probă / active / scoase), cu cifrele lor."""
    from betpredict.experimental import supersocial as SS

    try:
        c2 = conn.cursor()
        c2.row_factory = sqlite3.Row
        rows = c2.execute("SELECT * FROM rec_discovery ORDER BY CASE status WHEN 'activ' THEN 0 WHEN 'proba' THEN 1 ELSE 2 END, roi DESC").fetchall()
    except sqlite3.OperationalError:
        return []
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["label"] = SS.label(d["key"])
        except Exception:  # noqa: BLE001
            d["label"] = d["key"]
        out.append(d)
    return out
