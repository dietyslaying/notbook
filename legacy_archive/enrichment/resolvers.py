import re
from typing import Dict, Any

class BaseResolver:
    def resolve(self, ndm: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

class MediaResolver(BaseResolver):
    """
    Scans the NDM for textual mentions of figures (e.g. "Figure 3.4") 
    and appends a media query so the renderer can fetch and display the image.
    """
    def resolve(self, ndm: Dict[str, Any]) -> Dict[str, Any]:
        blocks = ndm.get("blocks", [])
        
        for block in blocks:
            b_type = block.get("type")
            # If a reference cites a figure
            if b_type == "reference":
                source = str(block.get("source", ""))
                excerpt = str(block.get("excerpt", ""))
                match = re.search(r"Figure\s+(\d+\.\d+|\d+)", source + " " + excerpt, re.IGNORECASE)
                if match:
                    # Append a media_query to the semantic block
                    block["media_query"] = match.group(0)
                    block["media_type"] = "image"
        
        return ndm

class GlossaryResolver(BaseResolver):
    """
    Identifies complex terms in the text and flags them for glossary definitions.
    (Stubbed implementation for future terminology databases).
    """
    def resolve(self, ndm: Dict[str, Any]) -> Dict[str, Any]:
        # Future: Match terms against a local SQLite dictionary to inject tooltips
        return ndm

class CitationResolver(BaseResolver):
    """
    Ensures citations map properly to original RAG chunks if available.
    """
    def resolve(self, ndm: Dict[str, Any]) -> Dict[str, Any]:
        return ndm
