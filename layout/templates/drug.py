from typing import List, Dict, Any
from layout.components import Section
from layout.templates.base import PageTemplate
from layout.presentation_engine import PresentationEngine

class DrugTemplate(PageTemplate):
    """
    Template for Drug/Pharmacology pages.
    Structure: Overview -> Mechanism -> Indications -> Warnings/Side Effects -> References
    """
    
    def __init__(self, presentation_engine: PresentationEngine):
        self.presentation_engine = presentation_engine

    def build_sections(self, ndm_doc: Dict[str, Any]) -> List[Section]:
        blocks = ndm_doc.get("blocks", [])
        
        overview_blocks = [b for b in blocks if b.get("type") in ("definition", "explanation")]
        drug_blocks = [b for b in blocks if b.get("type") == "drug_info"]
        reference_blocks = [b for b in blocks if b.get("type") == "reference"]
        other_blocks = [b for b in blocks if b not in overview_blocks + drug_blocks + reference_blocks]
        
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

        # 2. Drug Info (Mechanism, Indications, Warnings)
        if drug_blocks:
            # We map all drug info into a comprehensive Pharmacology section
            pharma_components = []
            for b in drug_blocks:
                pharma_components.extend(self.presentation_engine.apply_rules(b))
                
            if pharma_components:
                sections.append(Section(
                    kind="Pharmacology",
                    components=pharma_components,
                    supports_collapse=True
                ))

        # 3. References
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
