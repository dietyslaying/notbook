from typing import List, Dict, Any, Type
from layout.components import Section

class PageTemplate:
    """
    Abstract base class for all Page Templates.
    Defines the semantic structure of a document (the Sections).
    """
    
    def build_sections(self, ndm_doc: Dict[str, Any]) -> List[Section]:
        """
        Takes an NDM Document (a dict of parsed blocks) and returns a structured list of Sections.
        Each subclass decides which NDM blocks go into which Section.
        """
        raise NotImplementedError("Subclasses must implement build_sections()")
