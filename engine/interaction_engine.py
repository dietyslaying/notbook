from typing import List, Dict, Any
from pydantic import BaseModel
from layout.components import Document

class ActionNode(BaseModel):
    version: str = "1.0"
    label: str
    action_data: str
    is_primary: bool = False
    disabled: bool = False

class InteractionTree(BaseModel):
    version: str = "1.0"
    actions: List[ActionNode] = []

class InteractionEngine:
    """
    Decides "what happens next" by examining the Component Tree (Document).
    Produces an independent InteractionTree rather than appending to layout.
    """
    
    def generate_interactions(self, doc: Document) -> InteractionTree:
        actions = []
        
        # We always want Quiz, Flashcards
        actions.append(ActionNode(label="🧠 Quiz Me", action_data="action_quiz", is_primary=True))
        actions.append(ActionNode(label="🃏 Flashcards", action_data="action_flashcards"))
        
        # Analyze Document Sections to add dynamic actions
        section_kinds = [sec.kind.lower() for sec in doc.sections]
        
        if "symptoms" in section_kinds:
            actions.append(ActionNode(label="⚖️ Compare...", action_data="action_compare"))
            
        if "pharmacology" in section_kinds:
            actions.append(ActionNode(label="⚠️ Interactions", action_data="action_drug_interactions"))
            
        actions.append(ActionNode(label="🔖 Bookmark", action_data="action_bookmark"))
        
        # Ensure max 4 visible actions as per Design Language
        return InteractionTree(actions=actions[:4])
