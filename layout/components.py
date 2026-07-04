import uuid
from enum import Enum
from typing import List, Optional, Literal, Any, Dict, Union
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Component State & Lifecycle
# ---------------------------------------------------------------------------

class RenderEvent(Enum):
    ADD = "ADD"
    UPDATE = "UPDATE"
    REMOVE = "REMOVE"
    REPLACE = "REPLACE"
    MOVE = "MOVE"
    EXPAND = "EXPAND"
    COLLAPSE = "COLLAPSE"
    STREAM_APPEND = "STREAM_APPEND"
    STREAM_COMPLETE = "STREAM_COMPLETE"
    ERROR = "ERROR"

class ComponentState(BaseModel):
    """Encapsulates the rendering and interactivity state of a component."""
    visible: bool = True
    collapsed: bool = False
    loading: bool = False
    interactive: bool = True
    disabled: bool = False
    priority: int = 1
    importance: Literal["low", "medium", "high"] = "medium"
    streamed: bool = False
    animated: bool = False
    selected: bool = False

# ---------------------------------------------------------------------------
# Base Component Hierarchy
# ---------------------------------------------------------------------------

class BaseComponent(BaseModel):
    version: str = "1.0"
    component_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: str
    state: ComponentState = Field(default_factory=ComponentState)
    source_chunk_ids: List[str] = Field(default_factory=list)
    
    supports_streaming: bool = False
    supports_collapse: bool = False
    supports_animation: bool = False
    supports_export: bool = True

# ---------------------------------------------------------------------------
# High-Level Semantic Components
# ---------------------------------------------------------------------------

class HeaderCardComponent(BaseComponent):
    type: Literal["header_card"] = "header_card"
    title: str
    icon: str = "📚"
    subtitle: Optional[str] = None

class FooterCardComponent(BaseComponent):
    type: Literal["footer_card"] = "footer_card"
    source_textbook: str
    chapter: Optional[str] = None
    page: Optional[str] = None
    confidence: Optional[str] = None

class TLDRComponent(BaseComponent):
    type: Literal["tldr"] = "tldr"
    text: str

class FactGridComponent(BaseComponent):
    type: Literal["fact_grid"] = "fact_grid"
    title: str = "QUICK FACTS"
    facts: Dict[str, str] # e.g. {"Prevalence": "5-7%", "Genetics": "Highly heritable"}

class SectionHeaderComponent(BaseComponent):
    type: Literal["section_header"] = "section_header"
    title: str
    icon: Optional[str] = None

class ReferenceCardComponent(BaseComponent):
    type: Literal["reference_card"] = "reference_card"
    citations: List[str]

class BlockQuoteComponent(BaseComponent):
    type: Literal["block_quote"] = "block_quote"
    text: str

class DetailsComponent(BaseComponent):
    type: Literal["details"] = "details"
    title: str
    text: str
    
class SpoilerComponent(BaseComponent):
    type: Literal["spoiler"] = "spoiler"
    text: str

class FigureComponent(BaseComponent):
    type: Literal["figure"] = "figure"
    caption: str
    
class SlideshowComponent(BaseComponent):
    type: Literal["slideshow"] = "slideshow"
    title: str
    
class VideoComponent(BaseComponent):
    type: Literal["video"] = "video"
    title: str
    
class AudioComponent(BaseComponent):
    type: Literal["audio"] = "audio"
    title: str


# ---------------------------------------------------------------------------
# Standard Layout Components
# ---------------------------------------------------------------------------

class ParagraphComponent(BaseComponent):
    type: Literal["paragraph"] = "paragraph"
    text: str
    supports_streaming: bool = True

class ChecklistComponent(BaseComponent):
    type: Literal["checklist"] = "checklist"
    items: List[str]
    supports_streaming: bool = True
    supports_collapse: bool = True

class TableComponent(BaseComponent):
    type: Literal["table"] = "table"
    headers: List[str]
    rows: List[List[str]]
    supports_collapse: bool = True

class MathComponent(BaseComponent):
    type: Literal["math"] = "math"
    latex: str

class TimelineComponent(BaseComponent):
    type: Literal["timeline"] = "timeline"
    events: List[Dict[str, str]]

class SubheaderComponent(BaseComponent):
    type: Literal["subheader"] = "subheader"
    title: str

class CalloutComponent(BaseComponent):
    type: Literal["callout"] = "callout"
    variant: Literal["clinical_pearl", "warning", "memory_aid", "info"]
    text: str
    title: Optional[str] = None

class DividerComponent(BaseComponent):
    type: Literal["divider"] = "divider"

# ---------------------------------------------------------------------------
# Section (Container)
# ---------------------------------------------------------------------------

class Section(BaseComponent):
    type: Literal["section"] = "section"
    kind: str # e.g. "overview", "symptoms", "treatment"
    components: List[BaseComponent] = Field(default_factory=list)
    supports_collapse: bool = True

# ---------------------------------------------------------------------------
# Root Document
# ---------------------------------------------------------------------------

class Document(BaseModel):
    version: str = "1.0"
    document_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    follow_up_questions: List[str] = Field(default_factory=list)
    sections: List[Section] = Field(default_factory=list)