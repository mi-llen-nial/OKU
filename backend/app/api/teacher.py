from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import DBSession, require_role
from app.models import User, UserRole
from app.schemas.teacher import GroupAnalyticsResponse, GroupWeakTopicsResponse
from app.schemas.tests import StudentProgressResponse
from app.services.progress import build_group_analytics, build_group_weak_topics, build_student_progress

router = APIRouter(prefix="/teacher", tags=["teacher"])


@router.get("/groups/{group_id}/analytics", response_model=GroupAnalyticsResponse)
def group_analytics(
    group_id: int,
    db: DBSession,
    _: User = Depends(require_role(UserRole.teacher)),
) -> GroupAnalyticsResponse:
    try:
        return build_group_analytics(db, group_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/groups/{group_id}/weak-topics", response_model=GroupWeakTopicsResponse)
def group_weak_topics(
    group_id: int,
    db: DBSession,
    _: User = Depends(require_role(UserRole.teacher)),
) -> GroupWeakTopicsResponse:
    try:
        return build_group_weak_topics(db, group_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/students/{student_id}/progress", response_model=StudentProgressResponse)
def student_progress_for_teacher(
    student_id: int,
    db: DBSession,
    _: User = Depends(require_role(UserRole.teacher)),
) -> StudentProgressResponse:
    target = db.get(User, student_id)
    if not target or target.role != UserRole.student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    return build_student_progress(db, student_id)
