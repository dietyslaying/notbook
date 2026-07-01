from typing import List, Dict, Any
from layout.components import Section
from layout.templates.base import PageTemplate
from layout.presentation_engine import PresentationEngine

class GeneralTemplate(PageTemplate):
    """
    Fallback general template that just dumps everything into an Overview and References.
    """
    def __init__(self, presentation_engine: PresentationEngine):
        self.presentation_engine = presentation_engine

    def build_sections(self, ndm_doc: Dict[str, Any]) -> List[Section]:
        blocks = ndm_doc.get("blocks", [])
        reference_blocks = [b for b in blocks if b.get("type") == "reference"]
        other_blocks = [b for b in blocks if b.get("type") != "reference"]
        
        sections = []
        
        if other_blocks:
            components = []
            for b in other_blocks:
                components.extend(self.presentation_engine.apply_rules(b))
            if components:
                sections.append(Section(kind="Overview", components=components))
                
        if reference_blocks:
            components = []
            for b in reference_blocks:
                components.extend(self.presentation_engine.apply_rules(b))
            if components:
                sec = Section(kind="References", components=components)
                sec.state.importance = "low"
                sec.state.collapsed = True
                sections.append(sec)
                
        return sections
