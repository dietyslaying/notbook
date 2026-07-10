from abc import ABC, abstractmethod
from interfaces import NDMDocument
from services.gemini_service import GeminiService

class BaseWorkspace(ABC):
    def __init__(self):
        self.gemini = GeminiService()

    @abstractmethod
    async def process(self, query: str) -> dict:
        pass

class MedicalWorkspace(BaseWorkspace):
    """Generic workspace for standard medical queries."""
    async def process(self, query: str) -> dict:
        return await self.gemini.query_medical_knowledge(query)
