import uuid
from interfaces import IFlashcardEngine, KnowledgeTree, FlashcardDeck, Flashcard
from flashcard_engine.spaced_repetition import requeue_card

class FlashcardEngine(IFlashcardEngine):
    def generate(self, knowledge_tree: KnowledgeTree) -> FlashcardDeck:
        import asyncio
        from gemini_service import generate_flashcards
        
        context_text = ""
        for c in knowledge_tree.chunks:
            if c.text:
                context_text += f"{c.text}\n"
            else:
                context_text += f"{str(c.payload)}\n"
                
        if not context_text.strip():
            context_text = "General medical knowledge."
            
        num_cards = min(max(len(knowledge_tree.chunks), 5), 20)
        generated = asyncio.run(generate_flashcards(context_text, num_cards))
        
        cards = []
        for i, gc in enumerate(generated):
            cards.append(Flashcard(
                card_id=str(uuid.uuid4()),
                front=gc.get("front", f"Flashcard {i}?"),
                back_points=gc.get("back_points", ["Point 1"]),
                memory_tip=gc.get("memory_tip")
            ))
            
        # Fallback if generation fails
        if not cards:
            for i in range(num_cards):
                chunk = knowledge_tree.chunks[i % len(knowledge_tree.chunks)] if knowledge_tree.chunks else None
                cards.append(Flashcard(
                    card_id=str(uuid.uuid4()),
                    front=f"What is {chunk.text if chunk and chunk.text else f'Fact {i}'}?",
                    back_points=["Point 1", "Point 2"],
                    memory_tip="Tip from source" if i % 2 == 0 else None
                ))

            
        return FlashcardDeck(
            deck_id=str(uuid.uuid4()),
            topic=knowledge_tree.topic,
            cards=cards
        )

    def requeue_incorrect(
        self,
        deck: FlashcardDeck,
        card_id: str,
        positions_later: int = 3,
    ) -> FlashcardDeck:
        return requeue_card(deck, card_id, positions_later)
