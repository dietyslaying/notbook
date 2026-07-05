"""
notbook/interfaces.py — v1.1
Protocol contracts and data models for all Notbook AI modules.

RULES:
- All data models use pydantic.BaseModel (v2). Never @dataclass.
- All Protocols use typing.Protocol with @runtime_checkable.
- Never change an interface to fit an implementation.
- If you need a new field, add it here first, update the version, then implement.

VERSION: 1.1
"""
from __future__ import annotations
from typing import Protocol, runtime_checkable, Optional, Any
from enum import Enum
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class WorkspaceType(str, Enum):
    MENU       = "menu"
    DISEASE    = "disease"
    DRUG       = "drug"
    CASE       = "case"
    COMPARISON = "comparison"
    ALGORITHM  = "algorithm"
    LAB_TEST   = "lab_test"
    ANATOMY    = "anatomy"
    PROCEDURE  = "procedure"


class IntentType(str, Enum):
    TOPIC_OVERVIEW     = "topic_overview"
    TOPIC_SECTION      = "topic_section"
    DRUG_LOOKUP        = "drug_lookup"
    DRUG_SECTION       = "drug_section"
    CLINICAL_CASE      = "clinical_case"
    COMPARISON         = "comparison"
    ALGORITHM          = "algorithm"
    LAB_TEST           = "lab_test"
    QUIZ_REQUEST       = "quiz_request"
    FLASHCARD_REQUEST  = "flashcard_request"
    ANATOMY_LOOKUP     = "anatomy_lookup"
    PROCEDURE_LOOKUP   = "procedure_lookup"
    MAIN_MENU          = "main_menu"
    SETTINGS           = "settings"
    BOOKMARKS          = "bookmarks"
    UNKNOWN            = "unknown"


class UserMode(str, Enum):
    STUDENT        = "student"
    EXAM           = "exam"
    RAPID_REVISION = "rapid_revision"
    RESIDENT       = "resident"
    DEEP_STUDY     = "deep_study"
    PATIENT        = "patient"


class Confidence(str, Enum):
    HIGH       = "High"
    MEDIUM     = "Medium"
    LOW        = "Low"
    UNVERIFIED = "Unverified"


class Difficulty(str, Enum):
    EASY   = "easy"
    MEDIUM = "medium"
    HARD   = "hard"


