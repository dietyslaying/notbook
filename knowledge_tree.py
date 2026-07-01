import uuid
from typing import List, Union, Literal, Optional, Dict, Any
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Notbook Intermediate Representation (NIR) / Knowledge Tree
# ---------------------------------------------------------------------------
# This defines the semantic structure output by Gemini. 
# It contains NO layout, NO styling, and NO Telegram-specific logic.

class BaseKnowledgeBlock(BaseModel):
    # Every block gets a unique ID for component-level caching/updating later
    block_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    # Populated later during resolution to map to original RAG chunks
    source_chunk_ids: List[str] = Field(default_factory=list)

class DefinitionBlock(BaseKnowledgeBlock):
    type: Literal["definition"] = "definition"
    term: str
    definition: str

class ExplanationBlock(BaseKnowledgeBlock):
    type: Literal["explanation"] = "explanation"
    topic: str
    content: str

class DiseaseSymptomsBlock(BaseKnowledgeBlock):
    type: Literal["disease_symptoms"] = "disease_symptoms"
    disease_name: str
    symptoms: List[str]

class TreatmentBlock(BaseKnowledgeBlock):
    type: Literal["treatment"] = "treatment"
    condition: str
    treatments: List[str]
    notes: Optional[str] = None

class DrugInfoBlock(BaseKnowledgeBlock):
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

class ComparisonBlock(BaseKnowledgeBlock):
    type: Literal["comparison"] = "comparison"
    topic_a: str
    topic_b: str
    aspects: List[ComparisonAspect]

class TimelineEvent(BaseModel):
    time: str
    event: str

class TimelineBlock(BaseKnowledgeBlock):
    type: Literal["timeline"] = "timeline"
    events: List[TimelineEvent]

class FormulaVariable(BaseModel):
    name: str
    meaning: str

class FormulaBlock(BaseKnowledgeBlock):
    type: Literal["formula"] = "formula"
    name: str
    expression: str
    variables: List[FormulaVariable]

class GuidelineBlock(BaseKnowledgeBlock):
    type: Literal["guideline"] = "guideline"
    organization: str
    recommendations: List[str]

class ClinicalCaseBlock(BaseKnowledgeBlock):
    type: Literal["clinical_case"] = "clinical_case"
    patient_presentation: str
    key_findings: List[str]
    diagnosis: Optional[str] = None

class ReferenceBlock(BaseKnowledgeBlock):
    type: Literal["reference"] = "reference"
    source: str
    page: Optional[str] = None
    excerpt: Optional[str] = None

class ConceptBlock(BaseKnowledgeBlock):
    type: Literal["concept"] = "concept"
    name: str
    details: List[str]

class QuestionBlock(BaseKnowledgeBlock):
    type: Literal["question"] = "question"
    question: str
    options: List[str]
    answer: str
    explanation: str

# ---------------------------------------------------------------------------
# The Root Document
# ---------------------------------------------------------------------------
class KnowledgeDocument(BaseModel):
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
