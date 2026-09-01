Build a Python function `parse_markdown_table(text: str) -> list[dict]` that parses a markdown table into a list of dictionaries.

Requirements:
- Function name: parse_markdown_table
- Input: markdown table as string
- Output: list of dicts, one per row, keys from header row
- Handle alignment markers (---, :---:, :---)
- Handle extra whitespace
- Skip separator row
- No external imports

Example:
```python
table = """| Name | Age |
|------|-----|
| Alice | 30 |
| Bob | 25 |"""
result = parse_markdown_table(table)
assert result == [{"Name": "Alice", "Age": "30"}, {"Name": "Bob", "Age": "25"}]
```

Write to md_table.py.