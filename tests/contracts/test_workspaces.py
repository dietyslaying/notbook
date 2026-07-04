"""
tests/contracts/test_workspaces.py

Phase 1 - Workspaces Contract Tests
All tests MUST FAIL before implementation exists.
Run: pytest tests/contracts/test_workspaces.py -v
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from interfaces import Document, WorkspaceType

@pytest.fixture
def disease_workspace():
    from workspaces.disease import DiseaseWorkspace
    return DiseaseWorkspace()

@pytest.fixture
def drug_workspace():
    from workspaces.drug import DrugWorkspace
    return DrugWorkspace()

class TestWorkspaces:
    def test_disease_workspace_overview(self, disease_workspace):
        doc = disease_workspace.generate_screen(topic="ADHD", screen_id="overview")
        assert isinstance(doc, Document)
        assert doc.topic == "ADHD"
        assert doc.workspace_type == WorkspaceType.DISEASE
        assert doc.ia_schema is not None
        
        # Verify hardcoded navigation buttons for Phase 1
        labels = [b.label for b in doc.ia_schema.nav_buttons]
        assert "📋 Symptoms" in labels
        assert "🔬 Diagnosis" in labels
        assert "💊 Treatment" in labels
        assert "📚 References" in labels

    def test_disease_workspace_symptoms(self, disease_workspace):
        doc = disease_workspace.generate_screen(topic="ADHD", screen_id="symptoms")
        assert doc.ia_schema is not None
        labels = [b.label for b in doc.ia_schema.nav_buttons]
        assert "⬅️ Back" in labels
        assert "🏠 Menu" in labels

    def test_drug_workspace_overview(self, drug_workspace):
        doc = drug_workspace.generate_screen(topic="Methylphenidate", screen_id="overview")
        assert isinstance(doc, Document)
        assert doc.topic == "Methylphenidate"
        assert doc.workspace_type == WorkspaceType.DRUG
        assert doc.ia_schema is not None
        
        labels = [b.label for b in doc.ia_schema.nav_buttons]
        assert "⚙️ Mechanism" in labels
        assert "🎯 Indications" in labels
        assert "⚖️ Dosage" in labels
        assert "⚠️ Side Effects" in labels
        assert "🚫 Contraindications" in labels
