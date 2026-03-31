import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy import delete, func, select

from app.core.config import settings
from app.core.deps import DBSession
from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_password_hash,
    hash_refresh_token,
    verify_password,
)
from app.models import (
    Group,
    GroupMembership,
    Institution,
    InstitutionAdminBootstrapInvite,
    InstitutionMembership,
    InstitutionMembershipRole,
    InstitutionMembershipStatus,
    PreferredLanguage,
    StudentProfile,
    User,
    UserRole,
    UserSession,
)
from app.schemas.auth import (
    AuthResponse,
    EducationLevel,
    InstitutionAdminBootstrapAcceptRequest,
    InstitutionCodeLookupResponse,
    LoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetConfirmResponse,
    PasswordResetRequestPayload,
    PasswordResetRequestResponse,
    RefreshTokenRequest,
    RegisterRequest,
    SendRegisterCodeRequest,
    SendRegisterCodeResponse,
    TokenRefreshResponse,
    UsernameAvailabilityResponse,
    UserResponse,
)
from app.services.audit_logs import audit_log_service
from app.services.notifications import notification_service
from app.services.email_verification import (
    EmailVerificationError,
    EmailVerificationProviderError,
    EmailVerificationRateLimitError,
    email_verification_service,
)
from app.services.password_reset import PasswordResetError, password_reset_service

router = APIRouter(prefix="/auth", tags=["auth"])

_REGISTER_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,25}$")


@router.get("/register/username-available", response_model=UsernameAvailabilityResponse)
def register_username_available(
    db: DBSession,
    username: str = Query(..., min_length=1, max_length=32),
) -> UsernameAvailabilityResponse:
    """Публичная проверка: формат никнейма и отсутствие занятого имени (без учёта регистра)."""
    normalized = username.strip()
    if not _REGISTER_USERNAME_RE.fullmatch(normalized):
        return UsernameAvailabilityResponse(available=False, reason="invalid")
    exists = db.scalar(select(User.id).where(func.lower(User.username) == normalized.lower()))
    if exists:
        return UsernameAvailabilityResponse(available=False, reason="taken")
    return UsernameAvailabilityResponse(available=True)


@router.get("/register/institution-code", response_model=InstitutionCodeLookupResponse)
def register_institution_code_lookup(
    db: DBSession,
    code: str = Query(..., min_length=1, max_length=64),
) -> InstitutionCodeLookupResponse:
    """Публичная проверка кода учебного учреждения для заявки преподавателя."""
    raw = code.strip()
    if not raw:
        return InstitutionCodeLookupResponse(valid=False)
    institution = db.scalar(
        select(Institution).where(
            Institution.is_active.is_(True),
            Institution.join_code.is_not(None),
            func.lower(Institution.join_code) == func.lower(raw),
        )
    )
    if institution is None:
        return InstitutionCodeLookupResponse(valid=False)
    return InstitutionCodeLookupResponse(valid=True, institution_id=int(institution.id), name=str(institution.name))


@router.post("/register", response_model=AuthResponse)
def register(payload: RegisterRequest, request: Request, response: Response, db: DBSession) -> AuthResponse:
    email_value = payload.email.strip().lower()
    username_value = payload.username.strip()

    email_exists = db.scalar(select(User).where(func.lower(User.email) == email_value))
    if email_exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Пользователь с такой почтой уже существует")

    username_exists = db.scalar(select(User).where(func.lower(User.username) == username_value.lower()))
    if username_exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Пользователь с таким именем пользователя уже существует")

    if payload.role in {UserRole.methodist, UserRole.institution_admin, UserRole.superadmin}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Регистрация этой роли через публичную форму недоступна.",
        )

    if settings.email_verification_enabled:
        if not payload.email_verification_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Сначала подтвердите почту кодом из письма.",
            )
        verified = email_verification_service.consume_register_code(
            db=db,
            email=email_value,
            code=payload.email_verification_code,
        )
        if not verified:
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Неверный или истекший код подтверждения почты.",
            )

    # Public sign-up never grants elevated institutional roles directly.
    # Teacher onboarding is handled via teacher application flow after account creation.
    effective_role = UserRole.student

    user = User(
        email=email_value,
        full_name=payload.full_name,
        username=username_value,
        password_hash=get_password_hash(payload.password),
        role=effective_role,
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

    access_token, refresh_token = _create_tokens_for_user(
        db=db,
        user_id=user.id,
        request=request,
    )
    return _build_auth_response(response=response, access_token=access_token, refresh_token=refresh_token, user=user)


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: DBSession) -> AuthResponse:
    email_value = payload.email.strip().lower()
    user = db.scalar(select(User).where(func.lower(User.email) == email_value))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверная почта или пароль")

    access_token, refresh_token = _create_tokens_for_user(
        db=db,
        user_id=user.id,
        request=request,
        remember_me=payload.remember_me,
    )
    return _build_auth_response(
        response=response,
        access_token=access_token,
        refresh_token=refresh_token,
        user=user,
        remember_me=payload.remember_me,
    )


