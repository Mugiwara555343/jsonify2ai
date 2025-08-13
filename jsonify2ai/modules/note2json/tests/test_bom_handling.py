from pathlib import Path
import tempfile
from note_to_json.parser import parse_file
from ._helpers import normalize_text


def test_bom_handling():
    """Test that UTF-8 BOM is stripped when reading files"""
    # Create a temporary file with UTF-8 BOM
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8-sig"
    ) as tmp_file:
        tmp_file.write(
            "# Test Entry\n**Date:** 2025-01-15\n**Tags:** #test #demo\n**Tone:** Neutral\n\n**Summary:**\nThis is a test entry.\n\n**Core Reflections:**\n- First reflection\n- Second reflection\n- Third reflection"
        )
        tmp_path = Path(tmp_file.name)

    try:
        # Parse the file
        result = parse_file(tmp_path)

        # Assert BOM is stripped from raw_text
        assert not result["raw_text"].startswith(
            "\ufeff"
        ), "BOM not stripped from raw_text"
        # Use normalize_text for cross-platform stability
        assert normalize_text(result["raw_text"]).startswith(
            "# Test Entry"
        ), "raw_text doesn't start with expected content"

        # Assert BOM is stripped from plain_text
        assert not result["plain_text"].startswith(
            "\ufeff"
        ), "BOM not stripped from plain_text"
        # Use normalize_text for cross-platform stability
        assert normalize_text(result["plain_text"]).startswith(
            "# Test Entry"
        ), "plain_text doesn't start with expected content"

        # Verify other fields are parsed correctly
        assert result["title"] == "Test Entry"
        assert result["date"] == "2025-01-15"
        assert "test" in result["tags"]

    finally:
        # Clean up
        if tmp_path.exists():
            tmp_path.unlink()
