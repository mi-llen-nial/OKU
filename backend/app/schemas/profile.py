from datetime import datetime

from pydantic import BaseModel

from app.models import InvitationStatus, PreferredLanguage, UserRole


class ProfileInvitationResponse(BaseModel):
    id: int
    teacher_id: int
    teacher_name: str
    group_id: int | None
    group_name: str | None
    status: InvitationStatus
    created_at: datetime
    responded_at: datetime | None


class ProfileResponse(BaseModel):
    id: int
    role: UserRole
    email: str
    full_name: str | None
    username: str
    preferred_language: PreferredLanguage | None
    education_level: str | None
    direction: str | None
    group_id: int | None
    group_name: str | None
    invitations: list[ProfileInvitationResponse]
