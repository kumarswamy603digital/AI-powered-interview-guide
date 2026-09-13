from __future__ import annotations

from typing import List, Optional

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
    candidate_id: Optional[int] = None,
    extracted_text: Optional[str] = None,
    extraction_status: Optional[str] = None,
    extraction_detail: Optional[str] = None,
    extracted_skills: Optional[List[str]] = None,
) -> Resume:
    resume = Resume(
        user_id=user_id,
        candidate_id=candidate_id,
        original_filename=original_filename,
        stored_filename=stored_filename,
        content_type=content_type,
        size_bytes=size_bytes,
        storage_path=storage_path,
        extracted_text=extracted_text,
        extraction_status=extraction_status,
        extraction_detail=extraction_detail,
        extracted_skills=extracted_skills or [],
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return resume


def get_resume(db: Session, resume_id: int) -> Optional[Resume]:
    return db.query(Resume).filter(Resume.id == resume_id).first()


def list_resumes_for_user(db: Session, user_id: int, limit: int = 100) -> List[Resume]:
    return (
        db.query(Resume)
        .filter(Resume.user_id == user_id)
        .order_by(Resume.created_at.desc())
        .limit(limit)
        .all()
    )
