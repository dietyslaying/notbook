from typing import List, Dict, Any
from layout.components import (
    Section, HeaderCardComponent, MetadataCardComponent, 
    FactGridComponent, SectionHeaderComponent,
    ReferenceCardComponent, ChecklistComponent, ParagraphComponent
)
from layout.templates.base import PageTemplate
from layout.presentation_engine import PresentationEngine

class ClinicalCaseTemplate(PageTemplate):
    """
    Template for Clinical Cases.
    Structure: Header -> Metadata -> Presentation -> Key Findings -> Assessment -> Protocol -> References
    """
    
    def __init__(self, presentation_engine: PresentationEngine):
        self.presentation_engine = presentation_engine

    def build_sections(self, ndm_doc: Dict[str, Any]) -> List[Section]:
        blocks = ndm_doc.get("blocks", [])
        
        case_blocks = [b for b in blocks if b.get("type") == "clinical_case"]
        reference_blocks = [b for b in blocks if b.get("type") == "reference"]
        
        doc_topic = ndm_doc.get("topic", "Clinical Case")
        
        sections = []
        
        # --- 1. Header & Metadata ---
        sections.append(Section(
            kind="Header", 
            components=[
                HeaderCardComponent(title=doc_topic, icon="🩺", subtitle="Patient Presentation"),
                MetadataCardComponent(source_textbook="Primary Medical Text", reading_time_mins=2)
            ],
            supports_collapse=False
        ))
        
        if case_blocks:
            case_data = case_blocks[0]
            
            # --- 2. Patient Presentation ---
            presentation = case_data.get("patient_presentation")
            if presentation:
                sections.append(Section(
                    kind="Presentation",
                    components=[
                        SectionHeaderComponent(title="Presentation", icon="👤"),
                        ParagraphComponent(text=presentation)
                    ],
                    supports_collapse=False
                ))

            # --- 3. Key Findings ---
            findings = case_data.get("key_findings", [])
            if findings:
                # Convert list of findings to a FactGrid mapping if possible, or just a checklist
                # We'll use a checklist for findings, but wrap it in a SectionHeader
                sections.append(Section(
                    kind="Findings",
                    components=[
                        SectionHeaderComponent(title="Key Findings", icon="🔍"),
                        ChecklistComponent(items=findings)
                    ],
                    supports_collapse=True
                ))

            # --- 4. Assessment ---
            diagnosis = case_data.get("diagnosis")
            if diagnosis:
                sections.append(Section(
                    kind="Assessment",
                    components=[
                        SectionHeaderComponent(title="Assessment & Diagnosis", icon="⚕️"),
                        ParagraphComponent(text=diagnosis)
                    ],
                    supports_collapse=False
                ))

        # --- 5. References ---
        if reference_blocks:
            citations = []
            for b in reference_blocks:
                source = b.get("source", "Medical Textbook")
                if b.get("page"):
                    source += f", p. {b.get('page')}"
                citations.append(source)
                
            sec = Section(
                kind="References",
                components=[ReferenceCardComponent(citations=citations)],
                supports_collapse=True
            )
            sec.state.importance = "low"
            sec.state.collapsed = True
            sections.append(sec)

        return sections
