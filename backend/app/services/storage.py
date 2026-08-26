"""
Local-disk file storage for user-uploaded images (product photos so far).

Local disk, not object storage — a deliberate dev-mode tradeoff (see
docs/DECISIONS.md), same pattern as other pragmatic choices in this repo
(e.g. JWT in localStorage). Swap for S3/R2 before a real production launch;
nothing above this module should need to change when that happens since
callers only ever see the returned relative URL.
"""
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"

_ALLOWED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

MAX_IMAGE_BYTES = 5 * 1024 * 1024


async def save_image(file: UploadFile) -> tuple[str, bytes]:
    """Validate, persist, and return (public_url, raw_bytes) for an uploaded image.

    Returns the raw bytes too since the AI describe endpoint needs them
    right after saving — avoids reading the file twice.
    """
    ext = _ALLOWED_CONTENT_TYPES.get(file.content_type or "")
    if ext is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported image type. Use JPEG, PNG, or WebP.",
        )

    content = await file.read()
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image too large (max 5 MB).",
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    (UPLOAD_DIR / filename).write_bytes(content)

    return f"/uploads/{filename}", content
