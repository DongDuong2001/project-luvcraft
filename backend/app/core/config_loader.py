"""
Extensibility requirement: loads source definitions (subreddits, feeds,
platforms) from external YAML configuration so new sources can be enabled or
disabled without changing any Python source files.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "conf" / "collectors.yaml"

# Canonical registry key → YAML stanza key mapping.
# A YAML stanza key is the top-level key in collectors.yaml (e.g.
# "youtube_collector"). The registry key is what CollectorRegistry and
# orchestration code use (e.g. "youtube").
_REGISTRY_KEY_MAP: dict[str, str] = {
    "youtube":   "youtube_collector",
    "community": "community_collector",
    "hype":      "hype_collector",
    "social":    "social_collector",
}


@dataclass(frozen=True)
class CollectorConfig:
    """
    Validated, type-safe view of a single collector stanza from
    ``collectors.yaml``.  Consumers should obtain instances through
    :func:`get_collector_config` rather than constructing them directly.
    """

    registry_key: str          # "youtube", "community", …
    name: str                  # human-readable name
    endpoints: list[str]       # declared endpoint URLs
    enabled: bool              # whether this collector should run
    rate_limit_per_minute: int # requests/minute cap from YAML

    # ------------------------------------------------------------------ #
    # Convenience helpers used by orchestration / data-source creation     #
    # ------------------------------------------------------------------ #

    @property
    def rate_limit_config(self) -> dict[str, Any]:
        """Return a ``rate_limit_config`` dict suitable for ``DataSource``."""
        return {"requests_per_minute": self.rate_limit_per_minute}


def _load_raw(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load the YAML file and return the raw dict (or {} on failure)."""
    path = Path(config_path) if config_path is not None else _DEFAULT_CONFIG_PATH
    if not path.exists():
        logger.warning("Collectors config not found at %s; using defaults.", path)
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            logger.error("collectors.yaml must be a mapping; got %s", type(data))
            return {}
        logger.info("Loaded external collector configuration from %s", path)
        return data
    except yaml.YAMLError as exc:
        logger.error("Error parsing collectors.yaml: %s", exc)
        return {}


def _parse_stanza(registry_key: str, stanza: Any) -> CollectorConfig | None:
    """
    Convert one raw YAML stanza into a :class:`CollectorConfig`.
    Returns ``None`` and logs a warning when required fields are missing.
    """
    if not isinstance(stanza, dict):
        logger.warning("Collector stanza for '%s' is not a mapping; skipping.", registry_key)
        return None

    name = stanza.get("name", registry_key)
    endpoints = stanza.get("endpoints") or []
    if not isinstance(endpoints, list):
        endpoints = []

    enabled_raw = stanza.get("enabled", True)
    enabled = bool(enabled_raw)

    rate_raw = stanza.get("rate_limit_per_minute", 60)
    try:
        rate_limit = int(rate_raw)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid rate_limit_per_minute '%s' for collector '%s'; defaulting to 60.",
            rate_raw, registry_key,
        )
        rate_limit = 60

    return CollectorConfig(
        registry_key=registry_key,
        name=str(name),
        endpoints=[str(e) for e in endpoints],
        enabled=enabled,
        rate_limit_per_minute=rate_limit,
    )


def load_collectors_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """
    Public API – backward-compatible.

    Returns the raw YAML dict (keyed by YAML stanza keys such as
    ``"youtube_collector"``). Use :func:`get_collector_config` when you want a
    validated :class:`CollectorConfig` for a specific collector.
    """
    return _load_raw(config_path)


def get_collector_config(
    registry_key: str,
    config_path: str | Path | None = None,
) -> CollectorConfig:
    """
    Return the validated :class:`CollectorConfig` for *registry_key* (e.g.
    ``"youtube"``, ``"community"``).

    Falls back to a default ``CollectorConfig`` with ``enabled=True`` when the
    YAML file cannot be read or the stanza is missing, so callers never have to
    guard against ``None``.
    """
    raw = _load_raw(config_path)
    stanza_key = _REGISTRY_KEY_MAP.get(registry_key, f"{registry_key}_collector")
    stanza = raw.get(stanza_key)
    parsed = _parse_stanza(registry_key, stanza) if stanza is not None else None
    if parsed is None:
        logger.warning(
            "No valid YAML stanza for collector '%s' (looked for '%s'); "
            "defaulting to enabled=True, rate_limit_per_minute=60.",
            registry_key, stanza_key,
        )
        return CollectorConfig(
            registry_key=registry_key,
            name=registry_key,
            endpoints=[],
            enabled=True,
            rate_limit_per_minute=60,
        )
    return parsed


def active_collector_names(
    config_path: str | Path | None = None,
) -> list[str]:
    """
    Return the registry keys (e.g. ``["youtube", "community"]``) of every
    collector whose YAML stanza has ``enabled: true``.

    Collectors that have no stanza at all are *included* with a default
    ``enabled=True`` so that the registry stays backward-compatible when new
    collectors are added in code before their YAML stanza is written.
    """
    return [
        key for key in _REGISTRY_KEY_MAP
        if get_collector_config(key, config_path).enabled
    ]


# ---------------------------------------------------------------------------
# Module-level singleton – kept for backward compatibility with any code that
# still does ``from app.core.config_loader import COLLECTORS_CONFIG``.
# ---------------------------------------------------------------------------
COLLECTORS_CONFIG: dict[str, Any] = load_collectors_config()
