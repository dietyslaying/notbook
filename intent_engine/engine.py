import re
from interfaces import (
    IIntentEngine, IntentResult, IntentType, WorkspaceType
)

class IntentEngine(IIntentEngine):
    async def classify(self, text: str) -> IntentResult:
        if not text or not isinstance(text, str):
            return IntentResult(intent_type=IntentType.UNKNOWN)

        text_lower = text.lower().strip()

        # Fast-track menu
        if text_lower == "menu":
            return IntentResult(intent_type=IntentType.MAIN_MENU)

        import asyncio
        import gemini_service
        
        try:
            # classify_intent is synchronous but classify is async
            result_dict = await asyncio.to_thread(gemini_service.classify_intent, text)
            
            # Map strings back to enums safely
            itype_str = result_dict.get("intent_type", "unknown").upper()
            ttype_str = result_dict.get("topic_type", "").lower()
            
            try:
                itype = IntentType(itype_str.lower())
            except ValueError:
                itype = IntentType.UNKNOWN
                
            ttype = None
            if ttype_str:
                try:
                    ttype = WorkspaceType(ttype_str)
                except ValueError:
                    ttype = None
                    
            # Fallbacks if topic type is missing but intent implies it
            if ttype is None and itype != IntentType.UNKNOWN:
                if itype in (IntentType.TOPIC_OVERVIEW, IntentType.TOPIC_SECTION):
                    ttype = WorkspaceType.DISEASE
                elif itype in (IntentType.DRUG_LOOKUP, IntentType.DRUG_SECTION):
                    ttype = WorkspaceType.DRUG
                elif itype == IntentType.CLINICAL_CASE:
                    ttype = WorkspaceType.CASE
                elif itype == IntentType.COMPARISON:
                    ttype = WorkspaceType.COMPARISON
            
            return IntentResult(
                intent_type=itype,
                topic=result_dict.get("topic") or "UNKNOWN TOPIC",
                topic_type=ttype,
                section=result_dict.get("section"),
                confidence=float(result_dict.get("confidence", 0.0))
            )
            
        except Exception as e:
            # Log error and fallback to UNKNOWN, matching interface contract
            import logging
            logging.getLogger(__name__).error(f"Intent Engine failed: {e}")
            return IntentResult(intent_type=IntentType.UNKNOWN)
