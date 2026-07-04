from typing import Dict, Any, Type
from layout.templates.base import PageTemplate
from layout.templates.disease import DiseaseTemplate
from layout.templates.drug import DrugTemplate
from layout.templates.general import GeneralTemplate
from layout.templates.clinical_case import ClinicalCaseTemplate
from layout.templates.comparison import ComparisonTemplate
from layout.presentation_engine import PresentationEngine

class TemplateRegistry:
    """
    Maps topic categories to specific Page Templates.
    """
    
    def __init__(self, presentation_engine: PresentationEngine):
        self.presentation_engine = presentation_engine
        
        # Pre-instantiate templates with the engine
        self._templates = {
            "disease": DiseaseTemplate(self.presentation_engine),
            "drug": DrugTemplate(self.presentation_engine),
            "clinical_case": ClinicalCaseTemplate(self.presentation_engine),
            "comparison": ComparisonTemplate(self.presentation_engine),
            "general": GeneralTemplate(self.presentation_engine)
        }
        
    def get_template(self, category: str) -> PageTemplate:
        return self._templates.get(category, self._templates["general"])
