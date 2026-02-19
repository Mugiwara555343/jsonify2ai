"""
Tests for UTF-8 and UTF-16 file encoding handling.
"""

import tempfile
from pathlib import Path
import pytest
from note_to_json.parser import read_input
from note_to_json.utils import read_text_safely
from ._helpers import normalize_text


class TestUTF8AndUTF16Files:
    """Test encoding detection and handling for various UTF formats."""

    def test_utf8_file(self):
        """Test UTF-8 file reading."""
        content = "# Test Title\n\nThis is UTF-8 content with émojis 🎉"

        with tempfile.NamedTemporaryFile(mode="wb", suffix=".md", delete=False) as f:
            f.write(content.encode("utf-8"))
            temp_path = Path(f.name)

        try:
            # Test encoding utility
            text = read_text_safely(temp_path)
            # Use normalize_text for cross-platform stability
            assert normalize_text(text) == normalize_text(content)

            # Test full parsing
            parsed = read_input(text, "auto", filename_hint="test")
            assert parsed["title"] == "Test Title"
            assert "émojis" in parsed["raw_text"]
            assert "🎉" in parsed["raw_text"]
            assert "\u0000" not in parsed["raw_text"]  # No null bytes
            # plain_text should also contain the normalized content
            assert "émojis" in parsed["plain_text"]
            assert "🎉" in parsed["plain_text"]
        finally:
            temp_path.unlink()

    def test_utf8_bom_file(self):
        """Test UTF-8 BOM file reading."""
        content = "# BOM Test\n\nContent with BOM"

        with tempfile.NamedTemporaryFile(mode="wb", suffix=".md", delete=False) as f:
            f.write(b"\xef\xbb\xbf")  # UTF-8 BOM
            f.write(content.encode("utf-8"))
            temp_path = Path(f.name)

        try:
            text = read_text_safely(temp_path)
            # Use normalize_text for cross-platform stability
            assert normalize_text(text) == normalize_text(
                content
            )  # BOM should be stripped

            parsed = read_input(text, "auto", filename_hint="test")
            assert parsed["title"] == "BOM Test"
        finally:
            temp_path.unlink()

    def test_utf16_le_file(self):
        """Test UTF-16 LE file reading."""
        content = "# UTF-16 Test\n\nContent in UTF-16 LE"

        with tempfile.NamedTemporaryFile(mode="wb", suffix=".md", delete=False) as f:
            f.write(content.encode("utf-16-le"))
            temp_path = Path(f.name)

        try:
            text = read_text_safely(temp_path)
            # Use normalize_text for cross-platform stability
            assert normalize_text(text) == normalize_text(content)

            parsed = read_input(text, "auto", filename_hint="test")
            assert parsed["title"] == "UTF-16 Test"
        finally:
            temp_path.unlink()

    def test_utf16_be_file(self):
        """Test UTF-16 BE file reading."""
        content = "# UTF-16 BE Test\n\nContent in UTF-16 BE"

        with tempfile.NamedTemporaryFile(mode="wb", suffix=".md", delete=False) as f:
            f.write(content.encode("utf-16-be"))
            temp_path = Path(f.name)

        try:
            text = read_text_safely(temp_path)
            # Use normalize_text for cross-platform stability
            assert normalize_text(text) == normalize_text(content)

            parsed = read_input(text, "auto", filename_hint="test")
            assert parsed["title"] == "UTF-16 BE Test"
        finally:
            temp_path.unlink()

    def test_utf16_file(self):
        """Test UTF-16 file reading (system default endianness)."""
        content = "# UTF-16 Default Test\n\nContent in UTF-16"

        with tempfile.NamedTemporaryFile(mode="wb", suffix=".md", delete=False) as f:
            f.write(content.encode("utf-16"))
            temp_path = Path(f.name)

        try:
            text = read_text_safely(temp_path)
            # Use normalize_text for cross-platform stability
            assert normalize_text(text) == normalize_text(content)

            parsed = read_input(text, "auto", filename_hint="test")
            assert parsed["title"] == "UTF-16 Default Test"
        finally:
            temp_path.unlink()

    def test_invalid_encoding_fails_gracefully(self):
        """Test that invalid encodings fail with clear error message."""
        # Create a file with bytes that will pass decoding but fail validation
        # Use bytes with a high ratio of null bytes to trigger validation failure
        invalid_bytes = (
            b"Valid text" + b"\x00" * 20
        )  # 20 null bytes out of 30 total = 66% null ratio

        with tempfile.NamedTemporaryFile(mode="wb", suffix=".md", delete=False) as f:
            f.write(invalid_bytes)
            temp_path = Path(f.name)

        try:
            with pytest.raises(ValueError) as exc_info:
                read_text_safely(temp_path)

            error_msg = str(exc_info.value)
            # Use message_startswith for error message checking
            from ._helpers import message_startswith

            assert message_startswith(error_msg, "Decoding error")
            assert "try saving as UTF-8" in error_msg
        finally:
            temp_path.unlink()
