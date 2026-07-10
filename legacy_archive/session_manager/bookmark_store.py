import json
import os
from pydantic import BaseModel

class Bookmark(BaseModel):
    topic: str
    workspace_type: str
    screen_id: str

class BookmarkStore:
    def __init__(self, filename="bookmarks.json"):
        self.filename = filename
        self.bookmarks: dict[str, list[dict]] = self._load()
        
    def _load(self):
        if not os.path.exists(self.filename):
            return {}
        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
            
    def _save(self):
        with open(self.filename, "w", encoding="utf-8") as f:
            json.dump(self.bookmarks, f, indent=2)
            
    def add_bookmark(self, user_id: int, topic: str, workspace_type: str, screen_id: str):
        uid = str(user_id)
        if uid not in self.bookmarks:
            self.bookmarks[uid] = []
            
        # Avoid duplicates
        for b in self.bookmarks[uid]:
            if b["topic"] == topic and b["workspace_type"] == workspace_type:
                b["screen_id"] = screen_id # update latest screen
                self._save()
                return
                
        self.bookmarks[uid].append({
            "topic": topic,
            "workspace_type": workspace_type,
            "screen_id": screen_id
        })
        self._save()
        
    def get_bookmarks(self, user_id: int) -> list[Bookmark]:
        uid = str(user_id)
        raw = self.bookmarks.get(uid, [])
        return [Bookmark(**b) for b in raw]
