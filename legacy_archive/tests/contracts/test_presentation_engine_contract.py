import pytest
from interfaces import (
    IPresentationEngine,
    IASchema,
    KnowledgeTree,
    WorkspaceType,
    UserMode,
    SectionSpec,
    ButtonSpec,
    Chunk
)
from presentation_engine.engine import PresentationEngine

class TestPresentationEngineContract:
    @pytest.fixture
    def engine(self) -> IPresentationEngine:
        return PresentationEngine()

    def test_generate_document_creates_checklist(self, engine: IPresentationEngine):
        # A list of 3 items should become a checklist.
        # But how does the engine know it's a list? Maybe based on content structure or just 
        # multiple chunks mapped to a single section?
        # Let's say we have 3 symptom chunks
        chunks = [
            Chunk(chunk_id="s1", text="Fever", textbook="Book", retrieval_score=0.9),
            Chunk(chunk_id="s2", text="Cough", textbook="Book", retrieval_score=0.9),
            Chunk(chunk_id="s3", text="Fatigue", textbook="Book", retrieval_score=0.9),
        ]
        kt = KnowledgeTree(topic="Flu", workspace_type=WorkspaceType.DISEASE, chunks=chunks)
        
        schema = IASchema(
            workspace_type=WorkspaceType.DISEASE,
            topic="Flu",
            sections=[
                SectionSpec(section_id="symptoms", section_type="symptoms", has_content=True, content_chunks=["s1", "s2", "s3"], order=0)
            ],
            nav_buttons=[],
            user_mode=UserMode.STUDENT
        )
        
        doc = engine.generate_document(schema, kt, "symptoms")
        
        assert doc.topic == "Flu"
        assert doc.workspace_type == WorkspaceType.DISEASE
        assert len(doc.sections) == 1
        
        section = doc.sections[0]
        assert section.section_id == "symptoms"
        
        # We expect a Checklist component
        assert len(section.components) == 1
        comp = section.components[0]
        assert comp.component_type == "checklist"
        assert "items" in comp.payload
        assert len(comp.payload["items"]) == 3

    def test_generate_document_creates_expandable_for_many_items(self, engine: IPresentationEngine):
        # More than 10 items should render as Expandable
        chunks = [Chunk(chunk_id=f"s{i}", text=f"Symptom {i}", textbook="Book", retrieval_score=0.9) for i in range(15)]
        kt = KnowledgeTree(topic="Flu", workspace_type=WorkspaceType.DISEASE, chunks=chunks)
        
        schema = IASchema(
            workspace_type=WorkspaceType.DISEASE,
            topic="Flu",
            sections=[
                SectionSpec(section_id="symptoms", section_type="symptoms", has_content=True, content_chunks=[f"s{i}" for i in range(15)], order=0)
            ],
            nav_buttons=[],
            user_mode=UserMode.STUDENT
        )
        
        doc = engine.generate_document(schema, kt, "symptoms")
        section = doc.sections[0]
        comp = section.components[0]
        assert comp.component_type == "expandable"
        assert len(comp.payload["items"]) == 15