class AnswerPosition(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class BotState(str, Enum):
    IDLE                           = "IDLE"
    LOADING                        = "LOADING"
    WORKSPACE_DISEASE_OVERVIEW     = "WORKSPACE_DISEASE_OVERVIEW"
    WORKSPACE_DISEASE_SYMPTOMS     = "WORKSPACE_DISEASE_SYMPTOMS"
    WORKSPACE_DISEASE_DIAGNOSIS    = "WORKSPACE_DISEASE_DIAGNOSIS"
    WORKSPACE_DISEASE_CRITERIA_DETAIL = "WORKSPACE_DISEASE_CRITERIA_DETAIL"
    WORKSPACE_DISEASE_TREATMENT    = "WORKSPACE_DISEASE_TREATMENT"
    WORKSPACE_DISEASE_PATHOPHYSIOLOGY = "WORKSPACE_DISEASE_PATHOPHYSIOLOGY"
    WORKSPACE_DISEASE_COMPLICATIONS = "WORKSPACE_DISEASE_COMPLICATIONS"
    WORKSPACE_DISEASE_EPIDEMIOLOGY = "WORKSPACE_DISEASE_EPIDEMIOLOGY"
    WORKSPACE_DISEASE_PROGNOSIS    = "WORKSPACE_DISEASE_PROGNOSIS"
    WORKSPACE_DISEASE_REFERENCES   = "WORKSPACE_DISEASE_REFERENCES"
    WORKSPACE_DRUG_OVERVIEW        = "WORKSPACE_DRUG_OVERVIEW"
    WORKSPACE_DRUG_MECHANISM       = "WORKSPACE_DRUG_MECHANISM"
    WORKSPACE_DRUG_INDICATIONS     = "WORKSPACE_DRUG_INDICATIONS"
    WORKSPACE_DRUG_DOSAGE          = "WORKSPACE_DRUG_DOSAGE"
    WORKSPACE_DRUG_SIDE_EFFECTS    = "WORKSPACE_DRUG_SIDE_EFFECTS"
    WORKSPACE_DRUG_CONTRAINDICATIONS = "WORKSPACE_DRUG_CONTRAINDICATIONS"
    WORKSPACE_DRUG_INTERACTIONS    = "WORKSPACE_DRUG_INTERACTIONS"
    WORKSPACE_DRUG_REFERENCES      = "WORKSPACE_DRUG_REFERENCES"
    WORKSPACE_CASE_PRESENTATION    = "WORKSPACE_CASE_PRESENTATION"
    WORKSPACE_CASE_FINDINGS        = "WORKSPACE_CASE_FINDINGS"
    WORKSPACE_CASE_DIFFERENTIAL    = "WORKSPACE_CASE_DIFFERENTIAL"
    WORKSPACE_CASE_DIAGNOSIS       = "WORKSPACE_CASE_DIAGNOSIS"
    WORKSPACE_CASE_MANAGEMENT      = "WORKSPACE_CASE_MANAGEMENT"
    WORKSPACE_CASE_REFERENCES      = "WORKSPACE_CASE_REFERENCES"
    WORKSPACE_COMPARISON_OVERVIEW  = "WORKSPACE_COMPARISON_OVERVIEW"
    WORKSPACE_COMPARISON_TABLE     = "WORKSPACE_COMPARISON_TABLE"
    WORKSPACE_COMPARISON_DIFFERENCES = "WORKSPACE_COMPARISON_DIFFERENCES"
    WORKSPACE_COMPARISON_REFERENCES = "WORKSPACE_COMPARISON_REFERENCES"
    WORKSPACE_ALGORITHM_OVERVIEW   = "WORKSPACE_ALGORITHM_OVERVIEW"
    WORKSPACE_ALGORITHM_STEP       = "WORKSPACE_ALGORITHM_STEP"
    WORKSPACE_LAB_OVERVIEW         = "WORKSPACE_LAB_OVERVIEW"
    WORKSPACE_LAB_HIGH             = "WORKSPACE_LAB_HIGH"
    WORKSPACE_LAB_LOW              = "WORKSPACE_LAB_LOW"
    WORKSPACE_LAB_SIGNIFICANCE     = "WORKSPACE_LAB_SIGNIFICANCE"
    WORKSPACE_LAB_RELATED          = "WORKSPACE_LAB_RELATED"
    QUIZ_SETUP                     = "QUIZ_SETUP"
    QUIZ_QUESTION                  = "QUIZ_QUESTION"
    QUIZ_FEEDBACK                  = "QUIZ_FEEDBACK"
    QUIZ_RESULTS                   = "QUIZ_RESULTS"
    QUIZ_REVIEW                    = "QUIZ_REVIEW"
    FLASHCARD_FRONT                = "FLASHCARD_FRONT"
    FLASHCARD_BACK                 = "FLASHCARD_BACK"
    BOOKMARKS_LIST                 = "BOOKMARKS_LIST"
    SETTINGS                       = "SETTINGS"
    MAIN_MENU                      = "MAIN_MENU"
    ERROR                          = "ERROR"


class EventType(str, Enum):
    EVT_TEXT_MESSAGE       = "EVT_TEXT_MESSAGE"
    EVT_CALLBACK_NAV       = "EVT_CALLBACK_NAV"
    EVT_CALLBACK_ANSWER    = "EVT_CALLBACK_ANSWER"
    EVT_CALLBACK_REVEAL    = "EVT_CALLBACK_REVEAL"
    EVT_CALLBACK_NEXT      = "EVT_CALLBACK_NEXT"
    EVT_CALLBACK_PREV      = "EVT_CALLBACK_PREV"
    EVT_CALLBACK_BACK      = "EVT_CALLBACK_BACK"
    EVT_CALLBACK_MENU      = "EVT_CALLBACK_MENU"
    EVT_CALLBACK_RESUME    = "EVT_CALLBACK_RESUME"
    EVT_CALLBACK_STARTOVER = "EVT_CALLBACK_STARTOVER"
    EVT_CALLBACK_FOLLOW_UP = "EVT_CALLBACK_FOLLOW_UP"
    EVT_LOAD_COMPLETE      = "EVT_LOAD_COMPLETE"
    EVT_LOAD_ERROR         = "EVT_LOAD_ERROR"
    EVT_STREAM_CHUNK       = "EVT_STREAM_CHUNK"
    EVT_STREAM_COMPLETE    = "EVT_STREAM_COMPLETE"


# ---------------------------------------------------------------------------
# Intent Engine Models
# ---------------------------------------------------------------------------

class IntentResult(BaseModel):
    intent_type: IntentType
    topic: Optional[str] = None
    topic_type: Optional[WorkspaceType] = None
    section: Optional[str] = None
    entities: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(0.0, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Knowledge / RAG Models
# ---------------------------------------------------------------------------

class Chunk(BaseModel):
    chunk_id: str
    chunk_type: str = "text"
    payload: dict[str, Any] = Field(default_factory=dict)
    text: str = ""
    textbook: str
    edition: Optional[str] = None
    chapter_number: Optional[str] = None
    chapter_name: Optional[str] = None
    pages: Optional[str] = None          # e.g. "1010-1014"
    retrieval_score: float = Field(0.0, ge=0.0, le=1.0)


class Reference(BaseModel):
    textbook: str
    edition: Optional[str] = None
    chapter_number: Optional[str] = None
    chapter_name: Optional[str] = None
    pages: Optional[str] = None
    chunk_ids: list[str] = Field(default_factory=list)
    retrieval_score: float = Field(0.0, ge=0.0, le=1.0)
    confidence: Confidence = Confidence.LOW


class KnowledgeTree(BaseModel):
    topic: str
    workspace_type: WorkspaceType
    chunks: list[Chunk] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    retrieved_at: float = 0.0             # Unix timestamp


# ---------------------------------------------------------------------------
# IA Generator Models
# ---------------------------------------------------------------------------

class ButtonSpec(BaseModel):
    label: str                            # Max 20 chars, emoji prefix required
    callback_data: str                    # Max 64 chars. Format: namespace:action:value
    tier: int = Field(2, ge=1, le=4)      # 1=primary, 2=secondary, 3=follow-up, 4=exit
    full_width: bool = False


class SectionSpec(BaseModel):
    section_id: str
    section_type: str
    has_content: bool = False
    content_chunks: list[str] = Field(default_factory=list)
    order: int = 0


class IASchema(BaseModel):
    workspace_type: WorkspaceType
    topic: str
    sections: list[SectionSpec] = Field(default_factory=list)
    nav_buttons: list[ButtonSpec] = Field(default_factory=list)
    user_mode: UserMode = UserMode.STUDENT


# ---------------------------------------------------------------------------
# Presentation Engine Models
# ---------------------------------------------------------------------------

class Component(BaseModel):
    component_type: str                   # "checklist", "paragraph", "ascii_table", etc.
    payload: dict[str, Any] = Field(default_factory=dict)


class Section(BaseModel):
    section_id: str
    kind: str
    components: list[Component] = Field(default_factory=list)
    supports_collapse: bool = False
    is_collapsed: bool = False


class Document(BaseModel):
    topic: str
    workspace_type: WorkspaceType
    sections: list[Section] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    ia_schema: Optional[IASchema] = None


# ---------------------------------------------------------------------------
# Platform Capabilities
# ---------------------------------------------------------------------------

class PlatformCapabilities(BaseModel):
    """
    Describes what the target platform can render natively.
    The Renderer consults this to decide how to degrade gracefully.
    Telegram is the current platform. Others are future.
    """
    platform_name: str = "telegram"
    supports_html: bool = True
    supports_markdown: bool = False
    supports_tables: bool = False          # Native <table> tags
    supports_math: bool = False            # Native LaTeX
    supports_collapsible: bool = False     # Native expandable sections
    supports_streaming: bool = True        # Can edit messages in place
    supports_images_in_message: bool = False  # Images in text messages
    max_message_length: int = 4096
    max_caption_length: int = 1024
    max_buttons_per_row: int = 8
    max_callback_data_length: int = 64


TELEGRAM_CAPABILITIES = PlatformCapabilities(
    platform_name="telegram",
    supports_html=True,
    supports_streaming=True,
    max_message_length=4096,
    max_buttons_per_row=8,
    max_callback_data_length=64,
)


# ---------------------------------------------------------------------------
# Renderer Models
# ---------------------------------------------------------------------------

class TelegramButton(BaseModel):
    text: str
    callback_data: str                    # Max 64 chars


class TelegramKeyboard(BaseModel):
    rows: list[list[TelegramButton]] = Field(default_factory=list)


class EditStrategy(str, Enum):
    EDIT_IN_PLACE  = "edit_in_place"      # Edit existing message (primary)
    SEND_NEW       = "send_new"           # Send new message (confirmations only)
    EDIT_KEYBOARD  = "edit_keyboard_only" # Only update buttons, not text


class TelegramScreen(BaseModel):
    """
    Full output of the Renderer. html is one field — not the entire output.
    This keeps future rich Telegram features and other platforms easy to adopt.
    """
    html: str                             # Telegram HTML (parse_mode="HTML")
    keyboard: Optional[TelegramKeyboard] = None
    char_count: int = 0                   # Must be <= 4096
    edit_strategy: EditStrategy = EditStrategy.EDIT_IN_PLACE
    parse_mode: str = "HTML"
    disable_web_page_preview: bool = True
    # Render metadata (for debugging and testing)
    screen_id: Optional[str] = None
    topic: Optional[str] = None
    components_used: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)  # e.g. "truncated at 4096"


# ---------------------------------------------------------------------------
# State Machine Models
# ---------------------------------------------------------------------------

class Event(BaseModel):
    event_type: EventType
    callback_data: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)


