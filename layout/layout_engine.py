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

            elif b_type == "drug_info":
                name = block.get("drug_name", "Drug")
                components.append(HeadingComponent(text=f"{name} (Drug Info)", icon=icon, source_chunk_ids=source_ids))
                
                if block.get("mechanism"):
                    components.append(ParagraphComponent(text=f"Mechanism: {block.get('mechanism')}", source_chunk_ids=source_ids))
                
                if block.get("indications"):
                    components.append(ParagraphComponent(text="Indications:", source_chunk_ids=source_ids))
                    components.append(ChecklistComponent(items=block.get("indications"), source_chunk_ids=source_ids))
                
                if block.get("contraindications"):
                    components.append(ParagraphComponent(text="Contraindications:", source_chunk_ids=source_ids))
                    components.append(ChecklistComponent(items=block.get("contraindications"), source_chunk_ids=source_ids))
                    
                if block.get("side_effects"):
                    components.append(ParagraphComponent(text="Side Effects:", source_chunk_ids=source_ids))
                    components.append(ChecklistComponent(items=block.get("side_effects"), source_chunk_ids=source_ids))

            elif b_type == "timeline":
                components.append(HeadingComponent(text="Timeline", icon="⏱", source_chunk_ids=source_ids))
                events = block.get("events", [])
                rows = [[e.get("time", ""), e.get("event", "")] for e in events]
                if rows:
                    components.append(TableComponent(headers=["Time", "Event"], rows=rows, source_chunk_ids=source_ids))

            elif b_type == "formula":
                components.append(HeadingComponent(text=block.get("name", "Formula"), icon="🧮", source_chunk_ids=source_ids))
                components.append(ParagraphComponent(text=f"`{block.get('expression', '')}`", source_chunk_ids=source_ids))
                variables = block.get("variables", [])
                if variables:
                    var_list = [f"{v.get('name', '')}: {v.get('meaning', '')}" for v in variables]
                    components.append(ChecklistComponent(items=var_list, source_chunk_ids=source_ids))

            elif b_type == "guideline":
                org = block.get("organization", "Guideline")
                components.append(HeadingComponent(text=f"{org} Guidelines", icon="📜", source_chunk_ids=source_ids))
                if block.get("recommendations"):
                    components.append(ChecklistComponent(items=block.get("recommendations"), source_chunk_ids=source_ids))

            elif b_type == "clinical_case":
                components.append(HeadingComponent(text="Clinical Case", icon="🏥", source_chunk_ids=source_ids))
                components.append(ParagraphComponent(text=block.get("patient_presentation", ""), source_chunk_ids=source_ids))
                if block.get("key_findings"):
                    components.append(ParagraphComponent(text="Key Findings:", source_chunk_ids=source_ids))
                    components.append(ChecklistComponent(items=block.get("key_findings"), source_chunk_ids=source_ids))
                if block.get("diagnosis"):
                    components.append(ParagraphComponent(text=f"Diagnosis: {block.get('diagnosis')}", source_chunk_ids=source_ids))

            elif b_type == "concept":
                components.append(HeadingComponent(text=block.get("name", "Concept"), icon="💡", source_chunk_ids=source_ids))
                if block.get("details"):
                    components.append(ChecklistComponent(items=block.get("details"), source_chunk_ids=source_ids))

            elif b_type == "question":
                components.append(HeadingComponent(text="Practice Question", icon="❓", source_chunk_ids=source_ids))
                components.append(ParagraphComponent(text=block.get("question", ""), source_chunk_ids=source_ids))
                if block.get("options"):
                    components.append(ChecklistComponent(items=block.get("options"), source_chunk_ids=source_ids))
                # Answer and explanation might be hidden in a real UI, but shown as paragraph for now
                components.append(ParagraphComponent(text=f"Answer: {block.get('answer', '')}", source_chunk_ids=source_ids))
                components.append(ParagraphComponent(text=f"Explanation: {block.get('explanation', '')}", source_chunk_ids=source_ids))

            elif b_type == "reference":
                components.append(HeadingComponent(text="Reference", icon="📚", source_chunk_ids=source_ids))
                source_txt = block.get("source", "")
                if block.get("page"):
                    source_txt += f" (Page {block.get('page')})"
                components.append(ParagraphComponent(text=source_txt, source_chunk_ids=source_ids))
                if block.get("excerpt"):
                    components.append(ParagraphComponent(text=f"\"{block.get('excerpt')}\"", source_chunk_ids=source_ids))
                
            # Generic fallback divider for separation
            components.append(DividerComponent())

        return components
