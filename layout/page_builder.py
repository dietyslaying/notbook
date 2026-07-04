from typing import Dict, Any
from layout.components import Document
from layout.template_registry import TemplateRegistry

class PageBuilder:
    """
    Orchestrates the conversion of a semantic NDM Document into a fully structured Layout Document
    (Document -> Section -> Components).
    """
    
    def __init__(self, template_registry: TemplateRegistry):
        self.template_registry = template_registry
        
    def build_page(self, ndm_doc: Dict[str, Any]) -> Document:
        """
        Reads the NDM document, selects the appropriate template, and builds the Document tree.
        """
        if not ndm_doc:
            return Document()
            
        category = ndm_doc.get("topic_category", "general")
        template = self.template_registry.get_template(category)
        
        sections = template.build_sections(ndm_doc)
        
        doc = Document(sections=sections)
        
        # We might want to inject a TitleSection or TitleComponent at the very top of the Document.
        # For now, let's just return the Document containing the Sections.
        return doc
