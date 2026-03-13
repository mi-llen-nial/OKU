"""Add bilingual recommendation fields.

Revision ID: 20260313_0008
Revises: 20260308_0007
Create Date: 2026-03-13 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260313_0008"
down_revision: Union[str, None] = "20260308_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    if "recommendations" not in table_names:
        return

    columns = {column["name"] for column in inspector.get_columns("recommendations")}
    if "advice_text_ru" not in columns:
        op.add_column("recommendations", sa.Column("advice_text_ru", sa.Text(), nullable=True))
    if "advice_text_kz" not in columns:
        op.add_column("recommendations", sa.Column("advice_text_kz", sa.Text(), nullable=True))
    if "generated_tasks_ru_json" not in columns:
        op.add_column("recommendations", sa.Column("generated_tasks_ru_json", sa.JSON(), nullable=True))
    if "generated_tasks_kz_json" not in columns:
        op.add_column("recommendations", sa.Column("generated_tasks_kz_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    if "recommendations" not in table_names:
        return

    columns = {column["name"] for column in inspector.get_columns("recommendations")}
    if "generated_tasks_kz_json" in columns:
        op.drop_column("recommendations", "generated_tasks_kz_json")
    if "generated_tasks_ru_json" in columns:
        op.drop_column("recommendations", "generated_tasks_ru_json")
    if "advice_text_kz" in columns:
        op.drop_column("recommendations", "advice_text_kz")
    if "advice_text_ru" in columns:
        op.drop_column("recommendations", "advice_text_ru")

