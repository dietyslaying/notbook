"""
tests/contracts/test_handlers_contract.py

Phase 1 - Handlers Contract Tests
All tests MUST FAIL before implementation exists.
Run: pytest tests/contracts/test_handlers_contract.py -v
"""
import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from interfaces import IntentResult, IntentType, WorkspaceType, BotState

@pytest.fixture
def mock_deps():
    return {
        "intent_engine": AsyncMock(),
        "session_manager": AsyncMock(),
        "state_machine": MagicMock(),
        "menu_workspace": MagicMock(),
        "disease_workspace": MagicMock(),
        "drug_workspace": MagicMock(),
        "renderer": MagicMock()
    }

@pytest.mark.asyncio
class TestHandlersContract:
    
    async def test_handle_message_disease_topic(self, mock_deps):
        """Test that sending 'Tell me about ADHD' routes to DiseaseWorkspace."""
        from handlers.message_handler import handle_text_message
        
        # Setup mocks
        mock_deps["intent_engine"].classify.return_value = IntentResult(
            intent_type=IntentType.TOPIC_OVERVIEW,
            topic="ADHD",
            topic_type=WorkspaceType.DISEASE,
            confidence=0.9
        )
        
        mock_session = MagicMock()
        mock_session.current_state = BotState.WORKSPACE_DISEASE_OVERVIEW
        mock_deps["session_manager"].create.return_value = mock_session
        
        # Mock telegram message
        mock_message = AsyncMock()
        mock_message.text = "Tell me about ADHD"
        mock_message.from_user.id = 123
        
        # Call handler
        await handle_text_message(mock_message, **mock_deps)
        
        # Verify intent was checked
        mock_deps["intent_engine"].classify.assert_called_once_with("Tell me about ADHD")
        # Verify session was created
        mock_deps["session_manager"].create.assert_called_once()
        # Verify disease workspace was invoked
        mock_deps["disease_workspace"].generate_screen.assert_called_once_with(topic="ADHD", screen_id="overview")
        # Verify renderer was called
        mock_deps["renderer"].render.assert_called_once()
        # Verify message was replied to
        mock_message.answer.assert_called_once()

    async def test_handle_callback_navigation(self, mock_deps):
        """Test that tapping 'Symptoms' updates the message."""
        from handlers.callback_handler import handle_callback
        
        # Mock session
        mock_session = MagicMock()
        mock_session.topic = "ADHD"
        mock_session.workspace_type = WorkspaceType.DISEASE
        mock_session.current_state = BotState.WORKSPACE_DISEASE_OVERVIEW
        mock_deps["session_manager"].get.return_value = mock_session
        
        # Mock state machine transition
        transition = MagicMock()
        transition.is_forbidden = False
        transition.next_state = BotState.WORKSPACE_DISEASE_SYMPTOMS
        mock_deps["state_machine"].transition.return_value = transition
        
        # Mock callback query
        mock_callback = AsyncMock()
        mock_callback.data = "screen:symptoms"
        mock_callback.from_user.id = 123
        mock_callback.message = AsyncMock()
        
        # Call handler
        await handle_callback(mock_callback, **mock_deps)
        
        # Verify session state pushed
        mock_deps["session_manager"].push_state.assert_called_once_with(mock_session, BotState.WORKSPACE_DISEASE_OVERVIEW)
        # Verify disease workspace was invoked for symptoms
        mock_deps["disease_workspace"].generate_screen.assert_called_once_with(topic="ADHD", screen_id="symptoms")
        # Verify message was edited in place
        mock_callback.message.edit_text.assert_called_once()
