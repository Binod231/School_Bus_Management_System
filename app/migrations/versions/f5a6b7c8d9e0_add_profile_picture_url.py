"""add profile_picture_url to users and students

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-11-18 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f5a6b7c8d9e0'
down_revision: Union[str, None] = 'e4f5a6b7c8d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('profile_picture_url', sa.String(), nullable=True)
    )
    op.add_column(
        'students',
        sa.Column('profile_picture_url', sa.String(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('students', 'profile_picture_url')
    op.drop_column('users', 'profile_picture_url')
