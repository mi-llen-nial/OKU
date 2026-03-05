"""Add case-insensitive uniqueness for usernames.

Revision ID: 20260303_0006
Revises: 20260303_0005
Create Date: 2026-03-03 00:25:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260303_0006"
down_revision: Union[str, None] = "20260303_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    if "users" not in table_names:
        return

    op.execute(
        """
        WITH ranked AS (
            SELECT id, username, row_number() OVER (PARTITION BY lower(username) ORDER BY id ASC) AS rn
            FROM users
        )
        UPDATE users AS target
        SET username = LEFT(target.username, 20) || '_' || target.id::text
        FROM ranked
        WHERE target.id = ranked.id
          AND ranked.rn > 1
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_username_lower ON users ((lower(username)))")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    if "users" not in table_names:
        return

    op.execute("DROP INDEX IF EXISTS uq_users_username_lower")
