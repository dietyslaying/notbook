import logging
from interfaces import Component, Chunk

logger = logging.getLogger(__name__)

def build_components(section_id: str, chunks: list[Chunk]) -> list[Component]:
    """
    Transforms Semantic Blocks (Chunks) into Strongly Typed Components based on NDM schema.
    """
    if not chunks:
        return [Component(component_type="paragraph", payload={"text": "No content found."})]
        
    components = []
    for c in chunks:
        ctype = c.chunk_type.lower()
        payload = c.payload
        
        if ctype == "definition":
            components.append(Component(component_type="definition", payload={
                "term": payload.get("term", ""),
                "definition": payload.get("definition", "")
            }))
        elif ctype == "explanation":
            components.append(Component(component_type="explanation", payload={
                "topic": payload.get("topic", ""),
                "content": payload.get("content", "")
            }))
        elif ctype == "disease_symptoms":
            components.append(Component(component_type="checklist", payload={
                "heading": payload.get("disease_name", "Symptoms"),
                "items": payload.get("symptoms", [])
            }))
        elif ctype == "treatment":
            components.append(Component(component_type="treatment", payload={
                "condition": payload.get("condition", ""),
                "treatments": payload.get("treatments", []),
                "notes": payload.get("notes")
            }))
        elif ctype == "drug_info":
            components.append(Component(component_type="drug_card", payload={
                "drug_name": payload.get("drug_name", ""),
                "drug_class": payload.get("drug_class"),
                "mechanism": payload.get("mechanism", ""),
                "indications": payload.get("indications", []),
                "contraindications": payload.get("contraindications", []),
                "side_effects": payload.get("side_effects", [])
            }))
        elif ctype == "comparison":
            components.append(Component(component_type="comparison", payload={
                "topic_a": payload.get("topic_a", ""),
                "topic_b": payload.get("topic_b", ""),
                "aspects": payload.get("aspects", []) # using a/b from ndm.py
            }))
        elif ctype == "timeline":
            components.append(Component(component_type="timeline", payload={
                "events": payload.get("events", [])
            }))
        elif ctype == "formula":
            components.append(Component(component_type="formula", payload={
                "name": payload.get("name", ""),
                "expression": payload.get("expression", ""),
                "variables": payload.get("variables", [])
            }))
        elif ctype == "guideline":
            components.append(Component(component_type="guideline", payload={
                "organization": payload.get("organization", ""),
                "recommendations": payload.get("recommendations", [])
            }))
        elif ctype == "clinical_case":
            components.append(Component(component_type="clinical_case", payload={
                "patient_presentation": payload.get("patient_presentation", ""),
                "key_findings": payload.get("key_findings", []),
                "diagnosis": payload.get("diagnosis")
            }))
        elif ctype in ("reference", "citation"):
            components.append(Component(component_type="reference", payload={
                "source": payload.get("source", ""),
                "page": payload.get("page"),
                "excerpt": payload.get("excerpt")
            }))
        elif ctype == "concept":
            components.append(Component(component_type="concept", payload={
                "name": payload.get("name", ""),
                "details": payload.get("details", [])
            }))
        elif ctype == "question":
            # Quiz engine owns this, do not render inline
            continue
        elif ctype == "text":
            components.append(Component(component_type="paragraph", payload={"text": c.text}))
        else:
            logger.warning(f"Unrecognized chunk_type '{ctype}' encountered. Falling back to paragraph.")
            components.append(Component(component_type="paragraph", payload={"text": "[content unavailable]"}))
            
    return components
