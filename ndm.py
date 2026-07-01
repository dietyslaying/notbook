import uuid
from typing import List, Union, Literal, Optional, Dict, Any
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Notbook Intermediate Representation (NIR) / NDM
# ---------------------------------------------------------------------------
# This defines the semantic structure output by Gemini. 
# It contains NO layout, NO styling, and NO Telegram-specific logic.

class BaseNDMBlock(BaseModel):
    version: str = "1.0"
    # Every block gets a unique ID for component-level caching/updating later
    block_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    # Populated later during resolution to map to original RAG chunks
    source_chunk_ids: List[str] = Field(default_factory=list)

class DefinitionBlock(BaseNDMBlock):
    type: Literal["definition"] = "definition"
    term: str
    definition: str

class ExplanationBlock(BaseNDMBlock):
    type: Literal["explanation"] = "explanation"
    topic: str
    content: str

class DiseaseSymptomsBlock(BaseNDMBlock):
    type: Literal["disease_symptoms"] = "disease_symptoms"
    disease_name: str
    symptoms: List[str]

class TreatmentBlock(BaseNDMBlock):
    type: Literal["treatment"] = "treatment"
    condition: str
    treatments: List[str]
    notes: Optional[str] = None

class DrugInfoBlock(BaseNDMBlock):
    type: Literal["drug_info"] = "drug_info"
    drug_name: str
    drug_class: Optional[str] = None
    mechanism: str
    indications: List[str]
    contraindications: List[str]
    side_effects: List[str]

class ComparisonAspect(BaseModel):
    aspect: str
    a: str
    b: str

class ComparisonBlock(BaseNDMBlock):
    type: Literal["comparison"] = "comparison"
    topic_a: str
    topic_b: str
    aspects: List[ComparisonAspect]

class TimelineEvent(BaseModel):
    time: str
    event: str

class TimelineBlock(BaseNDMBlock):
    type: Literal["timeline"] = "timeline"
    events: List[TimelineEvent]

class FormulaVariable(BaseModel):
    name: str
    meaning: str

class FormulaBlock(BaseNDMBlock):
    type: Literal["formula"] = "formula"
    name: str
    expression: str
    variables: List[FormulaVariable]

class GuidelineBlock(BaseNDMBlock):
    type: Literal["guideline"] = "guideline"
    organization: str
    recommendations: List[str]

class ClinicalCaseBlock(BaseNDMBlock):
    type: Literal["clinical_case"] = "clinical_case"
    patient_presentation: str
    key_findings: List[str]
    diagnosis: Optional[str] = None

class ReferenceBlock(BaseNDMBlock):
    type: Literal["reference"] = "reference"
    source: str
    page: Optional[str] = None
    excerpt: Optional[str] = None

class ConceptBlock(BaseNDMBlock):
    type: Literal["concept"] = "concept"
    name: str
    details: List[str]

class QuestionBlock(BaseNDMBlock):
    type: Literal["question"] = "question"
    question: str
    options: List[str]
    answer: str
    explanation: str

# ---------------------------------------------------------------------------
# The Root Document
# ---------------------------------------------------------------------------
class NotbookDocument(BaseModel):
    version: str = "1.0"
    title: str
    topic_category: Literal["disease", "drug", "anatomy", "procedure", "general"]
    blocks: List[Union[
        DefinitionBlock,
        ExplanationBlock,
        DiseaseSymptomsBlock,
        TreatmentBlock,
        DrugInfoBlock,
        ComparisonBlock,
        TimelineBlock,
        FormulaBlock,
        GuidelineBlock,
        ClinicalCaseBlock,
        ReferenceBlock,
        ConceptBlock,
        QuestionBlock
    ]]
