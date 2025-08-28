def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """
    Chunk text using sliding window approach.

    Args:
        text: Input text to chunk
        size: Maximum chunk size in characters
        overlap: Overlap between chunks in characters

    Returns:
        List of text chunks
    """
    if not text or size <= 0:
        return []

    if len(text) <= size:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + size, len(text))
        chunk = text[start:end]
        chunks.append(chunk)

        if end >= len(text):
            break

        # Move start position, accounting for overlap
        start = end - overlap
        # Ensure we don't go backwards
        if start <= 0:
            start = 1
        # Ensure we make progress
        if start >= end:
            break

    return chunks
