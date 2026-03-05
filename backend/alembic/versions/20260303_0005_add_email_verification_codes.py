"""Add email verification codes table.

Revision ID: 20260303_0005
Revises: 20260302_0004
Create Date: 2026-03-03 00:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260303_0005"
down_revision: Union[str, None] = "20260302_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "email_verification_codes" in table_names:
        return

    op.create_table(
        "email_verification_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_email_verification_codes_email"),
        "email_verification_codes",
        ["email"],
        unique=False,
    )
    op.create_index(
        op.f("ix_email_verification_codes_purpose"),
        "email_verification_codes",
        ["purpose"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    if "email_verification_codes" not in table_names:
        return

    op.drop_index(op.f("ix_email_verification_codes_purpose"), table_name="email_verification_codes")
    op.drop_index(op.f("ix_email_verification_codes_email"), table_name="email_verification_codes")
    op.drop_table("email_verification_codes")
