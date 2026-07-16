"""Lightweight intent classifier (Gemini JSON)."""

from __future__ import annotations

import json
import logging
import re

from config import config
from interfaces import IntentType
from services.gemini_service import gemini_service

logger = logging.getLogger(__name__)

# Fast path heuristics — skip an LLM call when obvious
_DRUG_HINTS = re.compile(
    r"\b(dose|dosage|mg\b|tablet|side effect|contraindic|drug|medication|antibiotic|"
    r"metformin|insulin|aspirin|ibuprofen|paracetamol|acetaminophen|statin|acei|"
    r"beta.?blocker|ssri|opioid)\b",
    re.I,
)
_DISEASE_HINTS = re.compile(
    r"\b(disease|syndrome|pathophys|symptom|diagnosis|differential|prognosis|"
    r"hypertension|diabetes|asthma|copd|pneumonia|failure|infection|cancer|"
    r"what is|define)\b",
    re.I,
)
_COMPARE_HINTS = re.compile(r"\b(vs\.?|versus|compare|difference between|differ)\b", re.I)
_STUDY_HINTS = re.compile(r"\b(quiz|flashcard|test me|mcq|revise|high.?yield)\b", re.I)


class IntentEngine:
    def __init__(self) -> None:
        self.model_name = config.raw_config["llm"]["model_name"]

    def _heuristic(self, text: str) -> IntentType | None:
        if _STUDY_HINTS.search(text):
            return IntentType.STUDY
        if _COMPARE_HINTS.search(text):
            return IntentType.COMPARISON
        drug = bool(_DRUG_HINTS.search(text))
        disease = bool(_DISEASE_HINTS.search(text))
        if drug and not disease:
            return IntentType.DRUG
        if disease and not drug:
            return IntentType.DISEASE
        return None

    async def classify(self, text: str) -> IntentType:
        text = (text or "").strip()
        if not text:
            return IntentType.UNKNOWN

        quick = self._heuristic(text)
        if quick is not None:
            return quick

        prompt = f"""
Classify this medical study query into ONE intent.
Return JSON only: {{"intent": "disease"|"drug"|"comparison"|"study"|"unknown"}}

Rules:
- disease: condition, symptoms, pathophysiology, diagnosis
- drug: medication, dose, side effects, interactions
- comparison: vs / difference between
- study: quiz / flashcards / test me
- unknown: unclear

Query: {text}
"""
        try:
            raw = await gemini_service.generate_json(prompt)

            raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M)
            data = json.loads(raw)
            intent = str(data.get("intent", "unknown")).lower().strip()
            return IntentType(intent) if intent in IntentType._value2member_map_ else IntentType.UNKNOWN
        except Exception as e:
            logger.warning("Intent classify failed: %s", e)
            return IntentType.UNKNOWN
