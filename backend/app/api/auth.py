from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.deps import DBSession
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models import Group, GroupMembership, PreferredLanguage, StudentProfile, User, UserRole
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse)
def register(payload: RegisterRequest, db: DBSession) -> AuthResponse:
    email_exists = db.scalar(select(User).where(User.email == payload.email))
    if email_exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists")

    username_exists = db.scalar(select(User).where(User.username == payload.username))
    if username_exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")

    user = User(
        email=payload.email,
        username=payload.username,
        password_hash=get_password_hash(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.flush()

    if payload.role == UserRole.student:
        group_id = payload.group_id
        if group_id is not None and db.get(Group, group_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

        profile = StudentProfile(
            user_id=user.id,
            preferred_language=payload.preferred_language or PreferredLanguage.ru,
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
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    token = create_access_token(user.id)
    return AuthResponse(access_token=token, user=_build_user_response(user))


def _build_user_response(user: User) -> UserResponse:
    preferred_language = user.student_profile.preferred_language if user.student_profile else None
    group_id = user.student_profile.group_id if user.student_profile else None
    return UserResponse(
        id=user.id,
        role=user.role,
        email=user.email,
        username=user.username,
        created_at=user.created_at,
        preferred_language=preferred_language,
        group_id=group_id,
    )
