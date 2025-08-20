import json
from typing import Any, List

def _flatten(obj: Any, prefix: str = "", out: List[str] | None = None) -> List[str]:
    if out is None:
        out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            _flatten(v, f"{prefix}.{k}" if prefix else str(k), out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _flatten(v, f"{prefix}[{i}]", out)
    else:
        out.append(f"{prefix}: {obj}")
    return out

def extract_text_from_json(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return "\n".join(_flatten(data))

def extract_text_from_jsonl(path: str, max_lines: int = 10000) -> str:
    out: List[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            s = line.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
            except json.JSONDecodeError:
                continue
            out.extend(_flatten(obj, prefix=f"$[{i}]"))
            if i >= max_lines:
                break
    return "\n".join(out)
