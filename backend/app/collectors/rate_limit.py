"""PostgreSQL token-bucket limiting shared by every worker process."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Protocol

from sqlalchemy import text


class RateLimiter(Protocol):
    def acquire(self) -> None: ...


class RateLimiterUnavailableError(RuntimeError):
    """Raised when a distributed request token cannot be acquired."""


# A capacity of one preserves the original collector contract: requests are
# evenly paced instead of allowing a full minute's quota to burst at once.
# PostgreSQL serializes this upsert per scope, so separate worker processes and
# replicas compete for the same token.
_TRY_ACQUIRE_TOKEN = text(
    """
    INSERT INTO collector_rate_limits (
        scope,
        requests_per_minute,
        tokens,
        refilled_at,
        updated_at
    )
    VALUES (
        :scope,
        :requests_per_minute,
        0.0,
        clock_timestamp(),
        clock_timestamp()
    )
    ON CONFLICT (scope) DO UPDATE
    SET
        requests_per_minute = EXCLUDED.requests_per_minute,
        tokens = LEAST(
            1.0,
            collector_rate_limits.tokens
                + GREATEST(
                    0.0,
                    EXTRACT(
                        EPOCH FROM (
                            clock_timestamp()
                            - collector_rate_limits.refilled_at
                        )
                    )
                )
                * CAST(
                    LEAST(
                        collector_rate_limits.requests_per_minute,
                        EXCLUDED.requests_per_minute
                    ) AS double precision
                ) / 60.0
        ) - 1.0,
        refilled_at = clock_timestamp(),
        updated_at = clock_timestamp()
    WHERE
        LEAST(
            1.0,
            collector_rate_limits.tokens
                + GREATEST(
                    0.0,
                    EXTRACT(
                        EPOCH FROM (
                            clock_timestamp()
                            - collector_rate_limits.refilled_at
                        )
                    )
                )
                * CAST(
                    LEAST(
                        collector_rate_limits.requests_per_minute,
                        EXCLUDED.requests_per_minute
                    ) AS double precision
                ) / 60.0
        ) >= 1.0
    RETURNING TRUE AS granted
    """
)


_TOKEN_RETRY_DELAY = text(
    """
    SELECT GREATEST(
        0.0,
        (
            1.0
            - LEAST(
                1.0,
                tokens
                    + GREATEST(
                        0.0,
                        EXTRACT(EPOCH FROM (clock_timestamp() - refilled_at))
                    )
                    * CAST(
                        LEAST(requests_per_minute, :requests_per_minute)
                        AS double precision
                    ) / 60.0
            )
        ) / (
            CAST(
                LEAST(requests_per_minute, :requests_per_minute)
                AS double precision
            ) / 60.0
        )
    ) AS delay_seconds
    FROM collector_rate_limits
    WHERE scope = :scope
    """
)


class PostgresTokenBucketRateLimiter:
    """Acquire a shared token immediately before each external request.

    A denied attempt does not reserve a future token. The caller releases its
    database transaction, waits for the server-calculated refill interval, and
    retries. This prevents delayed worker processes from waking together and
    exceeding the aggregate configured rate.
    """

    def __init__(
        self,
        scope: str,
        requests_per_minute: int,
        *,
        session_factory=None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not isinstance(scope, str) or not scope.strip():
            raise ValueError("scope must be a non-empty string")
        if type(requests_per_minute) is not int or requests_per_minute <= 0:
            raise ValueError("requests_per_minute must be a positive integer")
        if session_factory is None:
            from app.db.session import SessionLocal

            session_factory = SessionLocal
        self.scope = scope.strip()
        self.requests_per_minute = requests_per_minute
        self._session_factory = session_factory
        self._sleeper = sleeper

    def acquire(self) -> None:
        parameters = {
            "scope": self.scope,
            "requests_per_minute": self.requests_per_minute,
        }
        while True:
            db = None
            try:
                db = self._session_factory()
                granted = db.execute(
                    _TRY_ACQUIRE_TOKEN,
                    parameters,
                ).scalar_one_or_none()
                if granted:
                    db.commit()
                    return

                delay_seconds = float(
                    db.execute(
                        _TOKEN_RETRY_DELAY,
                        parameters,
                    ).scalar_one()
                )
                db.commit()
            except Exception as exc:
                if db is not None:
                    db.rollback()
                raise RateLimiterUnavailableError(
                    f"Unable to acquire request token for {self.scope!r}"
                ) from exc
            finally:
                if db is not None:
                    db.close()

            if delay_seconds > 0:
                self._sleeper(delay_seconds)


class RateLimiterPool:
    """Cache clients locally while PostgreSQL retains all token-bucket state."""

    _limiters: dict[str, PostgresTokenBucketRateLimiter] = {}
    _lock = threading.Lock()

    @classmethod
    def get(
        cls,
        scope: str,
        requests_per_minute: int,
    ) -> PostgresTokenBucketRateLimiter:
        with cls._lock:
            limiter = cls._limiters.get(scope)
            if limiter is None or limiter.requests_per_minute != requests_per_minute:
                limiter = PostgresTokenBucketRateLimiter(scope, requests_per_minute)
                cls._limiters[scope] = limiter
            return limiter

    @classmethod
    def clear(cls) -> None:
        """Reset cached clients; durable bucket state remains in PostgreSQL."""
        with cls._lock:
            cls._limiters.clear()
