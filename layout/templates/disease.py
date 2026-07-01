from typing import List, Dict, Any
from layout.components import Section
from layout.templates.base import PageTemplate
from layout.presentation_engine import PresentationEngine

class DiseaseTemplate(PageTemplate):
    """
    Template for Disease/Condition pages.
    Structure: Overview -> Symptoms -> Treatment -> References
    """
    
    def __init__(self, presentation_engine: PresentationEngine):
        self.presentation_engine = presentation_engine

    def build_sections(self, ndm_doc: Dict[str, Any]) -> List[Section]:
        blocks = ndm_doc.get("blocks", [])
        
        overview_blocks = [b for b in blocks if b.get("type") in ("definition", "explanation")]
        symptom_blocks = [b for b in blocks if b.get("type") == "disease_symptoms"]
        treatment_blocks = [b for b in blocks if b.get("type") == "treatment"]
        reference_blocks = [b for b in blocks if b.get("type") == "reference"]
        other_blocks = [b for b in blocks if b not in overview_blocks + symptom_blocks + treatment_blocks + reference_blocks]
        
        sections = []
        
        # 1. Overview
        if overview_blocks or other_blocks:
            overview_components = []
            for b in overview_blocks + other_blocks:
                overview_components.extend(self.presentation_engine.apply_rules(b))
            
            if overview_components:
                sections.append(Section(
                    kind="Overview",
                    components=overview_components,
                    supports_collapse=False
                ))

        # 2. Symptoms
        if symptom_blocks:
            symptoms_components = []
            for b in symptom_blocks:
                symptoms_components.extend(self.presentation_engine.apply_rules(b))
            
            if symptoms_components:
                sections.append(Section(
                    kind="Symptoms",
                    components=symptoms_components,
                    supports_collapse=True
                ))

        # 3. Treatment
        if treatment_blocks:
            treatment_components = []
            for b in treatment_blocks:
                treatment_components.extend(self.presentation_engine.apply_rules(b))
            
            if treatment_components:
                sections.append(Section(
                    kind="Treatment",
                    components=treatment_components,
                    supports_collapse=True
                ))

        # 4. References
        if reference_blocks:
            reference_components = []
            for b in reference_blocks:
                reference_components.extend(self.presentation_engine.apply_rules(b))
            
            if reference_components:
                sec = Section(
                    kind="References",
                    components=reference_components,
                    supports_collapse=True
                )
                sec.state.importance = "low"
                sec.state.collapsed = True
                sections.append(sec)

        return sections
