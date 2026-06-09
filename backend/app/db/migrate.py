from pathlib import Path

from alembic import command
from alembic.config import Config


def upgrade_database() -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    config = Config()
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    config.set_main_option("prepend_sys_path", str(backend_dir))
    command.upgrade(config, "head")


if __name__ == "__main__":
    upgrade_database()
