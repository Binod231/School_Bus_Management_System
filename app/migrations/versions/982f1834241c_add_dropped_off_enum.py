"""add dropped_off status

Revision ID: 982f1834241c
Revises: faba9c812b44
Create Date: 2026-02-02 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '982f1834241c'
down_revision = 'faba9c812b44'
branch_labels = None
depends_on = None


def upgrade():
    # Use raw SQL to update the enum because Postgres enums are database-level types
    op.execute("ALTER TYPE studentstatus ADD VALUE 'DROPPED_OFF' AFTER 'ON_BUS'")


def downgrade():
    # Decrementing Enums in Postgres is not a simple command and usually requires recreating the type
    pass
