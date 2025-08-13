"""
Tests for glob pattern expansion and multi-file output handling.
"""

import tempfile
from pathlib import Path
from note_to_json.cli import expand_glob_patterns


class TestGlobAndMultiOutputs:
    """Test glob pattern expansion and multi-file processing."""

    def test_simple_glob_pattern(self):
        """Test simple glob pattern expansion."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test files
            (temp_path / "file1.md").write_text("# File 1\n\nContent 1")
            (temp_path / "file2.md").write_text("# File 2\n\nContent 2")
            (temp_path / "file3.txt").write_text("Text file content")

            # Test glob pattern
            pattern = str(temp_path / "*.md")
            expanded = expand_glob_patterns([pattern])

            assert len(expanded) == 2
            assert any("file1.md" in f for f in expanded)
            assert any("file2.md" in f for f in expanded)
            assert not any("file3.txt" in f for f in expanded)

    def test_recursive_glob_pattern(self):
        """Test recursive glob pattern with nested directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create nested structure
            (temp_path / "dir1").mkdir()
            (temp_path / "dir1" / "nested1.md").write_text("# Nested 1\n\nContent")
            (temp_path / "dir2").mkdir()
            (temp_path / "dir2" / "nested2.md").write_text("# Nested 2\n\nContent")
            (temp_path / "root.md").write_text("# Root\n\nContent")

            # Test recursive glob pattern
            pattern = str(temp_path / "**/*.md")
            expanded = expand_glob_patterns([pattern])

            assert len(expanded) == 3
            assert any("nested1.md" in f for f in expanded)
            assert any("nested2.md" in f for f in expanded)
            assert any("root.md" in f for f in expanded)

    def test_multiple_patterns(self):
        """Test multiple glob patterns."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test files
            (temp_path / "file1.md").write_text("# File 1\n\nContent")
            (temp_path / "file2.txt").write_text("Text content")
            (temp_path / "file3.json").write_text('{"title": "JSON"}')

            # Test multiple patterns
            patterns = [str(temp_path / "*.md"), str(temp_path / "*.txt")]
            expanded = expand_glob_patterns(patterns)

            assert len(expanded) == 2
            assert any("file1.md" in f for f in expanded)
            assert any("file2.txt" in f for f in expanded)
            assert not any("file3.json" in f for f in expanded)

    def test_literal_paths(self):
        """Test literal file paths (no glob characters)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test files
            (temp_path / "file1.md").write_text("# File 1\n\nContent")
            (temp_path / "file2.md").write_text("# File 2\n\nContent")

            # Test literal paths
            patterns = [str(temp_path / "file1.md"), str(temp_path / "file2.md")]
            expanded = expand_glob_patterns(patterns)

            assert len(expanded) == 2
            assert any("file1.md" in f for f in expanded)
            assert any("file2.md" in f for f in expanded)

    def test_mixed_patterns_and_literals(self):
        """Test mixing glob patterns with literal paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test files
            (temp_path / "file1.md").write_text("# File 1\n\nContent")
            (temp_path / "file2.md").write_text("# File 2\n\nContent")
            (temp_path / "file3.md").write_text("# File 3\n\nContent")

            # Test mixed patterns
            patterns = [
                str(temp_path / "*.md"),  # Glob pattern
                str(temp_path / "file3.md"),  # Literal path
            ]
            expanded = expand_glob_patterns(patterns)

            # Should get all 3 files (glob + literal, deduplicated)
            assert len(expanded) == 3
            assert any("file1.md" in f for f in expanded)
            assert any("file2.md" in f for f in expanded)
            assert any("file3.md" in f for f in expanded)

    def test_nonexistent_glob_pattern(self):
        """Test glob pattern that matches no files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Test pattern that won't match anything
            pattern = str(temp_path / "nonexistent*.md")
            expanded = expand_glob_patterns([pattern])

            # Should include the pattern itself when no matches found
            assert len(expanded) == 1
            assert "nonexistent*.md" in expanded[0]

    def test_deduplication_and_sorting(self):
        """Test that results are deduplicated and sorted."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test files
            (temp_path / "b_file.md").write_text("# B File\n\nContent")
            (temp_path / "a_file.md").write_text("# A File\n\nContent")
            (temp_path / "c_file.md").write_text("# C File\n\nContent")

            # Test glob pattern
            pattern = str(temp_path / "*.md")
            expanded = expand_glob_patterns([pattern])

            # Should be sorted alphabetically
            assert len(expanded) == 3
            assert "a_file.md" in expanded[0]
            assert "b_file.md" in expanded[1]
            assert "c_file.md" in expanded[2]
