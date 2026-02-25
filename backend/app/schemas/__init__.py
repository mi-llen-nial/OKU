from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserResponse
from app.schemas.subjects import SubjectResponse
from app.schemas.teacher import GroupAnalyticsResponse, GroupWeakTopicsResponse
from app.schemas.tests import (
    GenerateTestRequest,
    GeneratedQuestionPayload,
    GeneratedTestPayload,
    HistoryItemResponse,
    QuestionFeedback,
    QuestionResponse,
    RecommendationResponse,
    ResultResponse,
    StudentProgressResponse,
    SubmitAnswerItem,
    SubmitTestRequest,
    SubmitTestResponse,
    TestResponse,
    TestResultDetailsResponse,
)

__all__ = [
    "AuthResponse",
    "LoginRequest",
    "RegisterRequest",
    "UserResponse",
    "SubjectResponse",
    "GroupAnalyticsResponse",
    "GroupWeakTopicsResponse",
    "GenerateTestRequest",
    "GeneratedQuestionPayload",
    "GeneratedTestPayload",
    "HistoryItemResponse",
    "QuestionFeedback",
    "QuestionResponse",
    "RecommendationResponse",
    "ResultResponse",
    "StudentProgressResponse",
    "SubmitAnswerItem",
    "SubmitTestRequest",
    "SubmitTestResponse",
    "TestResponse",
    "TestResultDetailsResponse",
]
