from __future__ import annotations

import base64
import binascii
from datetime import date, datetime
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models import DifficultyLevel, PreferredLanguage, TestModerationStatus


AnswerType = Literal["choice", "free_text"]
MAX_QUESTION_IMAGE_BYTES = 1 * 1024 * 1024
IMAGE_DATA_URL_PATTERN = re.compile(
    r"^data:image/(png|jpeg|jpg|webp|gif);base64,([A-Za-z0-9+/=\s]+)$",
    flags=re.IGNORECASE,
)


class TeacherCustomQuestionInput(BaseModel):
    prompt: str = Field(min_length=5, max_length=2000)
    answer_type: AnswerType
    options: list[str] = Field(default_factory=list, max_length=8)
    correct_option_index: int | None = None
    sample_answer: str | None = Field(default=None, max_length=2000)
    image_data_url: str | None = Field(default=None, max_length=10_000_000)

    @field_validator("image_data_url")
    @classmethod
    def validate_image_data_url(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        if not normalized:
            return None

        matched = IMAGE_DATA_URL_PATTERN.match(normalized)
        if not matched:
            raise ValueError("Поддерживаются только изображения в формате data:image/*;base64.")

        raw_base64 = re.sub(r"\s+", "", matched.group(2))
        try:
            decoded = base64.b64decode(raw_base64, validate=True)
        except binascii.Error as exc:
            raise ValueError("Некорректный base64 в изображении.") from exc

        if len(decoded) > MAX_QUESTION_IMAGE_BYTES:
            raise ValueError("Размер изображения не должен превышать 1MB.")

        mime = matched.group(1).lower()
        return f"data:image/{mime};base64,{raw_base64}"

    @model_validator(mode="after")
    def validate_payload(self) -> "TeacherCustomQuestionInput":
        if self.answer_type == "choice":
            cleaned = [item.strip() for item in self.options if item and item.strip()]
            if len(cleaned) < 2:
                raise ValueError("Для вопроса с вариантами нужно минимум 2 варианта ответа.")
            if self.correct_option_index is None:
                raise ValueError("Выберите правильный вариант ответа.")
            if self.correct_option_index < 0 or self.correct_option_index >= len(cleaned):
                raise ValueError("Индекс правильного ответа вне диапазона вариантов.")
            self.options = cleaned
            self.sample_answer = None
            return self

        sample = (self.sample_answer or "").strip()
        if not sample:
            raise ValueError("Для свободного ответа укажите эталонный ответ.")
        self.sample_answer = sample
        self.options = []
        self.correct_option_index = None
        return self


class TeacherCustomTestCreateRequest(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    duration_minutes: int = Field(ge=1, le=300)
    warning_limit: int = Field(ge=0, le=20, default=0)
    due_date: date | None = None
    group_ids: list[int] = Field(default_factory=list, max_length=20)
    questions: list[TeacherCustomQuestionInput] = Field(min_length=1, max_length=120)


class TeacherCustomTestUpdateRequest(TeacherCustomTestCreateRequest):
    pass


class TeacherCustomMaterialGenerateRequest(BaseModel):
    topic: str = Field(min_length=2, max_length=160)
    difficulty: DifficultyLevel = DifficultyLevel.medium
    questions_count: int = Field(ge=1, le=120, default=10)
    language: PreferredLanguage = PreferredLanguage.ru


class TeacherCustomMaterialQuestion(BaseModel):
    prompt: str
    answer_type: AnswerType
    options: list[str] = Field(default_factory=list)
    correct_option_index: int | None = None
    sample_answer: str | None = None
    image_data_url: str | None = None


class TeacherCustomMaterialGenerateResponse(BaseModel):
    topic: str
    difficulty: DifficultyLevel
    questions_count: int
    rejected_count: int = 0
    questions: list[TeacherCustomMaterialQuestion]


class TeacherCustomMaterialParseResponse(BaseModel):
    source_filename: str
    questions_count: int
    questions: list[TeacherCustomMaterialQuestion]


class TeacherCustomGroupBrief(BaseModel):
    id: int
    name: str


class TeacherCustomQuestionResponse(BaseModel):
    id: int
    order_index: int
    prompt: str
    answer_type: AnswerType
    options: list[str] = Field(default_factory=list)
    correct_option_index: int | None = None
    sample_answer: str | None = None
    image_data_url: str | None = None


class TeacherCustomTestListItem(BaseModel):
    id: int
    title: str
    duration_minutes: int
    warning_limit: int
    due_date: date | None = None
    questions_count: int
    groups: list[TeacherCustomGroupBrief] = Field(default_factory=list)
    moderation_status: TestModerationStatus = TestModerationStatus.draft
    moderation_comment: str | None = None
    submitted_for_review_at: datetime | None = None
    reviewed_at: datetime | None = None
    current_draft_version: int = 1
    approved_version: int | None = None
    created_at: datetime
    updated_at: datetime


class TeacherCustomTestResponse(TeacherCustomTestListItem):
    questions: list[TeacherCustomQuestionResponse]


class TeacherCustomTestResultsGroupItem(BaseModel):
    id: int
    name: str
    members_count: int
    selected: bool = False


class TeacherCustomTestResultsStudentItem(BaseModel):
    student_id: int
    full_name: str
    group_id: int
    group_name: str
    percent: float | None = None
    warning_count: int | None = None
    submitted_at: datetime | None = None
    latest_test_id: int | None = None


class TeacherCustomTestResultsResponse(BaseModel):
    custom_test_id: int
    title: str
    questions_count: int
    warning_limit: int
    due_date: date | None = None
    groups: list[TeacherCustomTestResultsGroupItem] = Field(default_factory=list)
    students: list[TeacherCustomTestResultsStudentItem] = Field(default_factory=list)


class TeacherCustomTestSubmitReviewResponse(BaseModel):
    test_id: int
    status: TestModerationStatus
    current_draft_version: int
    submitted_for_review_at: datetime


class TeacherCustomTestAssignRequest(BaseModel):
    group_ids: list[int] = Field(default_factory=list, min_length=1, max_length=100)


class TeacherCustomTestAssignResponse(BaseModel):
    test_id: int
    status: TestModerationStatus
    assigned_group_ids: list[int] = Field(default_factory=list)
