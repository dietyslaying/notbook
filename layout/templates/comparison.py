from typing import List, Dict, Any
from layout.components import (
    Section, HeaderCardComponent, MetadataCardComponent, 
    TLDRComponent, SectionHeaderComponent,
    ReferenceCardComponent, TableComponent, CalloutComponent
)
from layout.templates.base import PageTemplate
from layout.presentation_engine import PresentationEngine

class ComparisonTemplate(PageTemplate):
    """
    Template for Comparison pages.
    Structure: Header -> Metadata -> TLDR -> Comparison Table -> Pearl -> References
    """
    
    def __init__(self, presentation_engine: PresentationEngine):
        self.presentation_engine = presentation_engine

    def build_sections(self, ndm_doc: Dict[str, Any]) -> List[Section]:
        blocks = ndm_doc.get("blocks", [])
        
        comparison_blocks = [b for b in blocks if b.get("type") == "comparison"]
        reference_blocks = [b for b in blocks if b.get("type") == "reference"]
        
        doc_topic = ndm_doc.get("topic", "Comparison")
        
        sections = []
        
        # --- 1. Header & Metadata ---
        sections.append(Section(
            kind="Header", 
            components=[
                HeaderCardComponent(title=doc_topic, icon="⚖️"),
                MetadataCardComponent(source_textbook="Primary Medical Text", reading_time_mins=2)
            ],
            supports_collapse=False
        ))
        
        if comparison_blocks:
            comp_data = comparison_blocks[0]
            topic_a = comp_data.get("topic_a", "A")
            topic_b = comp_data.get("topic_b", "B")
            
            # --- 2. TLDR ---
            sections.append(Section(
                kind="TLDR",
                components=[TLDRComponent(text=f"Key clinical differences between {topic_a} and {topic_b}.")],
                supports_collapse=False
            ))

            # --- 3. Comparison Table ---
            aspects = comp_data.get("aspects", [])
            if aspects:
                headers = ["Aspect", topic_a, topic_b]
                rows = [[a.get("aspect", ""), a.get("a", ""), a.get("b", "")] for a in aspects]
                sections.append(Section(
                    kind="Comparison Table",
                    components=[
                        SectionHeaderComponent(title="Head-to-Head", icon="📊"),
                        TableComponent(headers=headers, rows=rows)
                    ],
                    supports_collapse=False
                ))

            # --- 4. Clinical Pearl ---
            sections.append(Section(
                kind="Pearl",
                components=[CalloutComponent(variant="clinical_pearl", text=f"When distinguishing {topic_a} from {topic_b}, focus on the hallmark signs.", title="Differential Pearl")],
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
