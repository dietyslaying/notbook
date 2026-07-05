from interfaces import Component, Chunk

def build_components(section_id: str, chunks: list[Chunk]) -> list[Component]:
    """
    Transforms Semantic Blocks (Chunks) into Strongly Typed Components.
    """
    if not chunks:
        return [Component(component_type="paragraph", payload={"text": "No content found."})]
        
    components = []
    for c in chunks:
        ctype = c.chunk_type.lower()
        
        if ctype == "comparison":
            components.append(Component(component_type="comparison", payload=c.payload))
        elif ctype in ("reference", "citation"):
            components.append(Component(component_type="reference", payload=c.payload))
        elif ctype == "text":
            components.append(Component(component_type="paragraph", payload={"text": c.text}))
        else:
            # Fallback for general semantic blocks like disease_symptoms, treatment, etc.
            text = str(c.payload.get("content") or c.payload.get("definition") or c.payload.get("text") or c.payload)
            components.append(Component(component_type="paragraph", payload={"text": text}))
            
    return components