class TransitionResult(BaseModel):
    next_state: BotState
    actions: list[str] = Field(default_factory=list)
    is_forbidden: bool = False
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Session Models
# ---------------------------------------------------------------------------

class WorkspaceSession(BaseModel):
    session_id: str
    user_id: int
    topic: str
    workspace_type: WorkspaceType
    user_mode: UserMode = UserMode.STUDENT
    ia_schema: Optional[IASchema] = None
    knowledge_tree: Optional[KnowledgeTree] = None
    current_state: BotState = BotState.IDLE
    screen_history: list[BotState] = Field(default_factory=list)  # Max depth 10
    message_id: Optional[int] = None
    last_active: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"use_enum_values": True}


# ---------------------------------------------------------------------------
# Component Registry
# ---------------------------------------------------------------------------

class ComponentRegistry:
    """
    Maps content_type strings → component_type strings.
    PresentationEngine uses this instead of if/elif chains.

    Usage:
        registry = ComponentRegistry()
        registry.register("definition", "block_quote")
        component_type = registry.resolve("definition", item_count=1)
    """

    def __init__(self):
        self._rules: list[tuple[dict, str]] = []

    def register(
        self,
        component_type: str,
        *,
        content_type: str,
        min_items: int = 0,
        max_items: int = 9999,
        has_grouping: bool | None = None,
        has_comparison: bool | None = None,
    ) -> None:
        """Register a mapping rule. Rules are evaluated in registration order."""
        rule = {
            "content_type": content_type,
            "min_items": min_items,
            "max_items": max_items,
            "has_grouping": has_grouping,
            "has_comparison": has_comparison,
        }
        self._rules.append((rule, component_type))

    def resolve(
        self,
        content_type: str,
        item_count: int = 1,
        has_grouping: bool = False,
        has_comparison: bool = False,
    ) -> str:
        """
        Return the component_type for the given content characteristics.
        Returns "paragraph" as fallback if no rule matches.
        """
        for rule, component_type in self._rules:
            if rule["content_type"] != content_type:
                continue
            if not (rule["min_items"] <= item_count <= rule["max_items"]):
                continue
            if rule["has_grouping"] is not None and rule["has_grouping"] != has_grouping:
                continue
            if rule["has_comparison"] is not None and rule["has_comparison"] != has_comparison:
                continue
            return component_type
        return "paragraph"


