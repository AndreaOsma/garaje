"""fuel discount

Revision ID: 7c1d5e2f9a10
Revises: 2a0347255320
Create Date: 2026-10-09 10:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7c1d5e2f9a10"
down_revision: Union[str, None] = "2a0347255320"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("fuel_entries", sa.Column("discount", sa.Float(), server_default="0", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("fuel_entries") as batch:
        batch.drop_column("discount")
