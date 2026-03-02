import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import joinedload, selectinload

from app.core.config import settings
from app.core.deps import DBSession, require_role
from app.models import (
    Group,
    GroupInvitation,
    GroupMembership,
    InvitationStatus,
    PreferredLanguage,
    StudentProfile,
    TeacherAuthoredQuestion,
    TeacherAuthoredTestGroup,
    TeacherAuthoredTest,
    User,
    UserSession,
    UserRole,
)
from app.schemas.groups import (
    GroupMemberResponse,
    GroupMembersResponse,
    TeacherGroupCreateRequest,
    TeacherGroupCreateResponse,
    TeacherGroupUpdateRequest,
    TeacherGroupListItem,
    TeacherInvitationCreateRequest,
    TeacherInvitationResponse,
)
from app.schemas.teacher import GroupAnalyticsResponse, GroupWeakTopicsResponse
from app.schemas.teacher_tests import (
    TeacherCustomTestCreateRequest,
    TeacherCustomGroupBrief,
    TeacherCustomTestListItem,
    TeacherCustomTestResponse,
)
from app.schemas.tests import HistoryItemResponse, StudentProgressResponse
from app.services.cache import cache
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
    groups_count = _count_teacher_groups(db=db, teacher_id=current_user.id)
    if groups_count >= settings.teacher_max_groups:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Можно создать не более {settings.teacher_max_groups} групп.",
        )

    group_name = payload.name.strip()
    if not group_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Название группы не может быть пустым")

    existing_group = db.scalar(select(Group).where(func.lower(Group.name) == group_name.lower()))
    if existing_group:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Группа с таким названием уже существует")

    student_ids = sorted(set(int(item) for item in payload.student_ids if int(item) > 0))
    if len(student_ids) > settings.group_max_members:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"В группе может быть не более {settings.group_max_members} участников.",
        )

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
        history = build_student_history(db, student.id)
        last_test_activity = history[0].created_at if history else None
        last_session_activity = db.scalar(
            select(func.max(UserSession.last_used_at)).where(
                UserSession.user_id == student.id,
                UserSession.revoked_at.is_(None),
            )
        )
        if last_test_activity and last_session_activity:
            last_activity = max(last_test_activity, last_session_activity)
        else:
            last_activity = last_test_activity or last_session_activity
        members.append(
            GroupMemberResponse(
                student_id=student.id,
                username=student.username,
                full_name=student.full_name,
                tests_count=progress.total_tests,
                avg_percent=progress.avg_percent,
                warnings_count=progress.total_warnings,
                weak_topic=(progress.weak_topics[0] if progress.weak_topics else None),
                last_activity_at=last_activity,
            )
        )

    return GroupMembersResponse(id=group.id, name=group.name, members=members)


@router.patch("/groups/{group_id}", response_model=TeacherGroupCreateResponse)
def rename_group(
    group_id: int,
    payload: TeacherGroupUpdateRequest,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.teacher)),
) -> TeacherGroupCreateResponse:
    group = _get_teacher_group(db=db, teacher_id=current_user.id, group_id=group_id)

    group_name = payload.name.strip()
    if not group_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Название группы не может быть пустым")

    existing_group = db.scalar(
        select(Group).where(
            Group.id != group.id,
            func.lower(Group.name) == group_name.lower(),
        )
    )
    if existing_group:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Группа с таким названием уже существует")

    group.name = group_name
    db.commit()

    members_count = _count_group_members(db=db, group_id=group.id)
    return TeacherGroupCreateResponse(
        id=group.id,
        name=group.name,
        members_count=members_count,
    )


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(
    group_id: int,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.teacher)),
) -> None:
    group = _get_teacher_group(db=db, teacher_id=current_user.id, group_id=group_id)

    profiles = db.scalars(select(StudentProfile).where(StudentProfile.group_id == group.id)).all()
    for profile in profiles:
        profile.group_id = None

    db.delete(group)
    db.commit()


@router.delete("/groups/{group_id}/members/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_group_member(
    group_id: int,
    student_id: int,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.teacher)),
) -> None:
    _get_teacher_group(db=db, teacher_id=current_user.id, group_id=group_id)

    membership = db.scalar(
        select(GroupMembership).where(
            GroupMembership.group_id == group_id,
            GroupMembership.student_id == student_id,
        )
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ученик не состоит в этой группе")

    db.delete(membership)

    profile = db.get(StudentProfile, student_id)
    if profile and profile.group_id == group_id:
        profile.group_id = None

    db.commit()


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
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ученик с таким username не найден")
    if student.role in {UserRole.teacher}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя отправлять приглашение аккаунтам с ролью teacher/admin.",
        )
    if student.role != UserRole.student:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Приглашать можно только учеников.")

    target_group = None
    if payload.group_id is not None:
        target_group = _get_teacher_group(
            db=db,
            teacher_id=current_user.id,
            group_id=payload.group_id,
        )
        if _is_student_in_group(db=db, student_id=student.id, group_id=target_group.id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Этот ученик уже состоит в выбранной группе.",
            )
        group_members_count = _count_group_members(db=db, group_id=target_group.id)
        if group_members_count >= settings.group_max_members:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"В группе уже максимум {settings.group_max_members} участников.",
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


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_invitation(
    invitation_id: int,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.teacher)),
) -> None:
    invitation = db.scalar(
        select(GroupInvitation).where(
            GroupInvitation.id == invitation_id,
            GroupInvitation.teacher_id == current_user.id,
        )
    )
    if not invitation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Приглашение не найдено")
    if invitation.status != InvitationStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Можно отменять только активные (ожидающие) приглашения.",
        )

    db.delete(invitation)
    db.commit()


