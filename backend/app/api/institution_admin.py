from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import joinedload, selectinload

from app.core.config import settings
from app.core.deps import (
    DBSession,
    CurrentUser,
    assert_group_assignment_access,
    get_active_memberships,
    require_institution_role,
)
from app.models import (
    Group,
    GroupMembership,
    GroupTeacherAssignment,
    InstitutionMembership,
    InstitutionMembershipRole,
    InstitutionMembershipStatus,
    StudentProfile,
    TeacherApplication,
    TeacherApplicationStatus,
    User,
    UserRole,
)
from app.schemas.institutional import (
    AssignMethodistRequest,
    InstitutionGroupAssignTeacherRequest,
    InstitutionGroupCreateRequest,
    InstitutionGroupDetailsResponse,
    InstitutionGroupResponse,
    InstitutionGroupStudentResponse,
    InstitutionGroupTeacherResponse,
    InstitutionListItemResponse,
    InstitutionMemberListItemResponse,
    InstitutionMembershipResponse,
    InstitutionStudentMembershipAssignRequest,
    TeacherApplicationDecisionRequest,
    TeacherApplicationResponse,
)
from app.services.audit_logs import audit_log_service
from app.services.notifications import notification_service

router = APIRouter(prefix="/institution-admin", tags=["institution-admin"])


def _admin_membership_dependency():
    return Depends(require_institution_role(InstitutionMembershipRole.institution_admin))


def _assert_admin_scope(*, membership: InstitutionMembership, institution_id: int) -> None:
    if int(membership.institution_id) != int(institution_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к выбранному учебному учреждению.",
        )


@router.get("/institutions", response_model=list[InstitutionListItemResponse])
def my_admin_institutions(
    db: DBSession,
    current_user: CurrentUser,
) -> list[InstitutionListItemResponse]:
    memberships = get_active_memberships(
        db=db,
        user_id=current_user.id,
        roles={InstitutionMembershipRole.institution_admin},
    )
    return [
        InstitutionListItemResponse(
            id=int(membership.institution.id),
            name=str(membership.institution.name),
            role=membership.role,
            status=membership.status,
            is_primary=bool(membership.is_primary),
        )
        for membership in memberships
        if membership.institution is not None
    ]


@router.get(
    "/institutions/{institution_id}/teacher-applications",
    response_model=list[TeacherApplicationResponse],
)
def list_teacher_applications(
    institution_id: int,
    db: DBSession,
    status_filter: TeacherApplicationStatus | None = None,
    admin_membership: InstitutionMembership = _admin_membership_dependency(),
) -> list[TeacherApplicationResponse]:
    _assert_admin_scope(membership=admin_membership, institution_id=institution_id)

    stmt = (
        select(TeacherApplication)
        .options(joinedload(TeacherApplication.institution))
        .where(TeacherApplication.institution_id == int(institution_id))
        .order_by(TeacherApplication.created_at.desc(), TeacherApplication.id.desc())
    )
    if status_filter is not None:
        stmt = stmt.where(TeacherApplication.status == status_filter)

    rows = db.scalars(stmt).all()
    return [_serialize_teacher_application(item) for item in rows]


