"""
Collector registry: maps string names (e.g. ``"youtube"``) to their
:class:`~app.collectors.collector_base.BaseCollector` subclasses and
surfaces the *enabled* / *rate-limit* settings from
``conf/collectors.yaml`` so that orchestration code can respect them
without touching this file.

Contract
--------
* Only concrete subclasses of :class:`BaseCollector` may be registered.
  Attempting to register any other type raises :exc:`TypeError` immediately,
  at decoration time, not at instantiation time.
* Registration is **first-writer wins**: once a name is claimed, subsequent
  attempts to claim the *same* name raise :exc:`ValueError` rather than
  silently overwriting the existing class.  To intentionally replace a
  registration use :meth:`force_register_class`.
* :meth:`_load_all` only fills *missing* entries; it never overwrites names
  that are already in the registry, so a test-registered stub is never
  reverted by an unrelated missing-name lookup.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Type

from app.collectors.collector_base import BaseCollector


class CollectorRegistry:
    _registry: Dict[str, Type[BaseCollector]] = {}

    # ------------------------------------------------------------------ #
    # Internal validation helper                                            #
    # ------------------------------------------------------------------ #

    @classmethod
    def _validate_collector_class(
        cls, name: str, collector_class: object
    ) -> Type[BaseCollector]:
        """
        Assert that *collector_class* is a concrete subclass of
        :class:`BaseCollector`.  Returns it typed correctly.

        :raises TypeError: if *collector_class* is not a subclass of
            ``BaseCollector`` or is ``BaseCollector`` itself.
        """
        if (
            not isinstance(collector_class, type)
            or not issubclass(collector_class, BaseCollector)
            or collector_class is BaseCollector
        ):
            raise TypeError(
                f"Cannot register '{name}': {collector_class!r} is not a "
                "concrete subclass of BaseCollector."
            )
        return collector_class  # type: ignore[return-value]

    # ------------------------------------------------------------------ #
    # Registration helpers                                                  #
    # ------------------------------------------------------------------ #

    @classmethod
    def register(
        cls, name: str
    ) -> Callable[[Type[BaseCollector]], Type[BaseCollector]]:
        """
        Class decorator.  Registers *collector_class* under *name*.

        :raises TypeError: if the decorated class is not a concrete
            ``BaseCollector`` subclass.
        :raises ValueError: if *name* is already registered.  Use
            :meth:`force_register_class` to intentionally replace.
        """
        def decorator(
            collector_class: Type[BaseCollector],
        ) -> Type[BaseCollector]:
            validated = cls._validate_collector_class(name, collector_class)
            if name in cls._registry:
                raise ValueError(
                    f"Collector '{name}' is already registered as "
                    f"{cls._registry[name].__qualname__!r}. "
                    "Use force_register_class() to intentionally replace it."
                )
            cls._registry[name] = validated
            return validated

        return decorator

    @classmethod
    def register_class(
        cls, name: str, collector_class: Type[BaseCollector]
    ) -> None:
        """
        Register *collector_class* under *name* (first-writer wins).

        :raises TypeError: if *collector_class* is not a concrete
            ``BaseCollector`` subclass.
        :raises ValueError: if *name* is already registered.
        """
        validated = cls._validate_collector_class(name, collector_class)
        if name in cls._registry:
            raise ValueError(
                f"Collector '{name}' is already registered as "
                f"{cls._registry[name].__qualname__!r}. "
                "Use force_register_class() to intentionally replace it."
            )
        cls._registry[name] = validated

    @classmethod
    def force_register_class(
        cls, name: str, collector_class: Type[BaseCollector]
    ) -> None:
        """
        Unconditionally register *collector_class* under *name*, replacing
        any existing entry.  Intended for test overrides only.

        :raises TypeError: if *collector_class* is not a concrete
            ``BaseCollector`` subclass.
        """
        cls._registry[name] = cls._validate_collector_class(name, collector_class)

    # ------------------------------------------------------------------ #
    # Lookup                                                                #
    # ------------------------------------------------------------------ #

    @classmethod
    def get_class(cls, name: str) -> Type[BaseCollector]:
        """Retrieve the registered collector class by name."""
        if name not in cls._registry:
            cls._load_all()
        if name not in cls._registry:
            raise KeyError(f"Collector '{name}' is not registered.")
        return cls._registry[name]

    @classmethod
    def _load_all(cls) -> None:
        """
        Import all built-in collector modules so their ``@register``
        decorators fire.  Only fills *missing* entries – never overwrites
        a name that is already present in the registry.

        Because Python caches module imports, this is idempotent: re-importing
        an already-imported module is a no-op (the module body, including
        the decorator call, does not execute again).  The guard inside
        :meth:`register` therefore means a second call to ``_load_all`` after
        the modules are loaded is harmless even if the modules attempted to
        re-register their names.
        """
        # Each import triggers the module-level @CollectorRegistry.register(...)
        # decorator on the first load.  On subsequent loads the import is a
        # no-op so the guard in register() is never hit again.
        from app.collectors.youtube import YouTubeCollector      # noqa: F401
        from app.collectors.community import CommunityCollector  # noqa: F401
        from app.collectors.hype import HypeCollector            # noqa: F401
        from app.collectors.social import SocialCollector        # noqa: F401

    # ------------------------------------------------------------------ #
    # Configuration-aware helpers                                           #
    # ------------------------------------------------------------------ #

    @classmethod
    def active_collector_names(cls, config_path: str | None = None) -> list[str]:
        """
        Return the registry keys of every collector whose YAML stanza has
        ``enabled: true`` (or whose stanza is absent, which defaults to
        enabled for backward compatibility).

        This is the single place orchestration code should query to decide
        which collectors to schedule – changing ``enabled: false`` in
        ``conf/collectors.yaml`` is the only change needed to stop a
        collector from running.
        """
        from app.core.config_loader import active_collector_names
        return active_collector_names(config_path)

    @classmethod
    def is_enabled(cls, name: str, config_path: str | None = None) -> bool:
        """
        Return ``True`` when the YAML stanza for *name* has ``enabled: true``
        (or is absent, which defaults to ``True``).
        """
        from app.core.config_loader import get_collector_config
        return get_collector_config(name, config_path).enabled

    @classmethod
    def rate_limit_for(cls, name: str, config_path: str | None = None) -> int:
        """
        Return the ``rate_limit_per_minute`` declared for *name* in the YAML.
        Falls back to 60 when the stanza is absent.
        """
        from app.core.config_loader import get_collector_config
        return get_collector_config(name, config_path).rate_limit_per_minute

    @classmethod
    def rate_limit_config_for(
        cls, name: str, config_path: str | None = None
    ) -> dict[str, Any]:
        """
        Return a ``rate_limit_config`` dict (``{"requests_per_minute": N}``)
        suitable for storing in a ``DataSource`` row.  This lets
        orchestration code replace the previous hardcoded dicts with a
        single call that always reflects the current YAML value.
        """
        from app.core.config_loader import get_collector_config
        return get_collector_config(name, config_path).rate_limit_config

    # ------------------------------------------------------------------ #
    # Instantiation                                                         #
    # ------------------------------------------------------------------ #

    @classmethod
    def create(cls, name: str, **kwargs: Any) -> BaseCollector:
        """Create and return an instance of a registered collector."""
        collector_cls = cls.get_class(name)
        return collector_cls(**kwargs)
