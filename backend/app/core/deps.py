from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import TokenError, decode_access_token
from app.db.session import SessionLocal
from app.models import (
    Group,
    GroupTeacherAssignment,
    InstitutionMembership,
    InstitutionMembershipRole,
    InstitutionMembershipStatus,
    TeacherAuthoredTest,
    User,
    UserRole,
    UserSession,
)

_token_url = f"{settings.api_prefix_normalized}/auth/login" if settings.api_prefix_normalized else "/auth/login"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=_token_url)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DBSession = Annotated[Session, Depends(get_db)]


def get_current_user(db: DBSession, token: Annotated[str, Depends(oauth2_scheme)]) -> User:
    try:
        payload = decode_access_token(token)
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверные учетные данные") from exc

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверные учетные данные")

    session_id = payload.get("sid")
    if isinstance(session_id, str) and session_id:
        session = db.get(UserSession, session_id)
        if session and session.user_id == int(user_id) and session.revoked_at is None:
            now = datetime.now(timezone.utc)
            # Avoid committing on every request; update heartbeat roughly once per minute.
            if session.last_used_at <= now - timedelta(seconds=60):
                session.last_used_at = now
                db.commit()

    user = db.get(User, int(user_id))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не найден")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*roles: UserRole):
    def _checker(current_user: CurrentUser) -> User:
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав доступа")
        return current_user

    return _checker


def _extract_institution_id_from_request(request: Request) -> int | None:
    path_value = request.path_params.get("institution_id")
    query_value = request.query_params.get("institution_id")
    raw_value = path_value if path_value is not None else query_value
    if raw_value is None:
        return None
    try:
        resolved = int(raw_value)
    except (TypeError, ValueError):
        return None
    return resolved if resolved > 0 else None


def get_active_memberships(
    *,
    db: Session,
    user_id: int,
    institution_id: int | None = None,
    roles: set[InstitutionMembershipRole] | None = None,
) -> list[InstitutionMembership]:
    stmt = select(InstitutionMembership).where(
        InstitutionMembership.user_id == int(user_id),
        InstitutionMembership.status == InstitutionMembershipStatus.active,
    )
    if institution_id is not None:
        stmt = stmt.where(InstitutionMembership.institution_id == int(institution_id))
    if roles:
        stmt = stmt.where(InstitutionMembership.role.in_(tuple(roles)))

    rows = db.scalars(
        stmt.order_by(
            InstitutionMembership.is_primary.desc(),
            InstitutionMembership.id.asc(),
        )
    ).all()
    return list(rows)


def get_active_membership_or_403(
    *,
    db: Session,
    current_user: User,
    institution_id: int | None = None,
    allowed_roles: set[InstitutionMembershipRole] | None = None,
) -> InstitutionMembership:
    if current_user.role == UserRole.superadmin:
        stmt = select(InstitutionMembership).where(
            InstitutionMembership.user_id == current_user.id,
            InstitutionMembership.status == InstitutionMembershipStatus.active,
        )
        if institution_id is not None:
            stmt = stmt.where(InstitutionMembership.institution_id == int(institution_id))
        if allowed_roles:
            stmt = stmt.where(InstitutionMembership.role.in_(tuple(allowed_roles)))
        fallback = db.scalar(stmt.order_by(InstitutionMembership.is_primary.desc(), InstitutionMembership.id.asc()))
        if fallback is not None:
            return fallback
        if institution_id is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="У superadmin нет активного членства с требуемой ролью в выбранном учреждении.",
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Не найдено членство superadmin в учреждении.",
        )

    memberships = get_active_memberships(
        db=db,
        user_id=current_user.id,
        institution_id=institution_id,
        roles=allowed_roles,
    )
    if memberships:
        return memberships[0]

    if institution_id is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет активного доступа к этому учебному учреждению.",
        )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Нет активного членства в учебном учреждении.",
    )


def require_institution_role(*roles: InstitutionMembershipRole):
    required_roles = set(roles)

    def _checker(
        request: Request,
        db: DBSession,
        current_user: CurrentUser,
    ) -> InstitutionMembership:
        institution_id = _extract_institution_id_from_request(request)
        return get_active_membership_or_403(
            db=db,
            current_user=current_user,
            institution_id=institution_id,
            allowed_roles=(required_roles or None),
        )

    return _checker


def assert_same_institution(*memberships: InstitutionMembership) -> int:
    if not memberships:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не переданы членства для проверки.")
    institution_ids = {int(item.institution_id) for item in memberships}
    if len(institution_ids) != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нельзя выполнять действие между разными учебными учреждениями.",
        )
    return next(iter(institution_ids))


def assert_group_assignment_access(
    *,
    db: Session,
    group_id: int,
    membership: InstitutionMembership,
    require_teacher_assigned: bool = False,
) -> Group:
    group = db.scalar(select(Group).where(Group.id == int(group_id)))
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Группа не найдена.")
    if group.institution_id is None or int(group.institution_id) != int(membership.institution_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Группа недоступна в вашем учреждении.")

    if membership.role == InstitutionMembershipRole.teacher or require_teacher_assigned:
        assigned = db.scalar(
            select(GroupTeacherAssignment.id).where(
                GroupTeacherAssignment.group_id == group.id,
                GroupTeacherAssignment.teacher_membership_id == membership.id,
            )
        )
        if assigned is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Вы не назначены на эту группу.")
    return group


def assert_test_review_access(
    *,
    db: Session,
    test_id: int,
    membership: InstitutionMembership,
) -> TeacherAuthoredTest:
    test = db.scalar(select(TeacherAuthoredTest).where(TeacherAuthoredTest.id == int(test_id)))
    if test is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тест не найден.")
    if test.institution_id is None or int(test.institution_id) != int(membership.institution_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Тест недоступен в вашем учреждении.")

    if membership.role == InstitutionMembershipRole.teacher and int(test.teacher_id) != int(membership.user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Этот тест принадлежит другому преподавателю.")
    return test
