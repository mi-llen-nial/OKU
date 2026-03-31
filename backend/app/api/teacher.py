import csv
import io
import logging
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import joinedload, selectinload

from app.core.config import settings
from app.core.deps import DBSession, get_active_memberships, require_role
from app.models import (
    DifficultyLevel,
    Group,
    GroupInvitation,
    GroupInviteLink,
    GroupMembership,
    GroupTeacherAssignment,
    InstitutionMembership,
    InstitutionMembershipRole,
    InstitutionMembershipStatus,
    InvitationStatus,
    PreferredLanguage,
    StudentProfile,
    TeacherAuthoredQuestion,
    TeacherAuthoredTestGroup,
    TeacherAuthoredTest,
    TestAssignment,
    TestModerationStatus,
    TestReviewRequest,
    Test,
    TestSession,
    TestMode,
    User,
    UserSession,
    UserRole,
)
from app.schemas.groups import (
    GroupMemberResponse,
    GroupMembersResponse,
    TeacherGroupCreateRequest,
    TeacherGroupCreateResponse,
    TeacherGroupInviteLinkResponse,
    TeacherGroupUpdateRequest,
    TeacherGroupListItem,
    TeacherInvitationCreateRequest,
    TeacherInvitationResponse,
)
from app.schemas.teacher import GroupAnalyticsResponse, GroupWeakTopicsResponse
from app.schemas.teacher_tests import (
    TeacherCustomMaterialGenerateRequest,
    TeacherCustomMaterialParseResponse,
    TeacherCustomMaterialGenerateResponse,
    TeacherCustomMaterialQuestion,
    TeacherCustomTestAssignRequest,
    TeacherCustomTestAssignResponse,
    TeacherCustomTestCreateRequest,
    TeacherCustomTestUpdateRequest,
    TeacherCustomGroupBrief,
    TeacherCustomTestListItem,
    TeacherCustomTestSubmitReviewResponse,
    TeacherCustomTestResultsResponse,
    TeacherCustomTestResultsGroupItem,
    TeacherCustomTestResultsStudentItem,
    TeacherCustomTestResponse,
)
from app.schemas.tests import HistoryItemResponse, StudentProgressResponse
from app.services.cache import cache
from app.services.material_storage import material_storage
from app.services.custom_tests import custom_test_duration_minutes
from app.services.progress import (
    build_group_analytics,
    build_group_weak_topics,
    build_student_history,
    build_student_progress,
)
from app.services.teacher_file_import import MAX_IMPORT_SIZE_BYTES, parse_teacher_test_import_file
from app.services.teacher_material_service import (
    MaterialProviderError,
    MaterialQualityError,
    teacher_material_service,
)
from app.worker.queue import enqueue_task
from app.worker.tasks import generate_teacher_custom_material_task
from app.services.question_quality import validate_question_payload
from app.services.audit_logs import audit_log_service
from app.services.notifications import notification_service

router = APIRouter(prefix="/teacher", tags=["teacher"])
logger = logging.getLogger(__name__)


@router.get("/groups", response_model=list[TeacherGroupListItem])
def my_groups(
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.teacher)),
) -> list[TeacherGroupListItem]:
    memberships = _get_active_teacher_memberships(db=db, teacher_user_id=current_user.id)
    membership_ids = [int(item.id) for item in memberships]
    has_institutional_memberships = bool(membership_ids)

    assigned_rows = []
    if has_institutional_memberships:
        assigned_rows = db.execute(
            select(
                Group.id,
                Group.name,
                func.count(GroupMembership.id).label("members_count"),
            )
            .join(GroupTeacherAssignment, GroupTeacherAssignment.group_id == Group.id)
            .outerjoin(GroupMembership, GroupMembership.group_id == Group.id)
            .where(GroupTeacherAssignment.teacher_membership_id.in_(membership_ids))
            .group_by(Group.id)
            .order_by(Group.id.desc())
        ).all()
    assigned_ids = {int(row.id) for row in assigned_rows}

    legacy_rows = []
    if not has_institutional_memberships:
        legacy_rows = db.execute(
            select(
                Group.id,
                Group.name,
                func.count(GroupMembership.id).label("members_count"),
            )
            .outerjoin(GroupMembership, GroupMembership.group_id == Group.id)
            .where(
                Group.teacher_id == current_user.id,
                Group.institution_id.is_(None),
                Group.id.not_in(assigned_ids or [-1]),
            )
            .group_by(Group.id)
            .order_by(Group.id.desc())
        ).all()

    rows = list(assigned_rows) + list(legacy_rows)
    rows.sort(key=lambda item: int(item.id), reverse=True)
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
    _ = payload
    _ = db
    _ = current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Официальные группы создаёт администратор учебного учреждения.",
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
    _ = group_id
    _ = payload
    _ = db
    _ = current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Изменять официальные группы может только администратор учебного учреждения.",
    )


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(
    group_id: int,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.teacher)),
) -> None:
    _ = group_id
    _ = db
    _ = current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Удалять официальные группы может только администратор учебного учреждения.",
    )


@router.delete("/groups/{group_id}/members/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_group_member(
    group_id: int,
    student_id: int,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.teacher)),
) -> None:
    _ = group_id
    _ = student_id
    _ = db
    _ = current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Состав группы изменяет администратор учебного учреждения.",
    )


@router.post("/invitations", response_model=TeacherInvitationResponse)
def send_invitation(
    payload: TeacherInvitationCreateRequest,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.teacher)),
) -> TeacherInvitationResponse:
    _ = payload
    _ = db
    _ = current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Приглашения в институциональные группы отправляет администратор учебного учреждения.",
    )


@router.post("/groups/{group_id}/invite-link", response_model=TeacherGroupInviteLinkResponse)
def create_group_invite_link(
    group_id: int,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.teacher)),
) -> TeacherGroupInviteLinkResponse:
    _ = group_id
    _ = db
    _ = current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Ссылки-приглашения формирует администратор учебного учреждения.",
    )


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
    _ = invitation_id
    _ = db
    _ = current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Управление приглашениями выполняет администратор учебного учреждения.",
    )


