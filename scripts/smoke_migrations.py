"""Smoke test Alembic migrations against a disposable database.

This script intentionally requires MIGRATION_TEST_DATABASE_URL so it cannot
accidentally downgrade a developer, staging, or Supabase database.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]


def require_test_database_url() -> str:
    database_url = os.environ.get("MIGRATION_TEST_DATABASE_URL")
    if not database_url:
        raise SystemExit(
            "MIGRATION_TEST_DATABASE_URL is required. "
            "Point it at a disposable local/CI database."
        )

    parsed = urlparse(database_url)
    database_name = parsed.path.lstrip("/")
    if not database_name or "test" not in database_name.lower():
        raise SystemExit(
            "Refusing to run migration smoke test: database name must contain 'test'."
        )

    return database_url


def run_alembic(*args: str, database_url: str) -> None:
    env = os.environ.copy()
    env["MIGRATION_DATABASE_URL"] = database_url
    env["PYTHONPATH"] = str(REPO_ROOT / "backend")

    command = [sys.executable, "-m", "alembic", *args]
    subprocess.run(command, cwd=REPO_ROOT, env=env, check=True)


def main() -> None:
    database_url = require_test_database_url()

    run_alembic("downgrade", "base", database_url=database_url)
    run_alembic("upgrade", "head", database_url=database_url)
    run_alembic("downgrade", "base", database_url=database_url)


if __name__ == "__main__":
    main()
