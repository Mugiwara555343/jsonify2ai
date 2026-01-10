"""Unit tests for generic transcript detection and parsing."""

from worker.app.services.parse_transcript import (
    detect_transcript,
    parse_transcript,
    DETECTION_THRESHOLD,
)


class TestDetectTranscript:
    """Test transcript detection logic."""

    def test_detect_transcript_clear_pattern(self):
        """Test that a clearly formatted transcript is detected."""
        text = """User: How do I create a Python virtual environment?

Assistant: You can create a Python virtual environment using the venv module.

User: Thanks!"""
        is_transcript, confidence = detect_transcript(text, "chat.txt")
        assert is_transcript is True
        assert confidence >= DETECTION_THRESHOLD

    def test_detect_transcript_timestamped(self):
        """Test timestamped transcript pattern."""
        text = """[2024-01-15 10:30] user: Hello
[2024-01-15 10:31] assistant: Hi there!
[2024-01-15 10:32] user: How are you?"""
        is_transcript, confidence = detect_transcript(text, "transcript.txt")
        assert is_transcript is True
        assert confidence >= DETECTION_THRESHOLD

    def test_detect_transcript_normal_text(self):
        """Test that normal text is NOT misdetected."""
        text = """This is a regular document about Python programming.
It contains multiple paragraphs but no role indicators.
The content discusses various topics without any chat-like structure."""
        is_transcript, confidence = detect_transcript(text, "document.txt")
        assert is_transcript is False
        assert confidence < DETECTION_THRESHOLD

    def test_detect_transcript_single_role(self):
        """Test that single role (no conversation) has low confidence."""
        text = """User: This is just a single user message.
There's no assistant response, so it's not really a conversation."""
        is_transcript, confidence = detect_transcript(text, "notes.txt")
        # Should have low confidence because only one role
        assert confidence < DETECTION_THRESHOLD or is_transcript is False

    def test_detect_transcript_markdown_format(self):
        """Test markdown-style role indicators."""
        text = """**User**: What is Python?
**Assistant**: Python is a programming language.
**User**: Thanks!"""
        is_transcript, confidence = detect_transcript(text, "chat.md")
        assert is_transcript is True
        assert confidence >= DETECTION_THRESHOLD


class TestParseTranscript:
    """Test transcript parsing logic."""

    def test_parse_transcript_basic(self):
        """Test parsing a basic transcript."""
        text = """User: Hello
Assistant: Hi there!
User: How are you?"""
        results = parse_transcript(text, "test.txt")
        assert len(results) >= 1
        doc_id, formatted_text, meta = results[0]
        assert doc_id.startswith("transcript:")
        assert meta["source_system"] == "transcript"
        assert meta["doc_type"] == "chat"
        assert meta["detected_as"] == "transcript"
        assert "User:" in formatted_text
        assert "Assistant:" in formatted_text

    def test_parse_transcript_metadata(self):
        """Test that metadata fields are set correctly."""
        text = """User: Test question
Assistant: Test answer"""
        results = parse_transcript(text, "test_chat.txt")
        assert len(results) >= 1
        _, _, meta = results[0]
        assert meta["source_system"] == "transcript"
        assert meta["doc_type"] == "chat"
        assert meta["detected_as"] == "transcript"
        assert "logical_path" in meta
        assert meta["logical_path"].startswith("transcript/")
        assert "title" in meta
        assert "message_count" in meta
        assert meta["message_count"] >= 2

    def test_parse_transcript_empty(self):
        """Test parsing empty text."""
        results = parse_transcript("", "empty.txt")
        assert results == []

    def test_parse_transcript_deterministic_id(self):
        """Test that same content produces same document_id."""
        text = """User: Question
Assistant: Answer"""
        results1 = parse_transcript(text, "test1.txt")
        results2 = parse_transcript(text, "test1.txt")
        assert len(results1) >= 1
        assert len(results2) >= 1
        # Same content should produce same document_id
        assert results1[0][0] == results2[0][0]
