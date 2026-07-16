from interfaces import IntentType
from workspaces.base import MedicalWorkspace


class StudyWorkspace(MedicalWorkspace):
    intent = IntentType.STUDY
