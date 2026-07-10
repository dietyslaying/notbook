from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Optional, Any

class IntentType(str, Enum):
    DISEASE = "disease"
    DRUG = "drug"
    COMPARISON = "comparison"
    STUDY = "study"
    UNKNOWN = "unknown"

class NDMBlock(BaseModel):
    block_type: str
    content: str

class NDMDocument(BaseModel):
    """The Notbook Document Model. Strict JSON schema for LLM output."""
    title: str
    summary: str = Field(max_length=300)
    core_facts: List[str] = Field(max_items=3)
    expandable_details: str
    source_citation: str
    blocks: Optional[List[NDMBlock]] = None

class UIComponent(BaseModel):
    """A parsed piece of UI ready for rendering."""
    component_type: str # e.g., 'title', 'summary', 'fact_list', 'collapsible', 'source'
    data: Any

class TelegramScreen(BaseModel):
    """The final output ready for aiogram to send."""
    html_parts: List[str]
    inline_keyboard: List[List[dict]] # Button dicts