@router.get("/custom-tests", response_model=list[TeacherCustomTestListItem])
def list_custom_tests(
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.teacher)),
) -> list[TeacherCustomTestListItem]:
    tests = db.scalars(
        select(TeacherAuthoredTest)
        .options(
            selectinload(TeacherAuthoredTest.questions),
            selectinload(TeacherAuthoredTest.group_links).joinedload(TeacherAuthoredTestGroup.group),
        )
        .where(TeacherAuthoredTest.teacher_id == current_user.id)
        .order_by(TeacherAuthoredTest.created_at.desc())
    ).all()
    return [_serialize_custom_test_list_item(item) for item in tests]


@router.post("/custom-tests", response_model=TeacherCustomTestResponse)
def create_custom_test(
    payload: TeacherCustomTestCreateRequest,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.teacher)),
) -> TeacherCustomTestResponse:
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Название теста не может быть пустым.")

    if len(payload.questions) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Добавьте хотя бы один вопрос.")

    group_ids = sorted({int(item) for item in payload.group_ids if int(item) > 0})
    if not group_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Выберите минимум одну группу, в которую будет добавлен тест.",
        )

    teacher_groups = db.scalars(
        select(Group).where(
            Group.teacher_id == current_user.id,
            Group.id.in_(group_ids),
        )
    ).all()
    teacher_group_map = {group.id: group for group in teacher_groups}
    missing_group_ids = [group_id for group_id in group_ids if group_id not in teacher_group_map]
    if missing_group_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Часть выбранных групп не найдена или недоступна.",
        )

    custom_test = TeacherAuthoredTest(
        teacher_id=current_user.id,
        title=title,
        time_limit_seconds=int(payload.duration_minutes) * 60,
        warning_limit=int(payload.warning_limit),
    )
    db.add(custom_test)
    db.flush()

    for idx, question in enumerate(payload.questions, start=1):
        prompt = question.prompt.strip()
        if not prompt:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Вопрос #{idx} не может быть пустым.")

        if question.answer_type == "choice":
            options = [item.strip() for item in question.options if item and item.strip()]
            if len(options) < 2:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"В вопросе #{idx} с вариантами нужно минимум 2 варианта.",
                )
            if question.correct_option_index is None or question.correct_option_index < 0 or question.correct_option_index >= len(options):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"У вопроса #{idx} выберите корректный правильный вариант.",
                )

            options_json = {"options": [{"id": option_idx + 1, "text": option_text} for option_idx, option_text in enumerate(options)]}
            correct_answer_json = {"correct_option_ids": [int(question.correct_option_index) + 1]}
            question_type = "single_choice"
        else:
            sample_answer = (question.sample_answer or "").strip()
            if not sample_answer:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Для вопроса #{idx} со свободным ответом укажите эталонный ответ.",
                )

            options_json = None
            correct_answer_json = {
                "sample_answer": sample_answer,
                "keywords": _extract_keywords(sample_answer),
            }
            question_type = "short_text"

        db.add(
            TeacherAuthoredQuestion(
                test_id=custom_test.id,
                order_index=idx,
                prompt=prompt,
                question_type=question_type,
                options_json=options_json,
                correct_answer_json=correct_answer_json,
            )
        )

    for group_id in group_ids:
        db.add(
            TeacherAuthoredTestGroup(
                test_id=custom_test.id,
                group_id=group_id,
            )
        )

    db.commit()
    db.refresh(custom_test)
    _invalidate_group_tests_cache(db=db, group_ids=group_ids)
    return _serialize_custom_test(db=db, custom_test_id=custom_test.id, teacher_id=current_user.id)


@router.get("/custom-tests/{custom_test_id}", response_model=TeacherCustomTestResponse)
def get_custom_test(
    custom_test_id: int,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.teacher)),
) -> TeacherCustomTestResponse:
    return _serialize_custom_test(db=db, custom_test_id=custom_test_id, teacher_id=current_user.id)


@router.delete("/custom-tests/{custom_test_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_custom_test(
    custom_test_id: int,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.teacher)),
) -> None:
    custom_test = _get_teacher_custom_test(db=db, custom_test_id=custom_test_id, teacher_id=current_user.id)
    affected_group_ids = sorted({link.group_id for link in custom_test.group_links})
    db.delete(custom_test)
    db.commit()
    _invalidate_group_tests_cache(db=db, group_ids=affected_group_ids)


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


