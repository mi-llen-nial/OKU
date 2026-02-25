from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models import DifficultyLevel, PreferredLanguage, QuestionType, TestMode


class GenerateTestRequest(BaseModel):
    subject_id: int
    difficulty: DifficultyLevel
    language: PreferredLanguage
    mode: TestMode
    num_questions: int = Field(default=10, ge=3, le=30)


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
    created_at: datetime
    questions: list[QuestionResponse]

    model_config = {"from_attributes": True}


class SubmitAnswerItem(BaseModel):
    question_id: int
    student_answer_json: dict[str, Any]


class SubmitTestRequest(BaseModel):
    answers: list[SubmitAnswerItem]


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


class RecommendationResponse(BaseModel):
    weak_topics: list[str]
    advice_text: str
    generated_tasks: list[dict[str, Any]]


class SubmitTestResponse(BaseModel):
    test_id: int
    result: ResultResponse
    feedback: list[QuestionFeedback]
    recommendation: RecommendationResponse


class TestResultDetailsResponse(BaseModel):
    test_id: int
    submitted_at: datetime
    result: ResultResponse
    feedback: list[QuestionFeedback]
    recommendation: RecommendationResponse


class HistoryItemResponse(BaseModel):
    test_id: int
    subject_id: int
    subject_name: str
    difficulty: DifficultyLevel
    language: PreferredLanguage
    mode: TestMode
    created_at: datetime
    percent: float
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
    avg_percent: float
    best_percent: float
    weak_topics: list[str]
    trend: list[ProgressPoint]
    subject_stats: list[SubjectStat]
