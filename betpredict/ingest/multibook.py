"""Cote multi-casă (BSD Football Unlimited): /events/{id}/odds/comparison/ → consens propriu + Pinnacle + cea mai bună cotă.

Pe Unlimited, /odds/ fără filtru întoarce câte un rând pe casă (nu mai există rândul „consensus”), așa că
consensul îl calculăm noi: MEDIANA cotelor caselor (≥ 2 case) pe fiecare rezultat — aceeași semantică ca
vechiul consens BSD (cotă cu marjă; Robotul scoate marja cu Shin/proporțional). Se scriu în odds_snapshot:
  * ``bsd_consensus`` — mediana (deschiderea = primul consens văzut, din odds_open);
  * ``bsd:pinnacle``  — cota Pinnacle (benchmark CLV; deschiderea reală vine din feedul /odds/?bookmaker_slug=pinnacle);
  * ``bsd_best``      — cea mai bună cotă dintre case (comparație cu Superbet)."""

from __future__ import annotations

import sqlite3
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from betpredict.ingest.normalize import LEGACY_MARKET_MAP, _norm_outcome
from betpredict.store import repo
from betpredict.timeutil import canon_utc

MIN_BOOKS = 2


def rows_from_comparison(js: Dict[str, Any], observed: str, opening: Dict[tuple, float]) -> List[Dict[str, Any]]:
    mid = js.get("event_id")
    out: List[Dict[str, Any]] = []
    if not mid:
        return out
    for mk, outs in (js.get("markets") or {}).items():
        if mk not in LEGACY_MARKET_MAP or not isinstance(outs, dict):
            continue
        market, line = LEGACY_MARKET_MAP[mk]
        for o in outs.values():
            books = {k: (v or {}).get("decimal_odds") for k, v in (o.get("bookmakers") or {}).items()}
            prices = [float(x) for x in books.values() if isinstance(x, (int, float)) and x > 1.0]
            if not prices:
                continue
            oc = _norm_outcome(o.get("outcome"))
            base = {"match_id": int(mid), "market": market, "line": line, "period": "FT", "outcome": oc,
                    "previous_decimal": None, "movement": None, "observed_at": observed}
            if len(prices) >= MIN_BOOKS:
                med = round(statistics.median(prices), 3)
                op = opening.get((int(mid), market, float(line), oc), med)
                out.append({**base, "decimal": med, "opening_decimal": op, "source": "bsd_consensus"})
            pin = books.get("pinnacle")
            if isinstance(pin, (int, float)) and pin > 1.0:
                out.append({**base, "decimal": float(pin), "opening_decimal": None, "source": "bsd:pinnacle"})
            out.append({**base, "decimal": max(prices), "opening_decimal": None, "source": "bsd_best"})
            bk = max(((k, float(v)) for k, v in books.items() if isinstance(v, (int, float)) and v > 1.0), key=lambda kv: kv[1])[0]
            out.append({**base, "decimal": max(prices), "opening_decimal": None, "source": f"bsd_bestbook:{bk}"})
    return out


