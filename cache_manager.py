from typing import Dict, Any, Optional

class CacheManager:
    """
    Handles caching of NDMs and Component Trees based on query/context.
    """
    def __init__(self):
        # Stubbed memory cache for now. Use Redis/Pinecone in production.
        self._cache = {}
        
    def get_cached_component_tree(self, query: str, context_hash: str) -> Optional[Dict[str, Any]]:
        key = f"{query}_{context_hash}"
        return self._cache.get(key)
        
    def set_cached_component_tree(self, query: str, context_hash: str, component_tree: Dict[str, Any]):
        key = f"{query}_{context_hash}"
        self._cache[key] = component_tree
