from typing import List, Dict, Any
from layout.components import (
    Section, HeaderCardComponent, MetadataCardComponent, 
    TLDRComponent, FactGridComponent, SectionHeaderComponent,
    ReferenceCardComponent, CalloutComponent
)
from layout.templates.base import PageTemplate
from layout.presentation_engine import PresentationEngine

class DiseaseTemplate(PageTemplate):
    """
    Template for Disease/Condition pages.
    Structure: Header -> Metadata -> TLDR -> Quick Facts -> Symptoms -> Treatment -> Pearl -> References
    """
    
    def __init__(self, presentation_engine: PresentationEngine):
        self.presentation_engine = presentation_engine

    def build_sections(self, ndm_doc: Dict[str, Any]) -> List[Section]:
        blocks = ndm_doc.get("blocks", [])
        
        overview_blocks = [b for b in blocks if b.get("type") in ("definition", "explanation")]
        symptom_blocks = [b for b in blocks if b.get("type") == "disease_symptoms"]
        treatment_blocks = [b for b in blocks if b.get("type") == "treatment"]
        reference_blocks = [b for b in blocks if b.get("type") == "reference"]
        
        # We assume the AI produces a "title" block or we extract it from overview
        # For now, default to the topic or "Disease Overview"
        doc_topic = ndm_doc.get("topic", "Disease Overview")
        
        sections = []
        
        # --- 1. Header & Metadata ---
        header_components = [
            HeaderCardComponent(title=doc_topic, icon="🧠"),
            # We strictly enforce the AI persona as textbook reader
            MetadataCardComponent(source_textbook="Primary Medical Text", reading_time_mins=1)
        ]
        
        # Extrapolate TLDR from first definition block
        if overview_blocks:
            tldr_text = overview_blocks[0].get("definition", "A medical condition characterized by various symptoms.")
            header_components.append(TLDRComponent(text=tldr_text[:200] + "..."))
            
        sections.append(Section(kind="Header", components=header_components, supports_collapse=False))
        
        # --- 2. Quick Facts ---
        # Mocking QuickFacts extraction for now from overview
        facts = {"Prevalence": "Varies", "Diagnosis": "Clinical"}
        if symptom_blocks:
            facts["Hallmark"] = "See symptoms"
        sections.append(Section(
            kind="QuickFacts",
            components=[FactGridComponent(facts=facts)],
            supports_collapse=False
        ))
        
        # --- 3. Symptoms ---
        if symptom_blocks:
            symptoms_components = [SectionHeaderComponent(title="Symptoms", icon="🩺")]
            for b in symptom_blocks:
                symptoms_components.extend(self.presentation_engine.apply_rules(b))
            sections.append(Section(
                kind="Symptoms",
                components=symptoms_components,
                supports_collapse=True
            ))

        # --- 4. Treatment ---
        if treatment_blocks:
            treatment_components = [SectionHeaderComponent(title="Treatment", icon="💊")]
            for b in treatment_blocks:
                treatment_components.extend(self.presentation_engine.apply_rules(b))
            sections.append(Section(
                kind="Treatment",
                components=treatment_components,
                supports_collapse=True
            ))

        # --- 5. Clinical Pearl ---
        # Find any info callouts from treatments or general facts and promote one to a pearl
        # We just grab the first treatment note for now
        pearl_text = None
        for b in treatment_blocks:
            if b.get("notes"):
                pearl_text = b.get("notes")
                break
        
        if pearl_text:
            sections.append(Section(
                kind="Pearl",
                components=[CalloutComponent(variant="clinical_pearl", text=pearl_text, title="Key Insight")],
                supports_collapse=False
            ))

        # --- 6. References ---
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
