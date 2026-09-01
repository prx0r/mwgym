Build a Python function `json_diff(a: dict, b: dict) -> dict` that computes a deep diff between two JSON-serializable objects.

Requirements:
- Function name: json_diff
- Returns a dict with keys being dot-separated paths to changed values
- Each entry has {"old": ..., "new": ...} for modified values
- Entries with {"old": ..., "new": null} for deleted values
- Entries with {"old": null, "new": ...} for added values
- Handle nested dicts and lists
- No external imports

Example:
```python
result = json_diff({"a": 1, "b": 2}, {"a": 1, "b": 3, "c": 4})
assert result == {"b": {"old": 2, "new": 3}, "c": {"old": null, "new": 4}}
```

Write to json_diff.py.