from fastapi import APIRouter
from sqlalchemy import select

from app.core.deps import CurrentUser, DBSession
from app.models import Subject
from app.schemas.subjects import SubjectResponse

router = APIRouter(prefix="/subjects", tags=["subjects"])


@router.get("", response_model=list[SubjectResponse])
def list_subjects(_: CurrentUser, db: DBSession) -> list[SubjectResponse]:
    subjects = db.scalars(select(Subject).order_by(Subject.id.asc())).all()
    return [SubjectResponse.model_validate(item) for item in subjects]