@router.post(
    "/institutions/{institution_id}/teacher-applications/{application_id}/decision",
    response_model=TeacherApplicationResponse,
)
def decide_teacher_application(
    institution_id: int,
    application_id: int,
    payload: TeacherApplicationDecisionRequest,
    db: DBSession,
    admin_membership: InstitutionMembership = _admin_membership_dependency(),
) -> TeacherApplicationResponse:
    _assert_admin_scope(membership=admin_membership, institution_id=institution_id)

    application = db.scalar(
        select(TeacherApplication)
        .options(joinedload(TeacherApplication.institution))
        .where(
            TeacherApplication.id == int(application_id),
            TeacherApplication.institution_id == int(institution_id),
        )
    )
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заявка не найдена.")

    teacher_membership = db.scalar(
        select(InstitutionMembership).where(
            InstitutionMembership.user_id == int(application.applicant_user_id),
            InstitutionMembership.institution_id == int(institution_id),
            InstitutionMembership.role == InstitutionMembershipRole.teacher,
        )
    )

    decision_status_map = {
        "approve": TeacherApplicationStatus.approved,
        "reject": TeacherApplicationStatus.rejected,
        "suspend": TeacherApplicationStatus.suspended,
        "revoke": TeacherApplicationStatus.revoked,
    }
    next_status = decision_status_map[payload.action]

    application.status = next_status
    application.reviewer_user_id = int(admin_membership.user_id)
    application.reviewer_comment = (payload.comment or "").strip() or None
    application.decided_at = datetime.now(timezone.utc)

    applicant_user = db.get(User, int(application.applicant_user_id))
    if applicant_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь заявки не найден.")

    if payload.action == "approve":
        if teacher_membership is None:
            teacher_membership = InstitutionMembership(
                user_id=applicant_user.id,
                institution_id=int(institution_id),
                role=InstitutionMembershipRole.teacher,
                status=InstitutionMembershipStatus.active,
                is_primary=False,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(teacher_membership)
        else:
            teacher_membership.status = InstitutionMembershipStatus.active
            teacher_membership.updated_at = datetime.now(timezone.utc)
        if applicant_user.role == UserRole.student:
            applicant_user.role = UserRole.teacher
    elif payload.action == "suspend":
        if teacher_membership is not None:
            teacher_membership.status = InstitutionMembershipStatus.suspended
            teacher_membership.updated_at = datetime.now(timezone.utc)
    elif payload.action == "revoke":
        if teacher_membership is not None:
            teacher_membership.status = InstitutionMembershipStatus.revoked
            teacher_membership.updated_at = datetime.now(timezone.utc)

    notification_service.create(
        db=db,
        user_id=int(application.applicant_user_id),
        institution_id=int(institution_id),
        notification_type="teacher_application_decision",
        title="Решение по заявке преподавателя",
        message=(
            "Ваша заявка одобрена."
            if payload.action == "approve"
            else "По вашей заявке принято решение. Проверьте комментарий администратора."
        ),
        data={
            "application_id": application.id,
            "status": application.status.value,
            "comment": application.reviewer_comment,
        },
    )

    audit_log_service.record(
        db=db,
        institution_id=int(institution_id),
        actor_user_id=int(admin_membership.user_id),
        action=f"teacher_application_{payload.action}",
        target_type="teacher_application",
        target_id=application.id,
        metadata={
            "applicant_user_id": int(application.applicant_user_id),
            "status": application.status.value,
            "comment": application.reviewer_comment,
        },
    )
    db.commit()
    db.refresh(application)
    return _serialize_teacher_application(application)


@router.get(
    "/institutions/{institution_id}/staff",
    response_model=list[InstitutionMemberListItemResponse],
)
def list_institution_staff(
    institution_id: int,
    db: DBSession,
    admin_membership: InstitutionMembership = _admin_membership_dependency(),
) -> list[InstitutionMemberListItemResponse]:
    _assert_admin_scope(membership=admin_membership, institution_id=institution_id)

    memberships = db.scalars(
        select(InstitutionMembership)
        .options(joinedload(InstitutionMembership.user))
        .where(InstitutionMembership.institution_id == int(institution_id))
        .order_by(
            InstitutionMembership.user_id.asc(),
            InstitutionMembership.role.asc(),
            InstitutionMembership.id.asc(),
        )
    ).all()

    by_user: dict[int, list[InstitutionMembership]] = {}
    for membership in memberships:
        by_user.setdefault(int(membership.user_id), []).append(membership)

    payload: list[InstitutionMemberListItemResponse] = []
    for _, user_memberships in by_user.items():
        primary = next((item for item in user_memberships if item.is_primary), user_memberships[0])
        teacher_membership = next(
            (
                item
                for item in user_memberships
                if item.role == InstitutionMembershipRole.teacher
                and item.status == InstitutionMembershipStatus.active
            ),
            next((item for item in user_memberships if item.role == InstitutionMembershipRole.teacher), None),
        )
        user = primary.user
        if user is None:
            continue
        payload.append(
            InstitutionMemberListItemResponse(
                id=int(primary.id),
                user_id=int(user.id),
                institution_id=int(primary.institution_id),
                role=primary.role,
                status=primary.status,
                is_primary=bool(primary.is_primary),
                full_name=user.full_name,
                username=user.username,
                email=user.email,
                created_at=primary.created_at,
                updated_at=primary.updated_at,
                roles=[item.role for item in user_memberships],
                statuses=[item.status for item in user_memberships],
                teacher_membership_id=(int(teacher_membership.id) if teacher_membership is not None else None),
            )
        )
    payload.sort(key=lambda item: (item.full_name or item.username).lower())
    return payload


@router.post(
    "/institutions/{institution_id}/methodists",
    response_model=InstitutionMembershipResponse,
)
def assign_methodist_membership(
    institution_id: int,
    payload: AssignMethodistRequest,
    db: DBSession,
    admin_membership: InstitutionMembership = _admin_membership_dependency(),
) -> InstitutionMembershipResponse:
    _assert_admin_scope(membership=admin_membership, institution_id=institution_id)

    user = db.get(User, int(payload.user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден.")

    membership = db.scalar(
        select(InstitutionMembership).where(
            InstitutionMembership.user_id == user.id,
            InstitutionMembership.institution_id == int(institution_id),
            InstitutionMembership.role == InstitutionMembershipRole.methodist,
        )
    )
    if membership is None:
        membership = InstitutionMembership(
            user_id=user.id,
            institution_id=int(institution_id),
            role=InstitutionMembershipRole.methodist,
            status=InstitutionMembershipStatus.active,
            is_primary=bool(payload.make_primary),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(membership)
    else:
        membership.status = InstitutionMembershipStatus.active
        membership.is_primary = bool(payload.make_primary) or bool(membership.is_primary)
        membership.updated_at = datetime.now(timezone.utc)

    if payload.make_primary:
        others = db.scalars(
            select(InstitutionMembership).where(
                InstitutionMembership.institution_id == int(institution_id),
                InstitutionMembership.role == InstitutionMembershipRole.methodist,
                InstitutionMembership.id != membership.id,
            )
        ).all()
        for row in others:
            row.is_primary = False
            row.updated_at = datetime.now(timezone.utc)

    if user.role == UserRole.student:
        user.role = UserRole.methodist

    notification_service.create(
        db=db,
        user_id=user.id,
        institution_id=int(institution_id),
        notification_type="methodist_membership_assigned",
        title="Назначение методистом",
        message="Вам назначена роль методиста в учебном учреждении.",
        data={"institution_id": int(institution_id)},
    )
    audit_log_service.record(
        db=db,
        institution_id=int(institution_id),
        actor_user_id=int(admin_membership.user_id),
        action="methodist_assigned",
        target_type="institution_membership",
        target_id=membership.id,
        metadata={"target_user_id": user.id},
    )

    db.commit()
    db.refresh(membership)
    return _serialize_membership(membership)


@router.get(
    "/institutions/{institution_id}/groups",
    response_model=list[InstitutionGroupResponse],
)
def list_groups(
    institution_id: int,
    db: DBSession,
    admin_membership: InstitutionMembership = _admin_membership_dependency(),
) -> list[InstitutionGroupResponse]:
    _assert_admin_scope(membership=admin_membership, institution_id=institution_id)

    groups = db.scalars(
        select(Group)
        .options(
            selectinload(Group.teacher_assignments)
            .joinedload(GroupTeacherAssignment.teacher_membership)
            .joinedload(InstitutionMembership.user)
        )
        .where(Group.institution_id == int(institution_id))
        .order_by(Group.id.desc())
    ).all()

    members_count_rows = db.execute(
        select(GroupMembership.group_id, func.count(GroupMembership.id))
        .where(GroupMembership.group_id.in_([group.id for group in groups] or [-1]))
        .group_by(GroupMembership.group_id)
    ).all()
    members_count = {int(row[0]): int(row[1] or 0) for row in members_count_rows}

    payload: list[InstitutionGroupResponse] = []
    for group in groups:
        teachers = [
            InstitutionGroupTeacherResponse(
                membership_id=int(link.teacher_membership.id),
                user_id=int(link.teacher_membership.user_id),
                full_name=link.teacher_membership.user.full_name,
                username=link.teacher_membership.user.username,
                email=link.teacher_membership.user.email,
            )
            for link in group.teacher_assignments
            if link.teacher_membership is not None and link.teacher_membership.user is not None
        ]
        payload.append(
            InstitutionGroupResponse(
                id=int(group.id),
                name=group.name,
                institution_id=int(group.institution_id or 0),
                members_count=members_count.get(int(group.id), 0),
                teachers=teachers,
            )
        )
    return payload


@router.post(
    "/institutions/{institution_id}/groups",
    response_model=InstitutionGroupResponse,
)
def create_group(
    institution_id: int,
    payload: InstitutionGroupCreateRequest,
    db: DBSession,
    admin_membership: InstitutionMembership = _admin_membership_dependency(),
) -> InstitutionGroupResponse:
    _assert_admin_scope(membership=admin_membership, institution_id=institution_id)

    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Название группы не может быть пустым.")

    exists = db.scalar(
        select(Group.id).where(
            Group.institution_id == int(institution_id),
            func.lower(Group.name) == name.lower(),
        )
    )
    if exists is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Группа с таким названием уже существует.")

    group = Group(
        name=name,
        institution_id=int(institution_id),
        teacher_id=None,
    )
    db.add(group)
    db.flush()

    audit_log_service.record(
        db=db,
        institution_id=int(institution_id),
        actor_user_id=int(admin_membership.user_id),
        action="group_created",
        target_type="group",
        target_id=group.id,
        metadata={"name": group.name},
    )
    db.commit()
    db.refresh(group)
    return InstitutionGroupResponse(
        id=int(group.id),
        name=group.name,
        institution_id=int(group.institution_id or 0),
        members_count=0,
        teachers=[],
    )


@router.get(
    "/institutions/{institution_id}/groups/{group_id}",
    response_model=InstitutionGroupDetailsResponse,
)
def get_group_details(
    institution_id: int,
    group_id: int,
    db: DBSession,
    admin_membership: InstitutionMembership = _admin_membership_dependency(),
) -> InstitutionGroupDetailsResponse:
    _assert_admin_scope(membership=admin_membership, institution_id=institution_id)

    group = assert_group_assignment_access(
        db=db,
        group_id=int(group_id),
        membership=admin_membership,
        require_teacher_assigned=False,
    )
    if int(group.institution_id or 0) != int(institution_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Группа недоступна.")

    memberships = db.scalars(
        select(GroupMembership)
        .options(joinedload(GroupMembership.student))
        .where(GroupMembership.group_id == group.id)
        .order_by(GroupMembership.id.asc())
    ).all()
    students = [
        InstitutionGroupStudentResponse(
            user_id=int(item.student.id),
            username=item.student.username,
            full_name=item.student.full_name,
            email=item.student.email,
        )
        for item in memberships
        if item.student is not None
    ]

    teacher_links = db.scalars(
        select(GroupTeacherAssignment)
        .options(
            joinedload(GroupTeacherAssignment.teacher_membership).joinedload(InstitutionMembership.user)
        )
        .where(GroupTeacherAssignment.group_id == group.id)
        .order_by(GroupTeacherAssignment.id.asc())
    ).all()
    teachers = [
        InstitutionGroupTeacherResponse(
            membership_id=int(link.teacher_membership.id),
            user_id=int(link.teacher_membership.user_id),
            full_name=link.teacher_membership.user.full_name,
            username=link.teacher_membership.user.username,
            email=link.teacher_membership.user.email,
        )
        for link in teacher_links
        if link.teacher_membership is not None and link.teacher_membership.user is not None
    ]

    return InstitutionGroupDetailsResponse(
        id=int(group.id),
        name=group.name,
        institution_id=int(group.institution_id or 0),
        members_count=len(students),
        teachers=teachers,
        students=students,
    )


@router.post(
    "/institutions/{institution_id}/groups/{group_id}/teachers",
    response_model=InstitutionGroupResponse,
)
def assign_teacher_to_group(
    institution_id: int,
    group_id: int,
    payload: InstitutionGroupAssignTeacherRequest,
    db: DBSession,
    admin_membership: InstitutionMembership = _admin_membership_dependency(),
) -> InstitutionGroupResponse:
    _assert_admin_scope(membership=admin_membership, institution_id=institution_id)

    group = assert_group_assignment_access(
        db=db,
        group_id=int(group_id),
        membership=admin_membership,
        require_teacher_assigned=False,
    )
    if int(group.institution_id or 0) != int(institution_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Группа недоступна.")

    teacher_membership = db.get(InstitutionMembership, int(payload.teacher_membership_id))
    if teacher_membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Членство преподавателя не найдено.")
    if int(teacher_membership.institution_id) != int(institution_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Преподаватель из другого учреждения.")
    if teacher_membership.role != InstitutionMembershipRole.teacher:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Указанное членство не является преподавателем.")
    if teacher_membership.status != InstitutionMembershipStatus.active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Преподаватель не активен.")

    link = db.scalar(
        select(GroupTeacherAssignment).where(
            GroupTeacherAssignment.group_id == group.id,
            GroupTeacherAssignment.teacher_membership_id == teacher_membership.id,
        )
    )
    if link is None:
        link = GroupTeacherAssignment(
            group_id=group.id,
            teacher_membership_id=teacher_membership.id,
            assigned_by_membership_id=admin_membership.id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(link)

    if group.teacher_id is None:
        group.teacher_id = int(teacher_membership.user_id)

    notification_service.create(
        db=db,
        user_id=int(teacher_membership.user_id),
        institution_id=int(institution_id),
        notification_type="group_assignment",
        title="Назначение на группу",
        message=f"Вас назначили преподавателем группы «{group.name}».",
        data={"group_id": group.id},
    )
    audit_log_service.record(
        db=db,
        institution_id=int(institution_id),
        actor_user_id=int(admin_membership.user_id),
        action="group_teacher_assigned",
        target_type="group",
        target_id=group.id,
        metadata={"teacher_membership_id": teacher_membership.id},
    )

    db.commit()
    return _serialize_group_row(db=db, group=group)


@router.post(
    "/institutions/{institution_id}/groups/{group_id}/students",
    response_model=InstitutionGroupDetailsResponse,
)
def add_student_to_group(
    institution_id: int,
    group_id: int,
    payload: InstitutionStudentMembershipAssignRequest,
    db: DBSession,
    admin_membership: InstitutionMembership = _admin_membership_dependency(),
) -> InstitutionGroupDetailsResponse:
    _assert_admin_scope(membership=admin_membership, institution_id=institution_id)

    group = assert_group_assignment_access(
        db=db,
        group_id=int(group_id),
        membership=admin_membership,
        require_teacher_assigned=False,
    )
    if int(group.institution_id or 0) != int(institution_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Группа недоступна.")

    student = db.get(User, int(payload.student_user_id))
    if student is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Студент не найден.")

    student_membership = db.scalar(
        select(InstitutionMembership).where(
            InstitutionMembership.user_id == student.id,
            InstitutionMembership.institution_id == int(institution_id),
            InstitutionMembership.role == InstitutionMembershipRole.student,
        )
    )
    if student_membership is None and student.role != UserRole.student:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="В группу можно добавить только пользователя со студенческой ролью.",
        )

    if student_membership is None:
        student_membership = InstitutionMembership(
            user_id=student.id,
            institution_id=int(institution_id),
            role=InstitutionMembershipRole.student,
            status=InstitutionMembershipStatus.active,
            is_primary=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(student_membership)
    elif student_membership.status != InstitutionMembershipStatus.active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Студент не активен в учреждении.")

    exists = db.scalar(
        select(GroupMembership.id).where(
            GroupMembership.group_id == group.id,
            GroupMembership.student_id == student.id,
        )
    )
    if exists is None:
        current_count = db.scalar(
            select(func.count(GroupMembership.id)).where(GroupMembership.group_id == group.id)
        )
        if int(current_count or 0) >= int(settings.group_max_members):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"В группе может быть не более {int(settings.group_max_members)} участников.",
            )

        institution_group_ids = db.scalars(
            select(Group.id).where(Group.institution_id == int(institution_id))
        ).all()
        if institution_group_ids:
            db.execute(
                delete(GroupMembership).where(
                    GroupMembership.student_id == student.id,
                    GroupMembership.group_id.in_([int(item) for item in institution_group_ids]),
                )
            )
        db.add(GroupMembership(student_id=student.id, group_id=group.id))

    profile = db.get(StudentProfile, student.id)
    if profile is not None:
        profile.group_id = int(group.id)

    audit_log_service.record(
        db=db,
        institution_id=int(institution_id),
        actor_user_id=int(admin_membership.user_id),
        action="group_student_added",
        target_type="group",
        target_id=group.id,
        metadata={"student_user_id": student.id},
    )

    db.commit()
    return get_group_details(
        institution_id=int(institution_id),
        group_id=int(group_id),
        db=db,
        admin_membership=admin_membership,
    )


def _serialize_membership(membership: InstitutionMembership) -> InstitutionMembershipResponse:
    if membership.user is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Пользователь членства не найден.")
    return InstitutionMembershipResponse(
        id=int(membership.id),
        user_id=int(membership.user_id),
        institution_id=int(membership.institution_id),
        role=membership.role,
        status=membership.status,
        is_primary=bool(membership.is_primary),
        full_name=membership.user.full_name,
        username=membership.user.username,
        email=membership.user.email,
        created_at=membership.created_at,
        updated_at=membership.updated_at,
    )


def _serialize_teacher_application(item: TeacherApplication) -> TeacherApplicationResponse:
    if item.institution is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Учреждение заявки не найдено.")
    return TeacherApplicationResponse(
        id=int(item.id),
        applicant_user_id=int(item.applicant_user_id),
        institution={"id": int(item.institution.id), "name": str(item.institution.name)},
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


def _serialize_group_row(*, db: DBSession, group: Group) -> InstitutionGroupResponse:
    members_count = db.scalar(select(func.count(GroupMembership.id)).where(GroupMembership.group_id == group.id))
    teachers = db.scalars(
        select(GroupTeacherAssignment)
        .options(joinedload(GroupTeacherAssignment.teacher_membership).joinedload(InstitutionMembership.user))
        .where(GroupTeacherAssignment.group_id == group.id)
        .order_by(GroupTeacherAssignment.id.asc())
    ).all()
    teacher_payload = [
        InstitutionGroupTeacherResponse(
            membership_id=int(link.teacher_membership.id),
            user_id=int(link.teacher_membership.user_id),
            full_name=link.teacher_membership.user.full_name,
            username=link.teacher_membership.user.username,
            email=link.teacher_membership.user.email,
        )
        for link in teachers
        if link.teacher_membership is not None and link.teacher_membership.user is not None
    ]
    return InstitutionGroupResponse(
        id=int(group.id),
        name=group.name,
        institution_id=int(group.institution_id or 0),
        members_count=int(members_count or 0),
        teachers=teacher_payload,
    )
