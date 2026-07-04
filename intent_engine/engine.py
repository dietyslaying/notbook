import re
from interfaces import (
    IIntentEngine, IntentResult, IntentType, WorkspaceType
)

class IntentEngine(IIntentEngine):
    async def classify(self, text: str) -> IntentResult:
        if not text or not isinstance(text, str):
            return IntentResult(intent_type=IntentType.UNKNOWN)

        text_lower = text.lower()

        # Menu
        if text_lower.strip() == "menu":
            return IntentResult(intent_type=IntentType.MAIN_MENU)

        # Clinical case
        match = re.search(r"clinical case for (.*)", text_lower)
        if match:
            return IntentResult(
                intent_type=IntentType.CLINICAL_CASE,
                topic=match.group(1).strip().upper(),
                confidence=0.9
            )

        # Topic section (Disease)
        match = re.search(r"symptoms of (.*)", text_lower)
        if match:
            return IntentResult(
                intent_type=IntentType.TOPIC_SECTION,
                topic=match.group(1).strip().replace('?', '').upper(),
                section="symptoms",
                topic_type=WorkspaceType.DISEASE,
                confidence=0.9
            )

        # Topic overview (Disease)
        match = re.search(r"tell me about (.*)", text_lower)
        if match:
            return IntentResult(
                intent_type=IntentType.TOPIC_OVERVIEW,
                topic=match.group(1).strip().upper(),
                topic_type=WorkspaceType.DISEASE,
                confidence=0.9
            )

        # Drug section
        match = re.search(r"dosage for (.*)", text_lower)
        if match:
            return IntentResult(
                intent_type=IntentType.DRUG_SECTION,
                topic=match.group(1).strip().upper(),
                section="dosage",
                topic_type=WorkspaceType.DRUG,
                confidence=0.9
            )

        # Drug lookup
        if text_lower.strip() == "methylphenidate":
            return IntentResult(
                intent_type=IntentType.DRUG_LOOKUP,
                topic="METHYLPHENIDATE",
                topic_type=WorkspaceType.DRUG,
                confidence=0.9
            )

        return IntentResult(intent_type=IntentType.UNKNOWN)
