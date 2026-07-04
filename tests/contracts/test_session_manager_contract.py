"""
tests/contracts/test_session_manager_contract.py

Phase 1 - Session Manager Contract Tests
All tests MUST FAIL before implementation exists.
Run: pytest tests/contracts/test_session_manager_contract.py -v -W ignore::DeprecationWarning
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from interfaces import (
    ISessionManager, WorkspaceSession, WorkspaceType, UserMode, BotState, KnowledgeTree
)

@pytest.fixture
async def session_manager():
    """
    Provides the SessionManager implementation under test.
    Fails until implemented.
    """
    from session_manager.manager import SessionManager
    from session_manager.store import InMemoryStore  # We use memory store for fast unit tests
    
    store = InMemoryStore()
    manager = SessionManager(store)
    return manager

@pytest.mark.asyncio
class TestSessionManagerContract:
    
    async def test_satisfies_protocol(self, session_manager):
        assert isinstance(session_manager, ISessionManager)

    async def test_create_session(self, session_manager):
        user_id = 123
        session = await session_manager.create(
            user_id=user_id,
            topic="ADHD",
            workspace_type=WorkspaceType.DISEASE,
            user_mode=UserMode.STUDENT
        )
        assert session.user_id == user_id
        assert session.topic == "ADHD"
        assert session.workspace_type == WorkspaceType.DISEASE
        assert session.user_mode == UserMode.STUDENT
        assert session.current_state == BotState.IDLE
        assert isinstance(session.screen_history, list)
        assert len(session.screen_history) == 0

        # Verify it can be retrieved
        fetched = await session_manager.get(user_id)
        assert fetched is not None
        assert fetched.session_id == session.session_id

    async def test_get_nonexistent_returns_none(self, session_manager):
        fetched = await session_manager.get(999)
        assert fetched is None

    async def test_update_session(self, session_manager):
        session = await session_manager.create(111, "Asthma", WorkspaceType.DISEASE, UserMode.STUDENT)
        session.current_state = BotState.WORKSPACE_DISEASE_OVERVIEW
        await session_manager.update(session)
        
        fetched = await session_manager.get(111)
        assert fetched.current_state == BotState.WORKSPACE_DISEASE_OVERVIEW

    async def test_push_state(self, session_manager):
        session = await session_manager.create(222, "Asthma", WorkspaceType.DISEASE, UserMode.STUDENT)
        await session_manager.push_state(session, BotState.WORKSPACE_DISEASE_OVERVIEW)
        
        fetched = await session_manager.get(222)
        assert len(fetched.screen_history) == 1
        assert fetched.screen_history[0] == BotState.WORKSPACE_DISEASE_OVERVIEW

    async def test_push_state_enforces_max_depth_of_10(self, session_manager):
        session = await session_manager.create(333, "Asthma", WorkspaceType.DISEASE, UserMode.STUDENT)
        
        for i in range(15):
            # We push 15 times, history should cap at 10
            await session_manager.push_state(session, BotState.WORKSPACE_DISEASE_OVERVIEW)
            
        fetched = await session_manager.get(333)
        assert len(fetched.screen_history) == 10

    async def test_pop_state(self, session_manager):
        session = await session_manager.create(444, "Asthma", WorkspaceType.DISEASE, UserMode.STUDENT)
        await session_manager.push_state(session, BotState.WORKSPACE_DISEASE_OVERVIEW)
        await session_manager.push_state(session, BotState.WORKSPACE_DISEASE_SYMPTOMS)
        
        state1 = await session_manager.pop_state(session)
        assert state1 == BotState.WORKSPACE_DISEASE_SYMPTOMS
        
        state2 = await session_manager.pop_state(session)
        assert state2 == BotState.WORKSPACE_DISEASE_OVERVIEW
        
        # Empty history
        state3 = await session_manager.pop_state(session)
        assert state3 is None

    async def test_peek_state(self, session_manager):
        session = await session_manager.create(555, "Asthma", WorkspaceType.DISEASE, UserMode.STUDENT)
        await session_manager.push_state(session, BotState.WORKSPACE_DISEASE_OVERVIEW)
        
        peeked = await session_manager.peek_state(session)
        assert peeked == BotState.WORKSPACE_DISEASE_OVERVIEW
        
        # Ensure it was not removed
        fetched = await session_manager.get(555)
        assert len(fetched.screen_history) == 1

    async def test_expire_clears_knowledge_tree_but_retains_metadata(self, session_manager):
        session = await session_manager.create(666, "Asthma", WorkspaceType.DISEASE, UserMode.STUDENT)
        session.metadata = {"some": "data"}
        session.knowledge_tree = KnowledgeTree(topic="Asthma", workspace_type=WorkspaceType.DISEASE, chunks=[])
        await session_manager.update(session)
        
        await session_manager.expire(666)
        
        fetched = await session_manager.get(666)
        assert fetched is not None
        assert fetched.metadata == {"some": "data"}
        assert fetched.knowledge_tree is None
