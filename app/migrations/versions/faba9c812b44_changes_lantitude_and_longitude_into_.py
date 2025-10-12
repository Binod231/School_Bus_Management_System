"""changes latitude and longitude into float

Revision ID: faba9c812b44
Revises: 2a8281afd8d0
Create Date: 2025-09-15 09:36:47.178596

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'faba9c812b44'
down_revision: Union[str, None] = '2a8281afd8d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### safe conversion to DOUBLE PRECISION ###
    op.execute(
        "ALTER TABLE location_updates "
        "ALTER COLUMN latitude TYPE DOUBLE PRECISION USING NULLIF(latitude, '')::double precision;"
    )
    op.execute(
        "ALTER TABLE location_updates "
        "ALTER COLUMN longitude TYPE DOUBLE PRECISION USING NULLIF(longitude, '')::double precision;"
    )
    op.execute(
        "ALTER TABLE location_updates "
        "ALTER COLUMN speed TYPE DOUBLE PRECISION USING NULLIF(speed, '')::double precision;"
    )
    op.execute(
        "ALTER TABLE location_updates "
        "ALTER COLUMN heading TYPE DOUBLE PRECISION USING NULLIF(heading, '')::double precision;"
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### revert back to VARCHAR ###
    op.alter_column('location_updates', 'heading',
               existing_type=sa.Float(),
               type_=sa.VARCHAR(),
               existing_nullable=True)
    op.alter_column('location_updates', 'speed',
               existing_type=sa.Float(),
               type_=sa.VARCHAR(),
               existing_nullable=True)
    op.alter_column('location_updates', 'longitude',
               existing_type=sa.Float(),
               type_=sa.VARCHAR(),
               existing_nullable=False)
    op.alter_column('location_updates', 'latitude',
               existing_type=sa.Float(),
               type_=sa.VARCHAR(),
               existing_nullable=False)
    # ### end Alembic commands ###
