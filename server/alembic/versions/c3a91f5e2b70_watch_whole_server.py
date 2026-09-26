"""watch whole server

Revision ID: c3a91f5e2b70
Revises: 8d2f0c7a1e34
Create Date: 2026-09-26

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'c3a91f5e2b70'
down_revision: Union[str, None] = '8d2f0c7a1e34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # CHECK constraints can't be altered in Postgres: drop and recreate.
    op.drop_constraint('ck_watches_kind', 'watches', type_='check')
    op.create_check_constraint('ck_watches_kind', 'watches', "kind IN ('channel', 'guild', 'all_dms', 'requests')")
    op.create_check_constraint('ck_watches_guild_has_id', 'watches', "kind <> 'guild' OR guild_id IS NOT NULL")
    # One whole-server watch per server. The existing builtin-kind index is
    # "kind is unique where kind <> 'channel'", which would wrongly allow only
    # one guild watch in total -- narrow it to the true singletons.
    op.execute("DROP INDEX uq_watches_builtin_kind")
    op.execute("CREATE UNIQUE INDEX uq_watches_builtin_kind ON watches (kind) WHERE kind IN ('all_dms', 'requests')")
    op.execute("CREATE UNIQUE INDEX uq_watches_guild ON watches (guild_id) WHERE kind = 'guild'")


def downgrade() -> None:
    op.execute("DELETE FROM watches WHERE kind = 'guild'")
    op.execute("DROP INDEX uq_watches_guild")
    op.execute("DROP INDEX uq_watches_builtin_kind")
    op.execute("CREATE UNIQUE INDEX uq_watches_builtin_kind ON watches (kind) WHERE kind <> 'channel'")
    op.drop_constraint('ck_watches_guild_has_id', 'watches', type_='check')
    op.drop_constraint('ck_watches_kind', 'watches', type_='check')
    op.create_check_constraint('ck_watches_kind', 'watches', "kind IN ('channel', 'all_dms', 'requests')")
