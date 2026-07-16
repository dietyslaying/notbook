from __future__ import annotations

from abc import ABC, abstractmethod

from interfaces import IntentType
from services.gemini_service import gemini_service


class BaseWorkspace(ABC):
    intent: IntentType = IntentType.UNKNOWN

    @abstractmethod
    async def process(self, query: str, study_mode: str = "standard") -> dict:
        pass


class MedicalWorkspace(BaseWorkspace):
    intent = IntentType.UNKNOWN

    async def process(self, query: str, study_mode: str = "standard") -> dict:
        return await gemini_service.query_medical_knowledge(
            query, intent=self.intent, study_mode=study_mode
        )
