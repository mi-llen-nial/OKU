from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import CurrentUser
from app.worker.queue import enqueue_task, get_job_status
from app.worker.tasks import ping_worker

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/ping")
def enqueue_ping(_: CurrentUser) -> dict[str, str]:
    job_id = enqueue_task(ping_worker)
    if not job_id:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Worker queue is unavailable")
    return {"job_id": job_id}


@router.get("/{job_id}")
def job_status(job_id: str, current_user: CurrentUser) -> dict:
    status_payload = get_job_status(job_id)
    if not status_payload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    owner_user_id = status_payload.get("owner_user_id")
    if owner_user_id is not None and int(owner_user_id) != int(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough rights")

    # Hide internal owner field from response payload.
    status_payload.pop("owner_user_id", None)
    return status_payload