def ingest_comparison(conn: sqlite3.Connection, client, hours_ahead: int = 72, max_events: int = 400,
                      now: Optional[datetime] = None) -> Dict[str, Any]:
    from betpredict.ingest.opening import SCHEMA as OPEN_SCHEMA

    now = now or datetime.now(timezone.utc)
    lo, hi = canon_utc(now.isoformat()), canon_utc((now + timedelta(hours=hours_ahead)).isoformat())
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM match WHERE kickoff_utc > ? AND kickoff_utc <= ? AND (status IS NULL OR status IN ('notstarted','upcoming','scheduled')) "
        "ORDER BY kickoff_utc LIMIT ?", (lo, hi, max_events))]
    conn.execute(OPEN_SCHEMA)
    stats = {"events": 0, "rows": 0, "with_pinnacle": 0, "books_median": None}
    nbooks: List[int] = []
    observed = repo.now_iso()
    for mid in ids:
        try:
            js = client.get(f"events/{mid}/odds/comparison/", cache_ttl=120)
        except Exception:  # noqa: BLE001 — un meci fără grilă nu oprește rularea
            continue
        if not isinstance(js, dict):
            continue
        opening = {(r[0], r[1], float(r[2] or 0), r[3]): r[4] for r in conn.execute(
            "SELECT match_id, market, line, outcome, decimal FROM odds_open WHERE match_id=? AND source='bsd_consensus'", (mid,))}
        last = {(r[0], r[1], r[2], r[3]): r[4] for r in conn.execute(
            """SELECT o.source, o.market, o.line, o.outcome, o.decimal FROM odds_snapshot o JOIN (
                 SELECT source, market, line, outcome, MAX(observed_at) mx FROM odds_snapshot
                 WHERE match_id=? AND source IN ('bsd_consensus','bsd:pinnacle','bsd_best') GROUP BY 1,2,3,4) l
               ON o.source=l.source AND o.market=l.market AND o.line=l.line AND o.outcome=l.outcome AND o.observed_at=l.mx
               WHERE o.match_id=?""", (mid, mid))}
        # doar schimbările (DB-ul rămâne mic): ultima cotă rămâne valabilă până la o nouă mișcare
        rows = [r for r in rows_from_comparison(js, observed, opening)
                if last.get((r["source"], r["market"], float(r["line"]), r["outcome"])) != r["decimal"]]
        if not rows:
            continue
        stats["events"] += 1
        stats["with_pinnacle"] += any(r["source"] == "bsd:pinnacle" for r in rows)
        nbooks.append(int(js.get("bookmakers_count") or 0))
        with conn:
            stats["rows"] += repo.insert_odds(conn, rows)
    if nbooks:
        stats["books_median"] = sorted(nbooks)[len(nbooks) // 2]
    return stats


def collect_lineups(conn: sqlite3.Connection, client, hours_ahead: float = 2.0, now: Optional[datetime] = None) -> Dict[str, int]:
    """Echipele de start confirmate (+ indisponibili) pentru meciurile din următoarele ~2 h → match_context.lineups."""
    import json

    now = now or datetime.now(timezone.utc)
    lo, hi = canon_utc(now.isoformat()), canon_utc((now + timedelta(hours=hours_ahead)).isoformat())
    st = {"checked": 0, "confirmed": 0}
    for (mid,) in conn.execute("SELECT id FROM match WHERE kickoff_utc > ? AND kickoff_utc <= ?", (lo, hi)).fetchall():
        try:
            js = client.get(f"events/{mid}/lineups/", cache_ttl=600)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(js, dict):
            continue
        st["checked"] += 1
        lu = js.get("lineups") or {}
        info = {"status": js.get("lineup_status"),
                "formation": {s: (lu.get(s) or {}).get("formation") for s in ("home", "away")},
                "unavailable": js.get("unavailable_players") if isinstance(js.get("unavailable_players"), (list, dict)) else None}
        if info["status"] == "confirmed" and isinstance(info["unavailable"], dict):
            for side in ("home", "away"):
                for pl in info["unavailable"].get(side) or []:
                    if isinstance(pl, dict) and pl.get("id") and "imp" not in pl:
                        pl["imp"] = player_importance(client, pl["id"], now)
        st["confirmed"] += info["status"] == "confirmed"
        row = conn.execute("SELECT context_json FROM match_context WHERE match_id=?", (mid,)).fetchone()
        ctx = json.loads(row[0]) if row else {}
        ctx["lineups"] = info
        with conn:
            conn.execute("INSERT INTO match_context(match_id, context_json, updated_at) VALUES (?,?,?) ON CONFLICT(match_id) DO UPDATE SET "
                         "context_json=excluded.context_json, updated_at=excluded.updated_at", (mid, json.dumps(ctx, ensure_ascii=False), repo.now_iso()))
    return st


def player_importance(client, pid: int, now: datetime) -> Optional[float]:
    """Cât contează un jucător (0–1), din ultimele lui 10 meciuri jucate (BSD players/{id}/stats): partea de minute din
    10×90 și golurile + pasele decisive (4 în 10 meciuri = 1). Un titular de bază are ≥ 0.6. Accidentații de lungă durată
    n-au meciuri recente, deci ies mici: lipsa lor e deja în cote."""
    try:
        js = client.get(f"players/{int(pid)}/stats/?date_from={(now - timedelta(days=150)).date().isoformat()}&limit=50", cache_ttl=86400)
    except Exception:  # noqa: BLE001
        return None
    rows = js.get("results") if isinstance(js, dict) else js
    if not isinstance(rows, list):
        return None
    def _n(r, *ks):
        for k in ks:
            v = r.get(k)
            if isinstance(v, (int, float)):
                return float(v)
        return 0.0
    rows = sorted((r for r in rows if isinstance(r, dict)), key=lambda r: str(r.get("date") or r.get("event_date") or ""), reverse=True)[:10]
    mins = sum(_n(r, "minutes", "minutes_played", "mins") for r in rows)
    ga = sum(_n(r, "goals") + _n(r, "assists", "goal_assist") for r in rows)
    share = mins / 900.0
    return round(min(1.0, max(share if share >= 0.6 else share * 0.5, ga / 4.0)), 2)
