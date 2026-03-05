from datetime import datetime
import enum

from pydantic import BaseModel, Field, field_validator

from app.models import PreferredLanguage, UserRole


class EducationLevel(str, enum.Enum):
    school = "school"
    college = "college"
    university = "university"


class RegisterRequest(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    full_name: str = Field(min_length=2, max_length=255)
    username: str = Field(min_length=3, max_length=25, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=6, max_length=128)
    role: UserRole = UserRole.student
    preferred_language: PreferredLanguage = PreferredLanguage.ru
    education_level: EducationLevel | None = EducationLevel.school
    direction: str | None = Field(default=None, min_length=2, max_length=255)
    group_id: int | None = None
    email_verification_code: str | None = Field(default=None, min_length=6, max_length=6, pattern=r"^\d{6}$")

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("Имя пользователя не может быть пустым")
        return normalized

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        if len(value) > 25:
            raise ValueError("Имя пользователя должно быть не длиннее 25 символов")
        return value


class LoginRequest(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=6, max_length=128)
    remember_me: bool = False


class SendRegisterCodeRequest(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class SendRegisterCodeResponse(BaseModel):
    message: str
    expires_in_seconds: int


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=16, max_length=4096)


class UserResponse(BaseModel):
    id: int
    role: UserRole
    email: str
    full_name: str | None = None
    username: str
    created_at: datetime
    preferred_language: PreferredLanguage | None = None
    education_level: EducationLevel | None = None
    direction: str | None = None
    group_id: int | None = None

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    user: UserResponse


class TokenRefreshResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