@router.get("/custom-tests", response_model=list[TeacherCustomTestListItem])
def list_custom_tests(
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.teacher)),
) -> list[TeacherCustomTestListItem]:
    active_institution_ids = _get_active_teacher_institution_ids(db=db, teacher_user_id=current_user.id)
    tests = db.scalars(
        select(TeacherAuthoredTest)
        .options(
            selectinload(TeacherAuthoredTest.questions),
            selectinload(TeacherAuthoredTest.group_links).joinedload(TeacherAuthoredTestGroup.group),
            selectinload(TeacherAuthoredTest.assignments).joinedload(TestAssignment.group),
        )
        .where(TeacherAuthoredTest.teacher_id == current_user.id)
        .order_by(TeacherAuthoredTest.created_at.desc())
    ).all()
    visible_tests = [
        item
        for item in tests
        if item.institution_id is None or int(item.institution_id) in active_institution_ids
    ]
    return [_serialize_custom_test_list_item(item) for item in visible_tests]


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
    resolved_groups, institution_id = _resolve_teacher_groups_and_institution(
        db=db,
        teacher_user_id=current_user.id,
        group_ids=group_ids,
    )

    custom_test = TeacherAuthoredTest(
        teacher_id=current_user.id,
        institution_id=institution_id,
        title=title,
        time_limit_seconds=int(payload.duration_minutes) * 60,
        warning_limit=int(payload.warning_limit),
        due_date=payload.due_date,
        moderation_status=TestModerationStatus.draft,
    )
    db.add(custom_test)
    db.flush()

    _replace_custom_test_questions(
        db=db,
        custom_test_id=int(custom_test.id),
        title=title,
        questions=payload.questions,
    )
    _sync_custom_test_groups(
        db=db,
        custom_test=custom_test,
        target_group_ids=[int(group.id) for group in resolved_groups],
    )

    db.commit()
    db.refresh(custom_test)
    _invalidate_group_tests_cache(db=db, group_ids=group_ids)
    return _serialize_custom_test(db=db, custom_test_id=custom_test.id, teacher_id=current_user.id)


@router.patch("/custom-tests/{custom_test_id}", response_model=TeacherCustomTestResponse)
def update_custom_test(
    custom_test_id: int,
    payload: TeacherCustomTestUpdateRequest,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.teacher)),
) -> TeacherCustomTestResponse:
    custom_test = _get_teacher_custom_test(db=db, custom_test_id=custom_test_id, teacher_id=current_user.id)

    if custom_test.moderation_status in {TestModerationStatus.submitted_for_review, TestModerationStatus.in_review}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Тест находится на модерации и временно недоступен для редактирования.",
        )
    if custom_test.moderation_status in {TestModerationStatus.approved, TestModerationStatus.archived}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Одобренный или архивный тест нельзя изменить. Создайте новый тест.",
        )

    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Название теста не может быть пустым.")
    if len(payload.questions) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Добавьте хотя бы один вопрос.")

    group_ids = sorted({int(item) for item in payload.group_ids if int(item) > 0})
    resolved_groups, institution_id = _resolve_teacher_groups_and_institution(
        db=db,
        teacher_user_id=current_user.id,
        group_ids=group_ids,
        fallback_institution_id=(int(custom_test.institution_id) if custom_test.institution_id is not None else None),
    )

    previous_group_ids = sorted({int(group.id) for group in _resolve_custom_test_groups(custom_test)})

    custom_test.title = title
    custom_test.time_limit_seconds = int(payload.duration_minutes) * 60
    custom_test.warning_limit = int(payload.warning_limit)
    custom_test.due_date = payload.due_date
    custom_test.institution_id = institution_id
    custom_test.moderation_comment = None
    if custom_test.moderation_status in {TestModerationStatus.needs_revision, TestModerationStatus.rejected}:
        # Teacher updated the draft after feedback; resubmission is a separate explicit action.
        custom_test.moderation_status = TestModerationStatus.draft

    _replace_custom_test_questions(
        db=db,
        custom_test_id=int(custom_test.id),
        title=title,
        questions=payload.questions,
    )
    _sync_custom_test_groups(
        db=db,
        custom_test=custom_test,
        target_group_ids=[int(group.id) for group in resolved_groups],
    )

    db.commit()
    db.refresh(custom_test)
    _invalidate_group_tests_cache(db=db, group_ids=sorted(set(previous_group_ids + group_ids)))
    _invalidate_teacher_custom_results_cache(teacher_id=current_user.id, custom_test_id=int(custom_test.id))
    return _serialize_custom_test(db=db, custom_test_id=custom_test.id, teacher_id=current_user.id)


@router.post("/custom-tests/generate-material", response_model=TeacherCustomMaterialGenerateResponse)
@router.post("/material/generate", response_model=TeacherCustomMaterialGenerateResponse)
def generate_custom_test_material(
    payload: TeacherCustomMaterialGenerateRequest,
    current_user: User = Depends(require_role(UserRole.teacher)),
) -> TeacherCustomMaterialGenerateResponse:
    topic = payload.topic.strip()
    if not topic:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Тема не может быть пустой.")

    questions_count = max(1, int(payload.questions_count))
    try:
        validated = teacher_material_service.generate_and_validate(
            topic=topic,
            difficulty=payload.difficulty,
            language=payload.language,
            questions_count=questions_count,
            user_id=current_user.id,
        )
    except MaterialProviderError as exc:
        logger.error(
            "Teacher material generation provider failure user_id=%s topic=%r difficulty=%s language=%s questions_count=%s error=%s",
            current_user.id,
            topic,
            payload.difficulty.value,
            payload.language.value,
            questions_count,
            str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "MATERIAL_PROVIDER_FAILED",
                "message": "Не удалось получить ответ от AI-провайдера. Проверьте ключи и модель в окружении сервера.",
            },
        ) from exc
    except MaterialQualityError as exc:
        logger.warning(
            "Teacher material generation quality failure user_id=%s topic=%r difficulty=%s language=%s questions_count=%s error=%s",
            current_user.id,
            topic,
            payload.difficulty.value,
            payload.language.value,
            questions_count,
            str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "MATERIAL_QUALITY_FAILED",
                "message": str(exc),
            },
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Не удалось сгенерировать материал: {exc}",
        ) from exc

    return TeacherCustomMaterialGenerateResponse(
        topic=topic,
        difficulty=payload.difficulty,
        questions_count=len(validated.questions),
        rejected_count=int(validated.rejected_count),
        questions=validated.questions,
    )


