"""Validation for binary uploads (images) that get injected into live sessions.

Kept separate from documents.py (text/PDF -> RAG) because images travel a different
path: they are stored as-is and shown to the model as visual frames, never chunked
or embedded."""

import os

# MIME types Gemini Live accepts as image input.
ALLOWED_IMAGE_MIME = {"image/png", "image/jpeg", "image/webp", "image/gif"}

# Map common extensions to a canonical MIME when the browser sends a blank/odd type.
_EXT_TO_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

# Cap upload size — live frames are downscaled anyway, and this bounds a BYTEA row.
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB


class ImageValidationError(Exception):
    """Raised when an upload is not an accepted, in-bounds image."""


def resolve_image_mime(filename: str, content_type: str | None) -> str | None:
    """Best-effort canonical image MIME from the declared content type, else the
    filename extension. Returns None if neither identifies a supported image."""
    if content_type and content_type.lower() in ALLOWED_IMAGE_MIME:
        return content_type.lower()
    ext = os.path.splitext(filename or "")[1].lower()
    return _EXT_TO_MIME.get(ext)


def validate_image(filename: str, content_type: str | None, data: bytes) -> str:
    """Validate an image upload and return its canonical MIME type.

    Raises ImageValidationError for an empty file, an unsupported type, or one that
    exceeds MAX_IMAGE_BYTES."""
    if not data:
        raise ImageValidationError("Empty file.")
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageValidationError(
            f"Image is too large ({len(data) // (1024 * 1024)} MB). Max is "
            f"{MAX_IMAGE_BYTES // (1024 * 1024)} MB."
        )
    mime = resolve_image_mime(filename, content_type)
    if mime is None:
        raise ImageValidationError(
            "Unsupported image type. Upload a PNG, JPEG, WebP, or GIF."
        )
    return mime
