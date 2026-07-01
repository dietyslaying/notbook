from typing import List, Dict, Any

class ButtonComponent:
    def __init__(self, label: str, action_data: str):
        self.type = "button"
        self.label = label
        self.action_data = action_data

class ButtonBarComponent:
    def __init__(self, buttons: List[ButtonComponent]):
        self.type = "button_bar"
        self.buttons = buttons

class InteractionEngine:
    """
    Decides "what happens next" by examining the Component Tree and Knowledge Tree.
    Appends interactive buttons and action flows.
    """
    def __init__(self):
        pass
        
    def append_interactions(self, component_tree: List[Any], knowledge_tree: Dict[str, Any]) -> List[Any]:
        # Always provide standard study actions
        buttons = [
            ButtonComponent(label="🧠 Quiz Me", action_data="action_quiz"),
            ButtonComponent(label="🃏 Flashcards", action_data="action_flashcards"),
            ButtonComponent(label="🔖 Bookmark", action_data="action_bookmark")
        ]
        
        # If it's a disease, maybe offer comparison
        if knowledge_tree.get("topic_category") == "disease":
            buttons.append(ButtonComponent(label="⚖️ Compare...", action_data="action_compare"))
            
        component_tree.append(ButtonBarComponent(buttons=buttons))
        return component_tree