@router.post("/material/generate-async")
def generate_custom_test_material_async(
    payload: TeacherCustomMaterialGenerateRequest,
    current_user: User = Depends(require_role(UserRole.teacher)),
) -> dict[str, str]:
    """
    Async worker-backed teacher material generation.

    Returns `job_id`. Poll it via `GET /api/v1/jobs/{job_id}`.
    """
    topic = payload.topic.strip()
    if not topic:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Тема не может быть пустой.")

    questions_count = max(1, int(payload.questions_count))
    job_id = enqueue_task(
        generate_teacher_custom_material_task,
        topic=topic,
        difficulty=payload.difficulty.value,
        language=payload.language.value,
        questions_count=questions_count,
        user_id=current_user.id,
        meta={"user_id": int(current_user.id)},
    )
    if not job_id:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Worker queue is unavailable")

    return {"job_id": job_id}


@router.post("/custom-tests/parse-file", response_model=TeacherCustomMaterialParseResponse)
async def parse_custom_test_file(
    file: UploadFile = File(...),
    current_user: User = Depends(require_role(UserRole.teacher)),
) -> TeacherCustomMaterialParseResponse:
    _ = current_user.id  # explicit for role-bound access and audit parity

    filename = (file.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Файл не выбран.")

    extension = Path(filename).suffix.lower()
    if extension not in {".docx", ".csv"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Поддерживаются только файлы .docx и .csv.",
        )

    chunks: list[bytes] = []
    total_size = 0
    chunk_size = 256 * 1024
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > MAX_IMPORT_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Размер файла превышает лимит 5MB.",
            )
        chunks.append(chunk)
    content = b"".join(chunks)

    try:
        parsed_questions = parse_teacher_test_import_file(filename=filename, content=content)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Не удалось распознать файл: {exc}",
        ) from exc

    return TeacherCustomMaterialParseResponse(
        source_filename=filename,
        questions_count=len(parsed_questions),
        questions=[
            TeacherCustomMaterialQuestion(
                prompt=str(item.get("prompt", "")).strip(),
                answer_type="free_text" if str(item.get("answer_type", "")).strip() == "free_text" else "choice",
                options=[str(option).strip() for option in (item.get("options") or []) if str(option).strip()],
                correct_option_index=(
                    int(item["correct_option_index"])
                    if isinstance(item.get("correct_option_index"), (int, float, str))
                    and str(item.get("correct_option_index")).lstrip("-").isdigit()
                    else None
                ),
                sample_answer=(
                    None
                    if item.get("sample_answer") is None
                    else (str(item.get("sample_answer", "")).strip() or None)
                ),
                image_data_url=(
                    None
                    if item.get("image_data_url") is None
                    else (str(item.get("image_data_url", "")).strip() or None)
                ),
            )
            for item in parsed_questions
        ],
    )


@router.get("/custom-tests/{custom_test_id}", response_model=TeacherCustomTestResponse)
def get_custom_test(
    custom_test_id: int,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.teacher)),
) -> TeacherCustomTestResponse:
    return _serialize_custom_test(db=db, custom_test_id=custom_test_id, teacher_id=current_user.id)


@router.post("/custom-tests/{custom_test_id}/submit-review", response_model=TeacherCustomTestSubmitReviewResponse)
def submit_custom_test_for_review(
    custom_test_id: int,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.teacher)),
) -> TeacherCustomTestSubmitReviewResponse:
    custom_test = _get_teacher_custom_test(db=db, custom_test_id=custom_test_id, teacher_id=current_user.id)
    institution_id = _resolve_custom_test_institution_id(db=db, custom_test=custom_test)
    membership = _get_teacher_membership_for_institution(
        db=db,
        teacher_user_id=current_user.id,
        institution_id=institution_id,
    )

    if custom_test.moderation_status in {TestModerationStatus.submitted_for_review, TestModerationStatus.in_review}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Тест уже отправлен на модерацию.",
        )
    if custom_test.moderation_status in {TestModerationStatus.needs_revision, TestModerationStatus.rejected}:
        custom_test.current_draft_version = int(custom_test.current_draft_version or 1) + 1

    now = datetime.now(timezone.utc)
    custom_test.moderation_status = TestModerationStatus.submitted_for_review
    custom_test.submitted_for_review_at = now
    custom_test.reviewed_at = None
    custom_test.reviewed_by_membership_id = None
    custom_test.moderation_comment = None
    custom_test.institution_id = institution_id

    review_request = TestReviewRequest(
        institution_id=institution_id,
        test_id=custom_test.id,
        submitted_version=int(custom_test.current_draft_version or 1),
        status=TestModerationStatus.submitted_for_review,
        requested_by_membership_id=membership.id,
        reviewer_membership_id=None,
        comment=None,
        created_at=now,
        reviewed_at=None,
    )
    db.add(review_request)

    methodist_memberships = db.scalars(
        select(InstitutionMembership).where(
            InstitutionMembership.institution_id == institution_id,
            InstitutionMembership.role == InstitutionMembershipRole.methodist,
            InstitutionMembership.status == InstitutionMembershipStatus.active,
        )
    ).all()
    for row in methodist_memberships:
        notification_service.create(
            db=db,
            user_id=int(row.user_id),
            institution_id=institution_id,
            notification_type="test_submitted_for_review",
            title="Новый тест на модерацию",
            message=f"Тест «{custom_test.title}» отправлен на проверку.",
            data={"test_id": custom_test.id, "version": custom_test.current_draft_version},
        )

    audit_log_service.record(
        db=db,
        institution_id=institution_id,
        actor_user_id=current_user.id,
        action="test_submitted_for_review",
        target_type="teacher_authored_test",
        target_id=custom_test.id,
        metadata={
            "status": custom_test.moderation_status.value,
            "version": custom_test.current_draft_version,
        },
    )

    db.commit()
    db.refresh(custom_test)
    return TeacherCustomTestSubmitReviewResponse(
        test_id=int(custom_test.id),
        status=custom_test.moderation_status,
        current_draft_version=int(custom_test.current_draft_version or 1),
        submitted_for_review_at=custom_test.submitted_for_review_at or now,
    )


