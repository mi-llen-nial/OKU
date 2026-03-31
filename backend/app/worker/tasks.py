from __future__ import annotations

from datetime import datetime, timezone

from app.models import DifficultyLevel, PreferredLanguage
from app.services.teacher_material_service import (
    MaterialProviderError,
    MaterialQualityError,
    teacher_material_service,
)


def ping_worker() -> dict[str, str]:
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}


def generate_teacher_custom_material_task(
    *,
    topic: str,
    difficulty: str,
    language: str,
    questions_count: int,
    user_id: int,
) -> dict:
    """
    Heavy worker-side teacher material generation.

    Returns a JSON-serializable dict so `/api/v1/jobs/{job_id}` can safely serialize it.
    """
    try:
        resolved_difficulty = DifficultyLevel(str(difficulty))
        resolved_language = PreferredLanguage(str(language))
    except Exception:  # noqa: BLE001
        return {
            "error": {
                "code": "MATERIAL_INVALID_INPUT",
                "message": "Invalid difficulty/language values.",
            }
        }

    try:
        validated = teacher_material_service.generate_and_validate(
            topic=topic,
            difficulty=resolved_difficulty,
            language=resolved_language,
            questions_count=int(questions_count),
            user_id=int(user_id),
        )
    except MaterialProviderError as exc:
        return {
            "error": {
                "code": "MATERIAL_PROVIDER_FAILED",
                "message": str(exc),
            }
        }
    except MaterialQualityError as exc:
        return {
            "error": {
                "code": "MATERIAL_QUALITY_FAILED",
                "message": str(exc),
            }
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "error": {
                "code": "MATERIAL_FAILED",
                "message": str(exc),
            }
        }

    # TeacherCustomMaterialGenerateResponse-compatible payload.
    return {
        "topic": str(topic).strip(),
        "difficulty": resolved_difficulty.value,
        "questions_count": int(len(validated.questions)),
        "rejected_count": int(validated.rejected_count),
        "questions": [q.model_dump() for q in validated.questions],
    }

