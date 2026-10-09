"""Cache pe disc pentru răspunsurile BSD (o lovitură de cache nu consumă cotă)."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Optional


class DiskCache:
    def __init__(self, root: Optional[Path], clock: Callable[[], float] = time.time) -> None:
        self.root = Path(root) if root else None
        self._clock = clock

    @staticmethod
    def key(path: str, params: Optional[Mapping[str, Any]]) -> str:
        items = sorted((str(k), str(v)) for k, v in (params or {}).items())
        raw = json.dumps([path, items], separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _file(self, key: str) -> Optional[Path]:
        if not self.root:
            return None
        return self.root / key[:2] / f"{key}.json"

    def get(self, key: str, ttl: float) -> Any:
        f = self._file(key)
        if not f or ttl <= 0 or not f.exists():
            return None
        try:
            payload = json.loads(f.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None
        if self._clock() - float(payload.get("stored_at", 0)) > ttl:
            return None
        return payload.get("data")

    def set(self, key: str, data: Any) -> None:
        f = self._file(key)
        if not f:
            return
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps({"stored_at": self._clock(), "data": data}, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, f)
