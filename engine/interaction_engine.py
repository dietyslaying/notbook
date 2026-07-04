from typing import List, Dict, Any
from pydantic import BaseModel
from layout.components import Document

class ActionNode(BaseModel):
    version: str = "1.0"
    label: str
    action_data: str
    is_primary: bool = False
    disabled: bool = False
    kind: str = "quick_action"

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
        
        # 1. Follow-Up Questions (Top priority)
        number_emojis = ["1️⃣", "2️⃣", "3️⃣"]
        for i, q in enumerate(doc.follow_up_questions[:3]):
            prefix = number_emojis[i] if i < len(number_emojis) else "❓"
            # Truncate label if necessary
            label_text = f"{prefix} {q[:40]}..." if len(q) > 40 else f"{prefix} {q}"
            actions.append(ActionNode(
                label=label_text, 
                action_data=f"db|{q}"[:64], 
                kind="follow_up"
            ))
            
        # 2. General Quick Actions
        # Analyze Document Sections to add dynamic actions
        section_kinds = [sec.kind.lower() for sec in doc.sections]
        
        if "symptoms" in section_kinds:
            # Disease
            actions.append(ActionNode(label="🧠 Quiz", action_data="action_quiz", is_primary=True))
            actions.append(ActionNode(label="🃏 Flashcards", action_data="action_flashcards"))
            actions.append(ActionNode(label="⚖️ Differential", action_data="action_compare"))
            actions.append(ActionNode(label="📖 Guidelines", action_data="action_guidelines"))
        
        elif "mechanism" in section_kinds or "indications" in section_kinds:
            # Drug
            actions.append(ActionNode(label="🧠 Quiz", action_data="action_quiz", is_primary=True))
            actions.append(ActionNode(label="🃏 Flashcards", action_data="action_flashcards"))
            actions.append(ActionNode(label="⚠️ Interactions", action_data="action_drug_interactions"))
            actions.append(ActionNode(label="🚫 Contra", action_data="action_contraindications"))
            
        elif "presentation" in section_kinds:
            # Clinical Case
            actions.append(ActionNode(label="⚖️ Differential", action_data="action_compare", is_primary=True))
            actions.append(ActionNode(label="🔬 Investigations", action_data="action_investigations"))
            actions.append(ActionNode(label="💊 Management", action_data="action_management"))
            
        elif "comparison table" in section_kinds:
            # Comparison
            actions.append(ActionNode(label="🧠 Quiz", action_data="action_quiz", is_primary=True))
            actions.append(ActionNode(label="🃏 Flashcards", action_data="action_flashcards"))
            
        else:
            # General
            actions.append(ActionNode(label="🧠 Quiz Me", action_data="action_quiz", is_primary=True))
            actions.append(ActionNode(label="🃏 Flashcards", action_data="action_flashcards"))
            actions.append(ActionNode(label="🔖 Bookmark", action_data="action_bookmark"))
        
        # Ensure max 4 visible actions as per Design Language
        return InteractionTree(actions=actions[:4])
