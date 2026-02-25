from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
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


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.student, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
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


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)

    profiles: Mapped[list[StudentProfile]] = relationship(back_populates="group")
    memberships: Mapped[list[GroupMembership]] = relationship(back_populates="group", cascade="all, delete-orphan")


class GroupMembership(Base):
    __tablename__ = "group_memberships"
    __table_args__ = (UniqueConstraint("student_id", "group_id", name="uq_student_group"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), index=True)

    student: Mapped[User] = relationship(back_populates="memberships")
    group: Mapped[Group] = relationship(back_populates="memberships")


class StudentProfile(Base):
    __tablename__ = "student_profiles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id", ondelete="SET NULL"), nullable=True)
    preferred_language: Mapped[PreferredLanguage] = mapped_column(Enum(PreferredLanguage), default=PreferredLanguage.ru)

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
    generated_tasks_json: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    test: Mapped[Test] = relationship(back_populates="recommendation")
