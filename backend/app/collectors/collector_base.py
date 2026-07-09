from __future__ import annotations

import abc
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

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
    published_at: str
    engagement: dict[str, int | None]
    url: str
    channel_id: str | None
    platform_metadata: dict[str, Any]


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
    3. **Cross-cutting concerns** - SLA timeout tracking, the mandatory
       spam/bot filter and compliance passes, and (for API-backed sources) a
       shared JSON request helper all live here so individual collectors only
       implement source-specific search/fetch/normalize logic.

    Subclasses implement :meth:`_collect`; everything else is inherited.
    """

    #: API-backed collectors should set this to their API's base URL so they
    #: can use :meth:`_get_json` instead of hand-rolling HTTP error handling.
    base_url: str | None = None

    def __init__(
        self,
        *,
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.client = client
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
            logger.warning("Execution time exceeded the 3-minute SLA limit constraint.")

    # -- Mandatory global hooks ----------------------------------------------
    # Every collector runs through these two hooks before records are handed
    # back to the caller. Defaults are no-ops; subclasses that can cheaply
    # detect spam/PII at collection time (rather than during downstream
    # processing) should override them.

    def filter_spam_and_bots(self, records: list[CollectorRecord]) -> list[CollectorRecord]:
        """Global requirement: spam and bot filtering as a mandatory pass."""
        return records

    def enforce_compliance(self, records: list[CollectorRecord]) -> list[CollectorRecord]:
        """
        Ethics & Compliance: collect only publicly available data and strip
        PII (personally identifiable information) before records leave the
        collector. Never use authenticated routes or simulated logins.
        """
        return records

    def check_robots_txt(self, url: str) -> bool:
        """Ethics & Compliance: respect robots.txt/platform ToS before scraping."""
        logger.info("Verifying robots.txt compliance for %s", url)
        # Placeholder for actual urllib.robotparser logic.
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
        the source-specific :meth:`_collect` with SLA tracking and the
        mandatory filter/compliance pipeline so subclasses cannot
        accidentally skip either.
        """
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
            records = self.enforce_compliance(records)
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
        if self.base_url is None:
            raise NotImplementedError(
                f"{self.__class__.__name__} must set base_url to use _get_json"
            )
        try:
            if self.client is not None:
                response = self.client.get(path, params=params, timeout=self.timeout_seconds)
            else:
                with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds) as client:
                    response = client.get(path, params=params)
        except httpx.TimeoutException as exc:
            raise CollectorTimeoutError(f"{self.__class__.__name__} request timed out") from exc
        except httpx.HTTPError as exc:
            raise CollectorError(f"{self.__class__.__name__} request failed") from exc

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
