from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from app.core.config_loader import (
    CollectorConfigurationError,
    active_collector_names,
    get_collector_config,
    load_collectors_config,
    load_collector_configs,
)
from app.core.collector_runtime import validate_collector_runtime


def collector_entry(
    *,
    class_name: str = "YouTubeCollector",
    enabled: bool = True,
    task_name: str | None = "luvcraft.collect_test",
    endpoint: str = "https://example.com/api",
    rate: int = 60,
) -> dict:
    return {
        "collector_class": f"app.collectors.youtube:{class_name}",
        "task_name": task_name,
        "name": "Test Collector",
        "endpoints": [endpoint],
        "enabled": enabled,
        "rate_limit_per_minute": rate,
        "source": {
            "name": "Test API",
            "platform": "test",
            "category": "community",
            "access_method": "api",
        },
    }


def write_config(tmp_path: Path, entries: dict) -> Path:
    path = tmp_path / "collectors.yaml"
    path.write_text(yaml.safe_dump(entries, sort_keys=False), encoding="utf-8")
    return path


def test_committed_configuration_is_strict_and_declares_only_live_collectors_active():
    configs = load_collector_configs()

    assert set(configs) == {"youtube", "community", "rss", "hype", "social", "discord"}
    assert active_collector_names() == ["youtube", "rss", "hype", "social"]
    assert configs["youtube"].task_name == "luvcraft.collect_youtube"
    assert configs["community"].primary_endpoint == "https://api.github.com"
    assert configs["community"].enabled is False
    assert configs["discord"].primary_endpoint == "https://discord.com/api/v10"
    assert configs["discord"].enabled is False
    assert configs["rss"].task_name == "luvcraft.collect_rss"
    assert configs["rss"].primary_endpoint.startswith(
        "https://news.google.com/rss/search"
    )
    assert configs["rss"].source.platform == "rss"
    assert configs["hype"].enabled is True
    assert configs["hype"].primary_endpoint == "https://serpapi.com"
    assert configs["hype"].source.platform == "serpapi_trends"
    assert configs["social"].enabled is True
    assert configs["social"].task_name == "luvcraft.collect_social"
    assert configs["social"].source.platform == "serpapi_social"


def test_collector_names_are_discovered_from_yaml_without_a_central_map(tmp_path):
    path = write_config(
        tmp_path,
        {"new_source": collector_entry()},
    )

    configs = load_collector_configs(path)

    assert list(configs) == ["new_source"]
    assert active_collector_names(path) == ["new_source"]
    assert get_collector_config("new_source", path).registry_key == "new_source"


def test_disabled_collector_requires_no_task_and_is_not_active(tmp_path):
    path = write_config(
        tmp_path,
        {
            "enabled_source": collector_entry(),
            "disabled_source": collector_entry(enabled=False, task_name=None),
        },
    )

    assert active_collector_names(path) == ["enabled_source"]


@pytest.mark.parametrize("invalid_enabled", ["false", 0, 1, None])
def test_enabled_must_be_an_actual_boolean(tmp_path, invalid_enabled):
    entry = collector_entry()
    entry["enabled"] = invalid_enabled
    path = write_config(tmp_path, {"source": entry})

    with pytest.raises(CollectorConfigurationError, match="enabled must be a boolean"):
        load_collector_configs(path)


@pytest.mark.parametrize("invalid_rate", [True, False, 0, -1, "60", None])
def test_rate_limit_must_be_a_positive_non_boolean_integer(tmp_path, invalid_rate):
    entry = collector_entry()
    entry["rate_limit_per_minute"] = invalid_rate
    path = write_config(tmp_path, {"source": entry})

    with pytest.raises(CollectorConfigurationError, match="positive integer"):
        load_collector_configs(path)


def test_enabled_collector_requires_a_task(tmp_path):
    path = write_config(
        tmp_path,
        {"source": collector_entry(enabled=True, task_name=None)},
    )

    with pytest.raises(CollectorConfigurationError, match="task_name is required"):
        load_collector_configs(path)


@pytest.mark.parametrize(
    "endpoint",
    ["http://example.com", "example.com", "https://user:pass@example.com"],
)
def test_endpoints_must_be_credential_free_https_urls(tmp_path, endpoint):
    path = write_config(
        tmp_path,
        {"source": collector_entry(endpoint=endpoint)},
    )

    with pytest.raises(CollectorConfigurationError, match="HTTPS URL"):
        load_collector_configs(path)


def test_missing_file_fails_closed(tmp_path):
    with pytest.raises(CollectorConfigurationError, match="Unable to load"):
        load_collector_configs(tmp_path / "missing.yaml")


def test_missing_stanza_does_not_create_an_enabled_default(tmp_path):
    path = write_config(tmp_path, {"community": collector_entry()})

    with pytest.raises(CollectorConfigurationError, match="no configuration stanza"):
        get_collector_config("youtube", path)


def test_unknown_fields_are_rejected_to_catch_configuration_typos(tmp_path):
    entry = collector_entry()
    entry["enabledd"] = True
    path = write_config(tmp_path, {"source": entry})

    with pytest.raises(CollectorConfigurationError, match="unknown fields: enabledd"):
        load_collector_configs(path)


def test_non_string_field_names_are_rejected_as_configuration_errors(tmp_path):
    entry = collector_entry()
    entry[1] = "invalid"
    path = write_config(tmp_path, {"source": entry})

    with pytest.raises(CollectorConfigurationError, match="field names must be strings"):
        load_collector_configs(path)


def test_duplicate_yaml_keys_are_rejected(tmp_path):
    path = tmp_path / "collectors.yaml"
    body = yaml.safe_dump(collector_entry(), sort_keys=False)
    indented = "\n".join(f"  {line}" for line in body.splitlines())
    path.write_text(f"source:\n{indented}\nsource:\n{indented}\n", encoding="utf-8")

    with pytest.raises(CollectorConfigurationError, match="duplicate key"):
        load_collector_configs(path)


def test_environment_override_selects_configuration(monkeypatch, tmp_path):
    path = write_config(tmp_path, {"environment_source": collector_entry()})
    monkeypatch.setenv("COLLECTORS_CONFIG_PATH", str(path))

    assert active_collector_names() == ["environment_source"]


def test_rate_limit_config_has_the_database_shape(tmp_path):
    entry = deepcopy(collector_entry(rate=37))
    path = write_config(tmp_path, {"source": entry})

    config = get_collector_config("source", path)

    assert config.rate_limit_config == {"requests_per_minute": 37}


def test_runtime_fails_closed_when_every_collector_is_disabled(
    monkeypatch,
    tmp_path,
):
    configured = load_collectors_config()
    for entry in configured.values():
        entry["enabled"] = False
        entry["task_name"] = None
    path = write_config(tmp_path, configured)
    monkeypatch.setenv("COLLECTORS_CONFIG_PATH", str(path))

    with pytest.raises(CollectorConfigurationError, match="No collectors are enabled"):
        validate_collector_runtime()