@router.post("/password-reset/request", response_model=PasswordResetRequestResponse)
def password_reset_request(payload: PasswordResetRequestPayload, db: DBSession) -> PasswordResetRequestResponse:
    try:
        message = password_reset_service.request_password_reset(db=db, email=payload.email)
    except PasswordResetError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return PasswordResetRequestResponse(message=message)


@router.post("/password-reset/confirm", response_model=PasswordResetConfirmResponse)
def password_reset_confirm(payload: PasswordResetConfirmRequest, db: DBSession) -> PasswordResetConfirmResponse:
    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Пароли должны совпадать.")

    try:
        message = password_reset_service.confirm_password_reset(
            db=db, token=payload.token, new_password=payload.new_password
        )
    except PasswordResetError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return PasswordResetConfirmResponse(message=message)


@router.post("/register/send-code", response_model=SendRegisterCodeResponse)
def send_register_code(payload: SendRegisterCodeRequest, db: DBSession) -> SendRegisterCodeResponse:
    if not settings.email_verification_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Проверка почты отключена в настройках сервера.",
        )
    try:
        expires_in_seconds = email_verification_service.send_register_code(db=db, email=payload.email)
    except EmailVerificationRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Повторная отправка доступна через {exc.retry_after_seconds} сек.",
        ) from exc
    except EmailVerificationProviderError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except EmailVerificationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    db.commit()
    return SendRegisterCodeResponse(
        message="Код подтверждения отправлен на указанную почту.",
        expires_in_seconds=expires_in_seconds,
    )


@router.post("/refresh", response_model=TokenRefreshResponse)
def refresh_tokens(
    request: Request,
    response: Response,
    db: DBSession,
    payload: RefreshTokenRequest | None = None,
) -> TokenRefreshResponse:
    raw_refresh_token = _extract_refresh_token(payload=payload, request=request)
    if not raw_refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh токен отсутствует")

    try:
        token_payload = decode_refresh_token(raw_refresh_token)
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Некорректный refresh токен") from exc

    user_id = int(token_payload.get("sub") or 0)
    session_id = str(token_payload.get("sid") or "")
    if user_id <= 0 or not session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Некорректный refresh токен")

    session = db.get(UserSession, session_id)
    now = datetime.now(timezone.utc)
    if (
        not session
        or session.user_id != user_id
        or session.revoked_at is not None
        or session.expires_at <= now
        or session.refresh_token_hash != hash_refresh_token(raw_refresh_token)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия неактивна, войдите снова")

    session.last_used_at = now
    new_refresh_token = create_refresh_token(user_id, session.id, expires_delta=timedelta(days=settings.refresh_token_expire_days))
    session.refresh_token_hash = hash_refresh_token(new_refresh_token)
    session.expires_at = now + timedelta(days=settings.refresh_token_expire_days)
    session.user_agent = request.headers.get("user-agent") or session.user_agent
    session.ip_address = _extract_client_ip(request)

    access_token = create_access_token(user_id, session_id=session.id)
    db.commit()

    if settings.use_http_only_refresh_cookie:
        _set_refresh_cookie(response, new_refresh_token)
        return TokenRefreshResponse(access_token=access_token, refresh_token=None)

    return TokenRefreshResponse(access_token=access_token, refresh_token=new_refresh_token)


@router.post("/bootstrap/institution-admin/accept", response_model=AuthResponse)
def accept_institution_admin_bootstrap(
    payload: InstitutionAdminBootstrapAcceptRequest,
    request: Request,
    response: Response,
    db: DBSession,
) -> AuthResponse:
    email_value = payload.email.strip().lower()
    token_value = payload.token.strip()
    if not token_value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Токен приглашения обязателен.")

    invite_hash = hash_refresh_token(token_value)
    invite = db.scalar(
        select(InstitutionAdminBootstrapInvite).where(InstitutionAdminBootstrapInvite.token_hash == invite_hash)
    )
    if invite is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Приглашение не найдено.")
    if invite.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Приглашение отозвано.")
    now = datetime.now(timezone.utc)
    if invite.expires_at <= now:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Срок действия приглашения истек.")
    if invite.consumed_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Приглашение уже использовано.")
    if invite.email.strip().lower() != email_value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email не совпадает с приглашением.")

    institution = db.get(Institution, int(invite.institution_id))
    if institution is None or not institution.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Учреждение не найдено.")

    user = db.scalar(select(User).where(func.lower(User.email) == email_value))
    if user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Пользователь с таким email уже существует. Используйте вход и обратитесь к платформе для назначения прав.",
        )

    username_value = payload.username.strip()
    username_exists = db.scalar(select(User).where(func.lower(User.username) == username_value.lower()))
    if username_exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Пользователь с таким именем пользователя уже существует")

    user = User(
        email=email_value,
        full_name=payload.full_name.strip(),
        username=username_value,
        password_hash=get_password_hash(payload.password),
        role=UserRole.institution_admin,
    )
    db.add(user)
    db.flush()

    membership = InstitutionMembership(
        user_id=int(user.id),
        institution_id=int(institution.id),
        role=InstitutionMembershipRole.institution_admin,
        status=InstitutionMembershipStatus.active,
        is_primary=True,
        created_at=now,
        updated_at=now,
    )
    db.add(membership)

    invite.consumed_by_user_id = int(user.id)
    invite.consumed_at = now

    notification_service.create(
        db=db,
        user_id=int(user.id),
        institution_id=int(institution.id),
        notification_type="institution_admin_bootstrapped",
        title="Доступ администратора учреждения активирован",
        message=f"Вы назначены администратором учреждения {institution.name}.",
        data={"institution_id": int(institution.id)},
    )
    audit_log_service.record(
        db=db,
        actor_user_id=int(invite.created_by_user_id) if invite.created_by_user_id is not None else None,
        institution_id=int(institution.id),
        action="institution_admin_bootstrap_invite_consumed",
        target_type="institution_admin_bootstrap_invite",
        target_id=int(invite.id),
        metadata={"user_id": int(user.id), "email": email_value},
    )
    audit_log_service.record(
        db=db,
        actor_user_id=int(user.id),
        institution_id=int(institution.id),
        action="institution_admin_granted",
        target_type="institution_membership",
        target_id="new",
        metadata={"user_id": int(user.id), "membership_role": "institution_admin"},
    )
    db.commit()
    db.refresh(user)

    access_token, refresh_token = _create_tokens_for_user(db=db, user_id=user.id, request=request, remember_me=True)
    return _build_auth_response(response=response, access_token=access_token, refresh_token=refresh_token, user=user)


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


