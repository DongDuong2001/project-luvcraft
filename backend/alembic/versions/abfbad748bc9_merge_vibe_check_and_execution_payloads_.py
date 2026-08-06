"""merge vibe check and execution payloads heads

Revision ID: abfbad748bc9
Revises: b1f2c3d4e5f6, c91e4a7b2d10
Create Date: 2026-08-06 12:53:24.739857

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'abfbad748bc9'
down_revision: Union[str, Sequence[str], None] = ('b1f2c3d4e5f6', 'c91e4a7b2d10')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
