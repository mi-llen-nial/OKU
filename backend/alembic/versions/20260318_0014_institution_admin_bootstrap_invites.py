"""Add institution admin bootstrap invites.

Revision ID: 20260318_0014
Revises: 20260318_0013
Create Date: 2026-03-18 18:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260318_0014"
down_revision: Union[str, None] = "20260318_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(item.get("name") == index_name for item in inspector.get_indexes(table_name))


def _has_unique(inspector: sa.Inspector, table_name: str, constraint_name: str) -> bool:
    return any(item.get("name") == constraint_name for item in inspector.get_unique_constraints(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "institution_admin_bootstrap_invites"):
        op.create_table(
            "institution_admin_bootstrap_invites",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("institution_id", sa.Integer(), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("created_by_user_id", sa.Integer(), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_by_user_id", sa.Integer(), nullable=True),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["consumed_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    inspector = sa.inspect(bind)
    if _has_table(inspector, "institution_admin_bootstrap_invites"):
        if not _has_unique(
            inspector,
            "institution_admin_bootstrap_invites",
            "uq_institution_admin_bootstrap_invite_token_hash",
        ):
            op.create_unique_constraint(
                "uq_institution_admin_bootstrap_invite_token_hash",
                "institution_admin_bootstrap_invites",
                ["token_hash"],
            )

        inspector = sa.inspect(bind)
        if not _has_index(
            inspector,
            "institution_admin_bootstrap_invites",
            "ix_institution_admin_bootstrap_invites_institution_id",
        ):
            op.create_index(
                "ix_institution_admin_bootstrap_invites_institution_id",
                "institution_admin_bootstrap_invites",
                ["institution_id"],
            )

        inspector = sa.inspect(bind)
        if not _has_index(inspector, "institution_admin_bootstrap_invites", "ix_institution_admin_bootstrap_invites_email"):
            op.create_index(
                "ix_institution_admin_bootstrap_invites_email",
                "institution_admin_bootstrap_invites",
                ["email"],
            )

        inspector = sa.inspect(bind)
        if not _has_index(
            inspector,
            "institution_admin_bootstrap_invites",
            "ix_institution_admin_bootstrap_invites_token_hash",
        ):
            op.create_index(
                "ix_institution_admin_bootstrap_invites_token_hash",
                "institution_admin_bootstrap_invites",
                ["token_hash"],
            )

        inspector = sa.inspect(bind)
        if not _has_index(
            inspector,
            "institution_admin_bootstrap_invites",
            "ix_institution_admin_bootstrap_invites_created_by_user_id",
        ):
            op.create_index(
                "ix_institution_admin_bootstrap_invites_created_by_user_id",
                "institution_admin_bootstrap_invites",
                ["created_by_user_id"],
            )

        inspector = sa.inspect(bind)
        if not _has_index(
            inspector,
            "institution_admin_bootstrap_invites",
            "ix_institution_admin_bootstrap_invites_consumed_by_user_id",
        ):
            op.create_index(
                "ix_institution_admin_bootstrap_invites_consumed_by_user_id",
                "institution_admin_bootstrap_invites",
                ["consumed_by_user_id"],
            )

        inspector = sa.inspect(bind)
        if not _has_index(
            inspector,
            "institution_admin_bootstrap_invites",
            "ix_institution_admin_bootstrap_invites_expires_at",
        ):
            op.create_index(
                "ix_institution_admin_bootstrap_invites_expires_at",
                "institution_admin_bootstrap_invites",
                ["expires_at"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "institution_admin_bootstrap_invites"):
        for index_name in (
            "ix_institution_admin_bootstrap_invites_expires_at",
            "ix_institution_admin_bootstrap_invites_consumed_by_user_id",
            "ix_institution_admin_bootstrap_invites_created_by_user_id",
            "ix_institution_admin_bootstrap_invites_token_hash",
            "ix_institution_admin_bootstrap_invites_email",
            "ix_institution_admin_bootstrap_invites_institution_id",
        ):
            inspector = sa.inspect(bind)
            if _has_index(inspector, "institution_admin_bootstrap_invites", index_name):
                op.drop_index(index_name, table_name="institution_admin_bootstrap_invites")

        inspector = sa.inspect(bind)
        if _has_unique(
            inspector,
            "institution_admin_bootstrap_invites",
            "uq_institution_admin_bootstrap_invite_token_hash",
        ):
            op.drop_constraint(
                "uq_institution_admin_bootstrap_invite_token_hash",
                "institution_admin_bootstrap_invites",
                type_="unique",
            )

        op.drop_table("institution_admin_bootstrap_invites")

