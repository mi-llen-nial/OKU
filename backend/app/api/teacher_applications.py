from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.core.deps import DBSession, get_current_user
from app.models import (
    InstitutionMembership,
    InstitutionMembershipRole,
    InstitutionMembershipStatus,
    TeacherApplication,
    TeacherApplicationStatus,
    User,
)
from app.schemas.institutional import TeacherApplicationCreateRequest, TeacherApplicationResponse
from app.services.audit_logs import audit_log_service
from app.services.institutions import resolve_institution_for_application
from app.services.notifications import notification_service

router = APIRouter(prefix="/teacher-applications", tags=["teacher-applications"])


@router.post("", response_model=TeacherApplicationResponse)
def create_teacher_application(
    payload: TeacherApplicationCreateRequest,
    db: DBSession,
    current_user: User = Depends(get_current_user),
) -> TeacherApplicationResponse:
    institution = resolve_institution_for_application(
        db=db,
        institution_id=payload.institution_id,
        institution_name=payload.institution_name,
    )

    active_teacher_membership = db.scalar(
        select(InstitutionMembership).where(
            InstitutionMembership.user_id == current_user.id,
            InstitutionMembership.institution_id == institution.id,
            InstitutionMembership.role == InstitutionMembershipRole.teacher,
            InstitutionMembership.status == InstitutionMembershipStatus.active,
        )
    )
    if active_teacher_membership is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Вы уже являетесь преподавателем этого учебного учреждения.",
        )

    existing_pending = db.scalar(
        select(TeacherApplication).where(
            TeacherApplication.applicant_user_id == current_user.id,
            TeacherApplication.institution_id == institution.id,
            TeacherApplication.status == TeacherApplicationStatus.pending,
        )
    )
    if existing_pending is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="У вас уже есть активная заявка в это учебное учреждение.",
        )

    application = TeacherApplication(
        applicant_user_id=current_user.id,
        institution_id=institution.id,
        full_name=payload.full_name.strip(),
        email=payload.email.strip().lower(),
        subject=(payload.subject.strip() if payload.subject else None),
        position=(payload.position.strip() if payload.position else None),
        additional_info=(payload.additional_info.strip() if payload.additional_info else None),
        status=TeacherApplicationStatus.pending,
        created_at=datetime.now(timezone.utc),
    )
    db.add(application)
    db.flush()

    admin_memberships = db.scalars(
        select(InstitutionMembership).where(
            InstitutionMembership.institution_id == institution.id,
            InstitutionMembership.role == InstitutionMembershipRole.institution_admin,
            InstitutionMembership.status == InstitutionMembershipStatus.active,
        )
    ).all()
    for membership in admin_memberships:
        notification_service.create(
            db=db,
            user_id=int(membership.user_id),
            institution_id=institution.id,
            notification_type="teacher_application_submitted",
            title="Новая заявка преподавателя",
            message=f"Новая заявка от {application.full_name} в {institution.name}.",
            data={
                "application_id": application.id,
                "institution_id": institution.id,
                "applicant_user_id": current_user.id,
            },
        )

    audit_log_service.record(
        db=db,
        institution_id=institution.id,
        actor_user_id=current_user.id,
        action="teacher_application_submitted",
        target_type="teacher_application",
        target_id=application.id,
        metadata={
            "status": application.status.value,
            "subject": application.subject,
            "position": application.position,
        },
    )

    db.commit()
    db.refresh(application)
    return _serialize_teacher_application(application)


@router.get("/me", response_model=list[TeacherApplicationResponse])
def my_teacher_applications(
    db: DBSession,
    current_user: User = Depends(get_current_user),
) -> list[TeacherApplicationResponse]:
    rows = db.scalars(
        select(TeacherApplication)
        .options(joinedload(TeacherApplication.institution))
        .where(TeacherApplication.applicant_user_id == current_user.id)
        .order_by(TeacherApplication.created_at.desc(), TeacherApplication.id.desc())
    ).all()
    return [_serialize_teacher_application(item) for item in rows]


def _serialize_teacher_application(item: TeacherApplication) -> TeacherApplicationResponse:
    if item.institution is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Учреждение заявки не найдено.")
    return TeacherApplicationResponse(
        id=item.id,
        applicant_user_id=int(item.applicant_user_id),
        institution={"id": item.institution.id, "name": item.institution.name},
        full_name=item.full_name,
        email=item.email,
        subject=item.subject,
        position=item.position,
        additional_info=item.additional_info,
        status=item.status,
        reviewer_comment=item.reviewer_comment,
        created_at=item.created_at,
        decided_at=item.decided_at,
    )
