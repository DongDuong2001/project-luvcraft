from __future__ import annotations

import abc
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TYPE_CHECKING

import httpx

from .compliance import sanitize_record
from .rate_limit import (
    RateLimiter,
    RateLimiterPool,
    RateLimiterUnavailableError,
)

if TYPE_CHECKING:
    from app.core.config_loader import CollectorConfig

logger = logging.getLogger(__name__)

# End-to-end processing goal for a single collector run.
SLA_SECONDS = 180


# ---------------------------------------------------------------------------
# Standardized output
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CollectorRecord:
    """
    Standard normalized record every Project Luvcraft collector must produce,
    regardless of source platform. Downstream persistence and processing code
    (see ``app/tasks/analyze.py``) is written against this shape, not against
    any single platform's API payload, so a new source only needs to map its
    own response into a ``CollectorRecord`` to plug into the rest of the
    pipeline.
    """

    source: str
    external_item_id: str
    title: str
    content: str
    raw_text: str
    published_at: str | None
    engagement: dict[str, int | None]
    url: str
    channel_id: str | None
    platform_metadata: dict[str, Any]
    signal_type: str | None = None
    observed_at: str | None = None


# ---------------------------------------------------------------------------
# Standardized error hierarchy
# ---------------------------------------------------------------------------
# Source-specific collectors should raise these (or a subclass of these) so
# that orchestration code (Celery tasks) can handle failures the same way
# regardless of which platform failed.


class CollectorError(Exception):
    """Base error for all Project Luvcraft data collector failures."""


class CollectorAuthError(CollectorError):
    """Raised when a source's API key/credential is missing or rejected."""


class CollectorQuotaError(CollectorError):
    """Raised when a source's quota or daily rate limit is exceeded."""


class CollectorTimeoutError(CollectorError):
    """Raised when a request to a source times out."""


class CollectorMalformedResponseError(CollectorError):
    """Raised when a source returns an unexpected response shape."""


class CollectorDisabledError(CollectorError):
    """Raised when code attempts to execute a disabled collector."""


# ---------------------------------------------------------------------------
# Framework
# ---------------------------------------------------------------------------


