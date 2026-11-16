"""add features maintenance absences sweep and telematics

Revision ID: b7e12948a31c
Revises: a5e0254b95b4
Create Date: 2026-11-16 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e12948a31c'
down_revision: Union[str, None] = 'a5e0254b95b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update studentstatus enum safely in Postgres
    op.execute("ALTER TYPE studentstatus ADD VALUE IF NOT EXISTS 'ABSENT'")
    op.execute("ALTER TYPE studentstatus ADD VALUE IF NOT EXISTS 'SKIPPED'")

    # 2. Add columns to trips for end-of-trip sweep
    op.add_column('trips', sa.Column('sweep_verified', sa.Boolean(), server_default='false', nullable=True))
    op.add_column('trips', sa.Column('sweep_verified_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('trips', sa.Column('sweep_notes', sa.Text(), nullable=True))

    # 3. Add fleet telematics and maintenance columns to buses
    op.add_column('buses', sa.Column('current_odometer', sa.Float(), server_default='0.0', nullable=True))
    op.add_column('buses', sa.Column('insurance_expiry', sa.DateTime(timezone=True), nullable=True))
    op.add_column('buses', sa.Column('fitness_certificate_expiry', sa.DateTime(timezone=True), nullable=True))

    # 4. Add guardian alert customization columns to guardian_students
    op.add_column('guardian_students', sa.Column('alert_radius_meters', sa.Float(), server_default='500.0', nullable=True))
    op.add_column('guardian_students', sa.Column('notify_on_approaching', sa.Boolean(), server_default='true', nullable=True))

    # 5. Add coordinates to incidents for emergency SOS tracking
    op.add_column('incidents', sa.Column('latitude', sa.Float(), nullable=True))
    op.add_column('incidents', sa.Column('longitude', sa.Float(), nullable=True))

    # 6. Create bus_maintenances table
    op.create_table(
        'bus_maintenances',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('bus_id', sa.Integer(), sa.ForeignKey('buses.id'), nullable=False),
        sa.Column('school_id', sa.Integer(), sa.ForeignKey('schools.id'), nullable=False),
        sa.Column('service_type', sa.String(), nullable=False),
        sa.Column('status', sa.String(), server_default='COMPLETED', nullable=True),
        sa.Column('cost', sa.Float(), nullable=True),
        sa.Column('odometer_reading', sa.Float(), nullable=True),
        sa.Column('performed_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('next_service_due_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_service_due_odometer', sa.Float(), nullable=True),
        sa.Column('performed_by', sa.String(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now())
    )

    # 7. Create student_absences table
    op.create_table(
        'student_absences',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('student_id', sa.Integer(), sa.ForeignKey('students.id'), nullable=False),
        sa.Column('school_id', sa.Integer(), sa.ForeignKey('schools.id'), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('trip_type', sa.String(), server_default='ALL_DAY', nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('reported_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now())
    )


def downgrade() -> None:
    op.drop_table('student_absences')
    op.drop_table('bus_maintenances')
    op.drop_column('incidents', 'longitude')
    op.drop_column('incidents', 'latitude')
    op.drop_column('guardian_students', 'notify_on_approaching')
    op.drop_column('guardian_students', 'alert_radius_meters')
    op.drop_column('buses', 'fitness_certificate_expiry')
    op.drop_column('buses', 'insurance_expiry')
    op.drop_column('buses', 'current_odometer')
    op.drop_column('trips', 'sweep_notes')
    op.drop_column('trips', 'sweep_verified_at')
    op.drop_column('trips', 'sweep_verified')

