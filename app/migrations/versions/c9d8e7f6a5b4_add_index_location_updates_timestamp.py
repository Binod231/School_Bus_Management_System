"""add index location_updates timestamp

Revision ID: c9d8e7f6a5b4
Revises: b7e12948a31c
Create Date: 2026-11-16 16:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9d8e7f6a5b4'
down_revision: Union[str, None] = 'b7e12948a31c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'ix_location_updates_timestamp',
        'location_updates',
        ['timestamp'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_location_updates_timestamp', table_name='location_updates')
