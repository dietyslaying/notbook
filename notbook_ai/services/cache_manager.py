import time

class CacheManager:
    def __init__(self, ttl: int):
        self._cache = {}
        self._ttl = ttl

    def get(self, key: str):
        if key in self._cache:
            data, timestamp = self._cache[key]
            if time.time() - timestamp < self._ttl:
                return data
            else:
                del self._cache[key]
        return None

    def set(self, key: str, value):
        self._cache[key] = (value, time.time())
