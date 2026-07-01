import uuid
from typing import Dict, Any, List

class LayoutComponent:
    """Base class for all Layout Components in the Component Tree."""
    def __init__(self, c_type: str, source_chunk_ids: List[str] = None):
        self.component_id = str(uuid.uuid4())
        self.type = c_type
        self.source_chunk_ids = source_chunk_ids or []
        self.dependencies = []

class HeadingComponent(LayoutComponent):
    def __init__(self, text: str, icon: str = "", level: int = 2, **kwargs):
        super().__init__("heading", **kwargs)
        self.text = text
        self.icon = icon
        self.level = level

class ParagraphComponent(LayoutComponent):
    def __init__(self, text: str, **kwargs):
        super().__init__("paragraph", **kwargs)
        self.text = text

class ChecklistComponent(LayoutComponent):
    def __init__(self, items: List[str], **kwargs):
        super().__init__("checklist", **kwargs)
        self.items = items

class TableComponent(LayoutComponent):
    def __init__(self, rows: List[List[str]], headers: List[str] = None, **kwargs):
        super().__init__("table", **kwargs)
        self.headers = headers or []
        self.rows = rows

class DividerComponent(LayoutComponent):
    def __init__(self, **kwargs):
        super().__init__("divider", **kwargs)

class LayoutEngine:
    """
    Transforms an enriched Knowledge Tree into a Layout Component Tree.
    Never mutates the original Knowledge Tree.
    """
    def __init__(self, design_system=None):
        from .design_system import DesignSystem
        self.design = design_system or DesignSystem()

    def process(self, knowledge_tree: Dict[str, Any]) -> List[LayoutComponent]:
        components = []
        
        # Add title
        title = knowledge_tree.get("title", "Study Document")
        components.append(HeadingComponent(text=title, level=1))
        components.append(DividerComponent())
        
        blocks = knowledge_tree.get("blocks", [])
        
        for block in blocks:
            b_type = block.get("type")
            source_ids = block.get("source_chunk_ids", [])
            icon = self.design.get_icon_for_section(b_type)
            
            # Map Semantic blocks to UI Layout Components
            if b_type == "disease_symptoms":
                components.append(HeadingComponent(text="Symptoms", icon=icon, source_chunk_ids=source_ids))
                components.append(ChecklistComponent(items=block.get("symptoms", []), source_chunk_ids=source_ids))
                
            elif b_type == "treatment":
                components.append(HeadingComponent(text="Treatment", icon=icon, source_chunk_ids=source_ids))
                components.append(ChecklistComponent(items=block.get("treatments", []), source_chunk_ids=source_ids))
                if block.get("notes"):
                    components.append(ParagraphComponent(text=block["notes"], source_chunk_ids=source_ids))
                    
            elif b_type == "definition":
                components.append(HeadingComponent(text=block.get("term", "Definition"), icon="📖", source_chunk_ids=source_ids))
                components.append(ParagraphComponent(text=block.get("definition", ""), source_chunk_ids=source_ids))
                
            elif b_type == "comparison":
                components.append(HeadingComponent(text=f"Comparison: {block.get('topic_a')} vs {block.get('topic_b')}", icon=icon, source_chunk_ids=source_ids))
                aspects = block.get("aspects", [])
                if aspects:
                    headers = ["Aspect", block.get("topic_a", "A"), block.get("topic_b", "B")]
                    rows = [[a.get("aspect", ""), a.get("a", ""), a.get("b", "")] for a in aspects]
                    components.append(TableComponent(headers=headers, rows=rows, source_chunk_ids=source_ids))
                    
            elif b_type == "explanation":
                components.append(HeadingComponent(text=block.get("topic", "Explanation"), icon="📝", source_chunk_ids=source_ids))
                components.append(ParagraphComponent(text=block.get("content", ""), source_chunk_ids=source_ids))
                
            # Generic fallback divider for separation
            components.append(DividerComponent())

        return components
