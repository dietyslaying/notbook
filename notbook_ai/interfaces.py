"""Shared domain models for intent, NDM, UI, and paginated screens."""

from __future__ import annotations

from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator


class IntentType(str, Enum):
    DISEASE = "disease"
    DRUG = "drug"
    COMPARISON = "comparison"
    STUDY = "study"
    UNKNOWN = "unknown"


class StudyMode(str, Enum):
    BRIEF = "brief"
    STANDARD = "standard"
    EXAM = "exam"
    WARD = "ward"


class NDMBlock(BaseModel):
    block_type: str
    content: str


class DetailSection(BaseModel):
    heading: str = Field(max_length=80)
    body: str = Field(max_length=1200)

    @field_validator("heading", "body", mode="before")
    @classmethod
    def coerce_str(cls, v: Any) -> str:
        return "" if v is None else str(v).strip()


class Citation(BaseModel):
    ref: str = ""
    chunk_id: str = ""
    book: str = ""
    page: Any = "N/A"
    score: float = 0.0
    hybrid_score: float = 0.0
    excerpt: str = ""
    namespace: str = ""


class NDMDocument(BaseModel):
    """Strict schema for LLM medical study output (ADHD-friendly)."""

    title: str = Field(max_length=120)
    summary: str = Field(max_length=320)
    core_facts: List[str] = Field(default_factory=list, max_length=3)
    detail_sections: List[DetailSection] = Field(default_factory=list, max_length=5)
    expandable_details: Optional[str] = None
    source_citation: str = Field(max_length=200)
    citations_used: Optional[List[str]] = None
    blocks: Optional[List[NDMBlock]] = None

    @field_validator("title", "summary", "source_citation", mode="before")
    @classmethod
    def coerce_str(cls, v: Any) -> str:
        return "" if v is None else str(v).strip()

    @field_validator("core_facts", mode="before")
    @classmethod
    def coerce_facts(cls, v: Any) -> list:
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return list(v)[:5]


class UIComponent(BaseModel):
    component_type: str
    data: Any


class TelegramScreen(BaseModel):
    html: str
    inline_keyboard: List[List[dict]] = Field(default_factory=list)
    page_index: int = 0
    page_count: int = 1


class ContentSession(BaseModel):
    concept_id: str
    user_id: int
    query: str
    intent: str
    title: str
    pages_html: List[str] = Field(default_factory=list)
    source: str = ""
    facts: List[str] = Field(default_factory=list)
    raw_ndm: dict = Field(default_factory=dict)
    study_mode: str = "standard"
    citations: List[dict] = Field(default_factory=list)
