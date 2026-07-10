from interfaces import FlashcardDeck

def requeue_card(deck: FlashcardDeck, card_id: str, positions_later: int = 3) -> FlashcardDeck:
    # Find the card
    card = next(c for c in deck.cards if c.card_id == card_id)
    
    # Calculate target index (current_index + positions_later, but within bounds)
    target_idx = min(deck.current_index + positions_later, len(deck.cards))
    
    # Insert it
    deck.cards.insert(target_idx, card)
    
    return deck
