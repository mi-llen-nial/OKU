from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload

from app.core.config import settings
from app.core.deps import DBSession, require_role
from app.models import (
    Group,
    GroupMembership,
    TeacherAuthoredTest,
    TeacherAuthoredTestGroup,
    TestAssignment,
    TestModerationStatus,
    Test,
    TestSession,
    User,
    UserRole,
)
from app.schemas.tests import (
    GroupTestSummaryResponse,
    HistoryItemResponse,
    StudentDashboardResponse,
    StudentProgressResponse,
)
from app.services.cache import cache
from app.services.custom_tests import custom_test_duration_minutes
from app.services.progress import build_student_history, build_student_progress

router = APIRouter(prefix="/students/me", tags=["students"])


@router.get("/history", response_model=list[HistoryItemResponse])
def my_history(db: DBSession, current_user: User = Depends(require_role(UserRole.student))) -> list[HistoryItemResponse]:
    cache_key = f"student:{current_user.id}:history:v2"
    cached = cache.get_json(cache_key)
    if isinstance(cached, list):
        return [HistoryItemResponse.model_validate(item) for item in cached]

    payload = build_student_history(db, current_user.id)
    cache.set_json(cache_key, [item.model_dump(mode="json") for item in payload], ttl_seconds=settings.cache_history_ttl_seconds)
    return payload


@router.get("/progress", response_model=StudentProgressResponse)
def my_progress(db: DBSession, current_user: User = Depends(require_role(UserRole.student))) -> StudentProgressResponse:
    cache_key = f"student:{current_user.id}:progress:v2"
    cached = cache.get_json(cache_key)
    if isinstance(cached, dict):
        return StudentProgressResponse.model_validate(cached)

    payload = build_student_progress(db, current_user.id)
    cache.set_json(cache_key, payload.model_dump(mode="json"), ttl_seconds=settings.cache_progress_ttl_seconds)
    return payload


@router.get("/dashboard", response_model=StudentDashboardResponse)
def my_dashboard(db: DBSession, current_user: User = Depends(require_role(UserRole.student))) -> StudentDashboardResponse:
    cache_key = f"student:{current_user.id}:dashboard:v2"
    cached = cache.get_json(cache_key)
    if isinstance(cached, dict):
        return StudentDashboardResponse.model_validate(cached)

    progress = build_student_progress(db, current_user.id)
    history = build_student_history(db, current_user.id)
    payload = StudentDashboardResponse(progress=progress, history=history)
    cache.set_json(
        cache_key,
        payload.model_dump(mode="json"),
        ttl_seconds=min(settings.cache_progress_ttl_seconds, settings.cache_history_ttl_seconds),
    )
    return payload


