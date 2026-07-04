from typing import List, Dict, Any
from layout.components import (
    Section, HeaderCardComponent, MetadataCardComponent, 
    FactGridComponent, SectionHeaderComponent,
    ReferenceCardComponent, CalloutComponent, ChecklistComponent, ParagraphComponent
)
from layout.templates.base import PageTemplate
from layout.presentation_engine import PresentationEngine

class DrugTemplate(PageTemplate):
    """
    Template for Drug/Medication pages.
    Structure: Header -> Metadata -> Quick Facts -> Indications -> Mechanism -> Warnings & Side Effects -> Pearl -> References
    """
    
    def __init__(self, presentation_engine: PresentationEngine):
        self.presentation_engine = presentation_engine

    def build_sections(self, ndm_doc: Dict[str, Any]) -> List[Section]:
        blocks = ndm_doc.get("blocks", [])
        
        drug_blocks = [b for b in blocks if b.get("type") == "drug_info"]
        reference_blocks = [b for b in blocks if b.get("type") == "reference"]
        
        doc_topic = ndm_doc.get("topic", "Medication Overview")
        
        sections = []
        
        # --- 1. Header & Metadata ---
        sections.append(Section(
            kind="Header", 
            components=[
                HeaderCardComponent(title=doc_topic, icon="💊"),
                MetadataCardComponent(source_textbook="Primary Medical Text", reading_time_mins=1)
            ],
            supports_collapse=False
        ))
        
        if drug_blocks:
            drug_data = drug_blocks[0]
            
            # --- 2. Quick Facts ---
            facts = {}
            if "class" in drug_data:
                facts["Class"] = drug_data["class"]
            if "half_life" in drug_data:
                facts["Half-life"] = drug_data["half_life"]
            if not facts:
                facts = {"Type": "Pharmacological Agent", "Prescription": "Required"}
                
            sections.append(Section(
                kind="QuickFacts",
                components=[FactGridComponent(facts=facts)],
                supports_collapse=False
            ))
            
            # --- 3. Indications ---
            indications = drug_data.get("indications", [])
            if indications:
                sections.append(Section(
                    kind="Indications",
                    components=[
                        SectionHeaderComponent(title="Indications", icon="🎯"),
                        ChecklistComponent(items=indications)
                    ],
                    supports_collapse=True
                ))

            # --- 4. Mechanism ---
            mech = drug_data.get("mechanism")
            if mech:
                sections.append(Section(
                    kind="Mechanism",
                    components=[
                        SectionHeaderComponent(title="Mechanism of Action", icon="⚙️"),
                        ParagraphComponent(text=mech)
                    ],
                    supports_collapse=True
                ))

            # --- 5. Warnings & Side Effects ---
            se_components = [SectionHeaderComponent(title="Warnings & Side Effects", icon="⚠️")]
            
            contraindications = drug_data.get("contraindications", [])
            for c in contraindications:
                se_components.append(CalloutComponent(variant="warning", text=c, title="Contraindication"))
                
            side_effects = drug_data.get("side_effects", [])
            if side_effects:
                se_components.append(ChecklistComponent(items=side_effects))
                
            if len(se_components) > 1:
                sections.append(Section(
                    kind="Warnings",
                    components=se_components,
                    supports_collapse=True
                ))

        # --- 6. Clinical Pearl ---
        # Generic pearl if none found
        sections.append(Section(
            kind="Pearl",
            components=[CalloutComponent(variant="clinical_pearl", text="Always verify dosing based on renal function.", title="Prescribing Pearl")],
            supports_collapse=False
        ))

        # --- 7. References ---
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
