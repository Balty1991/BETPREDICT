import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from betpredict.config import Settings  # noqa: E402
from betpredict.ingest.bsd_client import BSDClient  # noqa: E402
from betpredict.ingest.cache import DiskCache  # noqa: E402
from betpredict.ingest.quota import QuotaTracker  # noqa: E402
from betpredict.ingest.ratelimit import TokenBucket  # noqa: E402


class FakeResp:
    def __init__(self, status: int = 200, payload: Any = None, headers: Optional[Dict[str, str]] = None):
        self.status_code = status
        self._payload = {} if payload is None else payload
        self.headers = headers or {}

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    """Răspunsuri programate pe cale (``events/``, ``odds/`` ...), în ordine; ultimul se repetă."""

    def __init__(self, routes: Optional[Dict[str, List[Any]]] = None):
        self.routes = routes or {}
        self.calls: List[Dict[str, Any]] = []

    def get(self, url, params=None, headers=None, timeout=None):
        path = urlparse(url).path.replace("/api/v2/", "", 1)
        query = urlparse(url).query
        self.calls.append({"url": url, "path": path, "query": query, "params": params, "headers": dict(headers or {})})
        key = f"{path}?{query}" if query and f"{path}?{query}" in self.routes else path
        queue = self.routes.get(key)
        if not queue:
            return FakeResp(404, {"error": True, "status": 404, "detail": "Not found."})
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def make_client(tmp_path):
    def _make(routes=None, env=None, quota_kwargs=None, settings_kwargs=None):
        env = {"BSD_API_KEY": "secret-test-key-123", **(env or {})}
        settings = Settings.from_env({**env, "BETPREDICT_STATE_DIR": str(tmp_path / "state")})
        for k, v in (settings_kwargs or {}).items():
            setattr(settings, k, v)
        sleeps: List[float] = []
        session = FakeSession(routes)
        quota = QuotaTracker(tmp_path / "state" / "q.json",
                             daily_quota=0 if settings.is_paid else settings.daily_quota,
                             reserve=settings.reserve, max_per_run=settings.max_requests_per_run,
                             **(quota_kwargs or {}))
        limiter = TokenBucket(1000, 1000, sleep=lambda s: None)
        client = BSDClient(settings, env=env, session=session, quota=quota, limiter=limiter,
                           cache=DiskCache(tmp_path / "cache"), sleep=sleeps.append)
        client._sleeps = sleeps  # type: ignore[attr-defined]
        return client, session

    return _make
