"""Configuration-driven collector discovery and construction."""

from __future__ import annotations

import importlib
import inspect
import re
from pathlib import Path
from typing import Any, Callable, TypeVar

from app.collectors.collector_base import (
    BaseCollector,
    CollectorDisabledError,
)
from app.core.config_loader import (
    CollectorConfig,
    CollectorConfigurationError,
    get_collector_config,
    load_collector_configs,
)


CollectorType = type[BaseCollector]
_CollectorT = TypeVar("_CollectorT", bound=BaseCollector)
_REGISTRY_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class CollectorRegistry:
    """
    Resolve collector implementations declared in ``collectors.yaml``.

    Configured classes are imported from their validated ``collector_class``
    path. Existing registrations are preserved, which makes explicit test or
    deployment overrides deterministic regardless of module import order.
    """

    _registry: dict[str, CollectorType] = {}

    @classmethod
    def _validate_name(cls, name: object) -> str:
        if not isinstance(name, str) or not _REGISTRY_NAME_RE.fullmatch(name):
            raise ValueError("Collector names must use lowercase snake_case")
        return name

    @classmethod
    def _validate_collector_class(
        cls,
        name: str,
        collector_class: object,
    ) -> CollectorType:
        if (
            not isinstance(collector_class, type)
            or not issubclass(collector_class, BaseCollector)
            or inspect.isabstract(collector_class)
        ):
            raise TypeError(
                f"Cannot register {name!r}: {collector_class!r} is not a "
                "concrete subclass of BaseCollector"
            )
        declared_name = getattr(collector_class, "registry_key", None)
        if declared_name is not None and declared_name != name:
            raise TypeError(
                f"Collector class {collector_class.__qualname__} declares registry_key "
                f"{declared_name!r}, not {name!r}"
            )
        return collector_class

    @classmethod
    def register(
        cls,
        name: str,
    ) -> Callable[[type[_CollectorT]], type[_CollectorT]]:
        """Register a programmatic collector; configured collectors need no decorator."""
        validated_name = cls._validate_name(name)

        def decorator(collector_class: type[_CollectorT]) -> type[_CollectorT]:
            cls.register_class(validated_name, collector_class)
            return collector_class

        return decorator

    @classmethod
    def register_class(cls, name: str, collector_class: CollectorType) -> None:
        validated_name = cls._validate_name(name)
        validated_class = cls._validate_collector_class(validated_name, collector_class)
        existing = cls._registry.get(validated_name)
        if existing is not None:
            raise ValueError(
                f"Collector {validated_name!r} is already registered as "
                f"{existing.__qualname__!r}"
            )
        cls._registry[validated_name] = validated_class

    @classmethod
    def force_register_class(cls, name: str, collector_class: CollectorType) -> None:
        """Install an explicit override while retaining all class invariants."""
        validated_name = cls._validate_name(name)
        cls._registry[validated_name] = cls._validate_collector_class(
            validated_name,
            collector_class,
        )

    @classmethod
    def _import_configured_class(cls, config: CollectorConfig) -> CollectorType:
        module_name, class_name = config.collector_class.split(":", 1)
        try:
            module = importlib.import_module(module_name)
            collector_class = getattr(module, class_name)
        except (ImportError, AttributeError) as exc:
            raise CollectorConfigurationError(
                f"Unable to import {config.collector_class!r} for collector "
                f"{config.registry_key!r}"
            ) from exc
        try:
            validated_class = cls._validate_collector_class(
                config.registry_key,
                collector_class,
            )
        except TypeError as exc:
            raise CollectorConfigurationError(
                f"Invalid collector class {config.collector_class!r} for "
                f"{config.registry_key!r}: {exc}"
            ) from exc
        cls._validate_config_constructor(config, validated_class)
        return validated_class

    @classmethod
    def _validate_config_constructor(
        cls,
        config: CollectorConfig,
        collector_class: CollectorType,
    ) -> None:
        try:
            parameters = inspect.signature(collector_class).parameters.values()
        except (TypeError, ValueError) as exc:
            raise CollectorConfigurationError(
                f"Cannot inspect constructor for {config.collector_class!r}"
            ) from exc
        accepts_config = any(
            parameter.name == "config"
            or parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in parameters
        )
        if not accepts_config:
            raise CollectorConfigurationError(
                f"Configured collector {config.collector_class!r} must accept "
                "a 'config' keyword argument"
            )

    @classmethod
    def _load_all(cls, config_path: str | Path | None = None) -> None:
        """Load every configured implementation without replacing overrides."""
        for name, config in load_collector_configs(config_path).items():
            existing = cls._registry.get(name)
            existing_path = (
                f"{existing.__module__}:{existing.__name__}"
                if existing is not None
                else None
            )
            if existing is not None and existing_path != config.collector_class:
                cls._validate_config_constructor(config, existing)
                continue
            configured_class = cls._import_configured_class(config)
            cls._registry[name] = configured_class

    @classmethod
    def get_class(
        cls,
        name: str,
        config_path: str | Path | None = None,
    ) -> CollectorType:
        validated_name = cls._validate_name(name)
        cls._load_all(config_path)
        try:
            return cls._registry[validated_name]
        except KeyError as exc:
            raise KeyError(f"Collector {validated_name!r} is not registered") from exc

    @classmethod
    def config_for(
        cls,
        name: str,
        config_path: str | Path | None = None,
    ) -> CollectorConfig:
        return get_collector_config(cls._validate_name(name), config_path)

    @classmethod
    def active_collector_configs(
        cls,
        config_path: str | Path | None = None,
    ) -> list[CollectorConfig]:
        configs = load_collector_configs(config_path)
        cls._load_all(config_path)
        return [config for config in configs.values() if config.enabled]

    @classmethod
    def active_collector_names(
        cls,
        config_path: str | Path | None = None,
    ) -> list[str]:
        return [config.registry_key for config in cls.active_collector_configs(config_path)]

    @classmethod
    def is_enabled(
        cls,
        name: str,
        config_path: str | Path | None = None,
    ) -> bool:
        return cls.config_for(name, config_path).enabled

    @classmethod
    def rate_limit_for(
        cls,
        name: str,
        config_path: str | Path | None = None,
    ) -> int:
        return cls.config_for(name, config_path).rate_limit_per_minute

    @classmethod
    def rate_limit_config_for(
        cls,
        name: str,
        config_path: str | Path | None = None,
    ) -> dict[str, int]:
        return cls.config_for(name, config_path).rate_limit_config

    @classmethod
    def create(
        cls,
        name: str,
        *,
        config_path: str | Path | None = None,
        **kwargs: Any,
    ) -> BaseCollector:
        validated_name = cls._validate_name(name)
        collector_class = cls.get_class(validated_name, config_path)
        configs = load_collector_configs(config_path)
        config = configs.get(validated_name)
        if config is None:
            # Keep isolated, undecorated test/tool collectors available without
            # weakening fail-closed behavior for named production collectors.
            if getattr(collector_class, "registry_key", None) is not None:
                raise CollectorConfigurationError(
                    f"Collector {validated_name!r} has no configuration stanza"
                )
            return collector_class(**kwargs)
        if not config.enabled:
            raise CollectorDisabledError(f"Collector {validated_name!r} is disabled")
        kwargs.setdefault("config", config)
        return collector_class(**kwargs)
