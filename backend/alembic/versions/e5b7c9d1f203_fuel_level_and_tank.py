"""nivel del depósito (%), capacidad del depósito y de dónde sale

Revision ID: e5b7c9d1f203
Revises: c3a9d5e7f102
Create Date: 2026-10-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5b7c9d1f203'
down_revision: Union[str, None] = 'c3a9d5e7f102'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('vehicles', sa.Column('fuel_level_pct', sa.Integer(), nullable=True))
    op.add_column('vehicles', sa.Column('fuel_level_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('vehicles', sa.Column('tank_capacity', sa.Float(), nullable=True))
    op.add_column('vehicles', sa.Column('tank_capacity_source', sa.String(length=8), nullable=True))
    op.add_column('vehicles', sa.Column('tank_capacity_note', sa.String(length=300), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('vehicles') as batch:
        for col in ('tank_capacity_note', 'tank_capacity_source', 'tank_capacity', 'fuel_level_at', 'fuel_level_pct'):
            batch.drop_column(col)
