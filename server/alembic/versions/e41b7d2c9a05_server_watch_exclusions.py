"""server watch exclusions

Revision ID: e41b7d2c9a05
Revises: c3a91f5e2b70
Create Date: 2026-09-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e41b7d2c9a05'
down_revision: Union[str, None] = 'c3a91f5e2b70'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('watches', sa.Column('excluded_channel_ids', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False))
    op.add_column('watches', sa.Column('excluded_category_ids', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False))
    # Filled in by the listener's next directory sync (on every READY).
    op.add_column('discord_channels', sa.Column('category_id', sa.String(length=32), nullable=True))
    op.add_column('discord_channels', sa.Column('category_position', sa.Integer(), server_default='-1', nullable=False))


def downgrade() -> None:
    op.drop_column('discord_channels', 'category_position')
    op.drop_column('discord_channels', 'category_id')
    op.drop_column('watches', 'excluded_category_ids')
    op.drop_column('watches', 'excluded_channel_ids')
