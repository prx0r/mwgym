Build a Python class `LRUCache` with time-to-live expiration.

Requirements:
- Class name: LRUCache
- Constructor: __init__(self, capacity: int, ttl_seconds: float)
- Method: get(self, key: str) -> Any | None — returns value or None if expired/missing
- Method: put(self, key: str, value: Any) -> None — inserts/updates, evicts LRU if full
- Method: size(self) -> int — returns current number of entries
- LRU eviction when capacity exceeded
- TTL expiration on get()
- No external imports (use collections.OrderedDict + time)

Write to lru_cache.py.