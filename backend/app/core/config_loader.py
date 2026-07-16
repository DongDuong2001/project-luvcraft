"""Strict, external configuration for collector discovery and execution."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml
from yaml.constructor import ConstructorError


_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "conf" / "collectors.yaml"
_CONFIG_PATH_ENV = "COLLECTORS_CONFIG_PATH"
_REGISTRY_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_CLASS_PATH_RE = re.compile(
    r"^app\.collectors(?:\.[A-Za-z_][A-Za-z0-9_]*)+:[A-Za-z_][A-Za-z0-9_]*$"
)
_TASK_NAME_RE = re.compile(r"^luvcraft\.[a-z][a-z0-9_.-]*$")


class CollectorConfigurationError(ValueError):
    """Raised when collector configuration is missing, malformed, or unsafe."""


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(loader, node, deep=False):
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


@dataclass(frozen=True)
class DataSourceConfig:
    """Database metadata for records emitted by one collector."""

    name: str
    platform: str
    category: str
    access_method: str


@dataclass(frozen=True)
class CollectorConfig:
    """Validated runtime configuration for one collector implementation."""

    registry_key: str
    collector_class: str
    task_name: str | None
    name: str
    endpoints: tuple[str, ...]
    enabled: bool
    rate_limit_per_minute: int
    source: DataSourceConfig

    @property
    def primary_endpoint(self) -> str:
        return self.endpoints[0]

    @property
    def rate_limit_config(self) -> dict[str, int]:
        return {"requests_per_minute": self.rate_limit_per_minute}


def collectors_config_path(config_path: str | Path | None = None) -> Path:
    """Resolve an explicit path, environment override, or repository default."""
    if config_path is not None:
        return Path(config_path)
    configured = os.getenv(_CONFIG_PATH_ENV)
    return Path(configured) if configured else _DEFAULT_CONFIG_PATH


def _load_raw(config_path: str | Path | None = None) -> dict[str, Any]:
    path = collectors_config_path(config_path)
    try:
        with path.open(encoding="utf-8") as handle:
            data = yaml.load(handle, Loader=_UniqueKeyLoader)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise CollectorConfigurationError(
            f"Unable to load collector configuration from {path}: {exc}"
        ) from exc

    if not isinstance(data, dict) or not data:
        raise CollectorConfigurationError(
            f"Collector configuration at {path} must be a non-empty mapping"
        )
    return data


def _required_string(mapping: dict[str, Any], field: str, context: str) -> str:
    value = mapping.get(field)
    if not isinstance(value, str) or not value.strip():
        raise CollectorConfigurationError(f"{context}.{field} must be a non-empty string")
    return value.strip()


def _reject_unknown_fields(
    mapping: dict[Any, Any],
    allowed: set[str],
    context: str,
) -> None:
    non_string = [key for key in mapping if not isinstance(key, str)]
    if non_string:
        raise CollectorConfigurationError(
            f"{context} field names must be strings: "
            + ", ".join(repr(key) for key in non_string)
        )
    unknown = set(mapping) - allowed
    if unknown:
        raise CollectorConfigurationError(
            f"{context} contains unknown fields: {', '.join(sorted(unknown))}"
        )


def _validate_endpoint(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CollectorConfigurationError(f"{context} endpoints must be non-empty strings")
    endpoint = value.strip().rstrip("/")
    parsed = urlsplit(endpoint)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise CollectorConfigurationError(
            f"{context} endpoint {value!r} must be an HTTPS URL without credentials"
        )
    return endpoint


def _parse_source(value: Any, context: str) -> DataSourceConfig:
    if not isinstance(value, dict):
        raise CollectorConfigurationError(f"{context}.source must be a mapping")
    allowed = {"name", "platform", "category", "access_method"}
    _reject_unknown_fields(value, allowed, f"{context}.source")
    return DataSourceConfig(
        name=_required_string(value, "name", f"{context}.source"),
        platform=_required_string(value, "platform", f"{context}.source"),
        category=_required_string(value, "category", f"{context}.source"),
        access_method=_required_string(value, "access_method", f"{context}.source"),
    )


def _parse_collector(registry_key: Any, value: Any) -> CollectorConfig:
    context = f"collector[{registry_key!r}]"
    if not isinstance(registry_key, str) or not _REGISTRY_KEY_RE.fullmatch(registry_key):
        raise CollectorConfigurationError(
            f"Collector key {registry_key!r} must use lowercase snake_case"
        )
    if not isinstance(value, dict):
        raise CollectorConfigurationError(f"{context} must be a mapping")

    allowed = {
        "collector_class",
        "task_name",
        "name",
        "endpoints",
        "enabled",
        "rate_limit_per_minute",
        "source",
    }
    _reject_unknown_fields(value, allowed, context)

    collector_class = _required_string(value, "collector_class", context)
    if not _CLASS_PATH_RE.fullmatch(collector_class):
        raise CollectorConfigurationError(
            f"{context}.collector_class must reference app.collectors as 'module:Class'"
        )

    enabled = value.get("enabled")
    if type(enabled) is not bool:
        raise CollectorConfigurationError(f"{context}.enabled must be a boolean")

    rate = value.get("rate_limit_per_minute")
    if type(rate) is not int or rate <= 0:
        raise CollectorConfigurationError(
            f"{context}.rate_limit_per_minute must be a positive integer"
        )

    endpoints = value.get("endpoints")
    if not isinstance(endpoints, list) or not endpoints:
        raise CollectorConfigurationError(f"{context}.endpoints must be a non-empty list")
    validated_endpoints = tuple(
        _validate_endpoint(endpoint, context) for endpoint in endpoints
    )

    raw_task_name = value.get("task_name")
    if raw_task_name is None:
        task_name = None
    elif isinstance(raw_task_name, str) and _TASK_NAME_RE.fullmatch(raw_task_name.strip()):
        task_name = raw_task_name.strip()
    else:
        raise CollectorConfigurationError(
            f"{context}.task_name must be a luvcraft.* Celery task name"
        )
    if enabled and task_name is None:
        raise CollectorConfigurationError(
            f"{context}.task_name is required when the collector is enabled"
        )

    return CollectorConfig(
        registry_key=registry_key,
        collector_class=collector_class,
        task_name=task_name,
        name=_required_string(value, "name", context),
        endpoints=validated_endpoints,
        enabled=enabled,
        rate_limit_per_minute=rate,
        source=_parse_source(value.get("source"), context),
    )


def load_collectors_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Return the raw YAML mapping after strict file-level validation."""
    return _load_raw(config_path)


def load_collector_configs(
    config_path: str | Path | None = None,
) -> dict[str, CollectorConfig]:
    """Load and strictly validate every configured collector."""
    raw = _load_raw(config_path)
    return {key: _parse_collector(key, stanza) for key, stanza in raw.items()}


def get_collector_config(
    registry_key: str,
    config_path: str | Path | None = None,
) -> CollectorConfig:
    configs = load_collector_configs(config_path)
    try:
        return configs[registry_key]
    except KeyError as exc:
        raise CollectorConfigurationError(
            f"Collector {registry_key!r} has no configuration stanza"
        ) from exc


def active_collector_names(config_path: str | Path | None = None) -> list[str]:
    """Return enabled collector keys in configuration order."""
    return [
        key
        for key, config in load_collector_configs(config_path).items()
        if config.enabled
    ]
