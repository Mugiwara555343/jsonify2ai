#!/usr/bin/env python3
"""
note_to_json.parser

Parses markdown/text or JSON into a structured JSON schema. Supports:
- Markdown/text parsing with inline metadata
- JSON passthrough/normalization
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from jsonschema import validate, ValidationError
from .utils import read_text_safely, decode_bytes

# === SCHEMA ===
SCHEMA = {
    "type": "object",
    "required": ["title", "timestamp", "raw_text", "plain_text"],
    "properties": {
        "title": {"type": "string"},
        "timestamp": {"type": "string", "format": "date-time"},
        "raw_text": {"type": "string"},
        "plain_text": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "headers": {"type": "array", "items": {"type": "string"}},
        "date": {"type": "string"},
        "tone": {"type": "string"},
        "summary": {"type": "string"},
        "reflections": {"type": "array", "items": {"type": "string"}},
    },
    "additionalProperties": False,
}


class ParsingError(ValueError):
    """Custom exception for parsing errors with context."""

    def __init__(
        self,
        message: str,
        error_type: str = "parsing_error",
        context: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.error_type = error_type
        self.context = context or {}


def _now_iso() -> str:
    """Get current timestamp in ISO format."""
    return datetime.utcnow().isoformat() + "Z"


def _normalize_from_json(
    obj, *, raw_text: str, filename_hint: str | None = None
) -> dict:
    # If it already matches our schema, return as-is
    if isinstance(obj, dict) and {
        "title",
        "timestamp",
        "raw_text",
        "plain_text",
        "tags",
        "headers",
        "reflections",
    } <= set(obj.keys()):
        return obj
    # Otherwise wrap primitive/array into our schema
    title = (filename_hint or "json").split(".")[0]
    if not isinstance(obj, (dict, list, str, int, float, bool)) and obj is not None:
        obj = str(obj)
    plain = json.dumps(obj, ensure_ascii=False) if not isinstance(obj, str) else obj

    # For objects, use the title field if present, otherwise use filename_hint
    if isinstance(obj, dict) and "title" in obj:
        title = str(obj["title"])
    elif isinstance(obj, (list, dict)):
        title = title
    else:
        # For primitives, use filename_hint as title, not the primitive value
        title = title

    # For objects, preserve tags if they exist and are valid
    tags = []
    if isinstance(obj, dict) and "tags" in obj and isinstance(obj["tags"], list):
        # Normalize tags: strip hash prefixes and convert to strings
        tags = []
        for t in obj["tags"]:
            if isinstance(t, (str, int, float, bool)):
                if isinstance(t, bool):
                    tag_str = "true" if t else "false"
                else:
                    tag_str = str(t)
                # Strip hash prefix if present
                if tag_str.startswith("#"):
                    tag_str = tag_str[1:]
                tags.append(tag_str)

    return {
        "title": title,
        "timestamp": _now_iso(),
        "raw_text": raw_text,
        "plain_text": plain,
        "tags": tags,
        "headers": [],
        "reflections": [],
    }


def validate_parsed(data: dict) -> None:
    """Validate parsed data against schema with detailed error reporting."""
    try:
        validate(instance=data, schema=SCHEMA)
    except ValidationError as e:
        # Provide more helpful error messages with actionable advice
        field_path = " -> ".join(str(p) for p in e.path) if e.path else "root"

        # Categorize validation errors for better handling
        if e.validator == "required":
            error_type = "missing_required_field"
            # Extract the field name from the error message safely
            field_name = "required field"
            if "'" in e.message:
                parts = e.message.split("'")
                if len(parts) >= 2:
                    field_name = parts[1]
            advice = f"Add the missing required field '{field_name}'"
        elif e.validator == "type":
            error_type = "wrong_field_type"
            expected_type = e.validator_value
            actual_value = type(e.instance).__name__
            advice = f"Change '{field_path}' from {actual_value} to {expected_type}"
        elif e.validator == "format":
            error_type = "invalid_format"
            advice = f"Ensure '{field_path}' follows the required format: {e.validator_value}"
        else:
            error_type = "validation_error"
            advice = (
                f"Check the value of '{field_path}' against the schema requirements"
            )

        raise ParsingError(
            f"Schema validation failed at '{field_path}': {e.message}",
            error_type=error_type,
            context={
                "field": field_path,
                "value": e.instance,
                "schema_requirement": e.validator_value,
                "advice": advice,
            },
        )


def sanitize_text(text: str, max_length: int = 10000) -> str:
    """Sanitize text content to prevent issues."""
    if not isinstance(text, str):
        text = str(text)

    # Remove null bytes and other problematic characters
    text = text.replace("\x00", "")

    # Truncate if too long
    if len(text) > max_length:
        text = text[:max_length] + "... [truncated]"

    return text


def _parse_text(text: str, *, filename_hint: Optional[str] = None) -> dict:
    """
    Parse markdown/plain text into structured JSON.

    Args:
        text: Full file content
        filename_hint: Used to derive a reasonable title when headers are absent

    Returns:
        dict: Parsed data with metadata, content, and reflections

    Raises:
        ParsingError: If parsing fails or validation fails
    """
    try:
        # Sanitize input text
        text = sanitize_text(text)

        if not text.strip():
            raise ParsingError(
                "Empty or whitespace-only input", error_type="empty_input"
            )

        lines = text.splitlines()

        raw_text = text.strip()
        plain_text = raw_text.replace("\n", " ")
        title = filename_hint or "stdin"
        tags, headers, reflections = [], [], []
        date_str, tone_str, summary_text = None, None, None
        in_summary = in_reflect = False

        for line in lines:
            line = line.rstrip("\r\n")  # Handle different line endings

            if line.startswith("# "):
                h = line.lstrip("# ").strip()
                if h:  # Only add non-empty headers
                    headers.append(h)
                    # Use the first H1 as title
                    if title == (filename_hint or "stdin"):
                        title = h

            if line.startswith("**Date:**"):
                date_str = line.split("**Date:**", 1)[1].strip()
            if line.startswith("**Tags:**"):
                vals = line.split("**Tags:**", 1)[1].strip()
                tags = [
                    t.strip().lstrip("#") for t in vals.split() if t.startswith("#")
                ]
            if line.startswith("**Tone:**"):
                tone_str = line.split("**Tone:**", 1)[1].strip()

            if line.lower().startswith("**summary:**"):
                in_summary = True
                summary_text = ""
                continue
            if in_summary:
                if line.strip() == "" or line.strip().startswith("---"):
                    in_summary = False
                else:
                    summary_text += line.strip() + " "

            if line.lower().startswith("**core reflections:**"):
                in_reflect = True
                continue
            if in_reflect:
                if not line.startswith("-"):
                    in_reflect = False
                else:
                    reflection = line.lstrip("- ").strip()
                    if reflection:  # Only add non-empty reflections
                        reflections.append(reflection)

        # If no headers were found and we still have the default title,
        # use the first non-empty line as a fallback title
        if headers == [] and title == (filename_hint or "stdin"):
            for line in lines:
                if line.strip():
                    title = line.strip()
                    break

        # Ensure title is not empty
        if not title or title.strip() == "":
            title = filename_hint or "untitled"

        # Parse date with better error handling
        if date_str:
            try:
                # Try various date formats
                for fmt in ["%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]:
                    try:
                        dt = datetime.strptime(date_str, fmt)
                        timestamp = dt.isoformat() + "Z"
                        break
                    except ValueError:
                        continue
                else:
                    # If no format worked, use current time
                    timestamp = datetime.utcnow().isoformat() + "Z"
            except Exception:
                timestamp = datetime.utcnow().isoformat() + "Z"
        else:
            timestamp = datetime.utcnow().isoformat() + "Z"

        parsed = {
            "title": title,
            "timestamp": timestamp,
            "raw_text": raw_text,
            "plain_text": plain_text,
            "tags": tags,
            "headers": headers,
            "date": date_str,
            "tone": tone_str,
            "summary": summary_text.strip() if summary_text else None,
            "reflections": reflections,
        }

        # Remove None values and validate
        parsed = {k: v for k, v in parsed.items() if v is not None}

        try:
            validate_parsed(parsed)
        except ParsingError:
            # If validation fails, try to fix common issues
            parsed = _fix_common_validation_issues(parsed)
            validate_parsed(parsed)

        return parsed

    except Exception as e:
        if isinstance(e, ParsingError):
            raise
        raise ParsingError(
            f"Failed to parse text: {str(e)}", error_type="parsing_error"
        )


def _fix_common_validation_issues(data: Dict[str, Any]) -> Dict[str, Any]:
    """Fix common validation issues in parsed data."""
    fixed = data.copy()

    # Ensure required fields exist and are not None
    if "title" not in fixed or not fixed["title"] or fixed["title"] is None:
        fixed["title"] = "untitled"

    if "timestamp" not in fixed or fixed["timestamp"] is None:
        fixed["timestamp"] = datetime.utcnow().isoformat() + "Z"

    if "raw_text" not in fixed or fixed["raw_text"] is None:
        fixed["raw_text"] = ""

    if "plain_text" not in fixed or fixed["plain_text"] is None:
        fixed["plain_text"] = ""

    # Ensure arrays are actually arrays
    for field in ["tags", "headers", "reflections"]:
        if field in fixed and not isinstance(fixed[field], list):
            fixed[field] = []

    # Ensure strings are actually strings (not None)
    for field in [
        "title",
        "timestamp",
        "raw_text",
        "plain_text",
        "date",
        "tone",
        "summary",
    ]:
        if field in fixed and fixed[field] is not None:
            if not isinstance(fixed[field], str):
                fixed[field] = str(fixed[field])
        elif field in ["title", "timestamp", "raw_text", "plain_text"]:
            # These are required fields, ensure they have default values
            if field == "title":
                fixed[field] = "untitled"
            elif field == "timestamp":
                fixed[field] = datetime.utcnow().isoformat() + "Z"
            elif field in ["raw_text", "plain_text"]:
                fixed[field] = ""

    return fixed


def read_input(source, input_format: str, *, filename_hint: str | None = None) -> dict:
    # 1) materialize text
    if hasattr(source, "read"):
        raw = source.read()
        if isinstance(raw, str):
            text = raw
        else:
            # Better: if bytes-like, pass to decode_bytes(raw)
            text = decode_bytes(raw)
    elif isinstance(source, (bytes, bytearray)):
        text = decode_bytes(bytes(source))
    else:
        # path or text
        if isinstance(source, str) and os.path.exists(source):
            text = read_text_safely(source)
        else:
            text = str(source)

    # 2) decide format
    effective = input_format
    if effective == "auto":
        s = text.lstrip()
        effective = "json" if s.startswith("{") or s.startswith("[") else "txt"

    # 3) parse
    if effective in ("md", "txt"):
        return _parse_text(text, filename_hint=filename_hint)  # your existing path
    if effective == "json":
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            raise ParsingError(
                "Invalid JSON input. If this is Markdown or text, use `--input-format md|txt`.",
                error_type="json_decode_error",
            ) from e
        return _normalize_from_json(obj, raw_text=text, filename_hint=filename_hint)

    raise ValueError(f"Unsupported input format: {input_format}")


def parse_file(md_path: Path) -> dict:
    """
    Parse a markdown file into structured JSON.

    Raises:
        ParsingError: If parsing fails
    """
    try:
        text = read_text_safely(md_path)
        return _parse_text(text, filename_hint=md_path.stem)
    except Exception as e:
        if isinstance(e, ParsingError):
            raise
        raise ParsingError(
            f"Failed to parse file {md_path}: {str(e)}", error_type="file_parsing_error"
        )


# Backward compatibility
def parse_md_file(md_path: Path) -> dict:
    """Alias for parse_file for backward compatibility"""
    return parse_file(md_path)
