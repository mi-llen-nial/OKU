from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import joinedload

from app.core.deps import DBSession, require_role
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
from app.schemas.groups import (
    GroupMemberResponse,
    GroupMembersResponse,
    TeacherGroupCreateRequest,
    TeacherGroupCreateResponse,
    TeacherGroupListItem,
    TeacherInvitationCreateRequest,
    TeacherInvitationResponse,
)
from app.schemas.teacher import GroupAnalyticsResponse, GroupWeakTopicsResponse
from app.schemas.tests import HistoryItemResponse, StudentProgressResponse
from app.services.progress import (
    build_group_analytics,
    build_group_weak_topics,
    build_student_history,
    build_student_progress,
)

router = APIRouter(prefix="/teacher", tags=["teacher"])


@router.get("/groups", response_model=list[TeacherGroupListItem])
def my_groups(
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.teacher)),
) -> list[TeacherGroupListItem]:
    rows = db.execute(
        select(
            Group.id,
            Group.name,
            func.count(GroupMembership.id).label("members_count"),
        )
        .outerjoin(GroupMembership, GroupMembership.group_id == Group.id)
        .where(Group.teacher_id == current_user.id)
        .group_by(Group.id)
        .order_by(Group.id.desc())
    ).all()
    return [
        TeacherGroupListItem(
            id=int(row.id),
            name=str(row.name),
            members_count=int(row.members_count or 0),
        )
        for row in rows
    ]


@router.post("/groups", response_model=TeacherGroupCreateResponse)
def create_group(
    payload: TeacherGroupCreateRequest,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.teacher)),
) -> TeacherGroupCreateResponse:
    group_name = payload.name.strip()
    if not group_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Название группы не может быть пустым")

    existing_group = db.scalar(select(Group).where(func.lower(Group.name) == group_name.lower()))
    if existing_group:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Группа с таким названием уже существует")

    student_ids = sorted(set(int(item) for item in payload.student_ids if int(item) > 0))
    if student_ids:
        students = db.scalars(select(User).where(User.id.in_(student_ids), User.role == UserRole.student)).all()
        student_id_set = {student.id for student in students}
        if len(student_id_set) != len(student_ids):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Часть выбранных участников не найдена")

        accepted = db.scalars(
            select(GroupInvitation).where(
                GroupInvitation.teacher_id == current_user.id,
                GroupInvitation.student_id.in_(student_ids),
                GroupInvitation.status == InvitationStatus.accepted,
            )
        ).all()
        accepted_ids = {item.student_id for item in accepted}
        missing_ids = [item for item in student_ids if item not in accepted_ids]
        if missing_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Добавлять в группу можно только студентов с принятым приглашением.",
            )

    group = Group(name=group_name, teacher_id=current_user.id)
    db.add(group)
    db.flush()

    members_count = 0
    if student_ids:
        for student_id in student_ids:
            db.execute(delete(GroupMembership).where(GroupMembership.student_id == student_id))
            db.add(GroupMembership(student_id=student_id, group_id=group.id))

            profile = db.get(StudentProfile, student_id)
            if not profile:
                profile = StudentProfile(
                    user_id=student_id,
                    preferred_language=PreferredLanguage.ru,
                )
                db.add(profile)
            profile.group_id = group.id
            members_count += 1

    db.commit()
    return TeacherGroupCreateResponse(
        id=group.id,
        name=group.name,
        members_count=members_count,
    )


@router.get("/groups/{group_id}/members", response_model=GroupMembersResponse)
def group_members(
    group_id: int,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.teacher)),
) -> GroupMembersResponse:
    group = _get_teacher_group(db=db, teacher_id=current_user.id, group_id=group_id)
    memberships = db.scalars(
        select(GroupMembership)
        .options(joinedload(GroupMembership.student))
        .where(GroupMembership.group_id == group.id)
        .order_by(GroupMembership.id.asc())
    ).all()

    members: list[GroupMemberResponse] = []
    for membership in memberships:
        student = membership.student
        progress = build_student_progress(db, student.id)
        members.append(
            GroupMemberResponse(
                student_id=student.id,
                username=student.username,
                full_name=student.full_name,
                tests_count=progress.total_tests,
                avg_percent=progress.avg_percent,
                warnings_count=progress.total_warnings,
            )
        )

    return GroupMembersResponse(id=group.id, name=group.name, members=members)


