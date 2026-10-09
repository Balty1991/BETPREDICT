"""Clientul BSD unic pentru BETPREDICT 3.0.

Garanții:
  * cheia se citește DOAR din variabila de mediu ``BSD_API_KEY`` și nu e niciodată
    logată sau scrisă pe disc;
  * rate-limit local 25 req/s (token bucket), sub limita per IP a BSD;
  * retry pe ``429 rate_limited`` (după ``Retry-After``), pe 5xx și pe erori de rețea
    (backoff exponențial); fără retry pe 400/401/402/403;
  * oprire imediată pe ``429 taster_exhausted`` (cota zilnică) → ``QuotaExhausted``;
  * buget zilnic 7.500 (Free) cu rezervă și plafon per rulare, contor persistent;
  * endpointurile care pe Free dau mereu 403 (``/odds/best/``,
    ``/events/{id}/odds/comparison/``, filtrul ``bookmaker_slug``) sunt blocate local,
    fără a consuma cotă, cât timp ``BSD_PLAN`` nu e un plan plătit;
  * cache pe disc opțional (TTL per apel).
"""

from __future__ import annotations

import logging
import random
import re
import time
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional
from urllib.parse import urlparse

import requests

from betpredict.config import Settings
from betpredict.ingest.cache import DiskCache
from betpredict.ingest.errors import (
    BSDAuthError,
    BSDBadRequest,
    BSDError,
    BudgetExceeded,
    EndpointNotEntitled,
    PaidEndpointBlocked,
    QuotaExhausted,
)
from betpredict.ingest.quota import PRIORITY_NORMAL, QuotaTracker
from betpredict.ingest.ratelimit import TokenBucket

log = logging.getLogger("betpredict.bsd")

# Endpointuri care cer Football Unlimited (403 bookmakers_not_entitled pe Free).
PAID_ONLY_PATTERNS = (
    re.compile(r"^odds/best/?$"),
    re.compile(r"^events/\d+/odds/comparison/?$"),
)
PAID_ONLY_PARAMS = ("bookmaker_slug", "bookmaker")

RETRY_STATUSES = {500, 502, 503, 504}


def normalize_path(path: str) -> str:
    """'/api/v2/events/12/odds/' sau '/events/12/odds/' → 'events/12/odds/'."""
    p = path.strip()
    if p.startswith("http://") or p.startswith("https://"):
        p = urlparse(p).path
    p = p.lstrip("/")
    if p.startswith("api/v2/"):
        p = p[len("api/v2/"):]
    if p and not p.endswith("/"):
        p += "/"
    return p


def endpoint_key(path: str) -> str:
    """Cheie de agregare fără ID-uri: 'events/123/odds/' → 'events/{id}/odds/'."""
    return re.sub(r"/\d+(?=/)", "/{id}", "/" + normalize_path(path)).lstrip("/")


def is_paid_only(path: str, params: Optional[Mapping[str, Any]] = None) -> bool:
    p = normalize_path(path)
    if any(rx.match(p) for rx in PAID_ONLY_PATTERNS):
        return True
    if p.startswith("odds/") and params and any(params.get(k) for k in PAID_ONLY_PARAMS):
        return True
    return False


def _json_or_empty(resp: Any) -> Dict[str, Any]:
    try:
        body = resp.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


def _retry_after(resp: Any, default: float) -> float:
    raw = (getattr(resp, "headers", {}) or {}).get("Retry-After")
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return default


