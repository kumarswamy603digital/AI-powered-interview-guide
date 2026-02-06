from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ResumeRead(BaseModel):
    id: int
    user_id: int
    original_filename: str
    stored_filename: str
    content_type: str
    size_bytes: int
    storage_path: str
    created_at: datetime

    model_config = {"from_attributes": True}

