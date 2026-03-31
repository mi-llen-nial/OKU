from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


class AuditLogService:
    def record(
        self,
        *,
        db: Session,
        action: str,
        target_type: str,
        target_id: str | int,
        actor_user_id: int | None = None,
        institution_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditLog:
        row = AuditLog(
            institution_id=(int(institution_id) if institution_id is not None else None),
            actor_user_id=(int(actor_user_id) if actor_user_id is not None else None),
            action=str(action).strip() or "unknown_action",
            target_type=str(target_type).strip() or "unknown_target",
            target_id=str(target_id).strip() or "unknown",
            metadata_json=dict(metadata or {}),
            created_at=datetime.now(timezone.utc),
        )
        db.add(row)
        return row


audit_log_service = AuditLogService()

