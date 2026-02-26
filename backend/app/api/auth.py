from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.core.deps import DBSession
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models import Group, GroupMembership, PreferredLanguage, StudentProfile, User, UserRole
from app.schemas.auth import AuthResponse, EducationLevel, LoginRequest, RegisterRequest, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse)
def register(payload: RegisterRequest, db: DBSession) -> AuthResponse:
    email_value = payload.email.strip().lower()
    username_value = payload.username.strip()

    email_exists = db.scalar(select(User).where(func.lower(User.email) == email_value))
    if email_exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Пользователь с такой почтой уже существует")

    username_exists = db.scalar(select(User).where(func.lower(User.username) == username_value.lower()))
    if username_exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Пользователь с таким именем пользователя уже существует")

    user = User(
        email=email_value,
        full_name=payload.full_name,
        username=username_value,
        password_hash=get_password_hash(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.flush()

    if payload.role == UserRole.student:
        group_id = payload.group_id
        if group_id is not None and db.get(Group, group_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Группа не найдена")

        profile = StudentProfile(
            user_id=user.id,
            preferred_language=payload.preferred_language or PreferredLanguage.ru,
            education_level=(payload.education_level.value if payload.education_level else None),
            direction=(payload.direction.strip() if payload.direction else None),
            group_id=group_id,
        )
        db.add(profile)

        if group_id is not None:
            db.add(GroupMembership(student_id=user.id, group_id=group_id))

    db.commit()
    db.refresh(user)

    token = create_access_token(user.id)
    return AuthResponse(access_token=token, user=_build_user_response(user))


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: DBSession) -> AuthResponse:
    email_value = payload.email.strip().lower()
    user = db.scalar(select(User).where(func.lower(User.email) == email_value))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверная почта или пароль")

    token = create_access_token(user.id)
    return AuthResponse(access_token=token, user=_build_user_response(user))


def _build_user_response(user: User) -> UserResponse:
    preferred_language = user.student_profile.preferred_language if user.student_profile else None
    education_level_raw = user.student_profile.education_level if user.student_profile else None
    education_level = None
    if education_level_raw:
        try:
            education_level = EducationLevel(education_level_raw)
        except ValueError:
            education_level = None
    direction = user.student_profile.direction if user.student_profile else None
    group_id = user.student_profile.group_id if user.student_profile else None
    return UserResponse(
        id=user.id,
        role=user.role,
        email=user.email,
        full_name=user.full_name,
        username=user.username,
        created_at=user.created_at,
        preferred_language=preferred_language,
        education_level=education_level,
        direction=direction,
        group_id=group_id,
    )
