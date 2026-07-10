from typing import List, Any
from pydantic import BaseModel

class StudyContext(BaseModel):
    platform: str = "telegram"
    theme: str = "medical"
    mode: str = "student"
    density: str = "compact"
    streaming: bool = True

class IncrementalRenderer:
    """
    Base class for renderers that incrementally process the Component Tree.
    """
    def __init__(self, context: StudyContext):
        self.context = context
        
    def render_incremental(self, component_stream):
        # Generator that yields rendered output (platform-specific)
        raise NotImplementedError