# ---------------------------------------------------------------------------
# Quiz Models
# ---------------------------------------------------------------------------

class QuizOption(BaseModel):
    position: AnswerPosition
    text: str
    is_correct: bool


class QuizQuestion(BaseModel):
    question_id: str
    question_text: str
    options: list[QuizOption]             # Always exactly 4
    correct_position: AnswerPosition      # Uniformly randomized across A/B/C/D
    explanation: str                      # From source knowledge only — never fabricated
    source_chunk_id: str
    reference: Optional[Reference] = None


class QuizSession(BaseModel):
    quiz_id: str
    topic: str
    difficulty: Difficulty
    questions: list[QuizQuestion]
    answers: dict[str, AnswerPosition] = Field(default_factory=dict)
    current_index: int = 0
    score: int = 0


# ---------------------------------------------------------------------------
# Flashcard Models
# ---------------------------------------------------------------------------

class Flashcard(BaseModel):
    card_id: str
    front: str
    back_points: list[str]
    memory_tip: Optional[str] = None      # Source only — never fabricated
    reference: Optional[Reference] = None
    times_shown: int = 0
    times_correct: int = 0


class FlashcardDeck(BaseModel):
    deck_id: str
    topic: str
    cards: list[Flashcard]
    current_index: int = 0


# ---------------------------------------------------------------------------
# Protocols (Interfaces)
# ---------------------------------------------------------------------------

