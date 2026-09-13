from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class ResumeRead(BaseModel):
    id: int
    user_id: int
    candidate_id: Optional[int] = None
    original_filename: str
    stored_filename: str
    content_type: str
    size_bytes: int
    storage_path: str
    created_at: datetime

    # Extraction outcome. The text itself is not returned here to keep upload
    # responses small; fetch it via the candidate profile when needed.
    extraction_status: Optional[str] = None
    extraction_detail: Optional[str] = None
    extracted_skills: List[str] = Field(default_factory=list)
    extracted_characters: int = 0

    model_config = {"from_attributes": True}

    @field_validator("extracted_skills", mode="before")
    @classmethod
    def _null_json_to_list(cls, value: Optional[List[str]]) -> List[str]:
        # Nullable JSON column: uploads that failed to parse store NULL.
        return list(value) if value else []


class ResumeTextRead(BaseModel):
    id: int
    candidate_id: Optional[int] = None
    extraction_status: Optional[str] = None
    extracted_skills: List[str] = Field(default_factory=list)
    extracted_text: str = ""
