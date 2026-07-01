from typing import Dict, Any, Literal

class ContentIntelligence:
    """
    Analyzes the Enriched Knowledge Tree and determines the macro-level Layout Template.
    e.g. A tree full of 'disease_symptoms' and 'treatment' should use the DiseaseTemplate.
    """
    
    def determine_template(self, knowledge_tree: Dict[str, Any]) -> Literal["disease", "drug", "comparison", "general"]:
        category = knowledge_tree.get("topic_category")
        
        if category in ("disease", "drug", "comparison"):
            return category
            
        # Fallback heuristic analysis if topic_category is missing/general
        blocks = knowledge_tree.get("blocks", [])
        types = [b.get("type") for b in blocks if isinstance(b, dict)]
        
        if "disease_symptoms" in types or "clinical_case" in types:
            return "disease"
        if "drug_info" in types:
            return "drug"
        if "comparison" in types:
            return "comparison"
            
        return "general"
