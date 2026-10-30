"""motos (vehicles.kind, checklists.vehicle_kind) y carnés (licencias + curso de lecciones)

Revision ID: c3a9d5e7f102
Revises: fb737731e730
Create Date: 2026-10-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3a9d5e7f102'
down_revision: Union[str, None] = 'fb737731e730'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Plantillas de revisión que ya existían y solo tienen sentido en un coche (cinturones,
# freno de mano, baliza V16…): a partir de ahora no se ofrecen a las motos.
CAR_TEMPLATES = ("Revisión rápida mensual", "Antes de un viaje largo", "Antes de la ITV")


def upgrade() -> None:
    op.add_column('vehicles', sa.Column('kind', sa.String(length=12), nullable=False, server_default='car'))
    op.add_column('checklists', sa.Column('vehicle_kind', sa.String(length=12), nullable=True))
    checklists = sa.table('checklists', sa.column('vehicle_id', sa.Integer), sa.column('name', sa.String), sa.column('vehicle_kind', sa.String))
    op.execute(
        checklists.update()
        .where(checklists.c.vehicle_id.is_(None), checklists.c.name.in_(CAR_TEMPLATES))
        .values(vehicle_kind='car')
    )

    op.create_table(
        'licenses',
        sa.Column('code', sa.String(length=8), primary_key=True),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('steps', sa.JSON(), nullable=False),
        sa.Column('next_exam_on', sa.Date(), nullable=True),
        sa.Column('obtained_on', sa.Date(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=False),
    )
    op.create_table(
        'learn_courses',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('slug', sa.String(length=64), nullable=False, unique=True),
        sa.Column('license_code', sa.String(length=8), nullable=False, unique=True),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('source_note', sa.Text(), nullable=False),
    )
    op.create_table(
        'learn_units',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('course_id', sa.Integer(), sa.ForeignKey('learn_courses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('ref', sa.String(length=64), nullable=False),
        sa.Column('source', sa.String(length=64), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('chest_claimed', sa.Boolean(), nullable=False),
        sa.Column('extra', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index('ix_learn_units_course_id', 'learn_units', ['course_id'])
    op.create_table(
        'learn_lessons',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('unit_id', sa.Integer(), sa.ForeignKey('learn_units.id', ondelete='CASCADE'), nullable=False),
        sa.Column('ref', sa.String(length=64), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('best_ratio', sa.Float(), nullable=True),
        sa.Column('runs', sa.Integer(), nullable=False),
    )
    op.create_index('ix_learn_lessons_unit_id', 'learn_lessons', ['unit_id'])
    op.create_table(
        'learn_steps',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('lesson_id', sa.Integer(), sa.ForeignKey('learn_lessons.id', ondelete='CASCADE'), nullable=False),
        sa.Column('ref', sa.String(length=64), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=12), nullable=False),
        sa.Column('prompt', sa.Text(), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('explanation', sa.Text(), nullable=False),
        sa.Column('source', sa.String(length=300), nullable=False),
        sa.Column('hints', sa.JSON(), nullable=False),
        sa.Column('concepts', sa.JSON(), nullable=False),
        sa.Column('box', sa.Integer(), nullable=False),
        sa.Column('due_on', sa.Date(), nullable=True),
        sa.Column('correct', sa.Integer(), nullable=False),
        sa.Column('wrong', sa.Integer(), nullable=False),
        sa.Column('confident_wrong', sa.Integer(), nullable=False),
    )
    op.create_index('ix_learn_steps_lesson_id', 'learn_steps', ['lesson_id'])
    op.create_table(
        'learn_days',
        sa.Column('date', sa.Date(), primary_key=True),
        sa.Column('xp', sa.Integer(), nullable=False),
        sa.Column('correct', sa.Integer(), nullable=False),
        sa.Column('best_combo', sa.Integer(), nullable=False),
        sa.Column('lessons', sa.Integer(), nullable=False),
        sa.Column('perfect_lessons', sa.Integer(), nullable=False),
        sa.Column('exams', sa.Integer(), nullable=False),
        sa.Column('claimed', sa.JSON(), nullable=False),
        sa.Column('frozen', sa.Boolean(), nullable=False),
    )
    op.create_table(
        'learn_profile',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('gems', sa.Integer(), nullable=False),
        sa.Column('streak_freezes', sa.Integer(), nullable=False),
        sa.Column('last_settled', sa.Date(), nullable=True),
    )


def downgrade() -> None:
    for table in ('learn_profile', 'learn_days', 'learn_steps', 'learn_lessons', 'learn_units', 'learn_courses', 'licenses'):
        op.drop_table(table)
    with op.batch_alter_table('checklists') as batch:
        batch.drop_column('vehicle_kind')
    with op.batch_alter_table('vehicles') as batch:
        batch.drop_column('kind')