@router.post("/invitations", response_model=TeacherInvitationResponse)
def send_invitation(
    payload: TeacherInvitationCreateRequest,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.teacher)),
) -> TeacherInvitationResponse:
    username = payload.username.strip().lstrip("@")
    if not username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Введите username ученика")

    student = db.scalar(select(User).where(func.lower(User.username) == username.lower()))
    if not student or student.role != UserRole.student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ученик с таким username не найден")

    target_group = None
    if payload.group_id is not None:
        target_group = _get_teacher_group(
            db=db,
            teacher_id=current_user.id,
            group_id=payload.group_id,
        )

    existing_pending = db.scalar(
        select(GroupInvitation).where(
            GroupInvitation.teacher_id == current_user.id,
            GroupInvitation.student_id == student.id,
            GroupInvitation.status == InvitationStatus.pending,
            GroupInvitation.group_id == payload.group_id,
        )
    )
    if existing_pending:
        return _serialize_invitation(existing_pending)

    invitation = GroupInvitation(
        teacher_id=current_user.id,
        student_id=student.id,
        group_id=(target_group.id if target_group else None),
        status=InvitationStatus.pending,
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    return _serialize_invitation(invitation)


@router.get("/invitations", response_model=list[TeacherInvitationResponse])
def my_invitations(
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.teacher)),
) -> list[TeacherInvitationResponse]:
    invitations = db.scalars(
        select(GroupInvitation)
        .options(
            joinedload(GroupInvitation.teacher),
            joinedload(GroupInvitation.student),
            joinedload(GroupInvitation.group),
        )
        .where(GroupInvitation.teacher_id == current_user.id)
        .order_by(GroupInvitation.created_at.desc())
    ).all()
    return [_serialize_invitation(item) for item in invitations]


@router.get("/groups/{group_id}/analytics", response_model=GroupAnalyticsResponse)
def group_analytics(
    group_id: int,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.teacher)),
) -> GroupAnalyticsResponse:
    _get_teacher_group(db=db, teacher_id=current_user.id, group_id=group_id)
    try:
        return build_group_analytics(db, group_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/groups/{group_id}/weak-topics", response_model=GroupWeakTopicsResponse)
def group_weak_topics(
    group_id: int,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.teacher)),
) -> GroupWeakTopicsResponse:
    _get_teacher_group(db=db, teacher_id=current_user.id, group_id=group_id)
    try:
        return build_group_weak_topics(db, group_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/students/{student_id}/progress", response_model=StudentProgressResponse)
def student_progress_for_teacher(
    student_id: int,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.teacher)),
) -> StudentProgressResponse:
    _assert_student_visible_to_teacher(db=db, teacher_id=current_user.id, student_id=student_id)
    return build_student_progress(db, student_id)


@router.get("/students/{student_id}/history", response_model=list[HistoryItemResponse])
def student_history_for_teacher(
    student_id: int,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.teacher)),
) -> list[HistoryItemResponse]:
    _assert_student_visible_to_teacher(db=db, teacher_id=current_user.id, student_id=student_id)
    return build_student_history(db, student_id)


def _get_teacher_group(*, db: DBSession, teacher_id: int, group_id: int) -> Group:
    group = db.scalar(select(Group).where(Group.id == group_id))
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Группа не найдена")
    if group.teacher_id != teacher_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Группа недоступна")
    return group


def _assert_student_visible_to_teacher(*, db: DBSession, teacher_id: int, student_id: int) -> None:
    student = db.get(User, student_id)
    if not student or student.role != UserRole.student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Студент не найден")

    membership = db.scalar(
        select(GroupMembership)
        .join(Group, Group.id == GroupMembership.group_id)
        .where(
            GroupMembership.student_id == student_id,
            Group.teacher_id == teacher_id,
        )
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Студент не относится к вашим группам")


def _serialize_invitation(invitation: GroupInvitation) -> TeacherInvitationResponse:
    teacher_name = invitation.teacher.full_name or invitation.teacher.username
    return TeacherInvitationResponse(
        id=invitation.id,
        teacher_id=invitation.teacher_id,
        teacher_name=teacher_name,
        student_id=invitation.student_id,
        student_username=invitation.student.username,
        student_name=invitation.student.full_name,
        group_id=invitation.group_id,
        group_name=(invitation.group.name if invitation.group else None),
        status=invitation.status,
        created_at=invitation.created_at,
        responded_at=invitation.responded_at,
    )
