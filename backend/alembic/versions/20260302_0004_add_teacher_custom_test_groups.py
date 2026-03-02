"""Add mapping between teacher custom tests and groups.

Revision ID: 20260302_0004
Revises: 20260302_0003
Create Date: 2026-03-02 14:05:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260302_0004"
down_revision: Union[str, None] = "20260302_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "teacher_authored_test_groups" in table_names:
        return

    op.create_table(
        "teacher_authored_test_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("test_id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["test_id"], ["teacher_authored_tests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("test_id", "group_id", name="uq_teacher_authored_test_group"),
    )
    op.create_index(
        op.f("ix_teacher_authored_test_groups_test_id"),
        "teacher_authored_test_groups",
        ["test_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_teacher_authored_test_groups_group_id"),
        "teacher_authored_test_groups",
        ["group_id"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    if "teacher_authored_test_groups" not in table_names:
        return

    op.drop_index(op.f("ix_teacher_authored_test_groups_group_id"), table_name="teacher_authored_test_groups")
    op.drop_index(op.f("ix_teacher_authored_test_groups_test_id"), table_name="teacher_authored_test_groups")
    op.drop_table("teacher_authored_test_groups")
