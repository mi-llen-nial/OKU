"""Add institution join_code for teacher registration lookup.

Revision ID: 20260322_0015
Revises: 20260318_0014
Create Date: 2026-03-22 12:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260322_0015"
down_revision: Union[str, None] = "20260318_0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _has_table(inspector, "institutions") or _has_column(inspector, "institutions", "join_code"):
        return
    op.add_column("institutions", sa.Column("join_code", sa.String(32), nullable=True))
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_institutions_join_code_lower
            ON institutions (lower(join_code))
            WHERE join_code IS NOT NULL AND trim(join_code) <> ''
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _has_table(inspector, "institutions") or not _has_column(inspector, "institutions", "join_code"):
        return
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS uq_institutions_join_code_lower")
    op.drop_column("institutions", "join_code")
