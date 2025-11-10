# Parser Guide

Parsers live in `worker/app/services/parse_*.py` and expose **one function**:

```python
def extract_text_from_<ext>(path: str) -> str:
    ...
