from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.resume import Resume


def create_resume(
    db: Session,
    *,
    user_id: int,
    original_filename: str,
    stored_filename: str,
    content_type: str,
    size_bytes: int,
    storage_path: str,
) -> Resume:
    resume = Resume(
        user_id=user_id,
        original_filename=original_filename,
        stored_filename=stored_filename,
        content_type=content_type,
        size_bytes=size_bytes,
        storage_path=storage_path,
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return resume