@router.post("/custom-tests/{custom_test_id}/assign", response_model=TeacherCustomTestAssignResponse)
def assign_custom_test_to_groups(
    custom_test_id: int,
    payload: TeacherCustomTestAssignRequest,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.teacher)),
) -> TeacherCustomTestAssignResponse:
    custom_test = _get_teacher_custom_test(db=db, custom_test_id=custom_test_id, teacher_id=current_user.id)
    if custom_test.moderation_status != TestModerationStatus.approved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Назначать группе можно только тест в статусе approved.",
        )

    group_ids = sorted({int(item) for item in payload.group_ids if int(item) > 0})
    if not group_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Выберите минимум одну группу.")

    institution_id = _resolve_custom_test_institution_id(db=db, custom_test=custom_test)
    membership = _get_teacher_membership_for_institution(
        db=db,
        teacher_user_id=current_user.id,
        institution_id=institution_id,
    )
    groups = _get_teacher_accessible_groups(
        db=db,
        teacher_user_id=current_user.id,
        group_ids=group_ids,
        institution_id=institution_id,
    )
    group_map = {int(group.id): group for group in groups}
    missing_group_ids = [group_id for group_id in group_ids if group_id not in group_map]
    if missing_group_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Часть выбранных групп не найдена или недоступна.",
        )

    assigned_group_ids: list[int] = []
    for group_id in group_ids:
        link = db.scalar(
            select(TestAssignment).where(
                TestAssignment.test_id == custom_test.id,
                TestAssignment.group_id == group_id,
            )
        )
        if link is None:
            db.add(
                TestAssignment(
                    test_id=custom_test.id,
                    group_id=group_id,
                    assigned_by_membership_id=membership.id,
                )
            )
        legacy_link = db.scalar(
            select(TeacherAuthoredTestGroup).where(
                TeacherAuthoredTestGroup.test_id == custom_test.id,
                TeacherAuthoredTestGroup.group_id == group_id,
            )
        )
        if legacy_link is None:
            db.add(
                TeacherAuthoredTestGroup(
                    test_id=custom_test.id,
                    group_id=group_id,
                )
            )
        assigned_group_ids.append(group_id)

    audit_log_service.record(
        db=db,
        institution_id=institution_id,
        actor_user_id=current_user.id,
        action="test_assigned_to_groups",
        target_type="teacher_authored_test",
        target_id=custom_test.id,
        metadata={"group_ids": assigned_group_ids},
    )

    db.commit()
    _invalidate_group_tests_cache(db=db, group_ids=assigned_group_ids)
    return TeacherCustomTestAssignResponse(
        test_id=int(custom_test.id),
        status=custom_test.moderation_status,
        assigned_group_ids=assigned_group_ids,
    )


@router.get("/custom-tests/{custom_test_id}/results", response_model=TeacherCustomTestResultsResponse)
def get_custom_test_results(
    custom_test_id: int,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.teacher)),
    group_ids: list[int] = Query(default=[]),
) -> TeacherCustomTestResultsResponse:
    normalized_group_ids = sorted({int(group_id) for group_id in group_ids if int(group_id) > 0})
    cache_key = _teacher_custom_results_cache_key(
        teacher_id=current_user.id,
        custom_test_id=custom_test_id,
        group_ids=normalized_group_ids,
    )
    cached = cache.get_json(cache_key)
    if isinstance(cached, dict):
        return TeacherCustomTestResultsResponse.model_validate(cached)

    custom_test = _get_teacher_custom_test(db=db, custom_test_id=custom_test_id, teacher_id=current_user.id)
    groups_payload, students_payload = _build_custom_test_results_payload(
        db=db,
        custom_test=custom_test,
        selected_group_ids=normalized_group_ids,
    )
    payload = TeacherCustomTestResultsResponse(
        custom_test_id=custom_test.id,
        title=custom_test.title,
        questions_count=len(custom_test.questions),
        warning_limit=int(custom_test.warning_limit or 0),
        due_date=custom_test.due_date,
        groups=groups_payload,
        students=students_payload,
    )
    cache.set_json(cache_key, payload.model_dump(mode="json"), ttl_seconds=60)
    return payload


@router.get("/custom-tests/{custom_test_id}/results.csv")
def export_custom_test_results_csv(
    custom_test_id: int,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.teacher)),
    group_ids: list[int] = Query(default=[]),
) -> Response:
    custom_test = _get_teacher_custom_test(db=db, custom_test_id=custom_test_id, teacher_id=current_user.id)
    _, students_payload = _build_custom_test_results_payload(
        db=db,
        custom_test=custom_test,
        selected_group_ids=group_ids,
    )

    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["Имя", "Результат", "Предупреждения", "Сдано", "Группа"])
    for row in students_payload:
        percent_value = "–" if row.percent is None else f"{round(row.percent, 1):g}%"
        warning_value = "–" if row.warning_count is None else str(row.warning_count)
        submitted_value = row.submitted_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M") if row.submitted_at else "–"
        writer.writerow([
            _sanitize_csv_cell(row.full_name),
            _sanitize_csv_cell(percent_value),
            _sanitize_csv_cell(warning_value),
            _sanitize_csv_cell(submitted_value),
            _sanitize_csv_cell(row.group_name),
        ])

    filename = f"custom_test_{custom_test.id}_results.csv"
    content = stream.getvalue()
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=content, media_type="text/csv; charset=utf-8", headers=headers)


