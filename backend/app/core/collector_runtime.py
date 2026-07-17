"""Startup and request-time validation for the configured collector pipeline."""

from __future__ import annotations

import inspect

from app.collectors import CollectorRegistry
from app.core.config_loader import CollectorConfig, CollectorConfigurationError
from app.core.worker import celery_app


def validate_collector_runtime() -> list[CollectorConfig]:
    """Return runnable collectors or fail before any collection is accepted."""
    configs = CollectorRegistry.active_collector_configs()
    if not configs:
        raise CollectorConfigurationError("No collectors are enabled")

    celery_app.loader.import_default_modules()
    missing_tasks = [
        config.task_name
        for config in configs
        if config.task_name not in celery_app.tasks
    ]
    if missing_tasks:
        raise CollectorConfigurationError(
            "Enabled collectors reference unregistered Celery tasks: "
            + ", ".join(str(task_name) for task_name in missing_tasks)
        )
    incompatible_tasks: list[str] = []
    for config in configs:
        task = celery_app.tasks[config.task_name]
        try:
            inspect.signature(task.run).bind("run-id", "module-run-id")
        except (TypeError, ValueError):
            incompatible_tasks.append(str(config.task_name))
    if incompatible_tasks:
        raise CollectorConfigurationError(
            "Collector tasks must accept (run_id, module_run_id): "
            + ", ".join(incompatible_tasks)
        )
    return configs
