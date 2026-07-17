from __future__ import annotations

import importlib
from pathlib import Path

import pytest
import yaml

from app.collectors import CollectorRegistry
from app.collectors.collector_base import (
    BaseCollector,
    CollectorDisabledError,
)
from app.collectors.community import CommunityCollector
from app.collectors.hype import HypeCollector
from app.collectors.rate_limit import PostgresTokenBucketRateLimiter
from app.collectors.youtube import YouTubeCollector
from app.core.config_loader import CollectorConfigurationError


@pytest.fixture(autouse=True)
def restore_registry():
    original = dict(CollectorRegistry._registry)
    try:
        yield
    finally:
        CollectorRegistry._registry = original


class ConcreteCollector(BaseCollector):
    def _collect(self, **kwargs):
        return []


def write_youtube_config(tmp_path: Path, *, endpoint="https://example.com/youtube") -> Path:
    entry = {
        "collector_class": "app.collectors.youtube:YouTubeCollector",
        "task_name": "luvcraft.collect_youtube",
        "name": "YouTube",
        "endpoints": [endpoint],
        "enabled": True,
        "rate_limit_per_minute": 120,
        "source": {
            "name": "YouTube",
            "platform": "youtube",
            "category": "video",
            "access_method": "api",
        },
    }
    path = tmp_path / "collectors.yaml"
    path.write_text(yaml.safe_dump({"youtube": entry}), encoding="utf-8")
    return path


def test_registry_discovers_classes_from_configuration():
    CollectorRegistry._registry = {}

    assert CollectorRegistry.get_class("youtube") is YouTubeCollector
    assert CollectorRegistry.get_class("community") is CommunityCollector
    assert CollectorRegistry.get_class("hype") is HypeCollector


def test_registry_create_injects_configured_endpoint_and_rate_limit(tmp_path):
    path = write_youtube_config(tmp_path)

    class NoopLimiter:
        def acquire(self):
            pass

    collector = CollectorRegistry.create(
        "youtube",
        config_path=path,
        api_key="dummy-key",
        rate_limiter=NoopLimiter(),
    )

    assert isinstance(collector, YouTubeCollector)
    assert collector.base_url == "https://example.com/youtube"
    assert collector.config.rate_limit_per_minute == 120


def test_configured_rate_limit_is_not_bypassed_by_an_injected_client(tmp_path):
    path = write_youtube_config(tmp_path)

    collector = CollectorRegistry.create(
        "youtube",
        config_path=path,
        api_key="dummy-key",
        client=object(),
    )

    assert isinstance(collector.rate_limiter, PostgresTokenBucketRateLimiter)
    assert collector.rate_limiter.requests_per_minute == 120


def test_disabled_configured_collector_cannot_be_created():
    with pytest.raises(CollectorDisabledError):
        CollectorRegistry.create("social")


def test_programmatic_registration_remains_available_for_isolated_collectors():
    CollectorRegistry.register_class("test_collector", ConcreteCollector)

    assert isinstance(CollectorRegistry.create("test_collector"), ConcreteCollector)


def test_programmatic_registration_does_not_hide_broken_configuration(tmp_path):
    CollectorRegistry.register_class("test_collector", ConcreteCollector)

    with pytest.raises(CollectorConfigurationError, match="Unable to load"):
        CollectorRegistry.create(
            "test_collector",
            config_path=tmp_path / "missing.yaml",
        )


def test_non_collector_and_abstract_collector_are_rejected():
    class NotACollector:
        pass

    class AbstractCollector(BaseCollector):
        pass

    with pytest.raises(TypeError, match="concrete subclass"):
        CollectorRegistry.register_class("invalid_class", NotACollector)
    with pytest.raises(TypeError, match="concrete subclass"):
        CollectorRegistry.register_class("abstract_collector", AbstractCollector)


def test_duplicate_registration_rejects_same_class_and_conflicts():
    class OtherCollector(BaseCollector):
        def _collect(self, **kwargs):
            return []

    CollectorRegistry.register_class("test_collector", ConcreteCollector)

    with pytest.raises(ValueError, match="already registered"):
        CollectorRegistry.register_class("test_collector", ConcreteCollector)

    with pytest.raises(ValueError, match="already registered"):
        CollectorRegistry.register_class("test_collector", OtherCollector)


