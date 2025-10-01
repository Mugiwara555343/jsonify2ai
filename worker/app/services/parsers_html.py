from __future__ import annotations
from typing import List
from bs4 import BeautifulSoup  # requires beautifulsoup4 and lxml


def parse_html(path: str) -> List[str]:
    """
    Parse HTML file, extracting visible text (drop scripts/styles).
    Returns a list with one big block per logical section (rough cut).
    """
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        html = f.read()
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    # normalize & split: drop empty lines, merge short runs
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    if not lines:
        return []
    # simple chunking heuristic here; the main chunker will still re-chunk downstream
    return ["\n".join(lines)]
