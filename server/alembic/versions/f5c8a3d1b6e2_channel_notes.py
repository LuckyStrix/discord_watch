"""channel notes on whole-server watches

Revision ID: f5c8a3d1b6e2
Revises: e41b7d2c9a05
Create Date: 2026-09-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'f5c8a3d1b6e2'
down_revision: Union[str, None] = 'e41b7d2c9a05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('watches', sa.Column('channel_notes', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False))
    op.add_column('items', sa.Column('parent_channel_id', sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column('items', 'parent_channel_id')
    op.drop_column('watches', 'channel_notes')