@router.get("/group-tests", response_model=list[GroupTestSummaryResponse])
def my_group_tests(db: DBSession, current_user: User = Depends(require_role(UserRole.student))) -> list[GroupTestSummaryResponse]:
    cache_key = f"student:{current_user.id}:group-tests:v2"
    cached = cache.get_json(cache_key)
    if isinstance(cached, list):
        return [GroupTestSummaryResponse.model_validate(item) for item in cached]

    memberships = db.scalars(
        select(GroupMembership)
        .options(joinedload(GroupMembership.group).joinedload(Group.teacher))
        .where(GroupMembership.student_id == current_user.id)
        .order_by(GroupMembership.group_id.asc())
    ).all()
    if not memberships:
        cache.set_json(cache_key, [], ttl_seconds=settings.cache_history_ttl_seconds)
        return []

    groups_by_id: dict[int, Group] = {}
    for membership in memberships:
        if membership.group:
            groups_by_id[int(membership.group_id)] = membership.group

    if not groups_by_id:
        cache.set_json(cache_key, [], ttl_seconds=settings.cache_history_ttl_seconds)
        return []

    group_ids = sorted(groups_by_id.keys())
    assignment_rows = db.execute(
        select(TeacherAuthoredTest, TestAssignment.group_id)
        .join(TestAssignment, TestAssignment.test_id == TeacherAuthoredTest.id)
        .options(selectinload(TeacherAuthoredTest.questions), joinedload(TeacherAuthoredTest.teacher))
        .where(
            TestAssignment.group_id.in_(group_ids),
            TeacherAuthoredTest.moderation_status == TestModerationStatus.approved,
        )
        .order_by(TeacherAuthoredTest.created_at.desc())
    ).all()
    assigned_test_ids = {int(item[0].id) for item in assignment_rows}

    legacy_stmt = (
        select(TeacherAuthoredTest, TeacherAuthoredTestGroup.group_id)
        .join(
            TeacherAuthoredTestGroup,
            TeacherAuthoredTestGroup.test_id == TeacherAuthoredTest.id,
        )
        .options(selectinload(TeacherAuthoredTest.questions), joinedload(TeacherAuthoredTest.teacher))
        .where(
            TeacherAuthoredTestGroup.group_id.in_(group_ids),
            TeacherAuthoredTest.id.not_in(sorted(assigned_test_ids) or [-1]),
            TeacherAuthoredTest.institution_id.is_(None),
        )
        .order_by(TeacherAuthoredTest.created_at.desc())
    )
    legacy_rows = db.execute(legacy_stmt).all()
    rows = list(assignment_rows) + list(legacy_rows)
    rows.sort(key=lambda item: item[0].created_at, reverse=True)

    completed_by_custom_test_id: dict[int, Test] = {}
    completed_tests = db.scalars(
        select(Test)
        .join(TestSession, TestSession.test_id == Test.id)
        .options(joinedload(Test.session), joinedload(Test.result))
        .where(
            Test.student_id == current_user.id,
            TestSession.exam_kind == "group_custom",
            TestSession.submitted_at.is_not(None),
        )
        .order_by(Test.created_at.asc(), Test.id.asc())
    ).all()
    for completed_test in completed_tests:
        if not completed_test.session or not completed_test.result:
            continue
        custom_test_id = _extract_custom_test_id(completed_test.session.exam_config_json or {})
        if custom_test_id <= 0:
            continue
        if custom_test_id not in completed_by_custom_test_id:
            completed_by_custom_test_id[custom_test_id] = completed_test

    payload: list[GroupTestSummaryResponse] = []
    for custom_test, group_id in rows:
        group = groups_by_id.get(int(group_id))
        if not group:
            continue
        completed_test = completed_by_custom_test_id.get(int(custom_test.id))
        # Transitional compatibility:
        # - institution-scoped tests are visible only through explicit TestAssignment
        # - legacy link fallback is preserved only for pre-institutional tests
        if int(custom_test.id) not in assigned_test_ids and custom_test.institution_id is not None:
            continue

        payload.append(
            GroupTestSummaryResponse(
                custom_test_id=custom_test.id,
                title=custom_test.title,
                questions_count=len(custom_test.questions),
                duration_minutes=custom_test_duration_minutes(custom_test.time_limit_seconds),
                warning_limit=int(custom_test.warning_limit or 0),
                teacher_name=(custom_test.teacher.full_name or custom_test.teacher.username),
                group_id=group.id,
                group_name=group.name,
                created_at=custom_test.created_at,
                due_date=custom_test.due_date,
                is_completed=bool(completed_test),
                completed_percent=(None if not completed_test else float(completed_test.result.percent)),
                completed_test_id=(None if not completed_test else int(completed_test.id)),
            )
        )

    cache.set_json(cache_key, [item.model_dump(mode="json") for item in payload], ttl_seconds=settings.cache_history_ttl_seconds)
    return payload


def _extract_custom_test_id(config: dict) -> int:
    raw_custom_test_id = config.get("custom_test_id")
    if isinstance(raw_custom_test_id, str) and raw_custom_test_id.isdigit():
        return int(raw_custom_test_id)
    if isinstance(raw_custom_test_id, int):
        return int(raw_custom_test_id)
    return 0