def _count_teacher_groups(*, db: DBSession, teacher_id: int) -> int:
    value = db.scalar(select(func.count(Group.id)).where(Group.teacher_id == teacher_id))
    return int(value or 0)


def _count_group_members(*, db: DBSession, group_id: int) -> int:
    value = db.scalar(select(func.count(GroupMembership.id)).where(GroupMembership.group_id == group_id))
    return int(value or 0)


def _is_student_in_group(*, db: DBSession, student_id: int, group_id: int) -> bool:
    membership = db.scalar(
        select(GroupMembership).where(
            GroupMembership.student_id == student_id,
            GroupMembership.group_id == group_id,
        )
    )
    return membership is not None


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


def _get_teacher_custom_test(*, db: DBSession, custom_test_id: int, teacher_id: int) -> TeacherAuthoredTest:
    custom_test = db.scalar(
        select(TeacherAuthoredTest)
        .options(
            selectinload(TeacherAuthoredTest.questions),
            selectinload(TeacherAuthoredTest.group_links).joinedload(TeacherAuthoredTestGroup.group),
        )
        .where(
            TeacherAuthoredTest.id == custom_test_id,
            TeacherAuthoredTest.teacher_id == teacher_id,
        )
    )
    if not custom_test:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тест не найден")
    return custom_test


def _serialize_custom_test(*, db: DBSession, custom_test_id: int, teacher_id: int) -> TeacherCustomTestResponse:
    custom_test = _get_teacher_custom_test(db=db, custom_test_id=custom_test_id, teacher_id=teacher_id)
    questions = []
    for question in custom_test.questions:
        if question.question_type == "single_choice":
            options = [
                str(item.get("text", ""))
                for item in ((question.options_json or {}).get("options", []) or [])
                if str(item.get("text", "")).strip()
            ]
            answer_type = "choice"
            correct_ids = [
                int(item)
                for item in (question.correct_answer_json or {}).get("correct_option_ids", [])
                if isinstance(item, (int, float, str)) and str(item).isdigit()
            ]
            correct_option_index = (correct_ids[0] - 1) if correct_ids else None
            sample_answer = None
        else:
            options = []
            answer_type = "free_text"
            correct_option_index = None
            sample_answer = str((question.correct_answer_json or {}).get("sample_answer", "")).strip() or None

        questions.append(
            {
                "id": question.id,
                "order_index": question.order_index,
                "prompt": question.prompt,
                "answer_type": answer_type,
                "options": options,
                "correct_option_index": correct_option_index,
                "sample_answer": sample_answer,
            }
        )

    return TeacherCustomTestResponse(
        id=custom_test.id,
        title=custom_test.title,
        duration_minutes=max(1, custom_test.time_limit_seconds // 60),
        warning_limit=custom_test.warning_limit,
        questions_count=len(custom_test.questions),
        groups=_serialize_custom_groups(custom_test),
        created_at=custom_test.created_at,
        updated_at=custom_test.updated_at,
        questions=questions,
    )


def _serialize_custom_groups(custom_test: TeacherAuthoredTest) -> list[TeacherCustomGroupBrief]:
    payload: list[TeacherCustomGroupBrief] = []
    links = sorted(custom_test.group_links, key=lambda item: item.group_id)
    for link in links:
        if not link.group:
            continue
        payload.append(TeacherCustomGroupBrief(id=link.group.id, name=link.group.name))
    return payload


def _serialize_custom_test_list_item(custom_test: TeacherAuthoredTest) -> TeacherCustomTestListItem:
    return TeacherCustomTestListItem(
        id=custom_test.id,
        title=custom_test.title,
        duration_minutes=max(1, custom_test.time_limit_seconds // 60),
        warning_limit=custom_test.warning_limit,
        questions_count=len(custom_test.questions),
        groups=_serialize_custom_groups(custom_test),
        created_at=custom_test.created_at,
        updated_at=custom_test.updated_at,
    )


def _invalidate_group_tests_cache(*, db: DBSession, group_ids: list[int]) -> None:
    unique_group_ids = sorted({int(group_id) for group_id in group_ids if int(group_id) > 0})
    if not unique_group_ids:
        return
    student_ids = db.scalars(
        select(GroupMembership.student_id).where(GroupMembership.group_id.in_(unique_group_ids))
    ).all()
    keys = [f"student:{student_id}:group-tests:v1" for student_id in student_ids if student_id]
    if keys:
        cache.delete_many(*keys)


def _extract_keywords(sample_answer: str) -> list[str]:
    tokens = re.findall(r"[A-Za-zА-Яа-яӘәІіҢңҒғҮүҰұҚқӨөҺһ0-9]+", sample_answer.lower())
    seen: set[str] = set()
    keywords: list[str] = []
    for token in tokens:
        cleaned = token.strip()
        if len(cleaned) <= 2:
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        keywords.append(cleaned)
        if len(keywords) >= 8:
            break
    return keywords