@router.delete("/custom-tests/{custom_test_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_custom_test(
    custom_test_id: int,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.teacher)),
) -> None:
    custom_test = _get_teacher_custom_test(db=db, custom_test_id=custom_test_id, teacher_id=current_user.id)
    affected_group_ids = sorted({
        int(group.id)
        for group in _resolve_custom_test_groups(custom_test)
    })
    _invalidate_teacher_custom_results_cache(teacher_id=current_user.id, custom_test_id=custom_test.id)
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
    groups = _get_teacher_accessible_groups(
        db=db,
        teacher_user_id=teacher_id,
        group_ids=[group_id],
    )
    if not groups:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Группа недоступна")
    return groups[0]


def _assert_student_visible_to_teacher(*, db: DBSession, teacher_id: int, student_id: int) -> None:
    student = db.get(User, student_id)
    if not student or student.role != UserRole.student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Студент не найден")

    teacher_memberships = _get_active_teacher_memberships(db=db, teacher_user_id=teacher_id)
    membership_ids = [int(item.id) for item in teacher_memberships]
    membership = None
    if membership_ids:
        membership = db.scalar(
            select(GroupMembership)
            .join(GroupTeacherAssignment, GroupTeacherAssignment.group_id == GroupMembership.group_id)
            .where(
                GroupMembership.student_id == student_id,
                GroupTeacherAssignment.teacher_membership_id.in_(membership_ids),
            )
        )
    if not membership:
        if teacher_memberships:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Студент не относится к вашим группам")

        legacy_membership = db.scalar(
            select(GroupMembership)
            .join(Group, Group.id == GroupMembership.group_id)
            .where(
                GroupMembership.student_id == student_id,
                Group.teacher_id == teacher_id,
                Group.institution_id.is_(None),
            )
        )
        if legacy_membership is not None:
            return
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Студент не относится к вашим группам")


def _count_teacher_groups(*, db: DBSession, teacher_id: int) -> int:
    memberships = _get_active_teacher_memberships(db=db, teacher_user_id=teacher_id)
    membership_ids = [int(item.id) for item in memberships]
    assigned_count = 0
    if membership_ids:
        assigned_count = int(
            db.scalar(
                select(func.count(func.distinct(GroupTeacherAssignment.group_id))).where(
                    GroupTeacherAssignment.teacher_membership_id.in_(membership_ids)
                )
            )
            or 0
        )
    legacy_count = 0
    if not memberships:
        legacy_count = int(
            db.scalar(
                select(func.count(Group.id)).where(
                    Group.teacher_id == teacher_id,
                    Group.institution_id.is_(None),
                )
            )
            or 0
        )
    value = int(assigned_count or 0) + int(legacy_count or 0)
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


def _effective_group_members_limit() -> int:
    return max(30, int(settings.group_max_members or 0))


def _generate_group_invite_token(*, db: DBSession) -> str:
    for _ in range(12):
        candidate = secrets.token_urlsafe(24)
        exists = db.scalar(
            select(GroupInviteLink.id).where(
                GroupInviteLink.token == candidate,
            )
        )
        if exists is None:
            return candidate
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Не удалось создать ссылку приглашения. Попробуйте снова.",
    )


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


def _serialize_group_invite_link(*, link: GroupInviteLink, group_name: str) -> TeacherGroupInviteLinkResponse:
    return TeacherGroupInviteLinkResponse(
        token=link.token,
        teacher_id=int(link.teacher_id),
        group_id=int(link.group_id),
        group_name=group_name,
        is_active=bool(link.is_active),
        expires_at=link.expires_at,
    )


def _get_teacher_custom_test(*, db: DBSession, custom_test_id: int, teacher_id: int) -> TeacherAuthoredTest:
    custom_test = db.scalar(
        select(TeacherAuthoredTest)
        .options(
            selectinload(TeacherAuthoredTest.questions),
            selectinload(TeacherAuthoredTest.group_links).joinedload(TeacherAuthoredTestGroup.group),
            selectinload(TeacherAuthoredTest.assignments).joinedload(TestAssignment.group),
        )
        .where(
            TeacherAuthoredTest.id == custom_test_id,
            TeacherAuthoredTest.teacher_id == teacher_id,
        )
    )
    if not custom_test:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тест не найден")
    if custom_test.institution_id is not None:
        _get_teacher_membership_for_institution(
            db=db,
            teacher_user_id=teacher_id,
            institution_id=int(custom_test.institution_id),
        )
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
            image_data_url = str((question.options_json or {}).get("image_data_url", "")).strip() or None
        else:
            options = []
            answer_type = "free_text"
            correct_option_index = None
            sample_answer = str((question.correct_answer_json or {}).get("sample_answer", "")).strip() or None
            image_data_url = str((question.options_json or {}).get("image_data_url", "")).strip() or None

        questions.append(
            {
                "id": question.id,
                "order_index": question.order_index,
                "prompt": question.prompt,
                "answer_type": answer_type,
                "options": options,
                "correct_option_index": correct_option_index,
                "sample_answer": sample_answer,
                "image_data_url": image_data_url,
            }
        )

    return TeacherCustomTestResponse(
        id=custom_test.id,
        title=custom_test.title,
        duration_minutes=custom_test_duration_minutes(custom_test.time_limit_seconds),
        warning_limit=custom_test.warning_limit,
        due_date=custom_test.due_date,
        questions_count=len(custom_test.questions),
        groups=_serialize_custom_groups(custom_test),
        moderation_status=custom_test.moderation_status,
        moderation_comment=custom_test.moderation_comment,
        submitted_for_review_at=custom_test.submitted_for_review_at,
        reviewed_at=custom_test.reviewed_at,
        current_draft_version=int(custom_test.current_draft_version or 1),
        approved_version=custom_test.approved_version,
        created_at=custom_test.created_at,
        updated_at=custom_test.updated_at,
        questions=questions,
    )


def _serialize_custom_groups(custom_test: TeacherAuthoredTest) -> list[TeacherCustomGroupBrief]:
    payload: list[TeacherCustomGroupBrief] = []
    seen_group_ids: set[int] = set()
    for group in _resolve_custom_test_groups(custom_test):
        if int(group.id) in seen_group_ids:
            continue
        seen_group_ids.add(int(group.id))
        payload.append(TeacherCustomGroupBrief(id=int(group.id), name=group.name))
    return payload


