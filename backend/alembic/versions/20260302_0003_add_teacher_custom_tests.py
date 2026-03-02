"""Add teacher-authored custom tests tables.

Revision ID: 20260302_0003
Revises: 20260228_0002
Create Date: 2026-03-02 12:20:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260302_0003"
down_revision: Union[str, None] = "20260228_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "teacher_authored_tests" not in table_names:
        op.create_table(
            "teacher_authored_tests",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("teacher_id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=160), nullable=False),
            sa.Column("time_limit_seconds", sa.Integer(), nullable=False),
            sa.Column("warning_limit", sa.Integer(), server_default=sa.text("0"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["teacher_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_teacher_authored_tests_teacher_id"),
            "teacher_authored_tests",
            ["teacher_id"],
            unique=False,
        )

    if "teacher_authored_questions" not in table_names:
        op.create_table(
            "teacher_authored_questions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("test_id", sa.Integer(), nullable=False),
            sa.Column("order_index", sa.Integer(), nullable=False),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("question_type", sa.String(length=32), nullable=False),
            sa.Column("options_json", sa.JSON(), nullable=True),
            sa.Column("correct_answer_json", sa.JSON(), nullable=False),
            sa.ForeignKeyConstraint(["test_id"], ["teacher_authored_tests.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("test_id", "order_index", name="uq_teacher_authored_question_order"),
        )
        op.create_index(
            op.f("ix_teacher_authored_questions_test_id"),
            "teacher_authored_questions",
            ["test_id"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "teacher_authored_questions" in table_names:
        op.drop_index(op.f("ix_teacher_authored_questions_test_id"), table_name="teacher_authored_questions")
        op.drop_table("teacher_authored_questions")

    if "teacher_authored_tests" in table_names:
        op.drop_index(op.f("ix_teacher_authored_tests_teacher_id"), table_name="teacher_authored_tests")
        op.drop_table("teacher_authored_tests")
