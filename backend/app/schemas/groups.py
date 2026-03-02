from datetime import datetime

from pydantic import BaseModel, Field

from app.models import InvitationStatus


class TeacherGroupListItem(BaseModel):
    id: int
    name: str
    members_count: int


class TeacherGroupCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    student_ids: list[int] = Field(default_factory=list, max_length=5)


class TeacherGroupCreateResponse(BaseModel):
    id: int
    name: str
    members_count: int


class TeacherGroupUpdateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class GroupMemberResponse(BaseModel):
    student_id: int
    username: str
    full_name: str | None
    tests_count: int
    avg_percent: float
    warnings_count: int
    weak_topic: str | None = None
    last_activity_at: datetime | None = None


class GroupMembersResponse(BaseModel):
    id: int
    name: str
    members: list[GroupMemberResponse]


class TeacherInvitationCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=26, pattern=r"^@?[A-Za-z0-9_]+$")
    group_id: int | None = None


class TeacherInvitationResponse(BaseModel):
    id: int
    teacher_id: int
    teacher_name: str
    student_id: int
    student_username: str
    student_name: str | None
    group_id: int | None
    group_name: str | None
    status: InvitationStatus
    created_at: datetime
    responded_at: datetime | None
