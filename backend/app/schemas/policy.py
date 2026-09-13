from __future__ import annotations

from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class PolicyChunkRead(BaseModel):
    id: int
    section: Optional[str] = None
    content: str
    ordinal: int

    model_config = {"from_attributes": True}


class PolicyCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    category: Optional[str] = Field(default=None, max_length=128)
    version: Optional[str] = Field(default=None, max_length=32)
    effective_date: Optional[date] = None
    applies_to: Optional[str] = Field(
        default="all",
        max_length=255,
        description="Comma-separated audience, e.g. 'full_time, India'. 'all' applies to everyone.",
    )
    source_url: Optional[str] = None
    # Raw text; split into citable sections on save.
    content: str = Field(..., min_length=20)


class PolicyRead(BaseModel):
    id: int
    title: str
    category: Optional[str] = None
    version: Optional[str] = None
    effective_date: Optional[date] = None
    applies_to: Optional[str] = None
    source_url: Optional[str] = None
    section_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class PolicyDetailRead(PolicyRead):
    chunks: List[PolicyChunkRead] = Field(default_factory=list)


class PolicyAskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000)
    # Scopes the answer and raises caveats when a policy targets another group.
    employee_id: Optional[int] = None
    top_k: int = Field(default=4, ge=1, le=10)
    use_llm: bool = Field(
        default=True,
        description="Synthesise with Gemini when configured; retrieval and citations are unchanged.",
    )


class CitationRead(BaseModel):
    marker: str
    policy_id: Optional[int] = None
    policy_title: str
    section: Optional[str] = None
    version: Optional[str] = None
    effective_date: Optional[str] = None
    relevance: float
    excerpt: str


class PolicyAnswerRead(BaseModel):
    question: str
    answered: bool
    answer: str
    citations: List[CitationRead]
    confidence: Literal["high", "medium", "low"]
    matched_terms: List[str]
    unmatched_terms: List[str]
    related_policies: List[str]
    caveats: List[str]
    generated_by: Literal["gemini", "extractive", "refusal"]
    follow_up_suggestions: List[str] = Field(default_factory=list)
