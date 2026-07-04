from typing import Dict, Any, List
from layout.components import (
    BaseComponent, MetadataCardComponent, ParagraphComponent, 
    ChecklistComponent, TableComponent, MathComponent, TimelineComponent, 
    CalloutComponent, DividerComponent, FactGridComponent, ReferenceCardComponent,
    BlockQuoteComponent, DetailsComponent, SpoilerComponent, FigureComponent,
    SlideshowComponent, VideoComponent, AudioComponent
)

class PresentationEngine:
    """
    Applies the Design Language rules to map Semantic NDM blocks into platform-agnostic Layout Components.
    Enforces rules like max 4 facts per grid, no generic paragraphs for symptoms, etc.
    """
    
    def apply_rules(self, block: Dict[str, Any]) -> List[BaseComponent]:
        """Converts a raw semantic NDM block dictionary into one or more styled Components."""
        components = []
        b_type = block.get("type")
        source_ids = block.get("source_chunk_ids", [])
        
        if not b_type:
            return components
            
        if b_type == "disease_symptoms":
            symptoms = block.get("symptoms", [])
            if symptoms:
                components.append(ChecklistComponent(
                    items=symptoms, 
                    source_chunk_ids=source_ids,
                    supports_collapse=len(symptoms) > 5
                ))
                
        elif b_type == "treatment":
            treatments = block.get("treatments", [])
            if treatments:
                components.append(ChecklistComponent(items=treatments, source_chunk_ids=source_ids))
            notes = block.get("notes")
            if notes:
                components.append(CalloutComponent(variant="info", text=notes, source_chunk_ids=source_ids))
                
        elif b_type == "definition":
            definition = block.get("definition")
            if definition:
                components.append(ParagraphComponent(text=definition, source_chunk_ids=source_ids))
                
        elif b_type == "comparison":
            aspects = block.get("aspects", [])
            if aspects:
                headers = ["Aspect", block.get("topic_a", "A"), block.get("topic_b", "B")]
                rows = [[a.get("aspect", ""), a.get("a", ""), a.get("b", "")] for a in aspects]
                components.append(TableComponent(headers=headers, rows=rows, source_chunk_ids=source_ids))
                
        elif b_type == "explanation":
            content = block.get("content")
            if content:
                components.append(ParagraphComponent(text=content, source_chunk_ids=source_ids))

        elif b_type == "drug_info":
            mech = block.get("mechanism")
            if mech:
                components.append(SubheaderComponent(title="Mechanism", source_chunk_ids=source_ids))
                components.append(ParagraphComponent(text=mech, source_chunk_ids=source_ids))
            
            indications = block.get("indications", [])
            if indications:
                components.append(SubheaderComponent(title="Indications", source_chunk_ids=source_ids))
                components.append(ChecklistComponent(items=indications, source_chunk_ids=source_ids))
            
            contraindications = block.get("contraindications", [])
            if contraindications:
                for c in contraindications:
                    components.append(CalloutComponent(variant="warning", text=f"Contraindication: {c}", source_chunk_ids=source_ids))
                    
            side_effects = block.get("side_effects", [])
            if side_effects:
                components.append(SubheaderComponent(title="Common Side Effects", source_chunk_ids=source_ids))
                components.append(ChecklistComponent(items=side_effects, source_chunk_ids=source_ids))

        elif b_type == "timeline":
            events = block.get("events", [])
            if events:
                components.append(TimelineComponent(events=events, source_chunk_ids=source_ids))

        elif b_type == "formula":
            expr = block.get("expression")
            if expr:
                components.append(MathComponent(latex=expr, source_chunk_ids=source_ids))
            variables = block.get("variables", [])
            if variables:
                var_list = [f"{v.get('name', '')}: {v.get('meaning', '')}" for v in variables]
                components.append(ChecklistComponent(items=var_list, source_chunk_ids=source_ids))

        elif b_type == "guideline":
            recs = block.get("recommendations", [])
            if recs:
                components.append(ChecklistComponent(items=recs, source_chunk_ids=source_ids))

        elif b_type == "clinical_case":
            presentation = block.get("patient_presentation")
            if presentation:
                components.append(ParagraphComponent(text=presentation, source_chunk_ids=source_ids))
            findings = block.get("key_findings", [])
            if findings:
                components.append(SubheaderComponent(title="Key Findings", source_chunk_ids=source_ids))
                components.append(ChecklistComponent(items=findings, source_chunk_ids=source_ids))
            diagnosis = block.get("diagnosis")
            if diagnosis:
                components.append(SubheaderComponent(title="Most Likely Diagnosis", source_chunk_ids=source_ids))
                components.append(ParagraphComponent(text=diagnosis, source_chunk_ids=source_ids))

        elif b_type == "concept":
            details = block.get("details", [])
            if details:
                components.append(ChecklistComponent(items=details, source_chunk_ids=source_ids))

        # References are handled directly by templates now using ReferenceCardComponent,
        # but if we get a raw one, map it generically:
        elif b_type == "reference":
            source = block.get("source", "")
            page = block.get("page")
            if page:
                source += f" (Page {page})"
            components.append(ParagraphComponent(text=source, source_chunk_ids=source_ids))
            excerpt = block.get("excerpt")
            if excerpt:
                components.append(BlockQuoteComponent(text=excerpt, source_chunk_ids=source_ids))
                
        return components
