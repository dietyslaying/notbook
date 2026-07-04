import pytest
from interfaces import (
    IIAGenerator,
    KnowledgeTree,
    WorkspaceType,
    UserMode,
    IASchema,
    Chunk
)
from ia_generator.generator import IAGenerator

class TestIAGeneratorContract:
    @pytest.fixture
    def generator(self) -> IIAGenerator:
        return IAGenerator()

    def test_generate_disease_workspace(self, generator: IIAGenerator):
        # Create a mock knowledge tree for a disease with only symptoms and treatment chunks
        kt = KnowledgeTree(
            topic="Asthma",
            workspace_type=WorkspaceType.DISEASE,
            chunks=[
                Chunk(chunk_id="symptoms", text="Wheezing is a common symptom", textbook="Harrison", retrieval_score=0.9),
                Chunk(chunk_id="treatment", text="Albuterol is a treatment", textbook="Harrison", retrieval_score=0.8)
            ]
        )
        # Note: We need some way to tag chunks with section hints or the generator will map them?
        # Actually, in PRD, the retriever might tag them, or IA generator analyzes them.
        # But for now, we just pass the tree. Let's see how IA generator handles it.
        
        schema = generator.generate(kt, WorkspaceType.DISEASE, UserMode.STUDENT)
        
        assert isinstance(schema, IASchema)
        assert schema.workspace_type == WorkspaceType.DISEASE
        assert schema.topic == "Asthma"
        
        # We expect sections for Overview, Symptoms, Treatment, References (because we have content or it's standard)
        # We should NOT see Pathophysiology because there are no chunks for it.
        section_ids = [s.section_id for s in schema.sections]
        assert "symptoms" in section_ids
        assert "treatment" in section_ids
        assert "pathophysiology" not in section_ids

    def test_generate_nav_buttons(self, generator: IIAGenerator):
        kt = KnowledgeTree(
            topic="Asthma",
            workspace_type=WorkspaceType.DISEASE,
            chunks=[]
        )
        schema = generator.generate(kt, WorkspaceType.DISEASE, UserMode.STUDENT)
        
        # Buttons should correspond to available sections.
        assert len(schema.nav_buttons) > 0
        
        # Every button should have a callback starting with nav: or screen:
        for btn in schema.nav_buttons:
            assert btn.callback_data.startswith("screen:") or btn.callback_data.startswith("nav:")

    def test_generate_case_workspace(self, generator: IIAGenerator):
        kt = KnowledgeTree(
            topic="25yo with cough",
            workspace_type=WorkspaceType.CASE,
            chunks=[]
        )
        schema = generator.generate(kt, WorkspaceType.CASE, UserMode.STUDENT)
        assert schema.workspace_type == WorkspaceType.CASE
        section_ids = [s.section_id for s in schema.sections]
        assert "presentation" in section_ids
