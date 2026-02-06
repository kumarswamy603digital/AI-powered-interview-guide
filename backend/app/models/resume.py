from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.db.base import Base


class Resume(Base):
    __tablename__ = "resumes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    original_filename = Column(String(512), nullable=False)
    stored_filename = Column(String(512), nullable=False)
    content_type = Column(String(128), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    storage_path = Column(String(1024), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", backref="resumes")

