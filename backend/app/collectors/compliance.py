"""Record-wide privacy sanitization for public collector outputs."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    from app.collectors.collector_base import CollectorRecord


REDACTED = "redacted"
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_HANDLE_RE = re.compile(r"(?<![A-Za-z0-9_])@[A-Za-z0-9_.-]{2,}")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d .()-]{7,}\d)(?!\d)")
_CAMEL_CASE_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_SENSITIVE_METADATA_KEYS = {
    "account",
    "actor",
    "author",
    "author_name",
    "avatar",
    "avatar_url",
    "channel_id",
    "channel_title",
    "creator",
    "email",
    "handle",
    "login",
    "owner",
    "phone",
    "profile",
    "profile_url",
    "user",
    "user_name",
    "username",
}
_IDENTITY_KEY_TOKENS = {
    "account",
    "actor",
    "author",
    "avatar",
    "channel",
    "creator",
    "email",
    "handle",
    "login",
    "owner",
    "phone",
    "profile",
    "user",
    "username",
}
_RAW_PAYLOAD_KEY_TOKENS = {"payload", "raw"}


def _known_value_pattern(value: str) -> re.Pattern[str] | None:
    normalized = value.strip()
    if not normalized:
        return None
    escaped = re.escape(normalized)
    if re.fullmatch(r"[A-Za-z0-9_.-]+", normalized):
        escaped = rf"(?<![A-Za-z0-9_.-]){escaped}(?![A-Za-z0-9_.-])"
    return re.compile(escaped, re.IGNORECASE)


def redact_text(value: str, sensitive_values: Iterable[str] = ()) -> str:
    """Redact common PII patterns and source-provided account identifiers."""
    redacted = value
    for sensitive in sensitive_values:
        pattern = _known_value_pattern(sensitive)
        if pattern is not None:
            redacted = pattern.sub(REDACTED, redacted)
    redacted = _EMAIL_RE.sub(REDACTED, redacted)
    redacted = _HANDLE_RE.sub(f"@{REDACTED}", redacted)
    redacted = _PHONE_RE.sub(REDACTED, redacted)
    return redacted


def _metadata_key_parts(key: object) -> tuple[str, set[str]]:
    separated = _CAMEL_CASE_BOUNDARY_RE.sub("_", str(key).strip())
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", separated).strip("_").lower()
    return normalized, set(normalized.split("_")) if normalized else set()


def _is_identity_metadata_key(key: object) -> bool:
    normalized, parts = _metadata_key_parts(key)
    return normalized in _SENSITIVE_METADATA_KEYS or bool(parts & _IDENTITY_KEY_TOKENS)


def _is_sensitive_metadata_key(key: object) -> bool:
    _, parts = _metadata_key_parts(key)
    return _is_identity_metadata_key(key) or bool(parts & _RAW_PAYLOAD_KEY_TOKENS)


def _sensitive_metadata_values(
    value: Any,
    *,
    identity_context: bool = False,
) -> set[str]:
    """Find account identifiers before their metadata containers are removed."""
    values: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            values.update(
                _sensitive_metadata_values(
                    item,
                    identity_context=(
                        identity_context or _is_identity_metadata_key(key)
                    ),
                )
            )
    elif isinstance(value, (list, tuple)):
        for item in value:
            values.update(
                _sensitive_metadata_values(
                    item,
                    identity_context=identity_context,
                )
            )
    elif identity_context and isinstance(value, str):
        normalized = value.strip()
        if normalized:
            values.add(normalized)
    return values


def sanitize_metadata(value: Any, sensitive_values: Iterable[str] = ()) -> Any:
    """Recursively remove identity/raw-payload keys and redact string values."""
    if isinstance(value, dict):
        return {
            key: sanitize_metadata(item, sensitive_values)
            for key, item in value.items()
            if not _is_sensitive_metadata_key(key)
        }
    if isinstance(value, list):
        return [sanitize_metadata(item, sensitive_values) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_metadata(item, sensitive_values) for item in value)
    if isinstance(value, str):
        return redact_text(value, sensitive_values)
    return value


def sanitize_record(record: "CollectorRecord") -> "CollectorRecord":
    """Apply the global privacy policy to every user-visible record field."""
    sensitive_values = _sensitive_metadata_values(record.platform_metadata)
    if record.channel_id:
        sensitive_values.add(record.channel_id)

    return replace(
        record,
        title=redact_text(record.title, sensitive_values),
        content=redact_text(record.content, sensitive_values),
        raw_text=redact_text(record.raw_text, sensitive_values),
        url=redact_text(record.url, sensitive_values),
        channel_id=None,
        platform_metadata=sanitize_metadata(
            record.platform_metadata,
            sensitive_values,
        ),
    )
