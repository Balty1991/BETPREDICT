"""Export Parquet (istoric/arhivă). ``pyarrow`` este opțional (requirements-v3.txt)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, Iterable, Optional

from betpredict.store.db import TABLES

DEFAULT_EXPORT = ("match", "odds_snapshot", "provider_prediction", "prediction", "ticket", "ticket_leg")


def export_parquet(conn: sqlite3.Connection, out_dir: Path, tables: Optional[Iterable[str]] = None) -> Dict[str, int]:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - depinde de mediu
        raise RuntimeError("pyarrow lipsește: pip install -r requirements-v3.txt") from exc
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result: Dict[str, int] = {}
    for table in tables or DEFAULT_EXPORT:
        if table not in TABLES:
            raise ValueError(f"tabel necunoscut: {table}")
        cur = conn.execute(f"SELECT * FROM {table}")
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        data = {c: [r[i] for r in rows] for i, c in enumerate(cols)}
        pq.write_table(pa.table(data), out_dir / f"{table}.parquet", compression="zstd")
        result[table] = len(rows)
    return result
