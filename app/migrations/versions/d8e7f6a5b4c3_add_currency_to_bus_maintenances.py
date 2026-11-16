"""add currency to bus_maintenances

Revision ID: d8e7f6a5b4c3
Revises: c9d8e7f6a5b4
Create Date: 2026-11-16 16:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8e7f6a5b4c3'
down_revision: Union[str, None] = 'c9d8e7f6a5b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'bus_maintenances',
        sa.Column('currency', sa.String(), server_default='NPR', nullable=False)
    )


def downgrade() -> None:
    op.drop_column('bus_maintenances', 'currency')
