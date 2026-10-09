"""Configurare centrală, citită exclusiv din variabile de mediu.

Cheia API se citește DOAR din ``BSD_API_KEY`` (secret GitHub Actions). Nu există
niciun alt canal (fișier, argument CLI, frontend) prin care cheia să intre în aplicație.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional

ROOT = Path(__file__).resolve().parent.parent

BSD_BASE_URL = "https://sports.bzzoiro.com/api/v2"
BSD_IMG_BASE = "https://sports.bzzoiro.com/img"

# Planul BSD Football Free: 7.500 cereri/zi, resetare la 00:00 UTC.
FREE_DAILY_QUOTA = 7500
# Limita per IP pe endpointurile cache-uite: 25 req/s (burst 110). Rămânem la 25/s.
DEFAULT_RATE_PER_SEC = 25.0
DEFAULT_BURST = 25

# Cota minimă pe selecție (regula globală din plan, configurabilă).
MIN_ODDS = 1.15

PAID_PLANS = {"unlimited", "paid", "football_unlimited"}


def _env_int(env: Mapping[str, str], key: str, default: Optional[int]) -> Optional[int]:
    raw = (env.get(key) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(env: Mapping[str, str], key: str, default: float) -> float:
    raw = (env.get(key) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass
class Settings:
    plan: str = "free"
    daily_quota: int = FREE_DAILY_QUOTA
    # Rezerva care NU se atinge de cererile cu prioritate normală (pipeline-ul vechi
    # rulează în paralel și are nevoie de cotă până la migrarea completă).
    reserve: int = 500
    # Plafon per rulare (None = fără plafon, doar bugetul zilnic).
    max_requests_per_run: Optional[int] = None
    rate_per_sec: float = DEFAULT_RATE_PER_SEC
    burst: int = DEFAULT_BURST
    timeout: float = 30.0
    max_retries: int = 4
    state_dir: Path = field(default_factory=lambda: ROOT / ".betpredict")
    db_path: Path = field(default_factory=lambda: ROOT / ".betpredict" / "data.db")
    base_url: str = BSD_BASE_URL

    @property
    def is_paid(self) -> bool:
        return self.plan in PAID_PLANS

    @property
    def cache_dir(self) -> Path:
        return self.state_dir / "cache"

    @property
    def quota_file(self) -> Path:
        return self.state_dir / "bsd_quota.json"

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "Settings":
        env = os.environ if env is None else env
        state_dir = Path(env.get("BETPREDICT_STATE_DIR") or (ROOT / ".betpredict"))
        db_path = Path(env.get("BETPREDICT_DB") or (state_dir / "data.db"))
        plan = (env.get("BSD_PLAN") or "free").strip().lower()
        default_quota = FREE_DAILY_QUOTA
        return cls(
            plan=plan,
            daily_quota=_env_int(env, "BSD_DAILY_QUOTA", default_quota) or default_quota,
            reserve=_env_int(env, "BETPREDICT_QUOTA_RESERVE", 500) or 0,
            max_requests_per_run=_env_int(env, "BETPREDICT_MAX_REQUESTS", None),
            rate_per_sec=_env_float(env, "BETPREDICT_RATE_PER_SEC", DEFAULT_RATE_PER_SEC),
            burst=_env_int(env, "BETPREDICT_BURST", DEFAULT_BURST) or DEFAULT_BURST,
            state_dir=state_dir,
            db_path=db_path,
            base_url=(env.get("BSD_BASE_URL") or BSD_BASE_URL).rstrip("/"),
        )


def img_url(kind: str, ident: object) -> Optional[str]:
    """URL public (fără autentificare) din Image API BSD."""
    if ident in (None, "", "null"):
        return None
    return f"{BSD_IMG_BASE}/{kind}/{ident}/"
