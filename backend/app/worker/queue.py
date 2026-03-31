from __future__ import annotations

import logging
from typing import Any, Callable

from redis import Redis
from rq import Queue
from rq.job import Job

from app.core.config import settings

logger = logging.getLogger(__name__)


def get_queue(name: str = "default") -> Queue | None:
    if not settings.redis_enabled:
        return None
    try:
        connection = Redis.from_url(settings.redis_url)
        return Queue(name, connection=connection)
    except Exception as exc:  # noqa: BLE001
        logger.warning("RQ queue disabled: %s", exc)
        return None


def enqueue_task(
    task: Callable[..., Any],
    *args: Any,
    meta: dict[str, Any] | None = None,
    **kwargs: Any,
) -> str | None:
    queue = get_queue()
    if not queue:
        return None
    job = queue.enqueue(task, *args, meta=meta, **kwargs)
    return job.id


def get_job_status(job_id: str) -> dict[str, Any] | None:
    queue = get_queue()
    if not queue:
        return None
    try:
        job = Job.fetch(job_id, connection=queue.connection)
    except Exception:  # noqa: BLE001
        return None
    owner_user_id: int | None = None
    try:
        if isinstance(job.meta, dict) and "user_id" in job.meta:
            owner_user_id = int(job.meta.get("user_id"))
    except Exception:  # noqa: BLE001
        owner_user_id = None

    return {
        "id": job.id,
        "status": job.get_status(refresh=True),
        "result": job.result,
        "enqueued_at": job.enqueued_at.isoformat() if job.enqueued_at else None,
        "ended_at": job.ended_at.isoformat() if job.ended_at else None,
        "owner_user_id": owner_user_id,
    }

