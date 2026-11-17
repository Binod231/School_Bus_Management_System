"""add fcm_token to users

Revision ID: e4f5a6b7c8d9
Revises: d8e7f6a5b4c3
Create Date: 2026-11-17 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4f5a6b7c8d9'
down_revision: Union[str, None] = 'd8e7f6a5b4c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('fcm_token', sa.String(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('users', 'fcm_token')