class BaseCollector(abc.ABC):
    """
    Abstract base class for Project Luvcraft data collectors.

    The framework standardizes three things across every source platform:

    1. **Input** - every collector is driven by the same keyword/time-window
       parameters, supplied to :meth:`collect` (not the constructor), so
       swapping or adding a source never changes how orchestration code calls
       it.
    2. **Output** - every collector returns ``list[CollectorRecord]``.
    3. **Cross-cutting behavior** - configuration-driven endpoints, request
       pacing, record validation and PII sanitization are enforced centrally.
       Spam filtering remains an extension point because downstream persistence
       retains spam audit statistics instead of silently dropping records.

    Subclasses implement :meth:`_collect`; everything else is inherited.

    .. note:: Requirement gaps (tracked explicitly)

       * **Spam filtering** – :meth:`filter_spam_and_bots` is an extension point.
         Downstream processing stores exclusion statistics for auditability.
       * **robots.txt** – :meth:`check_robots_txt` logs and returns ``True``
         unconditionally.  A full ``urllib.robotparser`` integration is a
         known gap.
       * **SLA enforcement** – the 3-minute SLA is tracked and logged; it
         does not yet interrupt or abort a running collector.  Enforcement
         via timeout cancellation is a known gap.
    """

    #: The registry injects the configured primary endpoint here for
    #: API-backed collectors using :meth:`_get_json`.
    base_url: str | None = None
    registry_key: str | None = None

    def __init__(
        self,
        *,
        config: "CollectorConfig | None" = None,
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        if config is None and self.registry_key is not None:
            from app.core.config_loader import get_collector_config

            config = get_collector_config(self.registry_key)
        if config is not None and self.registry_key not in {None, config.registry_key}:
            raise ValueError(
                f"Collector {type(self).__name__} cannot use config for "
                f"{config.registry_key!r}"
            )
        self.config = config
        self.base_url = config.primary_endpoint if config is not None else self.base_url
        self.timeout_seconds = timeout_seconds
        self.client = client
        self.rate_limiter = rate_limiter
        if self.rate_limiter is None and config is not None:
            self.rate_limiter = RateLimiterPool.get(
                config.registry_key,
                config.rate_limit_per_minute,
            )
        self.start_time: float | None = None
        self.end_time: float | None = None

    # -- SLA tracking -------------------------------------------------------

    def _start_tracking(self, keyword: str) -> None:
        self.start_time = time.time()
        logger.info("Started collection for '%s' via %s", keyword, self.__class__.__name__)

    def _stop_tracking(self) -> None:
        self.end_time = time.time()
        execution_time = self.end_time - (self.start_time or self.end_time)
        logger.info("Finished %s in %.2f seconds", self.__class__.__name__, execution_time)
        if execution_time > SLA_SECONDS:
            # REQUIREMENT GAP: SLA violation is logged but does not abort the
            # collector.  Enforcement via timeout cancellation is not yet
            # implemented.
            logger.warning(
                "SLA VIOLATION: %s exceeded the %ds limit (took %.2fs). "
                "Aborting via timeout cancellation is not yet implemented.",
                self.__class__.__name__,
                SLA_SECONDS,
                execution_time,
            )

    # -- Filtering and compliance --------------------------------------------
    # Spam handling remains overridable so persistence can retain audit counts;
    # compliance sanitization is always applied after that extension point.

    def filter_spam_and_bots(
        self, records: list[CollectorRecord]
    ) -> list[CollectorRecord]:
        """
        Extension point: per-collector spam and bot filtering.

        The base implementation is a **pass-through** (no filtering performed).
        Subclasses may override this to drop clearly spammy records early.
        Downstream processing in ``app/services/processing_service.py`` is the
        primary spam-detection layer.

        .. note:: REQUIREMENT GAP – in-collector spam enforcement is not yet
           implemented at the base level.
        """
        return records

    def apply_source_compliance(
        self, records: list[CollectorRecord]
    ) -> list[CollectorRecord]:
        """Optional source-specific compliance hook applied before global sanitization."""
        return records

    def enforce_compliance(
        self, records: list[CollectorRecord]
    ) -> list[CollectorRecord]:
        """
        Remove account-name metadata, raw API payloads, email addresses, phone
        numbers and public handles from every record before it leaves the
        collector. Source-specific normalizers may additionally provide known
        identifiers for redaction before constructing the record.
        """
        return [sanitize_record(record) for record in records]

    def check_robots_txt(self, url: str) -> bool:
        """
        Extension point: robots.txt / platform ToS compliance check.

        The base implementation **logs and returns True unconditionally**.
        A full ``urllib.robotparser`` integration is a known requirement gap.

        .. note:: REQUIREMENT GAP – robots.txt is not actually parsed or
           enforced.  This is a placeholder for future implementation.
        """
        logger.info(
            "robots.txt check for %s: not yet enforced (REQUIREMENT GAP).", url
        )
        return True

    # -- Standardized entrypoint ---------------------------------------------

    def collect(
        self,
        *,
        keyword: str,
        published_after: datetime,
        published_before: datetime,
        max_results: int = 50,
    ) -> list[CollectorRecord]:
        """
        Uniform entrypoint for every collector. Same inputs in
        (``keyword``, ``published_after``, ``published_before``,
        ``max_results``), standardized ``CollectorRecord`` list out. Wraps
        the source-specific :meth:`_collect` with SLA tracking, optional spam
        filtering, and mandatory record-wide compliance sanitization.
        """
        if self.config is not None and not self.config.enabled:
            raise CollectorDisabledError(
                f"Collector {self.config.registry_key!r} is disabled"
            )
        if self.base_url is not None:
            self.check_robots_txt(self.base_url)
        self._start_tracking(keyword)
        try:
            records = self._collect(
                keyword=keyword,
                published_after=published_after,
                published_before=published_before,
                max_results=max_results,
            )
            
            # Basic validation & text normalization (Task 5.6)
            from dataclasses import replace
            from app.services.processing_service import clean_text
            
            valid_records = []
            for r in records:
                ext_id = (r.external_item_id or "").strip()
                src = (r.source or "").strip()
                title_val = (r.title or "").strip()
                content_val = (r.content or "").strip()
                
                if not ext_id or not src:
                    logger.warning("CollectorRecord missing external_item_id or source, discarding.")
                    continue
                if not title_val and not content_val:
                    logger.warning("CollectorRecord has empty title and content, discarding.")
                    continue
                
                # Normalize and clean text fields
                cleaned_title = clean_text(title_val)
                cleaned_content = clean_text(content_val)
                cleaned_raw_text = clean_text(r.raw_text or "")
                
                cleaned_r = replace(
                    r,
                    external_item_id=ext_id,
                    source=src,
                    title=cleaned_title,
                    content=cleaned_content,
                    raw_text=cleaned_raw_text,
                )
                valid_records.append(cleaned_r)
                
            records = self.filter_spam_and_bots(valid_records)
            records = self.apply_source_compliance(records)
            # Call the base implementation explicitly so a subclass cannot
            # accidentally bypass the mandatory record-wide privacy boundary.
            records = BaseCollector.enforce_compliance(self, records)
            return records
        except Exception:
            logger.error("Collector %s failed", self.__class__.__name__, exc_info=True)
            raise
        finally:
            self._stop_tracking()

    @abc.abstractmethod
    def _collect(
        self,
        *,
        keyword: str,
        published_after: datetime,
        published_before: datetime,
        max_results: int,
    ) -> list[CollectorRecord]:
        """
        Subclasses implement their source-specific search + fetch + normalize
        logic here and return standardized ``CollectorRecord`` objects.
        """
        raise NotImplementedError

    # -- Shared HTTP/JSON helper (for API-backed collectors) -----------------

    def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        """
        Shared REST helper for JSON API-backed collectors. Handles transport
        errors, HTTP error-status classification (via the overridable
        :meth:`_raise_for_api_error` hook), and response-shape validation so
        each new collector doesn't reimplement this boilerplate.
        """
        return self._request_json("GET", path, params=params)

    def _post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """POST a JSON object while applying the shared HTTP/error boundary."""
        return self._request_json(
            "POST",
            path,
            json_payload=payload,
            headers=headers,
        )

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute one configured HTTP request and require an object response."""
        if self.base_url is None:
            raise NotImplementedError(
                f"{self.__class__.__name__} must set base_url to use HTTP helpers"
            )
        request_kwargs: dict[str, Any] = {"timeout": self.timeout_seconds}
        if params is not None:
            request_kwargs["params"] = params
        if json_payload is not None:
            request_kwargs["json"] = json_payload
        if headers is not None:
            request_kwargs["headers"] = headers

        try:
            if self.rate_limiter is not None:
                self.rate_limiter.acquire()
            if self.client is not None:
                request = getattr(self.client, method.lower())
                response = request(path, **request_kwargs)
            else:
                with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds) as client:
                    request = getattr(client, method.lower())
                    request_kwargs.pop("timeout")
                    response = request(path, **request_kwargs)
        except httpx.TimeoutException as exc:
            raise CollectorTimeoutError(f"{self.__class__.__name__} request timed out") from exc
        except httpx.HTTPError as exc:
            raise CollectorError(f"{self.__class__.__name__} request failed") from exc
        except RateLimiterUnavailableError as exc:
            raise CollectorError(
                f"{self.__class__.__name__} rate limiter is unavailable"
            ) from exc

        if response.status_code >= 400:
            self._raise_for_api_error(response)

        try:
            payload = response.json()
        except ValueError as exc:
            raise CollectorMalformedResponseError(
                f"{self.__class__.__name__} returned invalid JSON"
            ) from exc

        if not isinstance(payload, dict):
            raise CollectorMalformedResponseError(
                f"{self.__class__.__name__} response must be a JSON object"
            )
        return payload

    def _raise_for_api_error(self, response: httpx.Response) -> None:
        """
        Default HTTP error-status classification. Override in source-specific
        collectors to distinguish auth/quota/other failures using that
        platform's error payload shape (see ``YouTubeCollector`` for an
        example).
        """
        raise CollectorError(
            f"{self.__class__.__name__} request returned HTTP {response.status_code}"
        )

    # -- Small normalization utilities shared across collectors -------------

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _string_value(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        stripped = value.strip()
        return stripped or None
