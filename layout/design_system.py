from pydantic import BaseModel
from typing import Dict, Any

class DesignTokens(BaseModel):
    spacing_unit: int = 4
    primary_color: str = "#007AFF"
    emoji_theme: str = "clinical"  # e.g., 'clinical', 'student', 'minimal'
    
class Theme(BaseModel):
    name: str
    tokens: DesignTokens
    
class DesignSystem:
    def __init__(self, theme_name: str = "default"):
        self.theme = self._load_theme(theme_name)
        
    def _load_theme(self, name: str) -> Theme:
        # Stubbed theme loading
        return Theme(name=name, tokens=DesignTokens())
        
    def get_icon_for_section(self, section_type: str) -> str:
        """Returns thematic emojis for different section types."""
        icons = {
            "disease_symptoms": "🩺",
            "treatment": "💊",
            "drug_info": "🧪",
            "comparison": "⚖️",
            "clinical_case": "🏥",
            "guideline": "📜",
            "formula": "🧮",
        }
        return icons.get(section_type, "📌")
