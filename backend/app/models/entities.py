from __future__ import annotations

import enum
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
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


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    teacher_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)

    profiles: Mapped[list[StudentProfile]] = relationship(back_populates="group")
    memberships: Mapped[list[GroupMembership]] = relationship(back_populates="group", cascade="all, delete-orphan")
    teacher: Mapped[User | None] = relationship(back_populates="groups_created")
    invitations: Mapped[list[GroupInvitation]] = relationship(back_populates="group")
    custom_test_links: Mapped[list[TeacherAuthoredTestGroup]] = relationship(
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
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    time_limit_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    warning_limit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    teacher: Mapped[User] = relationship(back_populates="custom_tests_created")
    group_links: Mapped[list[TeacherAuthoredTestGroup]] = relationship(
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

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    student_answer_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    score: Mapped[float] = mapped_column(Float, default=0.0)

    question: Mapped[Question] = relationship(back_populates="answers")


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
