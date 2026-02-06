from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.crud.resume import create_resume
from app.db.session import get_db
from app.schemas.resume import ResumeRead
from app.schemas.user import UserRead


router = APIRouter(prefix="/api/resumes", tags=["resumes"])


DbSessionDep = Annotated[Session, Depends(get_db)]
CurrentUserDep = Annotated[UserRead, Depends(get_current_user)]


ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    # DOCX (Office Open XML)
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@router.post("/upload", response_model=ResumeRead, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    file: UploadFile = File(...),
    db: DbSessionDep = Depends(),
    current_user: CurrentUserDep = Depends(),
) -> ResumeRead:
    # Validate content type
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Only PDF and DOCX are allowed.",
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

    resume = create_resume(
        db,
        user_id=current_user.id,
        original_filename=original_name,
        stored_filename=stored_filename,
        content_type=file.content_type,
        size_bytes=size_bytes,
        storage_path=str(storage_path),
    )

    return ResumeRead.model_validate(resume)

