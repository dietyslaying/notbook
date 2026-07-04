from interfaces import Component, Chunk

def select_component(section_id: str, chunks: list[Chunk]) -> Component:
    """
    Selects the appropriate component based on section_id and chunks.
    Rule: length > 10 -> ExpandableList. Otherwise Checklist.
    If it's just a paragraph, use Paragraph.
    """
    if not chunks:
        return Component(component_type="paragraph", payload={"text": "No content found."})
        
    if section_id in ("symptoms", "causes", "complications"):
        if len(chunks) > 10:
            return Component(component_type="expandable", payload={"items": [c.text for c in chunks]})
        else:
            return Component(component_type="checklist", payload={"items": [c.text for c in chunks]})
            
    # Default to paragraph combining all texts
    text = " ".join([c.text for c in chunks])
    return Component(component_type="paragraph", payload={"text": text})
