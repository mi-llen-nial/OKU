from __future__ import annotations

import re

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Institution


_space_re = re.compile(r"\s+")


def normalize_institution_name(value: str) -> str:
    normalized = _space_re.sub(" ", (value or "").strip().lower())
    return normalized


def resolve_institution_for_application(
    *,
    db: Session,
    institution_id: int | None = None,
    institution_name: str | None = None,
) -> Institution:
    if institution_id is not None:
        institution = db.get(Institution, int(institution_id))
        if institution is None or not institution.is_active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Учебное учреждение не найдено.")
        return institution

    normalized_name = normalize_institution_name(str(institution_name or ""))
    if not normalized_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Укажите учебное учреждение для заявки.",
        )
    institution = db.scalar(
        select(Institution).where(
            func.lower(Institution.normalized_name) == normalized_name,
            Institution.is_active.is_(True),
        )
    )
    if institution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Учебное учреждение не найдено. Обратитесь к администратору учреждения.",
        )
    return institution

