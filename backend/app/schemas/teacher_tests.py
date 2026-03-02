from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


AnswerType = Literal["choice", "free_text"]


class TeacherCustomQuestionInput(BaseModel):
    prompt: str = Field(min_length=5, max_length=2000)
    answer_type: AnswerType
    options: list[str] = Field(default_factory=list, max_length=8)
    correct_option_index: int | None = None
    sample_answer: str | None = Field(default=None, max_length=2000)

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
    group_ids: list[int] = Field(default_factory=list, min_length=1, max_length=20)
    questions: list[TeacherCustomQuestionInput] = Field(min_length=1, max_length=120)


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


class TeacherCustomTestListItem(BaseModel):
    id: int
    title: str
    duration_minutes: int
    warning_limit: int
    questions_count: int
    groups: list[TeacherCustomGroupBrief] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class TeacherCustomTestResponse(TeacherCustomTestListItem):
    questions: list[TeacherCustomQuestionResponse]
