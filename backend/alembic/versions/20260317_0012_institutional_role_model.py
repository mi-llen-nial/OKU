"""Institutional role model foundation.

Revision ID: 20260317_0012
Revises: 20260316_0011
Create Date: 2026-03-17 13:30:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260317_0012"
down_revision: Union[str, None] = "20260316_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


membership_role_enum = postgresql.ENUM(
    "student",
    "teacher",
    "methodist",
    "institution_admin",
    name="institution_membership_role",
    create_type=False,
)
membership_status_enum = postgresql.ENUM(
    "pending",
    "active",
    "suspended",
    "revoked",
    name="institution_membership_status",
    create_type=False,
)
teacher_application_status_enum = postgresql.ENUM(
    "pending",
    "approved",
    "rejected",
    "suspended",
    "revoked",
    name="teacher_application_status",
    create_type=False,
)
test_moderation_status_enum = postgresql.ENUM(
    "draft",
    "submitted_for_review",
    "in_review",
    "needs_revision",
    "approved",
    "rejected",
    "archived",
    name="test_moderation_status",
    create_type=False,
)


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(item.get("name") == index_name for item in inspector.get_indexes(table_name))


def _has_unique(inspector: sa.Inspector, table_name: str, constraint_name: str) -> bool:
    return any(item.get("name") == constraint_name for item in inspector.get_unique_constraints(table_name))


def _drop_group_name_unique(inspector: sa.Inspector) -> None:
    if not _has_table(inspector, "groups"):
        return
    for item in inspector.get_unique_constraints("groups"):
        columns = item.get("column_names") or []
        name = item.get("name")
        if name and columns == ["name"]:
            op.drop_constraint(name, "groups", type_="unique")


def _create_enums(bind: sa.Connection) -> None:
    if bind.dialect.name != "postgresql":
        return
    membership_role_enum.create(bind, checkfirst=True)
    membership_status_enum.create(bind, checkfirst=True)
    teacher_application_status_enum.create(bind, checkfirst=True)
    test_moderation_status_enum.create(bind, checkfirst=True)


def _drop_enums(bind: sa.Connection) -> None:
    if bind.dialect.name != "postgresql":
        return
    test_moderation_status_enum.drop(bind, checkfirst=True)
    teacher_application_status_enum.drop(bind, checkfirst=True)
    membership_status_enum.drop(bind, checkfirst=True)
    membership_role_enum.drop(bind, checkfirst=True)


def _ensure_default_institution(bind: sa.Connection) -> int:
    bind.execute(
        sa.text(
            """
            INSERT INTO institutions (name, normalized_name, is_active, created_at)
            SELECT :name, :normalized_name, true, CURRENT_TIMESTAMP
            WHERE NOT EXISTS (SELECT 1 FROM institutions)
            """
        ),
        {
            "name": "Default Institution",
            "normalized_name": "default institution",
        },
    )
    institution_id = bind.execute(sa.text("SELECT id FROM institutions ORDER BY id ASC LIMIT 1")).scalar()
    if institution_id is None:
        raise RuntimeError("Failed to initialize institutions table")
    return int(institution_id)


def _backfill_memberships(bind: sa.Connection, institution_id: int) -> None:
    for role in ("student", "teacher", "methodist", "institution_admin"):
        bind.execute(
            sa.text(
                """
                INSERT INTO institution_memberships (
                    user_id,
                    institution_id,
                    role,
                    status,
                    is_primary,
                    created_at,
                    updated_at
                )
                SELECT
                    u.id,
                    :institution_id,
                    CAST(:membership_role_enum AS institution_membership_role),
                    'active',
                    true,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                FROM users u
                WHERE CAST(u.role AS TEXT) = :user_role
                  AND NOT EXISTS (
                      SELECT 1
                      FROM institution_memberships m
                      WHERE m.user_id = u.id
                        AND m.institution_id = :institution_id
                        AND CAST(m.role AS TEXT) = :membership_role_text
                  )
                """
            ),
            {
                "institution_id": institution_id,
                "user_role": role,
                "membership_role_enum": role,
                "membership_role_text": role,
            },
        )


def _backfill_group_teacher_assignments(bind: sa.Connection, institution_id: int) -> None:
    bind.execute(
        sa.text(
            """
            INSERT INTO group_teacher_assignments (
                group_id,
                teacher_membership_id,
                assigned_by_membership_id,
                created_at
            )
            SELECT
                g.id,
                m.id,
                NULL,
                CURRENT_TIMESTAMP
            FROM groups g
            JOIN institution_memberships m
              ON m.user_id = g.teacher_id
             AND m.institution_id = COALESCE(g.institution_id, :institution_id)
             AND CAST(m.role AS TEXT) = 'teacher'
             AND CAST(m.status AS TEXT) = 'active'
            WHERE g.teacher_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM group_teacher_assignments gta
                  WHERE gta.group_id = g.id
                    AND gta.teacher_membership_id = m.id
              )
            """
        ),
        {"institution_id": institution_id},
    )


def _backfill_test_assignments(bind: sa.Connection) -> None:
    bind.execute(
        sa.text(
            """
            INSERT INTO test_assignments (test_id, group_id, assigned_by_membership_id, created_at)
            SELECT
                tg.test_id,
                tg.group_id,
                NULL,
                CURRENT_TIMESTAMP
            FROM teacher_authored_test_groups tg
            WHERE NOT EXISTS (
                SELECT 1
                FROM test_assignments ta
                WHERE ta.test_id = tg.test_id
                  AND ta.group_id = tg.group_id
            )
            """
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    _create_enums(bind)

    inspector = sa.inspect(bind)

    if not _has_table(inspector, "institutions"):
        op.create_table(
            "institutions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("normalized_name", sa.String(length=255), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_by_user_id", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name", name="uq_institutions_name"),
            sa.UniqueConstraint("normalized_name", name="uq_institutions_normalized_name"),
        )
        op.alter_column("institutions", "is_active", server_default=None)
        op.create_index("ix_institutions_name", "institutions", ["name"])
        op.create_index("ix_institutions_normalized_name", "institutions", ["normalized_name"])

    inspector = sa.inspect(bind)
    if not _has_table(inspector, "institution_memberships"):
        op.create_table(
            "institution_memberships",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("institution_id", sa.Integer(), nullable=False),
            sa.Column("role", membership_role_enum, nullable=False),
            sa.Column("status", membership_status_enum, nullable=False, server_default="active"),
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "institution_id", "role", name="uq_institution_membership_user_role"),
        )
        op.alter_column("institution_memberships", "status", server_default=None)
        op.alter_column("institution_memberships", "is_primary", server_default=None)
        op.create_index("ix_institution_memberships_user_id", "institution_memberships", ["user_id"])
        op.create_index("ix_institution_memberships_institution_id", "institution_memberships", ["institution_id"])
        op.create_index("ix_institution_memberships_role", "institution_memberships", ["role"])
        op.create_index("ix_institution_memberships_status", "institution_memberships", ["status"])
        op.create_index(
            "ix_institution_membership_user_institution",
            "institution_memberships",
            ["user_id", "institution_id"],
        )

    inspector = sa.inspect(bind)
    if not _has_table(inspector, "teacher_applications"):
        op.create_table(
            "teacher_applications",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("applicant_user_id", sa.Integer(), nullable=False),
            sa.Column("institution_id", sa.Integer(), nullable=False),
            sa.Column("full_name", sa.String(length=255), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("subject", sa.String(length=255), nullable=True),
            sa.Column("position", sa.String(length=255), nullable=True),
            sa.Column("additional_info", sa.Text(), nullable=True),
            sa.Column("status", teacher_application_status_enum, nullable=False, server_default="pending"),
            sa.Column("reviewer_user_id", sa.Integer(), nullable=True),
            sa.Column("reviewer_comment", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["applicant_user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["reviewer_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.alter_column("teacher_applications", "status", server_default=None)
        op.create_index("ix_teacher_applications_applicant_user_id", "teacher_applications", ["applicant_user_id"])
        op.create_index("ix_teacher_applications_institution_id", "teacher_applications", ["institution_id"])
        op.create_index("ix_teacher_applications_status", "teacher_applications", ["status"])
        op.create_index(
            "ix_teacher_applications_institution_status",
            "teacher_applications",
            ["institution_id", "status"],
        )
        op.create_index(
            "ix_teacher_applications_applicant_status",
            "teacher_applications",
            ["applicant_user_id", "status"],
        )

    inspector = sa.inspect(bind)
    if _has_table(inspector, "groups") and not _has_column(inspector, "groups", "institution_id"):
        op.add_column("groups", sa.Column("institution_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_groups_institution_id_institutions",
            "groups",
            "institutions",
            ["institution_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_index("ix_groups_institution_id", "groups", ["institution_id"])

    inspector = sa.inspect(bind)
    _drop_group_name_unique(inspector)

    inspector = sa.inspect(bind)
    if _has_table(inspector, "groups") and not _has_unique(inspector, "groups", "uq_group_name_per_institution"):
        op.create_unique_constraint("uq_group_name_per_institution", "groups", ["institution_id", "name"])

    inspector = sa.inspect(bind)
    if not _has_table(inspector, "group_teacher_assignments"):
        op.create_table(
            "group_teacher_assignments",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("group_id", sa.Integer(), nullable=False),
            sa.Column("teacher_membership_id", sa.Integer(), nullable=False),
            sa.Column("assigned_by_membership_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["teacher_membership_id"], ["institution_memberships.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["assigned_by_membership_id"], ["institution_memberships.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("group_id", "teacher_membership_id", name="uq_group_teacher_assignment"),
        )
        op.create_index("ix_group_teacher_assignments_group_id", "group_teacher_assignments", ["group_id"])
        op.create_index(
            "ix_group_teacher_assignments_teacher_membership_id",
            "group_teacher_assignments",
            ["teacher_membership_id"],
        )

    inspector = sa.inspect(bind)
    if _has_table(inspector, "teacher_authored_tests"):
        if not _has_column(inspector, "teacher_authored_tests", "institution_id"):
            op.add_column("teacher_authored_tests", sa.Column("institution_id", sa.Integer(), nullable=True))
            op.create_foreign_key(
                "fk_teacher_authored_tests_institution_id_institutions",
                "teacher_authored_tests",
                "institutions",
                ["institution_id"],
                ["id"],
                ondelete="CASCADE",
            )
            op.create_index("ix_teacher_authored_tests_institution_id", "teacher_authored_tests", ["institution_id"])

        if not _has_column(inspector, "teacher_authored_tests", "moderation_status"):
            op.add_column(
                "teacher_authored_tests",
                sa.Column(
                    "moderation_status",
                    test_moderation_status_enum,
                    nullable=False,
                    server_default="draft",
                ),
            )
            op.alter_column("teacher_authored_tests", "moderation_status", server_default=None)
            op.create_index("ix_teacher_authored_tests_moderation_status", "teacher_authored_tests", ["moderation_status"])

        if not _has_column(inspector, "teacher_authored_tests", "moderation_comment"):
            op.add_column("teacher_authored_tests", sa.Column("moderation_comment", sa.Text(), nullable=True))

        if not _has_column(inspector, "teacher_authored_tests", "submitted_for_review_at"):
            op.add_column(
                "teacher_authored_tests",
                sa.Column("submitted_for_review_at", sa.DateTime(timezone=True), nullable=True),
            )

        if not _has_column(inspector, "teacher_authored_tests", "reviewed_at"):
            op.add_column("teacher_authored_tests", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))

        if not _has_column(inspector, "teacher_authored_tests", "reviewed_by_membership_id"):
            op.add_column("teacher_authored_tests", sa.Column("reviewed_by_membership_id", sa.Integer(), nullable=True))
            op.create_foreign_key(
                "fk_teacher_authored_tests_reviewed_by_membership_id",
                "teacher_authored_tests",
                "institution_memberships",
                ["reviewed_by_membership_id"],
                ["id"],
                ondelete="SET NULL",
            )
            op.create_index(
                "ix_teacher_authored_tests_reviewed_by_membership_id",
                "teacher_authored_tests",
                ["reviewed_by_membership_id"],
            )

        if not _has_column(inspector, "teacher_authored_tests", "current_draft_version"):
            op.add_column(
                "teacher_authored_tests",
                sa.Column("current_draft_version", sa.Integer(), nullable=False, server_default="1"),
            )
            op.alter_column("teacher_authored_tests", "current_draft_version", server_default=None)

        if not _has_column(inspector, "teacher_authored_tests", "approved_version"):
            op.add_column("teacher_authored_tests", sa.Column("approved_version", sa.Integer(), nullable=True))

    inspector = sa.inspect(bind)
    if not _has_table(inspector, "test_review_requests"):
        op.create_table(
            "test_review_requests",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("institution_id", sa.Integer(), nullable=False),
            sa.Column("test_id", sa.Integer(), nullable=False),
            sa.Column("submitted_version", sa.Integer(), nullable=False),
            sa.Column("status", test_moderation_status_enum, nullable=False),
            sa.Column("requested_by_membership_id", sa.Integer(), nullable=False),
            sa.Column("reviewer_membership_id", sa.Integer(), nullable=True),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["test_id"], ["teacher_authored_tests.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["requested_by_membership_id"], ["institution_memberships.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["reviewer_membership_id"], ["institution_memberships.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_test_review_requests_institution_id", "test_review_requests", ["institution_id"])
        op.create_index("ix_test_review_requests_test_id", "test_review_requests", ["test_id"])
        op.create_index("ix_test_review_requests_status", "test_review_requests", ["status"])
        op.create_index(
            "ix_test_review_requests_institution_status",
            "test_review_requests",
            ["institution_id", "status"],
        )

    inspector = sa.inspect(bind)
    if not _has_table(inspector, "test_assignments"):
        op.create_table(
            "test_assignments",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("test_id", sa.Integer(), nullable=False),
            sa.Column("group_id", sa.Integer(), nullable=False),
            sa.Column("assigned_by_membership_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["test_id"], ["teacher_authored_tests.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["assigned_by_membership_id"], ["institution_memberships.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("test_id", "group_id", name="uq_test_assignment_test_group"),
        )
        op.create_index("ix_test_assignments_test_id", "test_assignments", ["test_id"])
        op.create_index("ix_test_assignments_group_id", "test_assignments", ["group_id"])

    inspector = sa.inspect(bind)
    if not _has_table(inspector, "notifications"):
        op.create_table(
            "notifications",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("institution_id", sa.Integer(), nullable=True),
            sa.Column("type", sa.String(length=64), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("data_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.alter_column("notifications", "data_json", server_default=None)
        op.alter_column("notifications", "is_read", server_default=None)
        op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
        op.create_index("ix_notifications_type", "notifications", ["type"])
        op.create_index("ix_notifications_user_is_read", "notifications", ["user_id", "is_read"])

    inspector = sa.inspect(bind)
    if not _has_table(inspector, "audit_logs"):
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("institution_id", sa.Integer(), nullable=True),
            sa.Column("actor_user_id", sa.Integer(), nullable=True),
            sa.Column("action", sa.String(length=128), nullable=False),
            sa.Column("target_type", sa.String(length=64), nullable=False),
            sa.Column("target_id", sa.String(length=64), nullable=False),
            sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.alter_column("audit_logs", "metadata_json", server_default=None)
        op.create_index("ix_audit_logs_institution_id", "audit_logs", ["institution_id"])
        op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"])
        op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
        op.create_index(
            "ix_audit_logs_institution_action",
            "audit_logs",
            ["institution_id", "action", "created_at"],
        )

    institution_id = _ensure_default_institution(bind)

    bind.execute(
        sa.text("UPDATE groups SET institution_id = :institution_id WHERE institution_id IS NULL"),
        {"institution_id": institution_id},
    )

    bind.execute(
        sa.text(
            """
            UPDATE teacher_authored_tests
            SET institution_id = :institution_id
            WHERE institution_id IS NULL
            """
        ),
        {"institution_id": institution_id},
    )

    _backfill_memberships(bind, institution_id)
    _backfill_group_teacher_assignments(bind, institution_id)
    _backfill_test_assignments(bind)

    bind.execute(
        sa.text(
            """
            UPDATE teacher_authored_tests
            SET moderation_status = 'approved',
                approved_version = COALESCE(approved_version, 1),
                current_draft_version = COALESCE(current_draft_version, 1),
                reviewed_at = COALESCE(reviewed_at, updated_at, created_at)
            WHERE CAST(moderation_status AS TEXT) = 'draft'
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "audit_logs"):
        op.drop_table("audit_logs")

    inspector = sa.inspect(bind)
    if _has_table(inspector, "notifications"):
        op.drop_table("notifications")

    inspector = sa.inspect(bind)
    if _has_table(inspector, "test_assignments"):
        op.drop_table("test_assignments")

    inspector = sa.inspect(bind)
    if _has_table(inspector, "test_review_requests"):
        op.drop_table("test_review_requests")

    inspector = sa.inspect(bind)
    if _has_table(inspector, "teacher_authored_tests"):
        if _has_column(inspector, "teacher_authored_tests", "approved_version"):
            op.drop_column("teacher_authored_tests", "approved_version")
        if _has_column(inspector, "teacher_authored_tests", "current_draft_version"):
            op.drop_column("teacher_authored_tests", "current_draft_version")
        if _has_column(inspector, "teacher_authored_tests", "reviewed_by_membership_id"):
            op.drop_column("teacher_authored_tests", "reviewed_by_membership_id")
        if _has_column(inspector, "teacher_authored_tests", "reviewed_at"):
            op.drop_column("teacher_authored_tests", "reviewed_at")
        if _has_column(inspector, "teacher_authored_tests", "submitted_for_review_at"):
            op.drop_column("teacher_authored_tests", "submitted_for_review_at")
        if _has_column(inspector, "teacher_authored_tests", "moderation_comment"):
            op.drop_column("teacher_authored_tests", "moderation_comment")
        if _has_column(inspector, "teacher_authored_tests", "moderation_status"):
            op.drop_column("teacher_authored_tests", "moderation_status")
        if _has_column(inspector, "teacher_authored_tests", "institution_id"):
            op.drop_column("teacher_authored_tests", "institution_id")

    inspector = sa.inspect(bind)
    if _has_table(inspector, "group_teacher_assignments"):
        op.drop_table("group_teacher_assignments")

    inspector = sa.inspect(bind)
    if _has_table(inspector, "groups"):
        if _has_unique(inspector, "groups", "uq_group_name_per_institution"):
            op.drop_constraint("uq_group_name_per_institution", "groups", type_="unique")
        if _has_column(inspector, "groups", "institution_id"):
            op.drop_column("groups", "institution_id")

    inspector = sa.inspect(bind)
    if _has_table(inspector, "teacher_applications"):
        op.drop_table("teacher_applications")

    inspector = sa.inspect(bind)
    if _has_table(inspector, "institution_memberships"):
        op.drop_table("institution_memberships")

    inspector = sa.inspect(bind)
    if _has_table(inspector, "institutions"):
        op.drop_table("institutions")

    _drop_enums(bind)