def test_register_decorator_rejects_duplicate_name():
    CollectorRegistry.register("decorated_collector")(ConcreteCollector)

    with pytest.raises(ValueError, match="already registered"):
        CollectorRegistry.register("decorated_collector")(ConcreteCollector)


def test_force_registration_replaces_only_with_a_valid_collector():
    class ReplacementCollector(BaseCollector):
        def _collect(self, **kwargs):
            return []

    CollectorRegistry.register_class("test_collector", ConcreteCollector)
    CollectorRegistry.force_register_class("test_collector", ReplacementCollector)

    assert CollectorRegistry.get_class("test_collector") is ReplacementCollector
    with pytest.raises(TypeError, match="concrete subclass"):
        CollectorRegistry.force_register_class("test_collector", object)  # type: ignore[arg-type]


def test_force_override_before_configured_import_is_preserved():
    class StubYouTube(BaseCollector):
        registry_key = "youtube"

        def _collect(self, **kwargs):
            return []

    CollectorRegistry._registry = {}
    CollectorRegistry.force_register_class("youtube", StubYouTube)

    assert CollectorRegistry.get_class("community") is CommunityCollector
    assert CollectorRegistry.get_class("youtube") is StubYouTube


def test_force_override_skips_import_of_replaced_configured_module(monkeypatch):
    class StubYouTube(BaseCollector):
        registry_key = "youtube"

        def _collect(self, **kwargs):
            return []

    real_import = importlib.import_module

    def guarded_import(module_name):
        if module_name == "app.collectors.youtube":
            raise AssertionError("replaced collector module should not be imported")
        return real_import(module_name)

    CollectorRegistry._registry = {}
    CollectorRegistry.force_register_class("youtube", StubYouTube)
    monkeypatch.setattr(
        "app.collectors.registry.importlib.import_module",
        guarded_import,
    )

    configs = CollectorRegistry.active_collector_configs()

    assert [config.registry_key for config in configs] == ["youtube", "community", "hype"]
    assert CollectorRegistry.get_class("youtube") is StubYouTube


def test_registry_name_and_declared_class_key_must_match():
    class MisnamedCollector(BaseCollector):
        registry_key = "actual_name"

        def _collect(self, **kwargs):
            return []

    with pytest.raises(TypeError, match="declares registry_key"):
        CollectorRegistry.register_class("different_name", MisnamedCollector)


def test_unknown_collector_raises_key_error():
    with pytest.raises(KeyError):
        CollectorRegistry.get_class("unknown_collector")


def test_abstract_class_in_configuration_is_reported_as_configuration_error(
    tmp_path,
):
    path = write_youtube_config(tmp_path)
    configured = yaml.safe_load(path.read_text(encoding="utf-8"))
    configured["youtube"]["collector_class"] = (
        "app.collectors.collector_base:BaseCollector"
    )
    path.write_text(yaml.safe_dump(configured), encoding="utf-8")
    CollectorRegistry._registry = {}

    with pytest.raises(CollectorConfigurationError, match="Invalid collector class"):
        CollectorRegistry.active_collector_configs(path)


def test_configured_collector_must_accept_injected_configuration(
    monkeypatch,
    tmp_path,
):
    class IncompatibleCollector(BaseCollector):
        registry_key = "youtube"

        def __init__(self, required_token):
            self.required_token = required_token

        def _collect(self, **kwargs):
            return []

    path = write_youtube_config(tmp_path)
    module = type("ConfiguredModule", (), {"YouTubeCollector": IncompatibleCollector})
    monkeypatch.setattr(
        "app.collectors.registry.importlib.import_module",
        lambda _name: module,
    )
    CollectorRegistry._registry = {}

    with pytest.raises(CollectorConfigurationError, match="must accept a 'config'"):
        CollectorRegistry.active_collector_configs(path)