class BSDClient:
    def __init__(
        self,
        settings: Optional[Settings] = None,
        env: Optional[Mapping[str, str]] = None,
        session: Any = None,
        quota: Optional[QuotaTracker] = None,
        limiter: Optional[TokenBucket] = None,
        cache: Optional[DiskCache] = None,
        sleep: Callable[[float], None] = time.sleep,
        persist_quota: bool = True,
    ) -> None:
        import os

        env = os.environ if env is None else env
        self.settings = settings or Settings.from_env(env)
        self._api_key = (env.get("BSD_API_KEY") or "").strip()
        self.session = session or requests.Session()
        self.quota = quota or QuotaTracker(
            self.settings.quota_file if persist_quota else None,
            daily_quota=0 if self.settings.is_paid else self.settings.daily_quota,
            reserve=self.settings.reserve,
            max_per_run=self.settings.max_requests_per_run,
        )
        self.limiter = limiter or TokenBucket(self.settings.rate_per_sec, self.settings.burst, sleep=sleep)
        self.cache = cache if cache is not None else DiskCache(self.settings.cache_dir)
        self._sleep = sleep
        self.base_url = self.settings.base_url.rstrip("/")
        self.stats: Dict[str, int] = {"requests": 0, "cache_hits": 0, "retries": 0, "blocked_paid": 0}

    # Cheia nu apare niciodată în repr/log.
    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"BSDClient(plan={self.settings.plan!r}, has_key={self.has_key})"

    @property
    def has_key(self) -> bool:
        return bool(self._api_key)

    def _headers(self) -> Dict[str, str]:
        h = {"Accept": "application/json", "User-Agent": "betpredict/3.0"}
        if self._api_key:
            h["Authorization"] = f"Token {self._api_key}"
        return h

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            base_host = urlparse(self.base_url).netloc
            if urlparse(path).netloc != base_host:
                raise BSDError(f"URL extern refuzat: {path}")
            return path
        return f"{self.base_url}/{normalize_path(path)}"

    # ── API public ───────────────────────────────────────────────────────
    def get(
        self,
        path: str,
        params: Optional[Mapping[str, Any]] = None,
        *,
        priority: str = PRIORITY_NORMAL,
        cache_ttl: float = 0,
        allow_404: bool = True,
    ) -> Any:
        clean = {k: v for k, v in (params or {}).items() if v not in (None, "", [])}
        key_path = normalize_path(path)
        ep = endpoint_key(path)

        if not self.settings.is_paid and is_paid_only(path, clean):
            self.stats["blocked_paid"] += 1
            raise PaidEndpointBlocked(
                f"{ep} necesită Football Unlimited; blocat local pe planul '{self.settings.plan}'",
                status=403,
                path=ep,
            )
        if ep in self.quota.state.not_entitled and not self.settings.is_paid:
            raise EndpointNotEntitled(f"{ep} a răspuns deja 403/402 azi", status=403, path=ep)

        ckey = DiskCache.key(key_path, clean)
        if cache_ttl > 0:
            hit = self.cache.get(ckey, cache_ttl)
            if hit is not None:
                self.stats["cache_hits"] += 1
                return hit

        data = self._request(path, clean, ep, priority=priority, allow_404=allow_404)
        if cache_ttl > 0 and data is not None:
            self.cache.set(ckey, data)
        return data

    def paginate(
        self,
        path: str,
        params: Optional[Mapping[str, Any]] = None,
        *,
        max_pages: int = 50,
        page_size: int = 200,
        priority: str = PRIORITY_NORMAL,
        cache_ttl: float = 0,
    ) -> Iterator[Dict[str, Any]]:
        """Parcurge wrapperul ``{count, next, results}`` (limit max 200)."""
        query: Optional[Dict[str, Any]] = dict(params or {})
        query.setdefault("limit", page_size)
        url: Optional[str] = path
        seen: set = set()
        pages = 0
        while url and pages < max_pages:
            marker = (url, tuple(sorted((query or {}).items())))
            if marker in seen:
                break
            seen.add(marker)
            payload = self.get(url, query, priority=priority, cache_ttl=cache_ttl)
            pages += 1
            if isinstance(payload, list):
                for row in payload:
                    if isinstance(row, dict):
                        yield row
                break
            if not isinstance(payload, dict):
                break
            for row in payload.get("results") or []:
                if isinstance(row, dict):
                    yield row
            nxt = payload.get("next")
            if not nxt:
                break
            url, query = nxt, None

    def get_all(self, path: str, params: Optional[Mapping[str, Any]] = None, **kw: Any) -> List[Dict[str, Any]]:
        return list(self.paginate(path, params, **kw))

    def save_quota(self) -> None:
        self.quota.save()

    # ── implementare ─────────────────────────────────────────────────────
    def _request(self, path: str, params: Dict[str, Any], ep: str, *, priority: str, allow_404: bool) -> Any:
        url = self._url(path)
        attempt = 0
        while True:
            reason = self.quota.check(1, priority)
            if reason:
                raise BudgetExceeded(reason, path=ep)
            self.limiter.acquire()
            self.quota.record_request(ep)
            self.stats["requests"] += 1
            try:
                resp = self.session.get(url, params=params or None, headers=self._headers(), timeout=self.settings.timeout)
            except (requests.ConnectionError, requests.Timeout) as exc:
                if attempt >= self.settings.max_retries:
                    raise BSDError(f"rețea: {type(exc).__name__} după {attempt + 1} încercări", path=ep) from None
                self._backoff(attempt)
                attempt += 1
                continue

            self.quota.record_headers(getattr(resp, "headers", {}) or {})
            status = int(getattr(resp, "status_code", 0) or 0)

            if 200 <= status < 300:
                try:
                    return resp.json()
                except ValueError:
                    raise BSDError("răspuns JSON invalid", status=status, path=ep) from None

            body = _json_or_empty(resp)
            code = str(body.get("code") or "")
            detail = str(body.get("detail") or "")[:300]

            if status == 404 and allow_404:
                return None
            if status == 429:
                if code == "taster_exhausted":
                    self.quota.mark_exhausted(int(_retry_after(resp, 0)) or None)
                    raise QuotaExhausted("cota zilnică BSD epuizată (reset la 00:00 UTC)", status=429, path=ep)
                if attempt >= self.settings.max_retries:
                    raise BSDError("429 rate_limited persistent", status=429, path=ep)
                self.stats["retries"] += 1
                self._sleep(_retry_after(resp, 1.0))
                attempt += 1
                continue
            if status in RETRY_STATUSES:
                if attempt >= self.settings.max_retries:
                    raise BSDError(f"HTTP {status} după {attempt + 1} încercări", status=status, path=ep)
                self.stats["retries"] += 1
                self._backoff(attempt, _retry_after(resp, 0))
                attempt += 1
                continue
            if status == 401:
                raise BSDAuthError("401: BSD_API_KEY lipsă sau invalid", status=status, path=ep)
            if status in (402, 403):
                self.quota.mark_not_entitled(ep, code or str(status))
                raise EndpointNotEntitled(f"{status} {code or ''} {detail}".strip(), status=status, path=ep)
            if status == 400:
                raise BSDBadRequest(f"400: {detail}", status=status, path=ep)
            raise BSDError(f"HTTP {status}: {detail}", status=status, path=ep)

    def _backoff(self, attempt: int, minimum: float = 0.0) -> None:
        delay = max(minimum, min(30.0, (2 ** attempt) * 0.5 + random.uniform(0, 0.25)))
        self._sleep(delay)
