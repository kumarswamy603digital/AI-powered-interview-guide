from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.resume_text import extract_resume_text
from app.core.skills import extract_skills
from app.crud.hr import get_candidate, latest_resume_for_candidate
from app.crud.resume import create_resume, get_resume, list_resumes_for_user
from app.db.session import get_db
from app.schemas.resume import ResumeRead, ResumeTextRead
from app.schemas.user import UserRead


router = APIRouter(prefix="/api/resumes", tags=["resumes"])


DbSessionDep = Annotated[Session, Depends(get_db)]
CurrentUserDep = Annotated[UserRead, Depends(get_current_user)]


ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    # DOCX (Office Open XML)
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    # Plain text, so a resume can be attached without a converter.
    "text/plain",
}


def _to_read(resume) -> ResumeRead:
    payload = ResumeRead.model_validate(resume)
    payload.extracted_characters = len(resume.extracted_text or "")
    payload.extracted_skills = list(resume.extracted_skills or [])
    return payload


@router.post("/upload", response_model=ResumeRead, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    file: UploadFile = File(...),
    candidate_id: Optional[int] = Form(default=None),
    db: DbSessionDep = Depends(),
    current_user: CurrentUserDep = Depends(),
) -> ResumeRead:
    # Validate content type
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Only PDF, DOCX and TXT are allowed.",
        )

    if candidate_id is not None and get_candidate(db, candidate_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate {candidate_id} not found.",
        )

    max_size_bytes = settings.RESUME_MAX_SIZE_MB * 1024 * 1024

    upload_dir = Path(settings.RESUME_UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    original_name = file.filename or "resume"
    extension = Path(original_name).suffix or ""
    stored_filename = f"{uuid4().hex}{extension}"
    storage_path = upload_dir / stored_filename

    size_bytes = 0

    # Stream file to disk while enforcing size limit
    try:
        with storage_path.open("wb") as buffer:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size_bytes += len(chunk)
                if size_bytes > max_size_bytes:
                    buffer.close()
                    try:
                        os.remove(storage_path)
                    except OSError:
                        pass
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File too large. Max size is {settings.RESUME_MAX_SIZE_MB}MB.",
                    )
                buffer.write(chunk)
    finally:
        await file.close()

    # Extract text now: everything downstream (ATS scoring, interview
    # personalisation, candidate ranking) needs text, not a stored blob.
    extraction = extract_resume_text(storage_path, file.content_type or "")
    skills = extract_skills(extraction.text) if extraction.text else []

    resume = create_resume(
        db,
        user_id=current_user.id,
        candidate_id=candidate_id,
        original_filename=original_name,
        stored_filename=stored_filename,
        content_type=file.content_type,
        size_bytes=size_bytes,
        storage_path=str(storage_path),
        extracted_text=extraction.text or None,
        extraction_status=extraction.status,
        extraction_detail=extraction.detail,
        extracted_skills=skills,
    )

    return _to_read(resume)


@router.get("", response_model=list[ResumeRead])
def list_my_resumes(
    db: DbSessionDep,
    current_user: CurrentUserDep,
) -> list[ResumeRead]:
    return [_to_read(r) for r in list_resumes_for_user(db, user_id=current_user.id)]


@router.get("/{resume_id}/text", response_model=ResumeTextRead)
def get_resume_text(
    resume_id: int,
    db: DbSessionDep,
    current_user: CurrentUserDep,
) -> ResumeTextRead:
    """Return the extracted text, e.g. to prefill an interview or ATS request."""
    resume = get_resume(db, resume_id)
    if resume is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    if resume.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    return ResumeTextRead(
        id=resume.id,
        candidate_id=resume.candidate_id,
        extraction_status=resume.extraction_status,
        extracted_skills=list(resume.extracted_skills or []),
        extracted_text=resume.extracted_text or "",
    )


@router.get("/candidates/{candidate_id}/latest", response_model=ResumeTextRead)
def get_latest_candidate_resume(
    candidate_id: int,
    db: DbSessionDep,
    current_user: CurrentUserDep,
) -> ResumeTextRead:
    """Latest resume text for a candidate, used to start an interview."""
    if get_candidate(db, candidate_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    resume = latest_resume_for_candidate(db, candidate_id)
    if resume is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No resume uploaded for this candidate",
        )

    return ResumeTextRead(
        id=resume.id,
        candidate_id=resume.candidate_id,
        extraction_status=resume.extraction_status,
        extracted_skills=list(resume.extracted_skills or []),
        extracted_text=resume.extracted_text or "",
    )