@runtime_checkable
class IIntentEngine(Protocol):
    async def classify(self, text: str) -> IntentResult:
        """Never raises. Returns IntentType.UNKNOWN on failure."""
        ...


@runtime_checkable
class IRetriever(Protocol):
    async def retrieve(
        self,
        topic: str,
        workspace_type: WorkspaceType,
        section_hints: list[str] | None = None,
    ) -> KnowledgeTree:
        """Returns KnowledgeTree with empty chunks on failure. Never raises."""
        ...


@runtime_checkable
class IIAGenerator(Protocol):
    def generate(
        self,
        knowledge_tree: KnowledgeTree,
        workspace_type: WorkspaceType,
        user_mode: UserMode,
    ) -> IASchema:
        """
        Synchronous. Pure. No I/O.
        Sections with no retrieved content are excluded from IASchema.
        """
        ...


@runtime_checkable
class IPresentationEngine(Protocol):
    def build(
        self,
        ia_schema: IASchema,
        knowledge_tree: KnowledgeTree,
        screen_id: str,
    ) -> Document:
        """
        Synchronous. Pure. No I/O.
        Component selection follows PRD Section 7 + ComponentRegistry.
        """
        ...


@runtime_checkable
class IRenderer(Protocol):
    def render(
        self,
        document: Document,
        capabilities: PlatformCapabilities = TELEGRAM_CAPABILITIES,
    ) -> TelegramScreen:
        """
        Synchronous. Pure. No business logic. No content decisions.
        All user content must be HTML-escaped.
        TelegramScreen.html must never exceed capabilities.max_message_length.
        Degrades components based on capabilities (e.g. table → list if not supported).
        """
        ...


@runtime_checkable
class IStateMachine(Protocol):
    def transition(
        self,
        current_state: BotState,
        event: Event,
        context: dict[str, Any],
    ) -> TransitionResult:
        """
        Synchronous. Pure function — no side effects.
        Forbidden transitions return TransitionResult(is_forbidden=True).
        Never raises.
        """
        ...


@runtime_checkable
class ISessionManager(Protocol):
    async def create(
        self,
        user_id: int,
        topic: str,
        workspace_type: WorkspaceType,
        user_mode: UserMode,
    ) -> WorkspaceSession: ...

    async def get(self, user_id: int) -> Optional[WorkspaceSession]: ...

    async def update(self, session: WorkspaceSession) -> None: ...

    async def push_state(
        self, session: WorkspaceSession, state: BotState
    ) -> None:
        """Enforces max depth of 10. Drops oldest entry if exceeded."""
        ...

    async def pop_state(
        self, session: WorkspaceSession
    ) -> Optional[BotState]:
        """Returns None if history is empty."""
        ...

    async def peek_state(
        self, session: WorkspaceSession
    ) -> Optional[BotState]:
        """Returns top state without removing. None if empty."""
        ...

    async def expire(self, user_id: int) -> None:
        """Marks session as expired. Removes knowledge_tree, retains metadata."""
        ...


@runtime_checkable
class IQuizEngine(Protocol):
    def generate(
        self,
        knowledge_tree: KnowledgeTree,
        difficulty: Difficulty,
        count: int,
    ) -> QuizSession:
        """
        Correct answer position MUST be uniformly distributed: ~25% each A/B/C/D.
        Distractors MUST be from the same clinical category as correct answer.
        Synchronous. No I/O.
        """
        ...

    def evaluate(
        self,
        quiz_session: QuizSession,
        question_id: str,
        chosen: AnswerPosition,
    ) -> tuple[bool, QuizQuestion]: ...


@runtime_checkable
class IFlashcardEngine(Protocol):
    def generate(self, knowledge_tree: KnowledgeTree) -> FlashcardDeck:
        """Min 5 cards. Max 20. Memory tips from source only. Synchronous."""
        ...

    def requeue_incorrect(
        self,
        deck: FlashcardDeck,
        card_id: str,
        positions_later: int = 3,
    ) -> FlashcardDeck: ...
