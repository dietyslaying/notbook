import re
from typing import Dict, Any

# ---------------------------------------------------------------------------
# Document Composer
# ---------------------------------------------------------------------------

class DocumentComposer:
    def __init__(self):
        pass
        
    def compose(self, ast_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Takes the raw AST from Gemini and enriches it.
        Applies detectors (e.g., finding images in references).
        """
        enriched_blocks = []
        
        blocks = ast_dict.get("blocks", [])
        for block in blocks:
            # Run detectors on the block
            block = self._detect_images(block)
            enriched_blocks.append(block)
            
        ast_dict["blocks"] = enriched_blocks
        
        # We can enforce template ordering here if needed
        # e.g., if template_type == 'disease', ensure 'definition' is first.
        
        return ast_dict

    def _detect_images(self, block: Dict[str, Any]) -> Dict[str, Any]:
        """
        If a reference or text mentions a figure, inject an image block.
        """
        if block.get("type") == "reference":
            source = block.get("source", "")
            excerpt = block.get("excerpt", "")
            
            # Simple heuristic: Look for "Figure X.Y"
            match = re.search(r"Figure\s+(\d+\.\d+|\d+)", source + " " + excerpt, re.IGNORECASE)
            if match:
                # We append an image payload to the reference block
                block["image_query"] = match.group(0)
                
        return block
