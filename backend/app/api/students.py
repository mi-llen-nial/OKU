from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.core.config import settings
from app.core.deps import DBSession, require_role
from app.models import Group, GroupMembership, TeacherAuthoredTest, TeacherAuthoredTestGroup, User, UserRole
from app.schemas.tests import (
    GroupTestSummaryResponse,
    HistoryItemResponse,
    StudentDashboardResponse,
    StudentProgressResponse,
)
from app.services.cache import cache
from app.services.progress import build_student_history, build_student_progress

router = APIRouter(prefix="/students/me", tags=["students"])


@router.get("/history", response_model=list[HistoryItemResponse])
def my_history(db: DBSession, current_user: User = Depends(require_role(UserRole.student))) -> list[HistoryItemResponse]:
    cache_key = f"student:{current_user.id}:history:v1"
    cached = cache.get_json(cache_key)
    if isinstance(cached, list):
        return [HistoryItemResponse.model_validate(item) for item in cached]

    payload = build_student_history(db, current_user.id)
    cache.set_json(cache_key, [item.model_dump(mode="json") for item in payload], ttl_seconds=settings.cache_history_ttl_seconds)
    return payload


@router.get("/progress", response_model=StudentProgressResponse)
def my_progress(db: DBSession, current_user: User = Depends(require_role(UserRole.student))) -> StudentProgressResponse:
    cache_key = f"student:{current_user.id}:progress:v1"
    cached = cache.get_json(cache_key)
    if isinstance(cached, dict):
        return StudentProgressResponse.model_validate(cached)

    payload = build_student_progress(db, current_user.id)
    cache.set_json(cache_key, payload.model_dump(mode="json"), ttl_seconds=settings.cache_progress_ttl_seconds)
    return payload


@router.get("/dashboard", response_model=StudentDashboardResponse)
def my_dashboard(db: DBSession, current_user: User = Depends(require_role(UserRole.student))) -> StudentDashboardResponse:
    cache_key = f"student:{current_user.id}:dashboard:v1"
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
    cache_key = f"student:{current_user.id}:group-tests:v1"
    cached = cache.get_json(cache_key)
    if isinstance(cached, list):
        return [GroupTestSummaryResponse.model_validate(item) for item in cached]

    membership = db.scalar(
        select(GroupMembership)
        .options(joinedload(GroupMembership.group).joinedload(Group.teacher))
        .where(GroupMembership.student_id == current_user.id)
    )
    if not membership or not membership.group:
        cache.set_json(cache_key, [], ttl_seconds=settings.cache_history_ttl_seconds)
        return []

    group = membership.group
    tests = db.scalars(
        select(TeacherAuthoredTest)
        .join(TeacherAuthoredTestGroup, TeacherAuthoredTestGroup.test_id == TeacherAuthoredTest.id)
        .options(joinedload(TeacherAuthoredTest.questions), joinedload(TeacherAuthoredTest.teacher))
        .where(TeacherAuthoredTestGroup.group_id == group.id)
        .order_by(TeacherAuthoredTest.created_at.desc())
    ).all()

    payload = [
        GroupTestSummaryResponse(
            custom_test_id=item.id,
            title=item.title,
            questions_count=len(item.questions),
            duration_minutes=max(1, item.time_limit_seconds // 60),
            warning_limit=int(item.warning_limit or 0),
            teacher_name=(item.teacher.full_name or item.teacher.username),
            group_id=group.id,
            group_name=group.name,
            created_at=item.created_at,
        )
        for item in tests
    ]
    cache.set_json(cache_key, [item.model_dump(mode="json") for item in payload], ttl_seconds=settings.cache_history_ttl_seconds)
    return payload