def _serialize_custom_test_list_item(custom_test: TeacherAuthoredTest) -> TeacherCustomTestListItem:
    return TeacherCustomTestListItem(
        id=custom_test.id,
        title=custom_test.title,
        duration_minutes=custom_test_duration_minutes(custom_test.time_limit_seconds),
        warning_limit=custom_test.warning_limit,
        due_date=custom_test.due_date,
        questions_count=len(custom_test.questions),
        groups=_serialize_custom_groups(custom_test),
        moderation_status=custom_test.moderation_status,
        moderation_comment=custom_test.moderation_comment,
        submitted_for_review_at=custom_test.submitted_for_review_at,
        reviewed_at=custom_test.reviewed_at,
        current_draft_version=int(custom_test.current_draft_version or 1),
        approved_version=custom_test.approved_version,
        created_at=custom_test.created_at,
        updated_at=custom_test.updated_at,
    )


def _build_custom_test_results_payload(
    *,
    db: DBSession,
    custom_test: TeacherAuthoredTest,
    selected_group_ids: list[int],
) -> tuple[list[TeacherCustomTestResultsGroupItem], list[TeacherCustomTestResultsStudentItem]]:
    assigned_groups = sorted(_resolve_custom_test_groups(custom_test), key=lambda group: group.name.lower())
    assigned_group_ids = {group.id for group in assigned_groups}

    filtered_group_ids = sorted({int(group_id) for group_id in selected_group_ids if int(group_id) in assigned_group_ids})
    active_group_ids = filtered_group_ids or sorted(assigned_group_ids)

    members_rows = []
    if active_group_ids:
        members_rows = db.execute(
            select(GroupMembership)
            .options(
                joinedload(GroupMembership.student),
                joinedload(GroupMembership.group),
            )
            .where(GroupMembership.group_id.in_(active_group_ids))
            .order_by(GroupMembership.id.asc())
        ).scalars().all()

    students_index: dict[tuple[int, int], dict] = {}
    for row in members_rows:
        if not row.student or not row.group:
            continue
        student_id = int(row.student_id)
        group_id = int(row.group_id)
        membership_key = (student_id, group_id)
        if membership_key in students_index:
            continue
        students_index[membership_key] = {
            "student_id": student_id,
            "full_name": (row.student.full_name or row.student.username),
            "group_id": group_id,
            "group_name": row.group.name,
            "percent": None,
            "warning_count": None,
            "submitted_at": None,
            "latest_test_id": None,
        }

    student_ids = sorted({key[0] for key in students_index.keys()})
    latest_attempt_by_membership: dict[tuple[int, int], Test] = {}
    latest_attempt_by_student: dict[int, Test] = {}
    if student_ids:
        unresolved_memberships: set[tuple[int, int]] = set(students_index.keys())
        unresolved_students: set[int] = set(student_ids)
        candidate_tests = db.scalars(
            select(Test)
            .join(TestSession, TestSession.test_id == Test.id)
            .options(
                joinedload(Test.session),
                joinedload(Test.result),
            )
            .where(
                Test.student_id.in_(student_ids),
                TestSession.exam_kind == "group_custom",
                TestSession.submitted_at.is_not(None),
                Test.created_at >= custom_test.created_at,
            )
            .order_by(Test.created_at.asc(), Test.id.asc())
        ).all()
        for test in candidate_tests:
            session = test.session
            if not session:
                continue
            config = session.exam_config_json or {}
            custom_test_id = config.get("custom_test_id")
            if not isinstance(custom_test_id, int) and not (isinstance(custom_test_id, str) and custom_test_id.isdigit()):
                continue
            if int(custom_test_id) != custom_test.id:
                continue
            cfg_group_id = config.get("group_id")
            if isinstance(cfg_group_id, str) and cfg_group_id.isdigit():
                cfg_group_id = int(cfg_group_id)
            if isinstance(cfg_group_id, int):
                if active_group_ids and cfg_group_id not in active_group_ids:
                    continue
                membership_key = (int(test.student_id), cfg_group_id)
                if membership_key in unresolved_memberships:
                    latest_attempt_by_membership[membership_key] = test
                    unresolved_memberships.discard(membership_key)
                    unresolved_students.discard(int(test.student_id))
                continue

            student_key = int(test.student_id)
            if student_key in unresolved_students:
                latest_attempt_by_student[student_key] = test
                unresolved_students.discard(student_key)

            if not unresolved_memberships and not unresolved_students:
                break

    students_payload: list[TeacherCustomTestResultsStudentItem] = []
    for membership_key, item in students_index.items():
        latest = latest_attempt_by_membership.get(membership_key) or latest_attempt_by_student.get(item["student_id"])
        if latest and latest.result and latest.session:
            item["percent"] = float(latest.result.percent)
            item["warning_count"] = int(latest.session.warning_count or 0)
            item["submitted_at"] = latest.session.submitted_at or latest.created_at
            item["latest_test_id"] = int(latest.id)
        students_payload.append(TeacherCustomTestResultsStudentItem(**item))

    students_payload.sort(key=lambda item: (item.full_name.lower(), item.group_name.lower()))

    member_count_by_group: dict[int, int] = {}
    if assigned_group_ids:
        for row in db.execute(
            select(GroupMembership.group_id, func.count(GroupMembership.id))
            .where(GroupMembership.group_id.in_(sorted(assigned_group_ids)))
            .group_by(GroupMembership.group_id)
        ).all():
            member_count_by_group[int(row[0])] = int(row[1] or 0)

    groups_payload = [
        TeacherCustomTestResultsGroupItem(
            id=int(group.id),
            name=group.name,
            members_count=member_count_by_group.get(int(group.id), 0),
            selected=(int(group.id) in active_group_ids),
        )
        for group in assigned_groups
    ]

    return groups_payload, students_payload


