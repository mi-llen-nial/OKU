from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.models import DifficultyLevel, PreferredLanguage, QuestionType, TestMode


class GenerateTestRequest(BaseModel):
    subject_id: int
    difficulty: DifficultyLevel
    language: PreferredLanguage
    mode: TestMode
    num_questions: int = Field(default=10, ge=3, le=30)
    time_limit_minutes: int | None = Field(default=None, ge=5, le=60)

    @field_validator("time_limit_minutes")
    @classmethod
    def validate_time_limit_minutes(cls, value: int | None) -> int | None:
        if value is None:
            return value
        if value not in {5, 10, 20, 30, 60}:
            raise ValueError("time_limit_minutes должен быть одним из значений: 5, 10, 20, 30, 60")
        return value


class GenerateMistakesTestRequest(BaseModel):
    subject_id: int | None = None
    difficulty: DifficultyLevel = DifficultyLevel.medium
    language: PreferredLanguage | None = None
    num_questions: int = Field(default=10, ge=1, le=30)


class GenerateExamTestRequest(BaseModel):
    exam_type: Literal["ent", "ielts"]
    language: PreferredLanguage = PreferredLanguage.ru
    ent_profile_subject_id: int | None = None


class GeneratedQuestionPayload(BaseModel):
    type: QuestionType
    prompt: str
    options_json: dict[str, Any] | None = None
    correct_answer_json: dict[str, Any]
    explanation_json: dict[str, Any]
    tts_text: str | None = None


class GeneratedTestPayload(BaseModel):
    seed: str
    questions: list[GeneratedQuestionPayload]


class QuestionResponse(BaseModel):
    id: int
    type: QuestionType
    prompt: str
    options_json: dict[str, Any] | None = None
    tts_text: str | None = None

    model_config = {"from_attributes": True}


class TestResponse(BaseModel):
    id: int
    student_id: int
    subject_id: int
    difficulty: DifficultyLevel
    language: PreferredLanguage
    mode: TestMode
    time_limit_seconds: int | None = None
    warning_limit: int | None = None
    exam_kind: str | None = None
    exam_config_json: dict[str, Any] | None = None
    created_at: datetime
    questions: list[QuestionResponse]

    model_config = {"from_attributes": True}


class SubmitAnswerItem(BaseModel):
    question_id: int
    student_answer_json: dict[str, Any]


class TestWarningSignal(BaseModel):
    type: str
    at_seconds: int = Field(default=0, ge=0)
    question_id: int | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class TestTelemetryPayload(BaseModel):
    elapsed_seconds: int | None = Field(default=None, ge=0)
    warnings: list[TestWarningSignal] = Field(default_factory=list)


class SubmitTestRequest(BaseModel):
    answers: list[SubmitAnswerItem]
    telemetry: TestTelemetryPayload | None = None


class QuestionFeedback(BaseModel):
    question_id: int
    prompt: str
    topic: str
    student_answer: dict[str, Any]
    expected_hint: dict[str, Any]
    is_correct: bool
    score: float
    explanation: str


class ResultResponse(BaseModel):
    total_score: float
    max_score: float
    percent: float
    elapsed_seconds: int = 0
    time_limit_seconds: int | None = None
    warning_count: int = 0


class RecommendationResponse(BaseModel):
    weak_topics: list[str]
    advice_text: str
    generated_tasks: list[dict[str, Any]]


class SubmitTestResponse(BaseModel):
    test_id: int
    result: ResultResponse
    integrity_warnings: list[TestWarningSignal] = Field(default_factory=list)
    feedback: list[QuestionFeedback]
    recommendation: RecommendationResponse


class TestResultDetailsResponse(BaseModel):
    test_id: int
    submitted_at: datetime
    result: ResultResponse
    integrity_warnings: list[TestWarningSignal] = Field(default_factory=list)
    feedback: list[QuestionFeedback]
    recommendation: RecommendationResponse


class HistoryItemResponse(BaseModel):
    test_id: int
    subject_id: int
    subject_name: str
    exam_kind: str | None = None
    difficulty: DifficultyLevel
    language: PreferredLanguage
    mode: TestMode
    created_at: datetime
    percent: float
    warning_count: int = 0
    weak_topics: list[str]


class ProgressPoint(BaseModel):
    date: str
    percent: float


class SubjectStat(BaseModel):
    subject_id: int
    subject_name: str
    tests_count: int
    avg_percent: float


class StudentProgressResponse(BaseModel):
    total_tests: int
    total_warnings: int = 0
    avg_percent: float
    best_percent: float
    weak_topics: list[str]
    trend: list[ProgressPoint]
    subject_stats: list[SubjectStat]


class StudentDashboardResponse(BaseModel):
    progress: StudentProgressResponse
    history: list[HistoryItemResponse]


class GroupTestSummaryResponse(BaseModel):
    custom_test_id: int
    title: str
    questions_count: int
    duration_minutes: int
    warning_limit: int
    teacher_name: str
    group_id: int
    group_name: str
    created_at: datetime
