import os
import uuid
from pathlib import Path
from typing import Optional
from fastapi import UploadFile, HTTPException, status

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
UPLOAD_DIR = Path("uploads/profiles")


async def save_profile_picture(file: UploadFile) -> str:
    """
    Validates and saves an uploaded profile picture to disk.
    Returns the relative URL path, e.g., '/uploads/profiles/{filename}'.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file uploaded."
        )

    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file extension {file_ext}. Allowed extensions: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    content_type = file.content_type
    if content_type and content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type {content_type}. Only JPEG, PNG, and WebP images are allowed."
        )

    # Read contents with size check
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds maximum allowed limit of 5MB."
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{file_ext}"
    target_path = UPLOAD_DIR / filename

    with open(target_path, "wb") as f:
        f.write(contents)

    return f"/uploads/profiles/{filename}"


def delete_old_profile_picture(old_url: Optional[str]) -> None:
    """
    Safely removes the previous profile picture from disk if it was stored locally.
    """
    if not old_url or not old_url.startswith("/uploads/profiles/"):
        return

    try:
        filename = Path(old_url).name
        target_path = UPLOAD_DIR / filename
        if target_path.exists() and target_path.is_file():
            target_path.unlink()
    except Exception:
        pass
