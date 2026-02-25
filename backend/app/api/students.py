from fastapi import APIRouter, Depends

from app.core.deps import DBSession, require_role
from app.models import User, UserRole
from app.schemas.tests import HistoryItemResponse, StudentProgressResponse
from app.services.progress import build_student_history, build_student_progress

router = APIRouter(prefix="/students/me", tags=["students"])


@router.get("/history", response_model=list[HistoryItemResponse])
def my_history(db: DBSession, current_user: User = Depends(require_role(UserRole.student))) -> list[HistoryItemResponse]:
    return build_student_history(db, current_user.id)


@router.get("/progress", response_model=StudentProgressResponse)
def my_progress(db: DBSession, current_user: User = Depends(require_role(UserRole.student))) -> StudentProgressResponse:
    return build_student_progress(db, current_user.id)
