"""Token bucket simplu pentru limita BSD de 25 cereri/s per IP."""

from __future__ import annotations

import threading
import time
from typing import Callable


class TokenBucket:
    def __init__(
        self,
        rate_per_sec: float = 25.0,
        burst: int = 25,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if rate_per_sec <= 0:
            raise ValueError("rate_per_sec trebuie să fie > 0")
        self.rate = float(rate_per_sec)
        self.capacity = max(1, int(burst))
        self._tokens = float(self.capacity)
        self._clock = clock
        self._sleep = sleep
        self._last = clock()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._last)
        self._last = now
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)

    def acquire(self) -> float:
        """Blochează până există un token. Întoarce timpul total așteptat (s)."""
        waited = 0.0
        with self._lock:
            while True:
                self._refill()
                if self._tokens >= 1.0 - 1e-9:
                    self._tokens = max(0.0, self._tokens - 1.0)
                    return waited
                need = (1.0 - self._tokens) / self.rate
                self._sleep(need)
                waited += need
