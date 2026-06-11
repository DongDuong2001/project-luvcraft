import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.logging import setup_logging

logger = logging.getLogger(__name__)


def upgrade_database() -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    script_location = backend_dir / "alembic"
    config = Config()
    config.set_main_option("script_location", str(script_location))
    config.set_main_option("prepend_sys_path", str(backend_dir))

    logger.info("Starting database migrations from %s", script_location)
    command.upgrade(config, "head")
    logger.info("Database migrations completed successfully")


if __name__ == "__main__":
    setup_logging()
    upgrade_database()
