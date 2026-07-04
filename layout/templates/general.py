from typing import List, Dict, Any
from layout.components import (
    Section, HeaderCardComponent, MetadataCardComponent, 
    TLDRComponent, SectionHeaderComponent,
    ReferenceCardComponent
)
from layout.templates.base import PageTemplate
from layout.presentation_engine import PresentationEngine

class GeneralTemplate(PageTemplate):
    """
    Template for General/Generic topics that don't fit a specific schema.
    Structure: Header -> Metadata -> TLDR -> Content Sections -> References
    """
    
    def __init__(self, presentation_engine: PresentationEngine):
        self.presentation_engine = presentation_engine

    def build_sections(self, ndm_doc: Dict[str, Any]) -> List[Section]:
        blocks = ndm_doc.get("blocks", [])
        reference_blocks = [b for b in blocks if b.get("type") == "reference"]
        content_blocks = [b for b in blocks if b.get("type") != "reference"]
        
        doc_topic = ndm_doc.get("topic", "Topic Overview")
        
        sections = []
        
        # --- 1. Header & Metadata ---
        sections.append(Section(
            kind="Header", 
            components=[
                HeaderCardComponent(title=doc_topic, icon="📚"),
                MetadataCardComponent(source_textbook="Primary Medical Text", reading_time_mins=3)
            ],
            supports_collapse=False
        ))
        
        # --- 2. Content Sections ---
        # We group content blocks into sections artificially since we don't have strict schema
        if content_blocks:
            current_components = [SectionHeaderComponent(title="Overview", icon="🔹")]
            for b in content_blocks:
                current_components.extend(self.presentation_engine.apply_rules(b))
                
            sections.append(Section(
                kind="Content",
                components=current_components,
                supports_collapse=False
            ))

        # --- 3. References ---
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
