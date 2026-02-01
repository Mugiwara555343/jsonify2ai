"""
Tests for stdin input modes.
"""

import io
import json
import pytest
from note_to_json.parser import read_input
from note_to_json.utils import read_stdin_safely
from ._helpers import normalize_text, message_startswith


class TestStdinModes:
    """Test stdin input handling for various formats and encodings."""

    def test_stdin_markdown_utf8(self):
        """Test markdown input from stdin with UTF-8 encoding."""
        content = "# Stdin Test\n\nContent from stdin with émojis 🎉"
        stdin_buffer = io.BytesIO(content.encode("utf-8"))

        # Test encoding utility
        text = read_stdin_safely(stdin_buffer)
        # Use normalize_text for cross-platform stability
        assert normalize_text(text) == normalize_text(content)

        # Test full parsing
        parsed = read_input(text, "auto", filename_hint="stdin")
        assert parsed["title"] == "Stdin Test"
        assert "émojis" in parsed["raw_text"]
        assert "🎉" in parsed["raw_text"]
        # plain_text should also contain the normalized content
        assert "émojis" in parsed["plain_text"]
        assert "🎉" in parsed["plain_text"]

    def test_stdin_markdown_utf8_bom(self):
        """Test markdown input from stdin with UTF-8 BOM."""
        content = "# BOM Stdin Test\n\nContent with BOM"
        stdin_buffer = io.BytesIO(b"\xef\xbb\xbf" + content.encode("utf-8"))

        text = read_stdin_safely(stdin_buffer)
        # Use normalize_text for cross-platform stability
        assert normalize_text(text) == normalize_text(content)  # BOM should be stripped

        parsed = read_input(text, "auto", filename_hint="test")
        assert parsed["title"] == "BOM Stdin Test"

    def test_stdin_markdown_utf16_le(self):
        """Test markdown input from stdin with UTF-16 LE."""
        content = "# UTF-16 Stdin Test\n\nContent in UTF-16 LE"
        stdin_buffer = io.BytesIO(content.encode("utf-16-le"))

        text = read_stdin_safely(stdin_buffer)
        # Use normalize_text for cross-platform stability
        assert normalize_text(text) == normalize_text(content)

        parsed = read_input(text, "auto", filename_hint="stdin")
        assert parsed["title"] == "UTF-16 Stdin Test"

    def test_stdin_text_format(self):
        """Test text input from stdin with explicit format."""
        content = "Plain text content\n\nNo markdown formatting"
        stdin_buffer = io.BytesIO(content.encode("utf-8"))

        text = read_stdin_safely(stdin_buffer)
        parsed = read_input(text, "txt", filename_hint="stdin")

        assert parsed["title"] == "Plain text content"
        # Use normalize_text for cross-platform stability
        assert normalize_text(parsed["raw_text"]) == normalize_text(content)
        assert normalize_text(parsed["plain_text"]) == normalize_text(
            content.replace("\n", " ")
        )

    def test_stdin_json_format(self):
        """Test JSON input from stdin."""
        json_data = {"title": "JSON Input", "content": "JSON content"}
        content = json.dumps(json_data)
        stdin_buffer = io.BytesIO(content.encode("utf-8"))

        text = read_stdin_safely(stdin_buffer)
        parsed = read_input(text, "json", filename_hint="stdin")

        assert parsed["title"] == "JSON Input"
        assert "JSON content" in parsed["raw_text"]
        assert "JSON content" in parsed["plain_text"]

    def test_stdin_json_utf16(self):
        """Test JSON input from stdin with UTF-16 encoding."""
        json_data = {"title": "UTF-16 JSON", "content": "Content in UTF-16"}
        content = json.dumps(json_data)
        stdin_buffer = io.BytesIO(content.encode("utf-16-le"))

        text = read_stdin_safely(stdin_buffer)
        parsed = read_input(text, "json", filename_hint="stdin")

        assert parsed["title"] == "UTF-16 JSON"
        assert "Content in UTF-16" in parsed["raw_text"]
        assert "Content in UTF-16" in parsed["plain_text"]

    def test_stdin_invalid_encoding_fails_gracefully(self):
        """Test that invalid stdin encoding fails with clear error message."""
        # Create stdin with bytes that will pass decoding but fail validation
        # Use bytes with a high ratio of null bytes to trigger validation failure
        invalid_bytes = (
            b"Valid text" + b"\x00" * 20
        )  # 20 null bytes out of 30 total = 66% null ratio
        stdin_buffer = io.BytesIO(invalid_bytes)

        with pytest.raises(ValueError) as exc_info:
            read_stdin_safely(stdin_buffer)

        error_msg = str(exc_info.value)
        # Use message_startswith for error message checking
        assert message_startswith(error_msg, "Decoding error")
        assert "try saving as UTF-8" in error_msg

    def test_stdin_invalid_json_fails_gracefully(self):
        """Test that invalid JSON from stdin fails with clear error message."""
        invalid_json = "{ invalid json content"
        stdin_buffer = io.BytesIO(invalid_json.encode("utf-8"))

        text = read_stdin_safely(stdin_buffer)

        with pytest.raises(ValueError) as exc_info:
            read_input(text, "json", filename_hint="stdin")

        error_msg = str(exc_info.value)
        # Use message_startswith for error message checking
        assert message_startswith(error_msg, "Invalid JSON input")
        assert "use `--input-format md|txt`" in error_msg
