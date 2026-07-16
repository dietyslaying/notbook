from interfaces import IntentType
from workspaces.base import MedicalWorkspace


class DrugWorkspace(MedicalWorkspace):
    intent = IntentType.DRUG
