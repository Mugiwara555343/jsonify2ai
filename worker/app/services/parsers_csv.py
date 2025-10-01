from __future__ import annotations
from typing import List
import csv


def parse_csv(path: str, max_cols: int = 50, max_len: int = 2000) -> List[str]:
    """
    Parse CSV to a list of text chunks (one per row), capped to avoid explosions.
    - Truncates very wide rows at max_cols
    - Joins cells with " | "
    - Truncates each row string at max_len chars (hard cap)
    """
    out: List[str] = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            row = row[:max_cols]
            s = " | ".join(cell.strip() for cell in row if cell is not None)
            if not s:
                continue
            if len(s) > max_len:
                s = s[:max_len]
            out.append(s)
    return out
