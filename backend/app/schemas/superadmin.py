from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class InstitutionCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)


class InstitutionListItem(BaseModel):
    id: int
    name: str
    normalized_name: str
    is_active: bool
    created_at: datetime


class InstitutionListResponse(BaseModel):
    institutions: list[InstitutionListItem] = Field(default_factory=list)


class InstitutionDetailsResponse(BaseModel):
    id: int
    name: str
    normalized_name: str
    is_active: bool
    created_at: datetime
    created_by_user_id: int | None = None


class BootstrapInviteCreateRequest(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    expires_in_hours: int | None = Field(default=72, ge=1, le=24 * 30)
    note: str | None = Field(default=None, max_length=2000)


class BootstrapInviteResponse(BaseModel):
    id: int
    institution_id: int
    email: str
    token: str
    expires_at: datetime
    created_at: datetime
    note: str | None = None

