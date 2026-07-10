import time
from typing import Optional
from interfaces import (
    ISessionManager, WorkspaceSession, BotState, 
    WorkspaceType, UserMode
)
from session_manager.store import ISessionStore

class SessionManager(ISessionManager):
    def __init__(self, store: ISessionStore):
        self.store = store
        
    def _get_session_id(self, user_id: int) -> str:
        return f"notbook:session:{user_id}"

    async def create(
        self,
        user_id: int,
        topic: str,
        workspace_type: WorkspaceType,
        user_mode: UserMode,
    ) -> WorkspaceSession:
        session = WorkspaceSession(
            session_id=self._get_session_id(user_id),
            user_id=user_id,
            topic=topic,
            workspace_type=workspace_type,
            user_mode=user_mode,
            current_state=BotState.IDLE,
            screen_history=[],
            last_active=time.time()
        )
        await self.store.set(session.session_id, session)
        return session

    async def get(self, user_id: int) -> Optional[WorkspaceSession]:
        session_id = self._get_session_id(user_id)
        session = await self.store.get(session_id)
        if session:
            session.last_active = time.time()
            await self.store.set(session_id, session)
        return session

    async def update(self, session: WorkspaceSession) -> None:
        session.last_active = time.time()
        await self.store.set(session.session_id, session)

    async def push_state(self, session: WorkspaceSession, state: BotState) -> None:
        session.screen_history.append(state)
        # Enforce max depth of 10
        if len(session.screen_history) > 10:
            session.screen_history = session.screen_history[-10:]
        await self.update(session)

    async def pop_state(self, session: WorkspaceSession) -> Optional[BotState]:
        if not session.screen_history:
            return None
        state = session.screen_history.pop()
        await self.update(session)
        return state

    async def peek_state(self, session: WorkspaceSession) -> Optional[BotState]:
        if not session.screen_history:
            return None
        return session.screen_history[-1]

    async def expire(self, user_id: int) -> None:
        session = await self.get(user_id)
        if session:
            session.knowledge_tree = None
            await self.update(session)
