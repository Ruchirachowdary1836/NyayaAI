from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    """Process-local sliding-window limiter.

    Suitable for a single API instance. Multi-instance deployments need a shared
    store (for example Redis) so limits apply across processes.
    """

    def __init__(self, window_seconds: float = 60.0) -> None:
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int) -> bool:
        if limit <= 0:
            return True
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            while events and events[0] <= now - self.window_seconds:
                events.popleft()
            if len(events) >= limit:
                return False
            events.append(now)
            if len(self._events) > 50_000:
                self._prune(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._events.clear()

    def _prune(self, now: float) -> None:
        stale = [
            key
            for key, events in self._events.items()
            if not events or events[-1] <= now - self.window_seconds
        ]
        for key in stale:
            del self._events[key]


global_limiter = SlidingWindowLimiter()
auth_limiter = SlidingWindowLimiter()
qa_limiter = SlidingWindowLimiter()
upload_limiter = SlidingWindowLimiter()


def reset_all_limiters() -> None:
    for limiter in (global_limiter, auth_limiter, qa_limiter, upload_limiter):
        limiter.reset()
