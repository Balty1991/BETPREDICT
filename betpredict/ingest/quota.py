"""Contorul de cereri BSD, persistent pe disc, aliniat la ziua UTC a furnizorului.

Planul Free are 7.500 cereri/zi, resetare la 00:00 UTC. Combinăm două surse:
  * contorul local (câte cereri am trimis azi, din toate rulările acestui pachet);
  * antetul ``RateLimit: "football";r=<rămase>;t=<secunde>`` trimis de BSD, care
    include și consumul altor scripturi (pipeline-ul vechi) — deci e autoritar.
Pe planurile plătite antetul lipsește: lipsa lui înseamnă „nelimitat”, nu zero.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

PRIORITY_HIGH = "high"      # decontare / date critice: pot intra în rezervă
PRIORITY_NORMAL = "normal"  # colectare uzuală: se opresc înainte de rezervă
PRIORITY_LOW = "low"        # backfill istoric: se opresc la 2× rezerva


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_ratelimit(header: str) -> Dict[str, int]:
    """Parsează ``"football";r=7213;t=52800`` → {"r": 7213, "t": 52800}.

    Format IETF structured field; aici avem doar o listă cu un item și parametri
    întregi, deci un parser minimal e suficient și nu cere dependențe noi.
    """
    out: Dict[str, int] = {}
    if not header:
        return out
    first_item = header.split(",")[0]
    for part in first_item.split(";")[1:]:
        key, _, value = part.strip().partition("=")
        try:
            out[key.strip()] = int(value.strip())
        except ValueError:
            continue
    return out


@dataclass
class QuotaState:
    day: str = ""
    local_count: int = 0
    server_remaining: Optional[int] = None
    server_quota: Optional[int] = None
    server_reset_at: Optional[str] = None
    exhausted: bool = False
    by_endpoint: Dict[str, int] = field(default_factory=dict)
    not_entitled: Dict[str, str] = field(default_factory=dict)
    updated_at: Optional[str] = None


class QuotaTracker:
    def __init__(
        self,
        path: Optional[Path],
        daily_quota: int = 7500,
        reserve: int = 500,
        max_per_run: Optional[int] = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.path = Path(path) if path else None
        self.daily_quota = daily_quota
        self.reserve = max(0, reserve)
        self.max_per_run = max_per_run
        self.run_count = 0
        self._clock = clock
        self.state = self._load()
        self._roll_day()

    # ── persistență ──────────────────────────────────────────────────────
    def _load(self) -> QuotaState:
        if self.path and self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                known = {k: raw[k] for k in QuotaState.__dataclass_fields__ if k in raw}
                return QuotaState(**known)
            except (ValueError, TypeError, OSError):
                pass
        return QuotaState()

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        payload = asdict(self.state)
        payload["daily_quota"] = self.daily_quota
        payload["reserve"] = self.reserve
        payload["effective_remaining"] = self.effective_remaining()
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def _today(self) -> str:
        return self._clock().strftime("%Y-%m-%d")

    def _roll_day(self) -> None:
        today = self._today()
        if self.state.day != today:
            self.state = QuotaState(day=today)

    # ── buget ────────────────────────────────────────────────────────────
    def effective_remaining(self) -> Optional[int]:
        """Cereri rămase azi după cea mai prudentă estimare (None = nelimitat)."""
        if self.state.exhausted:
            return 0
        local_left = self.daily_quota - self.state.local_count if self.daily_quota else None
        server_left = self.state.server_remaining
        candidates = [v for v in (local_left, server_left) if v is not None]
        if not candidates:
            return None
        return max(0, min(candidates))

    def check(self, n: int = 1, priority: str = PRIORITY_NORMAL) -> Optional[str]:
        """Întoarce motivul refuzului sau None dacă cererea e permisă."""
        self._roll_day()
        if self.state.exhausted:
            return "cota zilnică BSD epuizată (taster_exhausted) până la 00:00 UTC"
        if self.max_per_run is not None and self.run_count + n > self.max_per_run:
            return f"plafonul per rulare atins ({self.max_per_run} cereri)"
        remaining = self.effective_remaining()
        if remaining is None:
            return None
        floor = {PRIORITY_HIGH: 0, PRIORITY_NORMAL: self.reserve, PRIORITY_LOW: 2 * self.reserve}.get(
            priority, self.reserve
        )
        if remaining - n < floor:
            return f"buget zilnic: rămân {remaining} cereri, rezerva pentru prioritatea '{priority}' este {floor}"
        return None

    def record_request(self, endpoint_key: str) -> None:
        self._roll_day()
        self.state.local_count += 1
        self.run_count += 1
        self.state.by_endpoint[endpoint_key] = self.state.by_endpoint.get(endpoint_key, 0) + 1
        self.state.updated_at = self._clock().isoformat()

    def record_headers(self, headers: Any) -> None:
        get = getattr(headers, "get", None)
        if get is None:
            return
        rate = parse_ratelimit(get("RateLimit") or "")
        policy = parse_ratelimit(get("RateLimit-Policy") or "")
        if "r" in rate:
            self.state.server_remaining = rate["r"]
        if "t" in rate:
            self.state.server_reset_at = (self._clock() + timedelta(seconds=rate["t"])).isoformat()
        if "q" in policy:
            self.state.server_quota = policy["q"]

    def mark_exhausted(self, retry_after: Optional[int] = None) -> None:
        self.state.exhausted = True
        self.state.server_remaining = 0
        if retry_after is not None:
            self.state.server_reset_at = (self._clock() + timedelta(seconds=retry_after)).isoformat()

    def mark_not_entitled(self, endpoint_key: str, code: str) -> None:
        self.state.not_entitled[endpoint_key] = code or "not_entitled"

    def summary(self) -> Dict[str, Any]:
        return {
            "day_utc": self.state.day,
            "local_count": self.state.local_count,
            "run_count": self.run_count,
            "server_remaining": self.state.server_remaining,
            "effective_remaining": self.effective_remaining(),
            "daily_quota": self.daily_quota,
            "reserve": self.reserve,
            "exhausted": self.state.exhausted,
            "not_entitled": dict(self.state.not_entitled),
            "top_endpoints": dict(sorted(self.state.by_endpoint.items(), key=lambda kv: -kv[1])[:15]),
        }
