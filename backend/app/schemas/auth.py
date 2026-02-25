from datetime import datetime

from pydantic import BaseModel, Field

from app.models import PreferredLanguage, UserRole


class RegisterRequest(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    role: UserRole = UserRole.student
    preferred_language: PreferredLanguage = PreferredLanguage.ru
    group_id: int | None = None


class LoginRequest(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=6, max_length=128)


class UserResponse(BaseModel):
    id: int
    role: UserRole
    email: str
    username: str
    created_at: datetime
    preferred_language: PreferredLanguage | None = None
    group_id: int | None = None

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
