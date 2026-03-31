from __future__ import annotations

import enum
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UserRole(str, enum.Enum):
    student = "student"
    teacher = "teacher"
    methodist = "methodist"
    institution_admin = "institution_admin"
    superadmin = "superadmin"


class PreferredLanguage(str, enum.Enum):
    ru = "RU"
    kz = "KZ"


class DifficultyLevel(str, enum.Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class TestMode(str, enum.Enum):
    text = "text"
    audio = "audio"
    oral = "oral"


class QuestionType(str, enum.Enum):
    single_choice = "single_choice"
    multi_choice = "multi_choice"
    short_text = "short_text"
    matching = "matching"
    oral_answer = "oral_answer"


class InvitationStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    declined = "declined"


class InstitutionMembershipRole(str, enum.Enum):
    student = "student"
    teacher = "teacher"
    methodist = "methodist"
    institution_admin = "institution_admin"


class InstitutionMembershipStatus(str, enum.Enum):
    pending = "pending"
    active = "active"
    suspended = "suspended"
    revoked = "revoked"


class TeacherApplicationStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    suspended = "suspended"
    revoked = "revoked"


class TestModerationStatus(str, enum.Enum):
    draft = "draft"
    submitted_for_review = "submitted_for_review"
    in_review = "in_review"
    needs_revision = "needs_revision"
    approved = "approved"
    rejected = "rejected"
    archived = "archived"


class CatalogQuestionStatus(str, enum.Enum):
    draft = "draft"
    validated = "validated"
    published = "published"
    archived = "archived"


class Institution(Base):
    __tablename__ = "institutions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    join_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    memberships: Mapped[list[InstitutionMembership]] = relationship(
        back_populates="institution",
        cascade="all, delete-orphan",
    )
    groups: Mapped[list[Group]] = relationship(back_populates="institution")
    teacher_applications: Mapped[list[TeacherApplication]] = relationship(
        back_populates="institution",
        cascade="all, delete-orphan",
    )
    notifications: Mapped[list[Notification]] = relationship(
        back_populates="institution",
        cascade="all, delete-orphan",
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(back_populates="institution", cascade="all, delete-orphan")
    custom_tests: Mapped[list[TeacherAuthoredTest]] = relationship(back_populates="institution")
    created_by: Mapped[User | None] = relationship(foreign_keys=[created_by_user_id])


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.student, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    student_profile: Mapped[StudentProfile | None] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    institution_memberships: Mapped[list[InstitutionMembership]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    submitted_teacher_applications: Mapped[list[TeacherApplication]] = relationship(
        back_populates="applicant",
        foreign_keys="TeacherApplication.applicant_user_id",
        cascade="all, delete-orphan",
    )
    reviewed_teacher_applications: Mapped[list[TeacherApplication]] = relationship(
        back_populates="reviewer",
        foreign_keys="TeacherApplication.reviewer_user_id",
    )
    received_notifications: Mapped[list[Notification]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    audit_events: Mapped[list[AuditLog]] = relationship(back_populates="actor")
    tests: Mapped[list[Test]] = relationship(back_populates="student", cascade="all, delete-orphan")
    memberships: Mapped[list[GroupMembership]] = relationship(back_populates="student", cascade="all, delete-orphan")
    groups_created: Mapped[list[Group]] = relationship(back_populates="teacher")
    custom_tests_created: Mapped[list[TeacherAuthoredTest]] = relationship(
        back_populates="teacher",
        cascade="all, delete-orphan",
    )
    sent_invitations: Mapped[list[GroupInvitation]] = relationship(
        back_populates="teacher",
        foreign_keys="GroupInvitation.teacher_id",
        cascade="all, delete-orphan",
    )
    group_invite_links: Mapped[list[GroupInviteLink]] = relationship(
        back_populates="teacher",
        cascade="all, delete-orphan",
    )
    received_invitations: Mapped[list[GroupInvitation]] = relationship(
        back_populates="student",
        foreign_keys="GroupInvitation.student_id",
        cascade="all, delete-orphan",
    )
    sessions: Mapped[list[UserSession]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    refresh_token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")


class EmailVerificationCode(Base):
    __tablename__ = "email_verification_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class InstitutionMembership(Base):
    __tablename__ = "institution_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "institution_id", "role", name="uq_institution_membership_user_role"),
        Index("ix_institution_membership_user_institution", "user_id", "institution_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    institution_id: Mapped[int] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[InstitutionMembershipRole] = mapped_column(
        Enum(
            InstitutionMembershipRole,
            name="institution_membership_role",
            create_type=False,
        ),
        nullable=False,
        index=True,
    )
    status: Mapped[InstitutionMembershipStatus] = mapped_column(
        Enum(
            InstitutionMembershipStatus,
            name="institution_membership_status",
            create_type=False,
        ),
        nullable=False,
        default=InstitutionMembershipStatus.active,
        index=True,
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user: Mapped[User] = relationship(back_populates="institution_memberships")
    institution: Mapped[Institution] = relationship(back_populates="memberships")
    assigned_groups: Mapped[list[GroupTeacherAssignment]] = relationship(
        back_populates="teacher_membership",
        cascade="all, delete-orphan",
        foreign_keys="GroupTeacherAssignment.teacher_membership_id",
    )
    assigned_by_group_links: Mapped[list[GroupTeacherAssignment]] = relationship(
        back_populates="assigned_by_membership",
        foreign_keys="GroupTeacherAssignment.assigned_by_membership_id",
    )
    review_requests_authored: Mapped[list[TestReviewRequest]] = relationship(
        back_populates="requested_by_membership",
        foreign_keys="TestReviewRequest.requested_by_membership_id",
    )
    review_requests_handled: Mapped[list[TestReviewRequest]] = relationship(
        back_populates="reviewer_membership",
        foreign_keys="TestReviewRequest.reviewer_membership_id",
    )
    test_assignments: Mapped[list[TestAssignment]] = relationship(
        back_populates="assigned_by_membership",
        foreign_keys="TestAssignment.assigned_by_membership_id",
    )


class InstitutionAdminBootstrapInvite(Base):
    __tablename__ = "institution_admin_bootstrap_invites"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_institution_admin_bootstrap_invite_token_hash"),
        Index("ix_institution_admin_bootstrap_invites_institution_id", "institution_id"),
        Index("ix_institution_admin_bootstrap_invites_email", "email"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    institution_id: Mapped[int] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    consumed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    institution: Mapped[Institution] = relationship()
    created_by: Mapped[User | None] = relationship(foreign_keys=[created_by_user_id])
    consumed_by: Mapped[User | None] = relationship(foreign_keys=[consumed_by_user_id])


class TeacherApplication(Base):
    __tablename__ = "teacher_applications"
    __table_args__ = (
        Index("ix_teacher_applications_institution_status", "institution_id", "status"),
        Index("ix_teacher_applications_applicant_status", "applicant_user_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    applicant_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    institution_id: Mapped[int] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    position: Mapped[str | None] = mapped_column(String(255), nullable=True)
    additional_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TeacherApplicationStatus] = mapped_column(
        Enum(
            TeacherApplicationStatus,
            name="teacher_application_status",
            create_type=False,
        ),
        nullable=False,
        default=TeacherApplicationStatus.pending,
        index=True,
    )
    reviewer_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reviewer_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    applicant: Mapped[User] = relationship(
        back_populates="submitted_teacher_applications",
        foreign_keys=[applicant_user_id],
    )
    reviewer: Mapped[User | None] = relationship(
        back_populates="reviewed_teacher_applications",
        foreign_keys=[reviewer_user_id],
    )
    institution: Mapped[Institution] = relationship(back_populates="teacher_applications")


class Group(Base):
    __tablename__ = "groups"
    __table_args__ = (
        UniqueConstraint("institution_id", "name", name="uq_group_name_per_institution"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    institution_id: Mapped[int | None] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    teacher_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)

    profiles: Mapped[list[StudentProfile]] = relationship(back_populates="group")
    memberships: Mapped[list[GroupMembership]] = relationship(back_populates="group", cascade="all, delete-orphan")
    teacher: Mapped[User | None] = relationship(back_populates="groups_created")
    institution: Mapped[Institution | None] = relationship(back_populates="groups")
    teacher_assignments: Mapped[list[GroupTeacherAssignment]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
    )
    invitations: Mapped[list[GroupInvitation]] = relationship(back_populates="group")
    invite_links: Mapped[list[GroupInviteLink]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
    )
    custom_test_links: Mapped[list[TeacherAuthoredTestGroup]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
    )
    test_assignments: Mapped[list[TestAssignment]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
    )


class GroupMembership(Base):
    __tablename__ = "group_memberships"
    __table_args__ = (UniqueConstraint("student_id", "group_id", name="uq_student_group"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), index=True)

    student: Mapped[User] = relationship(back_populates="memberships")
    group: Mapped[Group] = relationship(back_populates="memberships")


class GroupInvitation(Base):
    __tablename__ = "group_invitations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id", ondelete="SET NULL"), index=True, nullable=True)
    status: Mapped[InvitationStatus] = mapped_column(Enum(InvitationStatus), default=InvitationStatus.pending, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    teacher: Mapped[User] = relationship(back_populates="sent_invitations", foreign_keys=[teacher_id])
    student: Mapped[User] = relationship(back_populates="received_invitations", foreign_keys=[student_id])
    group: Mapped[Group | None] = relationship(back_populates="invitations")


class GroupInviteLink(Base):
    __tablename__ = "group_invite_links"
    __table_args__ = (
        UniqueConstraint("token", name="uq_group_invite_link_token"),
        Index("ix_group_invite_links_group_id", "group_id"),
        Index("ix_group_invite_links_teacher_id", "teacher_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    token: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    uses_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    teacher: Mapped[User] = relationship(back_populates="group_invite_links")
    group: Mapped[Group] = relationship(back_populates="invite_links")


class TeacherAuthoredTestGroup(Base):
    __tablename__ = "teacher_authored_test_groups"
    __table_args__ = (
        UniqueConstraint("test_id", "group_id", name="uq_teacher_authored_test_group"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    test_id: Mapped[int] = mapped_column(
        ForeignKey("teacher_authored_tests.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    test: Mapped[TeacherAuthoredTest] = relationship(back_populates="group_links")
    group: Mapped[Group] = relationship(back_populates="custom_test_links")


class TeacherAuthoredTest(Base):
    __tablename__ = "teacher_authored_tests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    institution_id: Mapped[int | None] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    time_limit_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    warning_limit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    moderation_status: Mapped[TestModerationStatus] = mapped_column(
        Enum(
            TestModerationStatus,
            name="test_moderation_status",
            create_type=False,
        ),
        default=TestModerationStatus.draft,
        nullable=False,
        index=True,
    )
    moderation_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_for_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by_membership_id: Mapped[int | None] = mapped_column(
        ForeignKey("institution_memberships.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    current_draft_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    approved_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    teacher: Mapped[User] = relationship(back_populates="custom_tests_created")
    institution: Mapped[Institution | None] = relationship(back_populates="custom_tests")
    group_links: Mapped[list[TeacherAuthoredTestGroup]] = relationship(
        back_populates="test",
        cascade="all, delete-orphan",
    )
    review_requests: Mapped[list[TestReviewRequest]] = relationship(
        back_populates="test",
        cascade="all, delete-orphan",
        order_by="TestReviewRequest.created_at.desc()",
    )
    assignments: Mapped[list[TestAssignment]] = relationship(
        back_populates="test",
        cascade="all, delete-orphan",
    )
    questions: Mapped[list[TeacherAuthoredQuestion]] = relationship(
        back_populates="test",
        cascade="all, delete-orphan",
        order_by="TeacherAuthoredQuestion.order_index.asc()",
    )


class TeacherAuthoredQuestion(Base):
    __tablename__ = "teacher_authored_questions"
    __table_args__ = (
        UniqueConstraint("test_id", "order_index", name="uq_teacher_authored_question_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    test_id: Mapped[int] = mapped_column(
        ForeignKey("teacher_authored_tests.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[str] = mapped_column(String(32), nullable=False)
    options_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    correct_answer_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    test: Mapped[TeacherAuthoredTest] = relationship(back_populates="questions")


class GroupTeacherAssignment(Base):
    __tablename__ = "group_teacher_assignments"
    __table_args__ = (
        UniqueConstraint("group_id", "teacher_membership_id", name="uq_group_teacher_assignment"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    teacher_membership_id: Mapped[int] = mapped_column(
        ForeignKey("institution_memberships.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assigned_by_membership_id: Mapped[int | None] = mapped_column(
        ForeignKey("institution_memberships.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    group: Mapped[Group] = relationship(back_populates="teacher_assignments")
    teacher_membership: Mapped[InstitutionMembership] = relationship(
        back_populates="assigned_groups",
        foreign_keys=[teacher_membership_id],
    )
    assigned_by_membership: Mapped[InstitutionMembership | None] = relationship(
        back_populates="assigned_by_group_links",
        foreign_keys=[assigned_by_membership_id],
    )


class TestReviewRequest(Base):
    __tablename__ = "test_review_requests"
    __table_args__ = (
        Index("ix_test_review_requests_institution_status", "institution_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    institution_id: Mapped[int] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    test_id: Mapped[int] = mapped_column(
        ForeignKey("teacher_authored_tests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    submitted_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[TestModerationStatus] = mapped_column(
        Enum(
            TestModerationStatus,
            name="test_moderation_status",
            create_type=False,
        ),
        nullable=False,
        index=True,
    )
    requested_by_membership_id: Mapped[int] = mapped_column(
        ForeignKey("institution_memberships.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reviewer_membership_id: Mapped[int | None] = mapped_column(
        ForeignKey("institution_memberships.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    test: Mapped[TeacherAuthoredTest] = relationship(back_populates="review_requests")
    requested_by_membership: Mapped[InstitutionMembership] = relationship(
        back_populates="review_requests_authored",
        foreign_keys=[requested_by_membership_id],
    )
    reviewer_membership: Mapped[InstitutionMembership | None] = relationship(
        back_populates="review_requests_handled",
        foreign_keys=[reviewer_membership_id],
    )


class TestAssignment(Base):
    __tablename__ = "test_assignments"
    __table_args__ = (
        UniqueConstraint("test_id", "group_id", name="uq_test_assignment_test_group"),
        Index("ix_test_assignments_group_id", "group_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    test_id: Mapped[int] = mapped_column(
        ForeignKey("teacher_authored_tests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    assigned_by_membership_id: Mapped[int | None] = mapped_column(
        ForeignKey("institution_memberships.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    test: Mapped[TeacherAuthoredTest] = relationship(back_populates="assignments")
    group: Mapped[Group] = relationship(back_populates="test_assignments")
    assigned_by_membership: Mapped[InstitutionMembership | None] = relationship(
        back_populates="test_assignments",
        foreign_keys=[assigned_by_membership_id],
    )


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_is_read", "user_id", "is_read"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    institution_id: Mapped[int | None] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    data_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user: Mapped[User] = relationship(back_populates="received_notifications")
    institution: Mapped[Institution | None] = relationship(back_populates="notifications")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_institution_action", "institution_id", "action", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    institution_id: Mapped[int | None] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    institution: Mapped[Institution | None] = relationship(back_populates="audit_logs")
    actor: Mapped[User | None] = relationship(back_populates="audit_events")


class StudentProfile(Base):
    __tablename__ = "student_profiles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id", ondelete="SET NULL"), nullable=True)
    preferred_language: Mapped[PreferredLanguage] = mapped_column(Enum(PreferredLanguage), default=PreferredLanguage.ru)
    education_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    direction: Mapped[str | None] = mapped_column(String(255), nullable=True)

    user: Mapped[User] = relationship(back_populates="student_profile")
    group: Mapped[Group | None] = relationship(back_populates="profiles")


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name_ru: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    name_kz: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)

    tests: Mapped[list[Test]] = relationship(back_populates="subject")


class CatalogQuestion(Base):
    __tablename__ = "catalog_questions"
    __table_args__ = (
        UniqueConstraint(
            "subject_id",
            "language",
            "mode",
            "difficulty",
            "content_hash",
            name="uq_catalog_question_content",
        ),
        CheckConstraint(
            "("
            "(type = 'single_choice' AND correct_options_count = 1) OR "
            "(type = 'multi_choice' AND correct_options_count >= 1) OR "
            "(type NOT IN ('single_choice', 'multi_choice') AND correct_options_count = 0)"
            ")",
            name="ck_catalog_correct_options_count",
        ),
        Index(
            "ix_catalog_questions_subject_language_mode_difficulty_status",
            "subject_id",
            "language",
            "mode",
            "difficulty",
            "status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), index=True, nullable=False)
    status: Mapped[CatalogQuestionStatus] = mapped_column(
        Enum(CatalogQuestionStatus),
        default=CatalogQuestionStatus.draft,
        nullable=False,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(64), default="question_bank", nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    language: Mapped[PreferredLanguage] = mapped_column(Enum(PreferredLanguage), nullable=False, index=True)
    mode: Mapped[TestMode] = mapped_column(Enum(TestMode), nullable=False, index=True)
    difficulty: Mapped[DifficultyLevel] = mapped_column(Enum(DifficultyLevel), nullable=False, index=True)
    type: Mapped[QuestionType] = mapped_column(Enum(QuestionType), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    options_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    correct_answer_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    explanation_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    topic_tags_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    correct_options_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    subject: Mapped[Subject] = relationship()


class StudentQuestionCoverage(Base):
    __tablename__ = "student_question_coverage"
    __table_args__ = (
        UniqueConstraint("student_id", "catalog_question_id", name="uq_student_catalog_question"),
        Index("ix_student_question_coverage_student_catalog", "student_id", "catalog_question_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    catalog_question_id: Mapped[int] = mapped_column(
        ForeignKey("catalog_questions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    seen_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    solved_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    correct_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    wrong_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_correct_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    student: Mapped[User] = relationship()
    catalog_question: Mapped[CatalogQuestion] = relationship()


class Test(Base):
    __tablename__ = "tests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), index=True)
    difficulty: Mapped[DifficultyLevel] = mapped_column(Enum(DifficultyLevel), nullable=False)
    language: Mapped[PreferredLanguage] = mapped_column(Enum(PreferredLanguage), nullable=False)
    mode: Mapped[TestMode] = mapped_column(Enum(TestMode), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    student: Mapped[User] = relationship(back_populates="tests")
    subject: Mapped[Subject] = relationship(back_populates="tests")
    questions: Mapped[list[Question]] = relationship(back_populates="test", cascade="all, delete-orphan")
    session: Mapped[TestSession | None] = relationship(back_populates="test", uselist=False, cascade="all, delete-orphan")
    result: Mapped[Result | None] = relationship(back_populates="test", uselist=False, cascade="all, delete-orphan")
    recommendation: Mapped[Recommendation | None] = relationship(
        back_populates="test",
        uselist=False,
        cascade="all, delete-orphan",
    )


class TestSession(Base):
    __tablename__ = "test_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    test_id: Mapped[int] = mapped_column(ForeignKey("tests.id", ondelete="CASCADE"), unique=True, index=True)
    time_limit_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    warning_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exam_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    exam_config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    elapsed_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    warning_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    warning_events_json: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(32), default="unified_v1", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    test: Mapped[Test] = relationship(back_populates="session")


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    test_id: Mapped[int] = mapped_column(ForeignKey("tests.id", ondelete="CASCADE"), index=True)
    type: Mapped[QuestionType] = mapped_column(Enum(QuestionType), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    options_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    correct_answer_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    explanation_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    tts_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    test: Mapped[Test] = relationship(back_populates="questions")
    answers: Mapped[list[Answer]] = relationship(back_populates="question", cascade="all, delete-orphan")


class Answer(Base):
    __tablename__ = "answers"
    __table_args__ = (
        UniqueConstraint("question_id", name="uq_answer_question"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    student_answer_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    score: Mapped[float] = mapped_column(Float, default=0.0)

    question: Mapped[Question] = relationship(back_populates="answers")


class AttemptQuestionEvent(Base):
    __tablename__ = "attempt_question_events"
    __table_args__ = (
        Index("ix_attempt_question_events_test_created_at", "test_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    test_id: Mapped[int] = mapped_column(ForeignKey("tests.id", ondelete="CASCADE"), index=True, nullable=False)
    question_id: Mapped[int | None] = mapped_column(
        ForeignKey("questions.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    catalog_question_id: Mapped[int | None] = mapped_column(
        ForeignKey("catalog_questions.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), default="answered", nullable=False)
    student_answer_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    warning_count_snapshot: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    test: Mapped[Test] = relationship()
    question: Mapped[Question | None] = relationship()
    catalog_question: Mapped[CatalogQuestion | None] = relationship()
    student: Mapped[User] = relationship()


class Result(Base):
    __tablename__ = "results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    test_id: Mapped[int] = mapped_column(ForeignKey("tests.id", ondelete="CASCADE"), unique=True)
    total_score: Mapped[float] = mapped_column(Float, nullable=False)
    max_score: Mapped[float] = mapped_column(Float, nullable=False)
    percent: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    test: Mapped[Test] = relationship(back_populates="result")


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    test_id: Mapped[int] = mapped_column(ForeignKey("tests.id", ondelete="CASCADE"), unique=True)
    weak_topics_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    advice_text: Mapped[str] = mapped_column(Text, nullable=False)
    advice_text_ru: Mapped[str | None] = mapped_column(Text, nullable=True)
    advice_text_kz: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_tasks_json: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    generated_tasks_ru_json: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    generated_tasks_kz_json: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    test: Mapped[Test] = relationship(back_populates="recommendation")
