import asyncio
from interfaces import Chunk, KnowledgeTree, WorkspaceType
from workspaces.disease import DiseaseWorkspace
from presentation_engine.engine import PresentationEngine
from ia_generator.generator import IAGenerator
from renderer.telegram_renderer import TelegramRenderer

async def run_test():
    chunk_1 = Chunk(
        chunk_id="comparison_0",
        chunk_type="comparison",
        payload={
            "type": "comparison",
            "topic_a": "Type 1 Diabetes",
            "topic_b": "Type 2 Diabetes",
            "aspects": [
                {"aspect": "Onset", "topic_a_value": "Sudden", "topic_b_value": "Gradual"}
            ]
        },
        textbook="test"
    )
    chunk_2 = Chunk(
        chunk_id="reference_0",
        chunk_type="reference",
        payload={
            "type": "reference",
            "source": "Murtagh's General Practice",
            "pages": "100-101"
        },
        textbook="test"
    )
    chunk_3 = Chunk(
        chunk_id="disease_symptoms_0",
        chunk_type="disease_symptoms",
        payload={
            "type": "disease_symptoms",
            "content": "Polyuria, polydipsia, weight loss."
        },
        textbook="test"
    )

    kt = KnowledgeTree(topic="Diabetes", workspace_type=WorkspaceType.DISEASE, chunks=[chunk_1, chunk_2, chunk_3])
    
    ia = IAGenerator()
    schema = ia.generate(kt, WorkspaceType.DISEASE, user_mode="student")
    print(f"Generated {len(schema.sections)} sections")
    for sec in schema.sections:
        print(f"Section {sec.section_id} has chunks: {sec.content_chunks}")

    engine = PresentationEngine()
    renderer = TelegramRenderer()

    # Test "overview" screen
    doc_overview = engine.generate_document(schema, kt, "overview")
    screen_overview = renderer.render(doc_overview)
    print("\n--- OVERVIEW SCREEN ---")
    print(screen_overview.html)

    # Test "symptoms" screen
    doc_symptoms = engine.generate_document(schema, kt, "symptoms")
    screen_symptoms = renderer.render(doc_symptoms)
    print("\n--- SYMPTOMS SCREEN ---")
    print(screen_symptoms.html)
    
    # Test "references" screen
    doc_references = engine.generate_document(schema, kt, "references")
    screen_references = renderer.render(doc_references)
    print("\n--- REFERENCES SCREEN ---")
    print(screen_references.html)

if __name__ == "__main__":
    asyncio.run(run_test())
