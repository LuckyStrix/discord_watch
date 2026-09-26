"""watch always_catch_up

Revision ID: 8d2f0c7a1e34
Revises: 471c9adcb2ad
Create Date: 2026-09-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '8d2f0c7a1e34'
down_revision: Union[str, None] = '471c9adcb2ad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('watches', sa.Column('always_catch_up', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    op.drop_column('watches', 'always_catch_up')
