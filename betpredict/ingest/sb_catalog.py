"""Catalogul ofertei Superbet: toate piețele și selecțiile văzute, nu doar cele păstrate în ``sb_offer``.

Se completează din detaliile de meci deja citite (fără apeluri în plus). Pe fiecare piață × selecție ținem câte meciuri
au avut-o, cota medie/minimă/maximă și când a fost văzută ultima dată. Publicat în ``api/supersocial/markets.json``,
ca să vedem ce se poate juca și ce merită urmărit sau testat în laborator."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from betpredict.timeutil import canon_utc

SCHEMA = """CREATE TABLE IF NOT EXISTS sb_catalog (
  market_name TEXT NOT NULL, outcome TEXT NOT NULL, market_id INTEGER, n INTEGER NOT NULL DEFAULT 0,
  price_sum REAL NOT NULL DEFAULT 0, price_min REAL, price_max REAL, last_mid INTEGER, last_seen TEXT,
  PRIMARY KEY (market_name, outcome))"""


def ensure(conn: sqlite3.Connection) -> None:
    conn.execute(SCHEMA)


def record(conn: sqlite3.Connection, mid: int, ev: Dict[str, Any], stamp: str) -> int:
    """O dată pe meci și selecție (aceeași selecție văzută din nou pe același meci nu se mai numără)."""
    ensure(conn)
    n = 0
    seen = set()
    for o in ev.get("odds") or []:
        if (o.get("status") or "active") != "active":
            continue
        name, out = str(o.get("marketName") or "").strip(), str(o.get("name") or "").strip()
        try:
            price = float(o.get("price"))
        except (TypeError, ValueError):
            continue
        if not name or not out or price <= 1.0 or (name, out) in seen:
            continue
        seen.add((name, out))
        conn.execute(
            """INSERT INTO sb_catalog(market_name, outcome, market_id, n, price_sum, price_min, price_max, last_mid, last_seen)
               VALUES (?,?,?,1,?,?,?,?,?)
               ON CONFLICT(market_name, outcome) DO UPDATE SET
                 n = n + (COALESCE(last_mid, -1) != excluded.last_mid),
                 price_sum = price_sum + CASE WHEN COALESCE(last_mid, -1) != excluded.last_mid THEN excluded.price_sum ELSE 0 END,
                 price_min = MIN(price_min, excluded.price_min), price_max = MAX(price_max, excluded.price_max),
                 market_id = COALESCE(excluded.market_id, market_id), last_mid = excluded.last_mid, last_seen = excluded.last_seen""",
            (name, out, o.get("marketId"), price, price, price, mid, stamp))
        n += 1
    return n


def doc(conn: sqlite3.Connection, now: Optional[datetime] = None, days: int = 30) -> Dict[str, Any]:
    """Piețele văzute în ultimele ``days`` zile, grupate pe nume, cu selecțiile lor; marcate cele urmărite de robot."""
    from betpredict.experimental.supersocial import MARKETS

    ensure(conn)
    now = now or datetime.now(timezone.utc)
    since = canon_utc((now - timedelta(days=days)).isoformat())
    tracked = {k for k in MARKETS}
    groups: Dict[str, Dict[str, Any]] = {}
    for r in conn.execute("SELECT * FROM sb_catalog WHERE last_seen >= ? ORDER BY n DESC", (since,)):
        g = groups.setdefault(r["market_name"], {"market": r["market_name"], "market_id": r["market_id"], "matches": 0, "outcomes": []})
        g["matches"] = max(g["matches"], r["n"])
        g["outcomes"].append({"outcome": r["outcome"], "n": r["n"], "avg": round(r["price_sum"] / r["n"], 2) if r["n"] else None,
                              "min": r["price_min"], "max": r["price_max"],
                              "tracked": (r["market_name"], r["outcome"]) in tracked})
    markets: List[Dict[str, Any]] = sorted(groups.values(), key=lambda g: -g["matches"])
    for g in markets:
        g["outcomes"].sort(key=lambda o: -o["n"])
        g["tracked"] = any(o["tracked"] for o in g["outcomes"])
    return {"generated_at": canon_utc(now.isoformat()), "days": days, "count": len(markets),
            "outcomes": sum(len(g["outcomes"]) for g in markets), "markets": markets}
