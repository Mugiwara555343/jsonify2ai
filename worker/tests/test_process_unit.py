import os
import pytest
from app.services.chunker import chunk_text
from app.services.parse_transcript import detect_transcript, DETECTION_THRESHOLD
from app.routers.process import (
    ProcessTextRequest,
    ProcessTextResponse,
    _build_meta_with_provenance,
)


class TestChunker:
    """Unit tests for text chunking service."""

    def test_chunk_text_empty(self):
        """Test chunking empty text."""
        result = chunk_text("", 100, 20)
        assert result == []

    def test_chunk_text_smaller_than_chunk(self):
        """Test text smaller than chunk size."""
        text = "Hello world"
        result = chunk_text(text, 100, 20)
        assert result == ["Hello world"]

    def test_chunk_text_exact_chunk_size(self):
        """Test text exactly chunk size."""
        text = "a" * 100
        result = chunk_text(text, 100, 20)
        assert result == ["a" * 100]

    def test_chunk_text_with_overlap(self):
        """Test chunking with overlap."""
        text = "a" * 200
        result = chunk_text(text, 100, 20)
        # With 200 chars, chunk size 100, overlap 20, we get 3 chunks:
        # First: 0-100 (100 chars), Second: 80-180 (100 chars), Third: 160-200 (40 chars)
        assert len(result) == 3
        assert result[0] == "a" * 100
        assert result[1] == "a" * 100
        assert result[2] == "a" * 40
        # Check overlap between first two chunks
        assert result[0][-20:] == result[1][:20]

    def test_chunk_text_multiple_chunks(self):
        """Test multiple chunks."""
        text = "a" * 300
        result = chunk_text(text, 100, 20)
        # With 300 chars, chunk size 100, overlap 20, we get 4 chunks:
        # First: 0-100, Second: 80-180, Third: 160-260, Fourth: 240-300
        assert len(result) == 4
        assert all(len(chunk) <= 100 for chunk in result)
        # Check overlaps
        assert result[0][-20:] == result[1][:20]
        assert result[1][-20:] == result[2][:20]
        assert result[2][-20:] == result[3][:20]

    def test_chunk_text_invalid_params(self):
        """Test invalid parameters."""
        result = chunk_text("hello", 0, 20)
        assert result == []

        result = chunk_text("hello", -1, 20)
        assert result == []


class TestProcessTextRequest:
    """Test request/response models."""

    def test_process_text_request(self):
        """Test request model validation."""
        request = ProcessTextRequest(document_id="test-123", text="Hello world")
        assert request.document_id == "test-123"
        assert request.text == "Hello world"
        assert request.path is None

    def test_process_text_response(self):
        """Test response model validation."""
        response = ProcessTextResponse(
            ok=True,
            document_id="test-123",
            chunks=2,
            embedded=2,
            upserted=2,
            collection="test_collection",
        )
        assert response.ok is True
        assert response.chunks == 2
        assert response.collection == "test_collection"


@pytest.mark.skipif(
    os.getenv("SERVICES_UP") != "1",
    reason="SERVICES_UP not set to 1 - skipping networked tests",
)
class TestProcessTextIntegration:
    """Integration tests that require external services."""

    def test_process_text_endpoint_smoke(self, client):
        """Smoke test for /process/text endpoint."""
        # This test will be skipped unless SERVICES_UP=1
        request_data = {
            "document_id": "00000000-0000-0000-0000-000000000000",
            "text": "Hello world, this is a test document for the jsonify2ai pipeline.",
        }

        response = client.post("/process/text", json=request_data)
        assert response.status_code == 200

        data = response.json()
        assert data["ok"] is True
        assert data["document_id"] == request_data["document_id"]
        assert data["chunks"] > 0
        assert data["embedded"] > 0
        assert data["upserted"] > 0
        assert data["collection"] == "jsonify2ai_chunks"


class TestTranscriptDetection:
    """Test transcript detection in text processing."""

    def test_detect_transcript_pattern(self):
        """Test that transcript pattern is detected correctly."""
        transcript_text = """User: How do I create a Python virtual environment?

Assistant: You can create a Python virtual environment using the venv module.

User: Thanks!"""
        is_transcript, confidence = detect_transcript(transcript_text, "chat.txt")
        assert is_transcript is True
        assert confidence >= DETECTION_THRESHOLD

    def test_normal_text_not_misdetected(self):
        """Test that normal text is NOT misdetected as transcript."""
        normal_text = """This is a regular document about Python programming.
It contains multiple paragraphs but no role indicators.
The content discusses various topics without any chat-like structure.
There are no User: or Assistant: prefixes here."""
        is_transcript, confidence = detect_transcript(normal_text, "document.txt")
        assert is_transcript is False
        assert confidence < DETECTION_THRESHOLD


class TestProvenanceContract:
    """Test provenance contract metadata fields."""

    def test_meta_fields_present(self):
        """Test that all provenance contract fields are present."""
        base_meta = {"source_ext": ".txt", "bytes": 100}
        meta = _build_meta_with_provenance(
            base_meta,
            source_system="filesystem",
            doc_type="text",
            detected_as="text",
            detect_confidence=1.0,
        )

        # Required fields
        assert "ingested_at" in meta
        assert "ingested_at_ts" in meta
        assert "source_system" in meta
        assert meta["source_system"] == "filesystem"
        assert "doc_type" in meta
        assert meta["doc_type"] == "text"
        assert "detected_as" in meta
        assert meta["detected_as"] == "text"
        assert "detect_confidence" in meta
        assert meta["detect_confidence"] == 1.0

        # Optional fields (should be present with defaults)
        assert "tags" in meta
        assert isinstance(meta["tags"], list)
        assert "author" in meta
        assert "created_at" in meta
        assert "created_at_ts" in meta
        assert "updated_at" in meta
        assert "updated_at_ts" in meta

    def test_transcript_meta_fields(self):
        """Test transcript-specific metadata fields."""
        base_meta = {"source_ext": ".txt", "bytes": 200}
        meta = _build_meta_with_provenance(
            base_meta,
            source_system="transcript",
            doc_type="chat",
            detected_as="transcript",
            detect_confidence=0.9,
        )

        assert meta["source_system"] == "transcript"
        assert meta["doc_type"] == "chat"
        assert meta["detected_as"] == "transcript"
        assert meta["detect_confidence"] == 0.9

    def test_chatgpt_meta_fields(self):
        """Test ChatGPT-specific metadata fields."""
        base_meta = {"source_ext": ".json", "bytes": 300}
        meta = _build_meta_with_provenance(
            base_meta,
            source_system="chatgpt",
            doc_type="chat",
            detected_as="chatgpt",
            detect_confidence=0.95,
            created_at="2024-01-15T10:30:00Z",
            updated_at="2024-01-15T11:00:00Z",
        )

        assert meta["source_system"] == "chatgpt"
        assert meta["doc_type"] == "chat"
        assert meta["detected_as"] == "chatgpt"
        assert meta["detect_confidence"] == 0.95
        assert meta["created_at"] == "2024-01-15T10:30:00Z"
        assert meta["created_at_ts"] is not None
        assert meta["updated_at"] == "2024-01-15T11:00:00Z"
        assert meta["updated_at_ts"] is not None
