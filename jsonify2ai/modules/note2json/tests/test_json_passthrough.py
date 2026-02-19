"""
Tests for JSON input format handling and validation.
"""

import json
import tempfile
from pathlib import Path
import pytest
from note_to_json.parser import read_input
from ._helpers import normalize_text, message_startswith


class TestJSONPassthrough:
    """Test JSON input format handling and validation."""

    def test_valid_json_passthrough(self):
        """Test that well-formed JSON files round-trip correctly."""
        json_data = {
            "title": "Test JSON",
            "timestamp": "2023-01-01T00:00:00Z",
            "raw_text": "JSON content",
            "plain_text": "JSON content",
            "tags": ["test", "json"],
            "headers": ["Test JSON"],
            "reflections": ["This is a test"],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(json_data, f)
            temp_path = Path(f.name)

        try:
            # Read and parse the JSON file
            with open(temp_path, "r", encoding="utf-8") as f:
                content = f.read()

            parsed = read_input(content, "json", filename_hint="test")

            # Should preserve the original data
            assert parsed["title"] == "Test JSON"
            assert parsed["timestamp"] == "2023-01-01T00:00:00Z"
            assert parsed["raw_text"] == "JSON content"
            assert parsed["plain_text"] == "JSON content"
            assert parsed["tags"] == ["test", "json"]
            assert parsed["headers"] == ["Test JSON"]
            assert parsed["reflections"] == ["This is a test"]
        finally:
            temp_path.unlink()

    def test_json_with_extra_fields(self):
        """Test JSON with extra fields gets normalized."""
        json_data = {
            "title": "Extra Fields Test",
            "extra_field": "This should be ignored",
            "another_extra": 123,
            "nested": {"key": "value"},
        }

        content = json.dumps(json_data)
        parsed = read_input(content, "json", filename_hint="test")

        # Should only include schema fields
        assert parsed["title"] == "Extra Fields Test"
        assert "extra_field" not in parsed
        assert "another_extra" not in parsed
        assert "nested" not in parsed

        # Should have required fields
        assert "timestamp" in parsed
        assert "raw_text" in parsed
        assert "plain_text" in parsed

    def test_json_with_missing_required_fields(self):
        """Test JSON with missing required fields gets normalized."""
        json_data = {
            "title": "Missing Fields Test"
            # Missing timestamp, raw_text, plain_text
        }

        content = json.dumps(json_data)
        parsed = read_input(content, "json", filename_hint="test")

        # Should add missing required fields
        assert parsed["title"] == "Missing Fields Test"
        assert "timestamp" in parsed
        assert "raw_text" in parsed
        assert "plain_text" in parsed

        # raw_text and plain_text should contain the minified JSON
        assert json_data["title"] in parsed["raw_text"]
        assert json_data["title"] in parsed["plain_text"]

    def test_json_array_input(self):
        """Test JSON array input gets normalized."""
        json_data = ["item1", "item2", "item3"]

        content = json.dumps(json_data)
        parsed = read_input(content, "json", filename_hint="test")

        # Should create a normalized structure
        assert parsed["title"] == "test"  # filename_hint
        assert "timestamp" in parsed
        assert "raw_text" in parsed
        assert "plain_text" in parsed

        # raw_text should contain the minified JSON
        assert "item1" in parsed["raw_text"]
        assert "item3" in parsed["raw_text"]
        # plain_text should contain the normalized content
        assert "item1" in parsed["plain_text"]
        assert "item3" in parsed["plain_text"]

    def test_json_primitive_input(self):
        """Test JSON primitive input gets normalized."""
        test_cases = [
            ("string", "string"),
            (123, "123"),
            (True, "true"),
            (None, "null"),
        ]

        for input_value, expected_text in test_cases:
            content = json.dumps(input_value)
            parsed = read_input(content, "json", filename_hint="test")

            assert parsed["title"] == "test"
            assert "timestamp" in parsed
            assert "raw_text" in parsed
            assert "plain_text" in parsed
            # Use normalize_text for cross-platform stability
            assert normalize_text(expected_text) in normalize_text(parsed["plain_text"])

    def test_invalid_json_fails_gracefully(self):
        """Test that malformed JSON fails with clear error message."""
        invalid_json_cases = [
            "{ invalid json",
            '{"title": "test",}',
            '{"title": "test" "missing": "comma"}',
            '{"title": "test", "unclosed": "quote}',
            '{"title": "test", "null_bytes": "\u0000"}',
        ]

        for invalid_json in invalid_json_cases:
            with pytest.raises(ValueError) as exc_info:
                read_input(invalid_json, "json", filename_hint="test")

            error_msg = str(exc_info.value)
            # Use message_startswith for error message checking
            assert message_startswith(error_msg, "Invalid JSON input")
            assert "use `--input-format md|txt`" in error_msg

    def test_json_with_unicode_content(self):
        """Test JSON with unicode content handles correctly."""
        json_data = {
            "title": "Unicode Test 🎉",
            "content": "Content with émojis and 🚀 symbols",
        }

        content = json.dumps(json_data, ensure_ascii=False)
        parsed = read_input(content, "json", filename_hint="test")

        assert parsed["title"] == "Unicode Test 🎉"
        assert "émojis" in parsed["raw_text"]
        assert "🚀" in parsed["raw_text"]
        assert "🎉" in parsed["raw_text"]
        # plain_text should also contain the normalized content
        assert "émojis" in parsed["plain_text"]
        assert "🚀" in parsed["plain_text"]
        assert "🎉" in parsed["plain_text"]

    def test_json_tags_normalization(self):
        """Test that JSON tags get properly normalized."""
        test_cases = [
            # Valid tags
            (["tag1", "tag2"], ["tag1", "tag2"]),
            (["#tag1", "#tag2"], ["tag1", "tag2"]),  # Hash prefix stripped
            ([123, True, "string"], ["123", "true", "string"]),  # Converted to strings
            ([], []),  # Empty list
            (None, []),  # None becomes empty list
        ]

        for input_tags, expected_tags in test_cases:
            json_data = {"title": "Tags Test", "tags": input_tags}
            content = json.dumps(json_data)
            parsed = read_input(content, "json", filename_hint="test")

            assert parsed["tags"] == expected_tags
