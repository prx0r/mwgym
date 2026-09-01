Build a Python function `deep_merge(base: dict, override: dict) -> dict` that deeply merges two configuration dicts.

Requirements:
- Function name: deep_merge
- Returns new dict (does not mutate inputs)
- Dict values merged recursively
- Override values win on conflict
- List values: override replaces (not appends)
- Handle None values
- No external imports

Example:
```python
base = {"db": {"host": "localhost", "port": 5432}, "debug": False}
override = {"db": {"port": 5433, "name": "prod"}, "debug": True}
result = deep_merge(base, override)
assert result == {"db": {"host": "localhost", "port": 5433, "name": "prod"}, "debug": True}
```

Write to config_merge.py.