from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models import (
    InstitutionMembershipRole,
    InstitutionMembershipStatus,
    TeacherApplicationStatus,
    TestModerationStatus,
)


class InstitutionBriefResponse(BaseModel):
    id: int
    name: str


class InstitutionListItemResponse(InstitutionBriefResponse):
    role: InstitutionMembershipRole
    status: InstitutionMembershipStatus
    is_primary: bool


class InstitutionContextResponse(BaseModel):
    institution: InstitutionBriefResponse
    membership: "InstitutionMembershipResponse"


class TeacherApplicationCreateRequest(BaseModel):
    institution_id: int | None = Field(default=None, ge=1)
    institution_name: str | None = Field(default=None, min_length=2, max_length=255)
    full_name: str = Field(min_length=2, max_length=255)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    subject: str | None = Field(default=None, max_length=255)
    position: str | None = Field(default=None, max_length=255)
    additional_info: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_institution_target(self) -> "TeacherApplicationCreateRequest":
        if self.institution_id is None and not (self.institution_name or "").strip():
            raise ValueError("Укажите institution_id или institution_name.")
        return self


class TeacherApplicationResponse(BaseModel):
    id: int
    applicant_user_id: int
    institution: InstitutionBriefResponse
    full_name: str
    email: str
    subject: str | None = None
    position: str | None = None
    additional_info: str | None = None
    status: TeacherApplicationStatus
    reviewer_comment: str | None = None
    created_at: datetime
    decided_at: datetime | None = None


class TeacherApplicationDecisionRequest(BaseModel):
    action: Literal["approve", "reject", "suspend", "revoke"]
    comment: str | None = Field(default=None, max_length=2000)


class InstitutionMembershipResponse(BaseModel):
    id: int
    user_id: int
    institution_id: int
    role: InstitutionMembershipRole
    status: InstitutionMembershipStatus
    is_primary: bool
    full_name: str | None = None
    username: str
    email: str
    created_at: datetime
    updated_at: datetime


class InstitutionMemberListItemResponse(InstitutionMembershipResponse):
    roles: list[InstitutionMembershipRole] = Field(default_factory=list)
    statuses: list[InstitutionMembershipStatus] = Field(default_factory=list)
    teacher_membership_id: int | None = None


class InstitutionGroupCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class InstitutionGroupAssignTeacherRequest(BaseModel):
    teacher_membership_id: int = Field(ge=1)


class InstitutionGroupTeacherResponse(BaseModel):
    membership_id: int
    user_id: int
    full_name: str | None = None
    username: str
    email: str


class InstitutionGroupResponse(BaseModel):
    id: int
    name: str
    institution_id: int
    members_count: int
    teachers: list[InstitutionGroupTeacherResponse] = Field(default_factory=list)


class InstitutionStudentMembershipAssignRequest(BaseModel):
    student_user_id: int = Field(ge=1)


class InstitutionGroupStudentResponse(BaseModel):
    user_id: int
    username: str
    full_name: str | None = None
    email: str


class InstitutionGroupDetailsResponse(InstitutionGroupResponse):
    students: list[InstitutionGroupStudentResponse] = Field(default_factory=list)


class AssignMethodistRequest(BaseModel):
    user_id: int = Field(ge=1)
    make_primary: bool = False


class TestReviewQueueItemResponse(BaseModel):
    test_id: int
    title: str
    teacher_user_id: int
    teacher_name: str
    moderation_status: TestModerationStatus
    submitted_for_review_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    questions_count: int


class ReviewDecisionRequest(BaseModel):
    status: Literal["approved", "rejected", "needs_revision"]
    comment: str | None = Field(default=None, max_length=2000)


class ReviewDetailsQuestionResponse(BaseModel):
    id: int
    order_index: int
    prompt: str
    question_type: str


class ReviewDetailsResponse(BaseModel):
    test_id: int
    institution_id: int
    title: str
    teacher_user_id: int
    teacher_name: str
    warning_limit: int
    duration_minutes: int
    due_date: date | None = None
    moderation_status: TestModerationStatus
    moderation_comment: str | None = None
    current_draft_version: int
    approved_version: int | None = None
    submitted_for_review_at: datetime | None = None
    reviewed_at: datetime | None = None
    questions: list[ReviewDetailsQuestionResponse] = Field(default_factory=list)


class AssignApprovedTestRequest(BaseModel):
    group_ids: list[int] = Field(default_factory=list, min_length=1, max_length=100)


class SubmitReviewRequestResponse(BaseModel):
    test_id: int
    status: TestModerationStatus
    current_draft_version: int
    submitted_for_review_at: datetime
