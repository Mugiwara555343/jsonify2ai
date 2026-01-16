"""Generic chat transcript parser for .txt/.md files.

Detects and parses chat transcripts with patterns like:
- User: / Assistant: / System: prefixes
- [YYYY-MM-DD ...] user: / assistant: formats
- role: user / role: assistant blocks

Each detected transcript becomes a chat document with kind="chat".
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Dict, Any, List, Tuple

log = logging.getLogger(__name__)

# Detection patterns with weights
# Higher weight = stronger signal of being a transcript

# Pattern: "User:" / "Assistant:" / "System:" at line start (case-insensitive)
ROLE_PREFIX_PATTERN = re.compile(
    r"^(user|assistant|system|human|ai|bot|agent)\s*:\s*",
    re.IGNORECASE | re.MULTILINE,
)

# Pattern: "[YYYY-MM-DD HH:MM] role:" or "[YYYY-MM-DD] role:"
TIMESTAMPED_ROLE_PATTERN = re.compile(
    r"^\[?\d{4}-\d{2}-\d{2}[T\s]?\d{0,2}:?\d{0,2}:?\d{0,2}[^\]]*\]?\s*(user|assistant|system|human|ai|bot|agent)\s*:\s*",
    re.IGNORECASE | re.MULTILINE,
)

# Pattern: "role: user" / "role: assistant" (JSON-like blocks)
JSON_ROLE_PATTERN = re.compile(
    r'["\']?role["\']?\s*:\s*["\']?(user|assistant|system|human|ai|bot|agent)["\']?',
    re.IGNORECASE,
)

# Pattern: "**User:**" or "**Assistant:**" (Markdown bold roles)
MARKDOWN_ROLE_PATTERN = re.compile(
    r"^\*\*(user|assistant|system|human|ai|bot|agent)\*\*\s*:\s*",
    re.IGNORECASE | re.MULTILINE,
)

# Minimum threshold for transcript detection
DETECTION_THRESHOLD = 0.85


def detect_transcript(text: str, filename: str = "") -> Tuple[bool, float]:
    """Detect if text is a chat transcript with confidence score.

    Args:
        text: The text content to analyze
        filename: Optional filename for additional hints

    Returns:
        Tuple of (is_transcript, confidence) where confidence is 0.0-1.0
    """
    if not text or len(text.strip()) < 20:
        return False, 0.0

    # Filename hints (boost confidence if filename suggests chat/transcript)
    filename_boost = 0.0
    filename_lower = filename.lower()
    if any(
        hint in filename_lower
        for hint in ["chat", "transcript", "conversation", "dialog", "dialogue"]
    ):
        filename_boost = 0.15

    # Count pattern matches
    lines = text.split("\n")
    total_lines = len([line for line in lines if line.strip()])
    if total_lines == 0:
        return False, 0.0

    # Count different pattern types
    role_prefix_matches = len(ROLE_PREFIX_PATTERN.findall(text))
    timestamped_matches = len(TIMESTAMPED_ROLE_PATTERN.findall(text))
    json_role_matches = len(JSON_ROLE_PATTERN.findall(text))
    markdown_role_matches = len(MARKDOWN_ROLE_PATTERN.findall(text))

    # Calculate weighted score
    # Timestamped patterns are strongest signal
    # Role prefix patterns are good signal
    # JSON-like patterns could be false positives (actual JSON), so lower weight
    weighted_matches = (
        timestamped_matches * 1.5
        + role_prefix_matches * 1.2
        + markdown_role_matches * 1.2
        + json_role_matches * 0.5
    )

    # Need at least 2 role transitions to be a conversation
    unique_roles_found = set()
    for pattern in [
        ROLE_PREFIX_PATTERN,
        TIMESTAMPED_ROLE_PATTERN,
        MARKDOWN_ROLE_PATTERN,
    ]:
        for match in pattern.finditer(text):
            role = match.group(1).lower()
            # Normalize role names
            if role in ("human", "user"):
                unique_roles_found.add("user")
            elif role in ("assistant", "ai", "bot", "agent"):
                unique_roles_found.add("assistant")
            elif role == "system":
                unique_roles_found.add("system")

    # Must have at least 2 different roles for it to be a conversation
    if len(unique_roles_found) < 2:
        # Single role doesn't make a conversation (unless it's a log)
        weighted_matches *= 0.3

    # Calculate base confidence
    # A good transcript should have role markers roughly every few lines
    expected_markers = max(2, total_lines / 10)  # Expect at least 1 marker per 10 lines
    ratio = min(weighted_matches / expected_markers, 2.0)  # Cap at 2x expected

    # Base confidence from pattern density
    base_confidence = min(ratio * 0.5, 0.95)

    # Apply filename boost
    confidence = min(base_confidence + filename_boost, 0.99)

    # Require minimum number of matches to avoid false positives
    if weighted_matches < 2:
        confidence = min(confidence, 0.5)

    # Strong signal: multiple timestamped role patterns
    if timestamped_matches >= 3:
        confidence = max(confidence, 0.9)

    # Strong signal: multiple role prefix patterns with alternation
    if role_prefix_matches >= 4 and len(unique_roles_found) >= 2:
        confidence = max(confidence, 0.88)

    is_transcript = confidence >= DETECTION_THRESHOLD
    return is_transcript, round(confidence, 3)


def _extract_messages(text: str) -> List[Dict[str, Any]]:
    """Extract individual messages from transcript text.

    Returns list of dicts with 'role', 'content', and optional 'timestamp'.
    """
    messages = []

    # Try timestamped pattern first
    timestamped_parts = TIMESTAMPED_ROLE_PATTERN.split(text)
    if len(timestamped_parts) > 2:
        # Pattern splits into [before, role1, content1, role2, content2, ...]
        # But we need to handle the timestamps too
        pass

    # Split by role prefix patterns
    # This regex captures the role and splits around it
    split_pattern = re.compile(
        r"(?:^|\n)(?:\[?\d{4}-\d{2}-\d{2}[T\s]?\d{0,2}:?\d{0,2}:?\d{0,2}[^\]]*\]?\s*)?"
        r"(?:\*\*)?(user|assistant|system|human|ai|bot|agent)(?:\*\*)?\s*:\s*",
        re.IGNORECASE,
    )

    parts = split_pattern.split(text)

    # parts[0] is text before first role marker (usually empty or preamble)
    # parts[1] is first role, parts[2] is first content, etc.
    if len(parts) < 3:
        # Couldn't split properly, return single message
        return [{"role": "unknown", "content": text.strip()}]

    # Skip preamble (parts[0])
    for i in range(1, len(parts), 2):
        if i + 1 < len(parts):
            role_raw = parts[i].lower().strip()
            content = parts[i + 1].strip()

            # Normalize role
            if role_raw in ("human", "user"):
                role = "user"
            elif role_raw in ("assistant", "ai", "bot", "agent"):
                role = "assistant"
            elif role_raw == "system":
                role = "system"
            else:
                role = role_raw

            if content:
                messages.append({"role": role, "content": content})

    return messages


def _generate_thread_id(text: str, index: int = 0) -> str:
    """Generate deterministic thread ID from content."""
    # Use SHA1 of first 1000 chars + index for determinism
    content_sig = hashlib.sha1(
        text[:1000].encode("utf-8", errors="replace")
    ).hexdigest()[:12]
    return f"{content_sig}_{index}"


def _derive_title(filename: str, messages: List[Dict[str, Any]]) -> str:
    """Derive title from filename and first meaningful message."""
    # Start with filename (without extension)
    base_name = filename.rsplit(".", 1)[0] if "." in filename else filename
    base_name = base_name.replace("_", " ").replace("-", " ").strip()

    # Find first user message for context
    first_user_msg = None
    for msg in messages:
        if msg.get("role") == "user" and msg.get("content"):
            first_user_msg = msg["content"][:50].strip()
            break

    if first_user_msg:
        # Truncate if too long
        if len(first_user_msg) > 40:
            first_user_msg = first_user_msg[:40] + "..."
        return f"{base_name}: {first_user_msg}"

    return base_name if base_name else "Chat Transcript"


def parse_transcript(
    text: str, filename: str = ""
) -> List[Tuple[str, str, Dict[str, Any]]]:
    """Parse a chat transcript into documents.

    Args:
        text: The transcript text content
        filename: Source filename for metadata

    Returns:
        List of (document_id, formatted_text, metadata) tuples.
        For simple transcripts, returns a single document.
        For multi-conversation files, may return multiple documents.
    """
    if not text.strip():
        return []

    # Generate file signature for deterministic IDs
    file_sig = hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()[:16]

    # Extract messages
    messages = _extract_messages(text)
    if not messages:
        return []

    # For now, treat entire file as one conversation
    # Future: could detect conversation boundaries (long gaps, explicit separators)
    thread_id = _generate_thread_id(text, 0)
    document_id = f"transcript:{file_sig}:{thread_id}"

    # Format messages for output (same format as ChatGPT parser)
    text_lines = []
    ROLE_LABEL = {"user": "User", "assistant": "Assistant", "system": "System"}
    for msg in messages:
        role = msg["role"]
        label = ROLE_LABEL.get(str(role).lower(), str(role).title())
        content = msg["content"]
        timestamp = msg.get("timestamp", "")
        if timestamp:
            text_lines.append(f"[{timestamp}] {label}: {content}")
        else:
            text_lines.append(f"{label}: {content}")

    formatted_text = "\n\n".join(text_lines)

    # Derive title
    title = _derive_title(filename, messages)

    # Build metadata
    metadata = {
        "source_system": "transcript",
        "doc_type": "chat",
        "detected_as": "transcript",
        "title": title,
        "logical_path": (
            f"transcript/{filename}/{thread_id}"
            if filename
            else f"transcript/{thread_id}"
        ),
        "source_file": filename,
        "message_count": len(messages),
    }

    return [(document_id, formatted_text, metadata)]


__all__ = ["detect_transcript", "parse_transcript", "DETECTION_THRESHOLD"]
