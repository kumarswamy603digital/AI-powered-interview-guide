from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.base import Base


class Resume(Base):
    __tablename__ = "resumes"

    id = Column(Integer, primary_key=True, index=True)
    # The HR user who uploaded the file.
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # The person the resume belongs to (null for self-service uploads).
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=True, index=True)

    original_filename = Column(String(512), nullable=False)
    stored_filename = Column(String(512), nullable=False)
    content_type = Column(String(128), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    storage_path = Column(String(1024), nullable=False)

    # Text extracted at upload time. Uploads used to be write-only blobs, which
    # forced every downstream feature to ask a human to paste the resume.
    extracted_text = Column(Text, nullable=True)
    # ok|empty|unsupported|missing_dependency|failed - see core/resume_text.py
    extraction_status = Column(String(32), nullable=True)
    extraction_detail = Column(String(512), nullable=True)
    extracted_skills = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", backref="resumes")
    candidate = relationship("Candidate", back_populates="resumes")
