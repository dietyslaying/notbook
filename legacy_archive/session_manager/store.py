from typing import Protocol, Optional
from interfaces import WorkspaceSession

class ISessionStore(Protocol):
    async def get(self, session_id: str) -> Optional[WorkspaceSession]: ...
    async def set(self, session_id: str, session: WorkspaceSession) -> None: ...
    async def delete(self, session_id: str) -> None: ...

class InMemoryStore:
    def __init__(self):
        self._store: dict[str, WorkspaceSession] = {}

    async def get(self, session_id: str) -> Optional[WorkspaceSession]:
        return self._store.get(session_id)

    async def set(self, session_id: str, session: WorkspaceSession) -> None:
        self._store[session_id] = session

    async def delete(self, session_id: str) -> None:
        self._store.pop(session_id, None)
