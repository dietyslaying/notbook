from typing import Dict, Any

class BaseGenerator:
    def generate(self, ndm: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

class MemoryAidGenerator(BaseGenerator):
    """
    Looks for complex lists (e.g., side effects or symptoms) and generates a mnemonic if applicable.
    Currently stubbed out.
    """
    def generate(self, ndm: Dict[str, Any]) -> Dict[str, Any]:
        return ndm

class ClinicalPearlGenerator(BaseGenerator):
    """
    Extracts high-yield facts and tags them as clinical pearls.
    """
    def generate(self, ndm: Dict[str, Any]) -> Dict[str, Any]:
        return ndm

class QuizSeedGenerator(BaseGenerator):
    """
    Pre-generates latent quiz questions based on the NDM contents for future quizzes.
    """
    def generate(self, ndm: Dict[str, Any]) -> Dict[str, Any]:
        # Future: store seeds in a background database linked to the user's progress.
        return ndm
