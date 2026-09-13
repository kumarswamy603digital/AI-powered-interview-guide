from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.base import Base


class PolicyDocument(Base):
    """
    An HR policy document.

    Answers must be source-backed, so policies are stored as documents split into
    addressable sections rather than as one opaque blob.
    """

    __tablename__ = "policy_documents"

    id = Column(Integer, primary_key=True, index=True)

    title = Column(String(255), nullable=False)
    category = Column(String(128), nullable=True, index=True)  # leave|benefits|conduct|...
    version = Column(String(32), nullable=True)

    effective_date = Column(Date, nullable=True)
    applies_to = Column(String(255), nullable=True)  # e.g. "all", "India", "full_time"
    source_url = Column(String(1024), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    chunks = relationship(
        "PolicyChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="PolicyChunk.ordinal",
    )


class PolicyChunk(Base):
    """
    One addressable section of a policy.

    Retrieval works at this granularity so an answer can cite an exact section
    instead of a whole document.
    """

    __tablename__ = "policy_chunks"

    id = Column(Integer, primary_key=True, index=True)
    policy_document_id = Column(
        Integer, ForeignKey("policy_documents.id"), nullable=False, index=True
    )

    section = Column(String(255), nullable=True)  # e.g. "3.2 Carry-forward"
    content = Column(Text, nullable=False)
    ordinal = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    document = relationship("PolicyDocument", back_populates="chunks")
