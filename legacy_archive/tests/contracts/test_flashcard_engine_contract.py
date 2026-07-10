import pytest
from interfaces import (
    IFlashcardEngine,
    KnowledgeTree,
    Chunk,
    WorkspaceType
)
from flashcard_engine.generator import FlashcardEngine

class TestFlashcardEngineContract:
    @pytest.fixture
    def engine(self) -> IFlashcardEngine:
        return FlashcardEngine()

    def test_generate_flashcards(self, engine: IFlashcardEngine):
        chunks = [Chunk(chunk_id=f"c{i}", text=f"Fact {i}", textbook="Book", retrieval_score=0.9) for i in range(10)]
        kt = KnowledgeTree(topic="Disease", workspace_type=WorkspaceType.DISEASE, chunks=chunks)
        
        deck = engine.generate(kt)
        
        assert len(deck.cards) >= 5
        assert len(deck.cards) <= 20
        assert deck.topic == "Disease"

    def test_requeue_incorrect(self, engine: IFlashcardEngine):
        chunks = [Chunk(chunk_id=f"c{i}", text=f"Fact {i}", textbook="Book", retrieval_score=0.9) for i in range(10)]
        kt = KnowledgeTree(topic="Disease", workspace_type=WorkspaceType.DISEASE, chunks=chunks)
        deck = engine.generate(kt)
        
        # Suppose card at index 0 is incorrect.
        failed_card = deck.cards[0]
        original_length = len(deck.cards)
        
        # Requeue 3 positions later
        deck = engine.requeue_incorrect(deck, failed_card.card_id, positions_later=3)
        
        # Deck size should increase by 1 since we re-inserted it
        assert len(deck.cards) == original_length + 1
        
        # The card should now appear at index 3 (0 + 3)
        assert deck.cards[3].card_id == failed_card.card_id
