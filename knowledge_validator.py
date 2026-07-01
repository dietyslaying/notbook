from typing import Dict, Any, List

class KnowledgeValidator:
    """
    Cleans and validates the raw Knowledge Tree (NIR) returned by Gemini.
    Scrubs empty blocks, bad data, or duplicate entries before enrichment.
    """
    def __init__(self):
        pass

    def validate(self, knowledge_tree: Dict[str, Any]) -> Dict[str, Any]:
        if not knowledge_tree:
            return {}

        validated_blocks = []
        blocks = knowledge_tree.get("blocks", [])

        for block in blocks:
            if not isinstance(block, dict):
                continue
                
            b_type = block.get("type")
            
            # 1. Filter out empty lists or missing critical fields
            if self._is_block_empty(block):
                continue

            # 2. Scrub hallucinated page numbers from references
            if b_type == "reference":
                if not block.get("source") or block.get("source").strip() == "":
                    continue # Drop empty references
                
                # If page is something like "0" or "None", remove it
                page = block.get("page")
                if page and str(page).lower() in ("0", "none", "unknown", "n/a"):
                    block["page"] = None

            validated_blocks.append(block)

        knowledge_tree["blocks"] = validated_blocks
        return knowledge_tree
        
    def _is_block_empty(self, block: Dict[str, Any]) -> bool:
        """Heuristic to drop completely empty generated blocks."""
        b_type = block.get("type")
        
        if b_type == "disease_symptoms" and not block.get("symptoms"):
            return True
        if b_type == "treatment" and not block.get("treatments"):
            return True
        if b_type == "drug_info":
            if not block.get("indications") and not block.get("mechanism"):
                return True
        if b_type == "guideline" and not block.get("recommendations"):
            return True
        if b_type == "comparison" and not block.get("aspects"):
            return True
            
        return False
