from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import Notification


class NotificationService:
    def create(
        self,
        *,
        db: Session,
        user_id: int,
        notification_type: str,
        title: str,
        message: str,
        institution_id: int | None = None,
        data: dict[str, Any] | None = None,
    ) -> Notification:
        row = Notification(
            user_id=int(user_id),
            institution_id=(int(institution_id) if institution_id is not None else None),
            type=str(notification_type).strip() or "info",
            title=str(title).strip() or "Уведомление",
            message=str(message).strip() or "",
            data_json=dict(data or {}),
            is_read=False,
            created_at=datetime.now(timezone.utc),
        )
        db.add(row)
        return row


notification_service = NotificationService()

