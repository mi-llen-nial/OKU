from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import joinedload

from app.core.deps import DBSession, get_current_user
from app.models import (
    Group,
    GroupInvitation,
    GroupMembership,
    InvitationStatus,
    PreferredLanguage,
    StudentProfile,
    User,
    UserRole,
)
from app.schemas.profile import ProfileInvitationResponse, ProfileResponse

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/me", response_model=ProfileResponse)
def my_profile(
    db: DBSession,
    current_user: User = Depends(get_current_user),
) -> ProfileResponse:
    group_id = current_user.student_profile.group_id if current_user.student_profile else None
    group_name = None
    if group_id is not None:
        group = db.get(Group, group_id)
        group_name = group.name if group else None

    invitations = (
        _load_teacher_invitations(db=db, teacher_id=current_user.id)
        if current_user.role == UserRole.teacher
        else _load_user_invitations(db=db, user_id=current_user.id)
    )
    return ProfileResponse(
        id=current_user.id,
        role=current_user.role,
        email=current_user.email,
        full_name=current_user.full_name,
        username=current_user.username,
        preferred_language=(current_user.student_profile.preferred_language if current_user.student_profile else None),
        education_level=(current_user.student_profile.education_level if current_user.student_profile else None),
        direction=(current_user.student_profile.direction if current_user.student_profile else None),
        group_id=group_id,
        group_name=group_name,
        invitations=invitations,
    )


@router.post("/invitations/{invitation_id}/accept", response_model=ProfileInvitationResponse)
def accept_invitation(
    invitation_id: int,
    db: DBSession,
    current_user: User = Depends(get_current_user),
) -> ProfileInvitationResponse:
    invitation = _get_user_invitation(db=db, invitation_id=invitation_id, user_id=current_user.id)
    if invitation.status != InvitationStatus.pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Приглашение уже обработано")

    if invitation.group_id is not None:
        target_group = db.get(Group, invitation.group_id)
        if not target_group:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Группа приглашения больше не существует")

        db.execute(delete(GroupMembership).where(GroupMembership.student_id == current_user.id))
        db.add(GroupMembership(student_id=current_user.id, group_id=target_group.id))

        profile = db.get(StudentProfile, current_user.id)
        if not profile:
            profile = StudentProfile(
                user_id=current_user.id,
                preferred_language=PreferredLanguage.ru,
            )
            db.add(profile)
        profile.group_id = target_group.id

    invitation.status = InvitationStatus.accepted
    invitation.responded_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(invitation)
    return _serialize_profile_invitation(invitation)


@router.post("/invitations/{invitation_id}/decline", response_model=ProfileInvitationResponse)
def decline_invitation(
    invitation_id: int,
    db: DBSession,
    current_user: User = Depends(get_current_user),
) -> ProfileInvitationResponse:
    invitation = _get_user_invitation(db=db, invitation_id=invitation_id, user_id=current_user.id)
    if invitation.status != InvitationStatus.pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Приглашение уже обработано")

    invitation.status = InvitationStatus.declined
    invitation.responded_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(invitation)
    return _serialize_profile_invitation(invitation)


def _load_user_invitations(*, db: DBSession, user_id: int) -> list[ProfileInvitationResponse]:
    invitations = db.scalars(
        select(GroupInvitation)
        .options(joinedload(GroupInvitation.teacher), joinedload(GroupInvitation.group))
        .where(GroupInvitation.student_id == user_id)
        .order_by(GroupInvitation.created_at.desc())
    ).all()
    return [_serialize_profile_invitation(item) for item in invitations]


def _load_teacher_invitations(*, db: DBSession, teacher_id: int) -> list[ProfileInvitationResponse]:
    invitations = db.scalars(
        select(GroupInvitation)
        .options(joinedload(GroupInvitation.student), joinedload(GroupInvitation.group))
        .where(GroupInvitation.teacher_id == teacher_id)
        .order_by(GroupInvitation.created_at.desc())
    ).all()
    return [_serialize_profile_invitation_for_teacher(item) for item in invitations]


def _get_user_invitation(*, db: DBSession, invitation_id: int, user_id: int) -> GroupInvitation:
    invitation = db.scalar(
        select(GroupInvitation)
        .options(joinedload(GroupInvitation.teacher), joinedload(GroupInvitation.group))
        .where(
            GroupInvitation.id == invitation_id,
            GroupInvitation.student_id == user_id,
        )
    )
    if not invitation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Приглашение не найдено")
    return invitation


def _serialize_profile_invitation(invitation: GroupInvitation) -> ProfileInvitationResponse:
    teacher_name = invitation.teacher.full_name or invitation.teacher.username
    return ProfileInvitationResponse(
        id=invitation.id,
        teacher_id=invitation.teacher_id,
        teacher_name=teacher_name,
        group_id=invitation.group_id,
        group_name=(invitation.group.name if invitation.group else None),
        status=invitation.status,
        created_at=invitation.created_at,
        responded_at=invitation.responded_at,
    )


def _serialize_profile_invitation_for_teacher(invitation: GroupInvitation) -> ProfileInvitationResponse:
    student_name = invitation.student.full_name or invitation.student.username
    return ProfileInvitationResponse(
        id=invitation.id,
        teacher_id=invitation.student_id,
        teacher_name=student_name,
        group_id=invitation.group_id,
        group_name=(invitation.group.name if invitation.group else None),
        status=invitation.status,
        created_at=invitation.created_at,
        responded_at=invitation.responded_at,
    )
