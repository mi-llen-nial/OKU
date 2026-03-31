from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from app.core.config import settings


DATA_URL_IMAGE_RE = re.compile(
    r"^data:image/(?P<mime>[^;]+);base64,(?P<b64>[A-Za-z0-9+/=\s]+)$",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class ImageMaterialRef:
    mode: str
    sha256: str
    content_type: str | None = None
    object_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "sha256": self.sha256,
            "content_type": self.content_type,
            "object_key": self.object_key,
        }


class MaterialStorage:
    """
    Storage abstraction for teacher question images/materials.

    Current phase: do NOT change API contract.
    - DB mode keeps inline `image_data_url` exactly like today.
    - Object mode is prepared via `image_material_ref` reference fields only.

    Next phases can implement real S3-compatible uploads and retrieval by ref.
    """

    def __init__(self, *, mode: str) -> None:
        self._mode = mode.lower().strip() if mode else "db"
        if self._mode not in {"db", "object"}:
            self._mode = "db"

    def build_question_image_options(self, *, image_data_url: str) -> dict[str, Any]:
        image_data_url = (image_data_url or "").strip()
        if not image_data_url:
            return {}

        content_type = None
        match = DATA_URL_IMAGE_RE.match(image_data_url)
        if match:
            content_type = f"image/{match.group('mime').lower().strip()}"

        digest = hashlib.sha256(image_data_url.encode("utf-8")).hexdigest()
        sha256_short = digest[:16]

        if self._mode == "object":
            # Prepared ref for future S3-compatible storage. For now we still keep inline data
            # to preserve current UI and DB contract.
            ref = ImageMaterialRef(
                mode="object",
                sha256=sha256_short,
                content_type=content_type,
                object_key=f"teacher-question-images/{sha256_short}",
            )
        else:
            ref = ImageMaterialRef(
                mode="db",
                sha256=sha256_short,
                content_type=content_type,
            )

        return {
            "image_data_url": image_data_url,
            "image_material_ref": ref.to_dict(),
        }


material_storage = MaterialStorage(mode=settings.material_storage_mode)

