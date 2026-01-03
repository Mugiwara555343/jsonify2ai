"""ChatGPT export parser for conversations.json files.

Parses ChatGPT export format where one file contains multiple conversations.
Each conversation becomes a separate document.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

log = logging.getLogger(__name__)


def is_chatgpt_export(data: Any, filename: str = "") -> bool:
    """Detect if data is a ChatGPT export format.

    Args:
        data: Parsed JSON data
        filename: Optional filename for quick detection

    Returns:
        True if this appears to be a ChatGPT export
    """
    # Quick check: filename
    if filename.lower() == "conversations.json":
        return True

    # Structure check: should be a list
    if not isinstance(data, list):
        return False

    if not data:
        return False

    # Check first item has ChatGPT structure
    first = data[0]
    if not isinstance(first, dict):
        return False

    # ChatGPT exports have: title, mapping, create_time/update_time
    has_mapping = "mapping" in first
    has_title = "title" in first
    has_time = "create_time" in first or "update_time" in first

    return has_mapping and (has_title or has_time)


def parse_conversation(
    conv: Dict[str, Any], source_file: str
) -> Optional[Tuple[str, str, Dict[str, Any]]]:
    """Parse a single conversation into text and metadata.

    Args:
        conv: Conversation object from ChatGPT export
        source_file: Source filename for metadata

    Returns:
        Tuple of (conversation_id, text, metadata) or None if parsing fails
    """
    try:
        # Extract conversation ID
        conversation_id = (
            conv.get("id") or conv.get("conversation_id") or str(conv.get("uuid", ""))
        )
        if not conversation_id:
            log.warning("Conversation missing ID, skipping")
            return None

        # Extract title
        title = conv.get("title") or conv.get("conversation_title") or None

        # Extract timestamps
        create_time = conv.get("create_time")
        update_time = conv.get("update_time")

        # Convert timestamps to ISO-8601 UTC
        iso_created = None
        iso_updated = None

        if create_time:
            try:
                # ChatGPT timestamps are typically Unix timestamps (seconds)
                if isinstance(create_time, (int, float)):
                    dt = datetime.fromtimestamp(create_time, tz=timezone.utc)
                    iso_created = dt.isoformat().replace("+00:00", "Z")
                elif isinstance(create_time, str):
                    # Try parsing as ISO string
                    try:
                        dt = datetime.fromisoformat(create_time.replace("Z", "+00:00"))
                        iso_created = dt.isoformat().replace("+00:00", "Z")
                    except ValueError:
                        pass
            except Exception as e:
                log.debug(f"Failed to parse create_time: {e}")

        if update_time:
            try:
                if isinstance(update_time, (int, float)):
                    dt = datetime.fromtimestamp(update_time, tz=timezone.utc)
                    iso_updated = dt.isoformat().replace("+00:00", "Z")
                elif isinstance(update_time, str):
                    try:
                        dt = datetime.fromisoformat(update_time.replace("Z", "+00:00"))
                        iso_updated = dt.isoformat().replace("+00:00", "Z")
                    except ValueError:
                        pass
            except Exception as e:
                log.debug(f"Failed to parse update_time: {e}")

        # Extract messages from mapping
        mapping = conv.get("mapping", {})
        if not isinstance(mapping, dict):
            log.warning(f"Conversation {conversation_id} has invalid mapping, skipping")
            return None

        # Collect all messages
        messages = []
        for node_id, node in mapping.items():
            if not isinstance(node, dict):
                continue

            message = node.get("message")
            if not message or not isinstance(message, dict):
                continue

            # Extract role and content
            role = (
                message.get("author", {}).get("role")
                or message.get("role")
                or "unknown"
            )
            if role == "system" and "system" not in str(message.get("content", {})):
                # Sometimes system messages are in metadata
                role = "system"

            # Extract content
            content_obj = message.get("content", {})
            content_text = ""

            if isinstance(content_obj, str):
                content_text = content_obj
            elif isinstance(content_obj, dict):
                # Check for parts array
                parts = content_obj.get("parts", [])
                if isinstance(parts, list):
                    text_parts = []
                    for part in parts:
                        if isinstance(part, str):
                            text_parts.append(part)
                        elif isinstance(part, dict):
                            # Could be text or other content type
                            if "text" in part:
                                text_parts.append(part["text"])
                            elif "type" in part and part.get("type") == "text":
                                text_parts.append(part.get("text", ""))
                    content_text = "\n".join(text_parts)
                elif "text" in content_obj:
                    content_text = content_obj["text"]
            elif isinstance(content_obj, list):
                # List of strings or objects
                text_parts = []
                for item in content_obj:
                    if isinstance(item, str):
                        text_parts.append(item)
                    elif isinstance(item, dict) and "text" in item:
                        text_parts.append(item["text"])
                content_text = "\n".join(text_parts)

            if not content_text.strip():
                continue

            # Extract timestamp
            create_time_msg = message.get("create_time") or node.get("create_time")
            timestamp_str = ""
            if create_time_msg:
                try:
                    if isinstance(create_time_msg, (int, float)):
                        dt = datetime.fromtimestamp(create_time_msg, tz=timezone.utc)
                        timestamp_str = dt.strftime("%Y-%m-%d %H:%M")
                    elif isinstance(create_time_msg, str):
                        # Try to parse and format
                        try:
                            dt = datetime.fromisoformat(
                                create_time_msg.replace("Z", "+00:00")
                            )
                            timestamp_str = dt.strftime("%Y-%m-%d %H:%M")
                        except ValueError:
                            timestamp_str = (
                                create_time_msg[:16]
                                if len(create_time_msg) >= 16
                                else ""
                            )
                except Exception:
                    pass

            messages.append(
                {
                    "role": role,
                    "content": content_text,
                    "timestamp": timestamp_str,
                    "create_time": create_time_msg,
                }
            )

        # Sort messages by create_time (or keep order if unavailable)
        try:
            messages.sort(key=lambda m: m.get("create_time") or 0)
        except Exception:
            pass  # Keep original order if sorting fails

        # Build text with timestamps and roles
        text_lines = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            timestamp = msg["timestamp"]

            if timestamp:
                text_lines.append(f"[{timestamp}] {role}: {content}")
            else:
                text_lines.append(f"{role}: {content}")

        text = "\n\n".join(text_lines)

        if not text.strip():
            log.warning(
                f"Conversation {conversation_id} has no extractable text, skipping"
            )
            return None

        # Build metadata
        metadata = {
            "source_system": "chatgpt",
            "conversation_id": conversation_id,
            "source_file": source_file,
        }

        if title:
            metadata["title"] = title
        if iso_created:
            metadata["chat_created_at"] = iso_created
        if iso_updated:
            metadata["chat_updated_at"] = iso_updated

        return (conversation_id, text, metadata)

    except Exception as e:
        log.warning(f"Failed to parse conversation: {e}", exc_info=True)
        return None


def parse_chatgpt_export(
    data: List[Dict[str, Any]], source_file: str = "conversations.json"
) -> List[Tuple[str, str, Dict[str, Any]]]:
    """Parse ChatGPT export into list of conversations.

    Args:
        data: List of conversation objects from ChatGPT export
        source_file: Source filename for metadata

    Returns:
        List of (conversation_id, text, metadata) tuples
    """
    results = []

    for conv in data:
        if not isinstance(conv, dict):
            continue

        parsed = parse_conversation(conv, source_file)
        if parsed:
            results.append(parsed)

    return results
