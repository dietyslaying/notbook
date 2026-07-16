from interfaces import IntentType
from workspaces.base import MedicalWorkspace


class ComparisonWorkspace(MedicalWorkspace):
    intent = IntentType.COMPARISON
