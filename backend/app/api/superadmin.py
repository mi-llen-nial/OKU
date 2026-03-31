from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from app.core.deps import DBSession, require_role
from app.core.security import hash_refresh_token
from app.models import (
    Institution,
    InstitutionAdminBootstrapInvite,
    InstitutionMembership,
    InstitutionMembershipRole,
    InstitutionMembershipStatus,
    User,
    UserRole,
)
from app.schemas.superadmin import (
    BootstrapInviteCreateRequest,
    BootstrapInviteResponse,
    InstitutionCreateRequest,
    InstitutionDetailsResponse,
    InstitutionListResponse,
    InstitutionListItem,
)
from app.services.audit_logs import audit_log_service
from app.services.institutions import normalize_institution_name
from app.services.notifications import notification_service

router = APIRouter(prefix="/superadmin", tags=["superadmin"])


@router.get("/institutions", response_model=InstitutionListResponse)
def list_institutions(
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.superadmin)),
) -> InstitutionListResponse:
    _ = current_user
    rows = db.scalars(select(Institution).order_by(Institution.id.desc())).all()
    return InstitutionListResponse(
        institutions=[
            InstitutionListItem(
                id=int(row.id),
                name=str(row.name),
                normalized_name=str(row.normalized_name),
                is_active=bool(row.is_active),
                created_at=row.created_at,
            )
            for row in rows
        ]
    )


@router.post("/institutions", response_model=InstitutionDetailsResponse)
def create_institution(
    payload: InstitutionCreateRequest,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.superadmin)),
) -> InstitutionDetailsResponse:
    name = payload.name.strip()
    normalized = normalize_institution_name(name)
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Название учреждения не может быть пустым.")

    existing = db.scalar(select(Institution).where(func.lower(Institution.normalized_name) == normalized))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Учреждение с таким названием уже существует.")

    row = Institution(
        name=name,
        normalized_name=normalized,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        created_by_user_id=int(current_user.id),
    )
    db.add(row)
    db.flush()

    audit_log_service.record(
        db=db,
        actor_user_id=int(current_user.id),
        institution_id=int(row.id),
        action="institution_created",
        target_type="institution",
        target_id=int(row.id),
        metadata={"name": row.name},
    )
    db.commit()
    db.refresh(row)
    return InstitutionDetailsResponse(
        id=int(row.id),
        name=str(row.name),
        normalized_name=str(row.normalized_name),
        is_active=bool(row.is_active),
        created_at=row.created_at,
        created_by_user_id=(int(row.created_by_user_id) if row.created_by_user_id is not None else None),
    )


@router.get("/institutions/{institution_id}", response_model=InstitutionDetailsResponse)
def get_institution(
    institution_id: int,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.superadmin)),
) -> InstitutionDetailsResponse:
    _ = current_user
    row = db.get(Institution, int(institution_id))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Учреждение не найдено.")
    return InstitutionDetailsResponse(
        id=int(row.id),
        name=str(row.name),
        normalized_name=str(row.normalized_name),
        is_active=bool(row.is_active),
        created_at=row.created_at,
        created_by_user_id=(int(row.created_by_user_id) if row.created_by_user_id is not None else None),
    )


@router.post("/institutions/{institution_id}/bootstrap-invites", response_model=BootstrapInviteResponse)
def create_bootstrap_invite(
    institution_id: int,
    payload: BootstrapInviteCreateRequest,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.superadmin)),
) -> BootstrapInviteResponse:
    institution = db.get(Institution, int(institution_id))
    if institution is None or not institution.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Учреждение не найдено.")

    email = payload.email.strip().lower()
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email обязателен.")

    token = secrets.token_urlsafe(32)
    token_hash = hash_refresh_token(token)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=int(payload.expires_in_hours or 72))

    row = InstitutionAdminBootstrapInvite(
        institution_id=int(institution.id),
        email=email,
        token_hash=token_hash,
        created_by_user_id=int(current_user.id),
        expires_at=expires_at,
        created_at=datetime.now(timezone.utc),
        consumed_by_user_id=None,
        consumed_at=None,
        revoked_at=None,
        note=(payload.note.strip() if payload.note else None),
    )
    db.add(row)
    db.flush()

    audit_log_service.record(
        db=db,
        actor_user_id=int(current_user.id),
        institution_id=int(institution.id),
        action="institution_admin_bootstrap_invite_created",
        target_type="institution_admin_bootstrap_invite",
        target_id=int(row.id),
        metadata={"email": email, "expires_at": expires_at.isoformat()},
    )

    db.commit()
    return BootstrapInviteResponse(
        id=int(row.id),
        institution_id=int(institution.id),
        email=email,
        token=token,
        expires_at=expires_at,
        created_at=row.created_at,
        note=row.note,
    )


@router.post("/institutions/{institution_id}/institution-admins/{user_id}/revoke")
def revoke_institution_admin(
    institution_id: int,
    user_id: int,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.superadmin)),
) -> dict[str, bool]:
    membership = db.scalar(
        select(InstitutionMembership).where(
            InstitutionMembership.user_id == int(user_id),
            InstitutionMembership.institution_id == int(institution_id),
            InstitutionMembership.role == InstitutionMembershipRole.institution_admin,
        )
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Членство institution_admin не найдено.")

    membership.status = InstitutionMembershipStatus.revoked

    notification_service.create(
        db=db,
        user_id=int(user_id),
        institution_id=int(institution_id),
        notification_type="institution_admin_revoked",
        title="Доступ администратора учреждения отозван",
        message="Ваш доступ администратора учреждения был отозван платформой.",
        data={"institution_id": int(institution_id)},
    )
    audit_log_service.record(
        db=db,
        actor_user_id=int(current_user.id),
        institution_id=int(institution_id),
        action="institution_admin_revoked",
        target_type="institution_membership",
        target_id=int(membership.id),
        metadata={"user_id": int(user_id)},
    )
    db.commit()
    return {"ok": True}

