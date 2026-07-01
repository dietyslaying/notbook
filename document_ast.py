import json
from typing import List, Union, Literal, Optional
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Semantic Document AST
# ---------------------------------------------------------------------------

class DefinitionBlock(BaseModel):
    type: Literal["definition"] = "definition"
    term: str
    definition: str

class FactBlock(BaseModel):
    type: Literal["facts"] = "facts"
    title: str = "Key Facts"
    facts: List[str]

class ClinicalPearlBlock(BaseModel):
    type: Literal["clinical_pearl"] = "clinical_pearl"
    pearl: str

class ComparisonTableBlock(BaseModel):
    type: Literal["comparison_table"] = "comparison_table"
    title: str
    headers: List[str]
    rows: List[List[str]]

class ChecklistBlock(BaseModel):
    type: Literal["checklist"] = "checklist"
    title: str
    items: List[str]

class SectionBlock(BaseModel):
    type: Literal["section"] = "section"
    title: str
    paragraphs: List[str]

class ReferenceBlock(BaseModel):
    type: Literal["reference"] = "reference"
    source: str
    page: Optional[str] = None
    excerpt: Optional[str] = None

class DocumentAST(BaseModel):
    title: str
    template_type: Literal["disease", "drug", "anatomy", "general"]
    blocks: List[Union[
        DefinitionBlock,
        FactBlock,
        ClinicalPearlBlock,
        ComparisonTableBlock,
        ChecklistBlock,
        SectionBlock,
        ReferenceBlock
    ]]
    recommended_actions: List[str] = Field(
        description="List of 3 to 5 highly contextual next steps (e.g., 'Symptoms', 'Mechanism of Action', 'Flashcards')"
    )
