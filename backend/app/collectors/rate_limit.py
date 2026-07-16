"""Thread-safe request pacing shared by collector instances in one worker."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Protocol


class RateLimiter(Protocol):
    def acquire(self) -> None: ...


class RequestRateLimiter:
    """Reserve evenly-spaced request slots for a configured requests/minute cap."""

    def __init__(
        self,
        requests_per_minute: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if type(requests_per_minute) is not int or requests_per_minute <= 0:
            raise ValueError("requests_per_minute must be a positive integer")
        self.requests_per_minute = requests_per_minute
        self._interval = 60.0 / requests_per_minute
        self._clock = clock
        self._sleeper = sleeper
        self._next_allowed = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = self._clock()
            scheduled = max(now, self._next_allowed)
            self._next_allowed = scheduled + self._interval
            delay = scheduled - now
        if delay > 0:
            self._sleeper(delay)


class RateLimiterPool:
    """Share a limiter per configured collector within the current process."""

    _limiters: dict[str, RequestRateLimiter] = {}
    _lock = threading.Lock()

    @classmethod
    def get(cls, scope: str, requests_per_minute: int) -> RequestRateLimiter:
        with cls._lock:
            limiter = cls._limiters.get(scope)
            if limiter is None or limiter.requests_per_minute != requests_per_minute:
                limiter = RequestRateLimiter(requests_per_minute)
                cls._limiters[scope] = limiter
            return limiter

    @classmethod
    def clear(cls) -> None:
        """Reset process-local limiter state (primarily for isolated tests)."""
        with cls._lock:
            cls._limiters.clear()