def _create_tokens_for_user(
    *,
    db: DBSession,
    user_id: int,
    request: Request,
    remember_me: bool = True,
) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    session_id = str(uuid4())
    refresh_days = settings.refresh_token_expire_days if remember_me else 1
    refresh_expires = now + timedelta(days=refresh_days)
    refresh_token = create_refresh_token(user_id, session_id, expires_delta=timedelta(days=refresh_days))

    session = UserSession(
        id=session_id,
        user_id=user_id,
        refresh_token_hash=hash_refresh_token(refresh_token),
        user_agent=request.headers.get("user-agent"),
        ip_address=_extract_client_ip(request),
        created_at=now,
        last_used_at=now,
        expires_at=refresh_expires,
    )
    db.add(session)
    db.execute(
        delete(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.expires_at < now,
        )
    )
    db.commit()

    access_token = create_access_token(user_id, session_id=session_id)
    return access_token, refresh_token


def _build_auth_response(
    *,
    response: Response,
    access_token: str,
    refresh_token: str,
    user: User,
    remember_me: bool = True,
) -> AuthResponse:
    if settings.use_http_only_refresh_cookie:
        max_age_days = settings.refresh_token_expire_days if remember_me else 1
        _set_refresh_cookie(response, refresh_token, max_age_days=max_age_days)
        response_refresh_token: str | None = None
    else:
        response_refresh_token = refresh_token
    return AuthResponse(
        access_token=access_token,
        refresh_token=response_refresh_token,
        user=_build_user_response(user),
    )


def _extract_refresh_token(*, payload: RefreshTokenRequest | None, request: Request) -> str | None:
    body_token = payload.refresh_token if payload else None
    cookie_token = request.cookies.get(settings.refresh_cookie_name)
    return body_token or cookie_token


def _set_refresh_cookie(response: Response, token: str, *, max_age_days: int) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        httponly=True,
        secure=settings.app_env.lower() == "production",
        samesite="lax",
        max_age=max_age_days * 24 * 60 * 60,
    )


def _extract_client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if forwarded:
        return forwarded
    if request.client:
        return request.client.host
    return None