def _invalidate_group_tests_cache(*, db: DBSession, group_ids: list[int]) -> None:
    unique_group_ids = sorted({int(group_id) for group_id in group_ids if int(group_id) > 0})
    if not unique_group_ids:
        return
    student_ids = db.scalars(
        select(GroupMembership.student_id).where(GroupMembership.group_id.in_(unique_group_ids))
    ).all()
    keys = [f"student:{student_id}:group-tests:v2" for student_id in student_ids if student_id]
    if keys:
        cache.delete_many(*keys)


def _invalidate_teacher_custom_results_cache(*, teacher_id: int, custom_test_id: int) -> None:
    if int(teacher_id) <= 0 or int(custom_test_id) <= 0:
        return
    cache.delete_pattern(f"teacher:{int(teacher_id)}:custom-test:{int(custom_test_id)}:results:*")


def _teacher_custom_results_cache_key(*, teacher_id: int, custom_test_id: int, group_ids: list[int]) -> str:
    suffix = ",".join(str(group_id) for group_id in sorted({int(group_id) for group_id in group_ids if int(group_id) > 0}))
    return f"teacher:{teacher_id}:custom-test:{custom_test_id}:results:{suffix or 'all'}:v1"


def _sanitize_csv_cell(value: str) -> str:
    normalized = str(value or "")
    if normalized.startswith(("=", "+", "-", "@")):
        return f"'{normalized}"
    return normalized


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


def _get_active_teacher_memberships(*, db: DBSession, teacher_user_id: int) -> list[InstitutionMembership]:
    return get_active_memberships(
        db=db,
        user_id=int(teacher_user_id),
        roles={InstitutionMembershipRole.teacher},
    )


def _get_active_teacher_institution_ids(*, db: DBSession, teacher_user_id: int) -> set[int]:
    memberships = _get_active_teacher_memberships(db=db, teacher_user_id=teacher_user_id)
    return {int(item.institution_id) for item in memberships if int(item.institution_id) > 0}


def _get_teacher_membership_for_institution(
    *,
    db: DBSession,
    teacher_user_id: int,
    institution_id: int,
) -> InstitutionMembership:
    memberships = _get_active_teacher_memberships(db=db, teacher_user_id=teacher_user_id)
    for membership in memberships:
        if int(membership.institution_id) == int(institution_id):
            return membership
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="У вас нет активного членства преподавателя в этом учебном учреждении.",
    )


def _get_teacher_accessible_groups(
    *,
    db: DBSession,
    teacher_user_id: int,
    group_ids: list[int] | None = None,
    institution_id: int | None = None,
) -> list[Group]:
    memberships = _get_active_teacher_memberships(db=db, teacher_user_id=teacher_user_id)
    membership_ids = [int(item.id) for item in memberships]
    has_institutional_memberships = bool(membership_ids)

    assigned_stmt = (
        select(Group)
        .join(GroupTeacherAssignment, GroupTeacherAssignment.group_id == Group.id)
        .where(GroupTeacherAssignment.teacher_membership_id.in_(membership_ids or [-1]))
    )
    if group_ids is not None:
        normalized_ids = sorted({int(item) for item in group_ids if int(item) > 0})
        assigned_stmt = assigned_stmt.where(Group.id.in_(normalized_ids or [-1]))
    if institution_id is not None:
        assigned_stmt = assigned_stmt.where(Group.institution_id == int(institution_id))
    assigned_groups = db.scalars(assigned_stmt).all()

    groups_by_id: dict[int, Group] = {int(group.id): group for group in assigned_groups}
    requested_ids = sorted({int(item) for item in (group_ids or []) if int(item) > 0})
    missing_ids = [group_id for group_id in requested_ids if group_id not in groups_by_id]
    if missing_ids and institution_id is None and not has_institutional_memberships:
        legacy_stmt = select(Group).where(
            Group.id.in_(missing_ids),
            Group.teacher_id == int(teacher_user_id),
            Group.institution_id.is_(None),
        )
        for group in db.scalars(legacy_stmt).all():
            groups_by_id[int(group.id)] = group

    if group_ids is None and institution_id is None and not has_institutional_memberships:
        legacy_stmt = select(Group).where(
            Group.teacher_id == int(teacher_user_id),
            Group.institution_id.is_(None),
        )
        for group in db.scalars(legacy_stmt).all():
            groups_by_id.setdefault(int(group.id), group)

    return [groups_by_id[group_id] for group_id in sorted(groups_by_id.keys())]


def _resolve_teacher_groups_and_institution(
    *,
    db: DBSession,
    teacher_user_id: int,
    group_ids: list[int],
    fallback_institution_id: int | None = None,
) -> tuple[list[Group], int | None]:
    normalized_group_ids = sorted({int(group_id) for group_id in group_ids if int(group_id) > 0})
    groups = _get_teacher_accessible_groups(
        db=db,
        teacher_user_id=teacher_user_id,
        group_ids=normalized_group_ids,
    )
    groups_by_id = {int(group.id): group for group in groups}
    missing_group_ids = [group_id for group_id in normalized_group_ids if group_id not in groups_by_id]
    if missing_group_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Часть выбранных групп не найдена или недоступна.",
        )

    if not groups:
        if fallback_institution_id is not None:
            _get_teacher_membership_for_institution(
                db=db,
                teacher_user_id=teacher_user_id,
                institution_id=int(fallback_institution_id),
            )
            return [], int(fallback_institution_id)

        memberships = _get_active_teacher_memberships(db=db, teacher_user_id=teacher_user_id)
        if len(memberships) == 1:
            return [], int(memberships[0].institution_id)
        if len(memberships) > 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Для нескольких учреждений выберите группы одного учреждения.",
            )
        return [], None

    institution_ids = {
        int(group.institution_id)
        for group in groups
        if group.institution_id is not None
    }
    has_legacy_groups = any(group.institution_id is None for group in groups)
    if has_legacy_groups and institution_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Нельзя смешивать институциональные и legacy-группы в одном тесте.",
        )

    if len(institution_ids) > 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Тест может быть привязан только к одному учебному учреждению.",
        )

    institution_id = next(iter(institution_ids)) if institution_ids else None
    if institution_id is None and fallback_institution_id is not None:
        institution_id = int(fallback_institution_id)
    if (
        institution_id is not None
        and fallback_institution_id is not None
        and int(institution_id) != int(fallback_institution_id)
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Нельзя перенести тест между разными учебными учреждениями.",
        )

    if institution_id is not None:
        _get_teacher_membership_for_institution(
            db=db,
            teacher_user_id=teacher_user_id,
            institution_id=int(institution_id),
        )

    return [groups_by_id[group_id] for group_id in normalized_group_ids], institution_id


