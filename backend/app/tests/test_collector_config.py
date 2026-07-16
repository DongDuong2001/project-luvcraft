"""
Tests for the external-configuration → registry wiring (capstone requirement).

Covers:
  * Disabled collectors are excluded from active_collector_names() and
    CollectorRegistry.active_collector_names()
  * Enabled collectors are included
  * rate_limit_per_minute is read from YAML and surfaced through the registry
  * CollectorRegistry.rate_limit_config_for() returns the right dict shape
  * CollectorRegistry.is_enabled() reflects the YAML flag
  * youtube_collector is present in collectors.yaml
  * Validation / fallback behaviour when stanzas are missing or malformed
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from app.collectors.registry import CollectorRegistry
from app.core.config_loader import (
    CollectorConfig,
    active_collector_names,
    get_collector_config,
    load_collectors_config,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _yaml_file(tmp_path: Path, content: str) -> Path:
    """Write *content* to a temp YAML file and return its path."""
    p = tmp_path / "collectors.yaml"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# collectors.yaml schema tests (real file)
# ---------------------------------------------------------------------------

class TestCollectorsYamlSchema:
    """Validate the committed collectors.yaml contains all required stanzas."""

    def test_youtube_collector_present(self):
        raw = load_collectors_config()
        assert "youtube_collector" in raw, (
            "youtube_collector stanza is missing from conf/collectors.yaml"
        )

    def test_all_four_collectors_present(self):
        raw = load_collectors_config()
        for key in ("youtube_collector", "community_collector", "hype_collector", "social_collector"):
            assert key in raw, f"'{key}' stanza missing from collectors.yaml"

    def test_each_stanza_has_required_fields(self):
        raw = load_collectors_config()
        for key, stanza in raw.items():
            assert "enabled" in stanza, f"'{key}' missing 'enabled'"
            assert "rate_limit_per_minute" in stanza, f"'{key}' missing 'rate_limit_per_minute'"
            assert isinstance(stanza["rate_limit_per_minute"], int), (
                f"'{key}'.rate_limit_per_minute must be an int"
            )

    def test_youtube_stanza_defaults_to_enabled(self):
        cfg = get_collector_config("youtube")
        assert cfg.enabled is True

    def test_youtube_rate_limit_is_positive(self):
        cfg = get_collector_config("youtube")
        assert cfg.rate_limit_per_minute > 0


# ---------------------------------------------------------------------------
# Disabled-collector tests
# ---------------------------------------------------------------------------

class TestDisabledCollectors:
    """
    Collectors with ``enabled: false`` must be excluded from
    active_collector_names() and CollectorRegistry.active_collector_names().
    """

    def test_disabled_collector_excluded_from_active_names(self, tmp_path):
        yaml_path = _yaml_file(
            tmp_path,
            """
            youtube_collector:
              name: YouTube
              endpoints: []
              enabled: false
              rate_limit_per_minute: 100
            community_collector:
              name: Community
              endpoints: []
              enabled: true
              rate_limit_per_minute: 60
            hype_collector:
              name: Hype
              endpoints: []
              enabled: false
              rate_limit_per_minute: 30
            social_collector:
              name: Social
              endpoints: []
              enabled: true
              rate_limit_per_minute: 100
            """,
        )
        names = active_collector_names(yaml_path)
        assert "youtube" not in names, "disabled youtube should not appear in active list"
        assert "hype" not in names, "disabled hype should not appear in active list"
        assert "community" in names
        assert "social" in names

    def test_disabled_collector_excluded_via_registry(self, tmp_path):
        yaml_path = _yaml_file(
            tmp_path,
            """
            youtube_collector:
              name: YouTube
              endpoints: []
              enabled: false
              rate_limit_per_minute: 100
            community_collector:
              name: Community
              endpoints: []
              enabled: true
              rate_limit_per_minute: 60
            hype_collector:
              name: Hype
              endpoints: []
              enabled: true
              rate_limit_per_minute: 30
            social_collector:
              name: Social
              endpoints: []
              enabled: true
              rate_limit_per_minute: 100
            """,
        )
        names = CollectorRegistry.active_collector_names(str(yaml_path))
        assert "youtube" not in names
        assert set(names) == {"community", "hype", "social"}

    def test_all_disabled_returns_empty_list(self, tmp_path):
        yaml_path = _yaml_file(
            tmp_path,
            """
            youtube_collector:
              name: YouTube
              endpoints: []
              enabled: false
              rate_limit_per_minute: 100
            community_collector:
              name: Community
              endpoints: []
              enabled: false
              rate_limit_per_minute: 60
            hype_collector:
              name: Hype
              endpoints: []
              enabled: false
              rate_limit_per_minute: 30
            social_collector:
              name: Social
              endpoints: []
              enabled: false
              rate_limit_per_minute: 100
            """,
        )
        assert active_collector_names(yaml_path) == []

    def test_all_enabled_returns_all_four(self, tmp_path):
        yaml_path = _yaml_file(
            tmp_path,
            """
            youtube_collector:
              name: YouTube
              endpoints: []
              enabled: true
              rate_limit_per_minute: 100
            community_collector:
              name: Community
              endpoints: []
              enabled: true
              rate_limit_per_minute: 60
            hype_collector:
              name: Hype
              endpoints: []
              enabled: true
              rate_limit_per_minute: 30
            social_collector:
              name: Social
              endpoints: []
              enabled: true
              rate_limit_per_minute: 100
            """,
        )
        assert set(active_collector_names(yaml_path)) == {"youtube", "community", "hype", "social"}

    def test_is_enabled_reflects_yaml_flag(self, tmp_path):
        yaml_path = _yaml_file(
            tmp_path,
            """
            youtube_collector:
              name: YouTube
              endpoints: []
              enabled: false
              rate_limit_per_minute: 100
            community_collector:
              name: Community
              endpoints: []
              enabled: true
              rate_limit_per_minute: 60
            hype_collector:
              name: Hype
              endpoints: []
              enabled: true
              rate_limit_per_minute: 30
            social_collector:
              name: Social
              endpoints: []
              enabled: true
              rate_limit_per_minute: 100
            """,
        )
        assert CollectorRegistry.is_enabled("youtube", str(yaml_path)) is False
        assert CollectorRegistry.is_enabled("community", str(yaml_path)) is True


# ---------------------------------------------------------------------------
# Rate-limit tests
# ---------------------------------------------------------------------------

class TestRateLimitSettings:
    """
    rate_limit_per_minute from YAML must surface through the registry helpers
    with no transformation other than wrapping in the standard dict shape.
    """

    def test_rate_limit_for_reads_yaml_value(self, tmp_path):
        yaml_path = _yaml_file(
            tmp_path,
            """
            youtube_collector:
              name: YouTube
              endpoints: []
              enabled: true
              rate_limit_per_minute: 42
            community_collector:
              name: Community
              endpoints: []
              enabled: true
              rate_limit_per_minute: 7
            hype_collector:
              name: Hype
              endpoints: []
              enabled: true
              rate_limit_per_minute: 30
            social_collector:
              name: Social
              endpoints: []
              enabled: true
              rate_limit_per_minute: 100
            """,
        )
        assert CollectorRegistry.rate_limit_for("youtube", str(yaml_path)) == 42
        assert CollectorRegistry.rate_limit_for("community", str(yaml_path)) == 7

    def test_rate_limit_config_for_returns_dict_with_requests_per_minute(self, tmp_path):
        yaml_path = _yaml_file(
            tmp_path,
            """
            youtube_collector:
              name: YouTube
              endpoints: []
              enabled: true
              rate_limit_per_minute: 99
            community_collector:
              name: Community
              endpoints: []
              enabled: true
              rate_limit_per_minute: 60
            hype_collector:
              name: Hype
              endpoints: []
              enabled: true
              rate_limit_per_minute: 30
            social_collector:
              name: Social
              endpoints: []
              enabled: true
              rate_limit_per_minute: 100
            """,
        )
        cfg = CollectorRegistry.rate_limit_config_for("youtube", str(yaml_path))
        assert isinstance(cfg, dict)
        assert cfg.get("requests_per_minute") == 99

    def test_rate_limit_config_for_community(self, tmp_path):
        yaml_path = _yaml_file(
            tmp_path,
            """
            youtube_collector:
              name: YouTube
              endpoints: []
              enabled: true
              rate_limit_per_minute: 100
            community_collector:
              name: Community
              endpoints: []
              enabled: true
              rate_limit_per_minute: 15
            hype_collector:
              name: Hype
              endpoints: []
              enabled: true
              rate_limit_per_minute: 30
            social_collector:
              name: Social
              endpoints: []
              enabled: true
              rate_limit_per_minute: 100
            """,
        )
        cfg = CollectorRegistry.rate_limit_config_for("community", str(yaml_path))
        assert cfg.get("requests_per_minute") == 15

    def test_rate_limit_defaults_to_60_when_stanza_missing(self, tmp_path):
        """When a stanza is absent the loader falls back to 60 rpm."""
        yaml_path = _yaml_file(tmp_path, "# empty\n")
        assert CollectorRegistry.rate_limit_for("youtube", str(yaml_path)) == 60

    def test_real_yaml_rate_limits_are_positive_integers(self):
        """Integration: committed YAML values are usable positive ints."""
        for key in ("youtube", "community", "hype", "social"):
            rate = CollectorRegistry.rate_limit_for(key)
            assert isinstance(rate, int) and rate > 0, (
                f"rate_limit_for('{key}') should be a positive int, got {rate!r}"
            )


# ---------------------------------------------------------------------------
# CollectorConfig dataclass
# ---------------------------------------------------------------------------

class TestCollectorConfig:
    def test_rate_limit_config_property(self):
        cfg = CollectorConfig(
            registry_key="test",
            name="Test",
            endpoints=["https://example.com"],
            enabled=True,
            rate_limit_per_minute=55,
        )
        assert cfg.rate_limit_config == {"requests_per_minute": 55}

    def test_disabled_config(self):
        cfg = CollectorConfig(
            registry_key="test",
            name="Test",
            endpoints=[],
            enabled=False,
            rate_limit_per_minute=10,
        )
        assert cfg.enabled is False
        assert cfg.rate_limit_config == {"requests_per_minute": 10}


# ---------------------------------------------------------------------------
# Fallback / malformed YAML
# ---------------------------------------------------------------------------

class TestFallbackBehaviour:
    def test_missing_yaml_file_returns_enabled_defaults(self):
        cfg = get_collector_config("youtube", "/nonexistent/path/collectors.yaml")
        assert cfg.enabled is True
        assert cfg.rate_limit_per_minute == 60

    def test_invalid_rate_limit_falls_back_to_60(self, tmp_path):
        yaml_path = _yaml_file(
            tmp_path,
            """
            youtube_collector:
              name: YouTube
              endpoints: []
              enabled: true
              rate_limit_per_minute: "not_a_number"
            community_collector:
              name: Community
              endpoints: []
              enabled: true
              rate_limit_per_minute: 60
            hype_collector:
              name: Hype
              endpoints: []
              enabled: true
              rate_limit_per_minute: 30
            social_collector:
              name: Social
              endpoints: []
              enabled: true
              rate_limit_per_minute: 100
            """,
        )
        cfg = get_collector_config("youtube", yaml_path)
        assert cfg.rate_limit_per_minute == 60

    def test_missing_stanza_defaults_to_enabled_true(self, tmp_path):
        yaml_path = _yaml_file(
            tmp_path,
            """
            community_collector:
              name: Community
              endpoints: []
              enabled: true
              rate_limit_per_minute: 60
            hype_collector:
              name: Hype
              endpoints: []
              enabled: true
              rate_limit_per_minute: 30
            social_collector:
              name: Social
              endpoints: []
              enabled: true
              rate_limit_per_minute: 100
            """,
        )
        cfg = get_collector_config("youtube", yaml_path)
        # No stanza → defaults to enabled so registry stays backward-compatible
        assert cfg.enabled is True
        assert cfg.rate_limit_per_minute == 60