def _replace_custom_test_questions(
    *,
    db: DBSession,
    custom_test_id: int,
    title: str,
    questions: list,
) -> None:
    db.execute(
        delete(TeacherAuthoredQuestion).where(
            TeacherAuthoredQuestion.test_id == int(custom_test_id),
        )
    )

    for index, question in enumerate(questions):
        answer_type = "choice" if str(getattr(question, "answer_type", "")).strip() == "choice" else "free_text"
        prompt = str(getattr(question, "prompt", "") or "").strip()
        image_data_url = str(getattr(question, "image_data_url", "") or "").strip() or None

        if answer_type == "choice":
            options = [
                str(option).strip()
                for option in (getattr(question, "options", None) or [])
                if str(option).strip()
            ]
            correct_option_index = int(getattr(question, "correct_option_index", 0))
            payload = {
                "type": "single_choice",
                "prompt": prompt,
                "topic": title,
                "options": options,
                "correct_option_ids": [correct_option_index + 1],
            }
        else:
            payload = {
                "type": "short_text",
                "prompt": prompt,
                "topic": title,
                "sample_answer": str(getattr(question, "sample_answer", "") or "").strip(),
                "keywords": _extract_keywords(str(getattr(question, "sample_answer", "") or "")),
            }

        validated = validate_question_payload(
            payload=payload,
            language=PreferredLanguage.ru,
            mode=TestMode.text,
            difficulty=DifficultyLevel.medium,
        )
        if not validated.is_valid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Вопрос №{index + 1} не прошёл проверку качества: {'; '.join(validated.issues)}",
            )

        options_json = validated.payload.get("options_json")
        if not isinstance(options_json, dict):
            options_json = {}
        else:
            options_json = dict(options_json)
        if image_data_url:
            # Keep existing inline `image_data_url` contract,
            # but also store a ref field to prepare future object-storage migration.
            options_json.update(material_storage.build_question_image_options(image_data_url=image_data_url))
        if not options_json:
            options_json = None

        db.add(
            TeacherAuthoredQuestion(
                test_id=int(custom_test_id),
                order_index=int(index + 1),
                prompt=str(validated.payload.get("prompt", "")).strip(),
                question_type=str(validated.payload.get("type", "single_choice")).strip(),
                options_json=options_json,
                correct_answer_json=dict(validated.payload.get("correct_answer_json") or {}),
            )
        )


def _sync_custom_test_groups(
    *,
    db: DBSession,
    custom_test: TeacherAuthoredTest,
    target_group_ids: list[int],
) -> None:
    normalized_target_group_ids = sorted({int(group_id) for group_id in target_group_ids if int(group_id) > 0})
    target_ids_set = set(normalized_target_group_ids)

    current_link_group_ids = {
        int(group_id)
        for group_id in db.scalars(
            select(TeacherAuthoredTestGroup.group_id).where(
                TeacherAuthoredTestGroup.test_id == int(custom_test.id),
            )
        ).all()
    }
    links_to_remove = current_link_group_ids - target_ids_set
    if links_to_remove:
        db.execute(
            delete(TeacherAuthoredTestGroup).where(
                TeacherAuthoredTestGroup.test_id == int(custom_test.id),
                TeacherAuthoredTestGroup.group_id.in_(sorted(links_to_remove)),
            )
        )
    links_to_add = target_ids_set - current_link_group_ids
    for group_id in sorted(links_to_add):
        db.add(
            TeacherAuthoredTestGroup(
                test_id=int(custom_test.id),
                group_id=int(group_id),
            )
        )

    if custom_test.moderation_status != TestModerationStatus.approved:
        db.execute(
            delete(TestAssignment).where(
                TestAssignment.test_id == int(custom_test.id),
            )
        )
        return

    current_assignment_group_ids = {
        int(group_id)
        for group_id in db.scalars(
            select(TestAssignment.group_id).where(TestAssignment.test_id == int(custom_test.id))
        ).all()
    }
    assignments_to_remove = current_assignment_group_ids - target_ids_set
    if assignments_to_remove:
        db.execute(
            delete(TestAssignment).where(
                TestAssignment.test_id == int(custom_test.id),
                TestAssignment.group_id.in_(sorted(assignments_to_remove)),
            )
        )
    assignments_to_add = target_ids_set - current_assignment_group_ids
    for group_id in sorted(assignments_to_add):
        db.add(
            TestAssignment(
                test_id=int(custom_test.id),
                group_id=int(group_id),
                assigned_by_membership_id=None,
            )
        )


def _resolve_custom_test_groups(custom_test: TeacherAuthoredTest) -> list[Group]:
    groups: list[Group] = []
    for assignment in custom_test.assignments:
        if assignment.group is not None:
            groups.append(assignment.group)
    if groups:
        return groups

    for link in custom_test.group_links:
        if link.group is not None:
            groups.append(link.group)
    return groups


def _resolve_custom_test_institution_id(*, db: DBSession, custom_test: TeacherAuthoredTest) -> int:
    if custom_test.institution_id is not None:
        return int(custom_test.institution_id)

    group_institution_ids = {
        int(group.institution_id)
        for group in _resolve_custom_test_groups(custom_test)
        if group.institution_id is not None
    }
    if len(group_institution_ids) == 1:
        resolved = next(iter(group_institution_ids))
        custom_test.institution_id = resolved
        db.flush()
        return resolved

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Для модерации тест должен быть привязан к одному учебному учреждению.",
    )
