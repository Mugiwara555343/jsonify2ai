import pytest
from unittest.mock import patch, Mock
import os
import sys
import requests
from pathlib import Path

# Add the app directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from services.embed_ollama import (
    embed_texts,
    _parse_embeddings,
    _generate_dummy_embedding,
)


class TestEmbedOllama:
    def test_dev_mode_returns_correct_shape(self):
        """Test that dev mode returns vectors of correct shape and is deterministic."""
        # Set dev mode
        os.environ["EMBED_DEV_MODE"] = "1"

        try:
            texts = ["hello world", "test text"]
            embeddings = embed_texts(texts, dim=768)

            # Check shape
            assert len(embeddings) == 2
            assert len(embeddings[0]) == 768
            assert len(embeddings[1]) == 768

            # Check deterministic (same input -> same vector)
            embeddings2 = embed_texts(texts, dim=768)
            assert embeddings == embeddings2

            # Check values are in [0, 1)
            for emb in embeddings:
                for val in emb:
                    assert 0 <= val < 1

        finally:
            # Clean up
            if "EMBED_DEV_MODE" in os.environ:
                del os.environ["EMBED_DEV_MODE"]

    def test_dev_mode_different_texts_different_vectors(self):
        """Test that different texts produce different vectors in dev mode."""
        os.environ["EMBED_DEV_MODE"] = "1"

        try:
            text1 = ["hello"]
            text2 = ["world"]

            emb1 = embed_texts(text1, dim=10)
            emb2 = embed_texts(text2, dim=10)

            # Different texts should produce different vectors
            assert emb1 != emb2

        finally:
            if "EMBED_DEV_MODE" in os.environ:
                del os.environ["EMBED_DEV_MODE"]

    def test_parse_embeddings_single_input(self):
        """Test parser accepts single-input shape."""
        response = {"embedding": [0.1, 0.2, 0.3]}
        result = _parse_embeddings(response)

        assert result == [[0.1, 0.2, 0.3]]

    def test_parse_embeddings_batch_input(self):
        """Test parser accepts batch shape."""
        response = {
            "embeddings": [
                {"embedding": [0.1, 0.2, 0.3]},
                {"embedding": [0.4, 0.5, 0.6]},
            ]
        }
        result = _parse_embeddings(response)

        assert result == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]

    def test_parse_embeddings_invalid_format(self):
        """Test parser accepts batch shape."""
        response = {"data": [{"embedding": [0.1, 0.2]}]}

        with pytest.raises(ValueError, match="Unexpected Ollama response format"):
            _parse_embeddings(response)

    @patch("requests.post")
    def test_ollama_api_single_response(self, mock_post):
        """Test Ollama API call with single response format."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"embedding": [0.1, 0.2, 0.3]}
        mock_post.return_value = mock_response

        # Ensure dev mode is off
        if "EMBED_DEV_MODE" in os.environ:
            del os.environ["EMBED_DEV_MODE"]

        result = embed_texts(["test"], dim=3)

        assert result == [[0.1, 0.2, 0.3]]
        mock_post.assert_called_once()

    @patch("requests.post")
    def test_ollama_api_batch_response(self, mock_post):
        """Test Ollama API call with batch response format."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "embeddings": [
                {"embedding": [0.1, 0.2, 0.3]},
                {"embedding": [0.4, 0.5, 0.6]},
            ]
        }
        mock_post.return_value = mock_response

        # Ensure dev mode is off
        if "EMBED_DEV_MODE" in os.environ:
            del os.environ["EMBED_DEV_MODE"]

        result = embed_texts(["test1", "test2"], dim=3)

        assert result == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        mock_post.assert_called_once()

    @patch("requests.post")
    def test_ollama_api_http_error(self, mock_post):
        """Test Ollama API call with HTTP error."""
        # Mock HTTP error
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.HTTPError(
            "Internal Server Error"
        )
        mock_post.return_value = mock_response

        # Ensure dev mode is off
        if "EMBED_DEV_MODE" in os.environ:
            del os.environ["EMBED_DEV_MODE"]

        with pytest.raises(ValueError, match="Ollama API error"):
            embed_texts(["test"], dim=3)

    @patch("requests.post")
    def test_ollama_api_count_mismatch(self, mock_post):
        """Test Ollama API call with count mismatch."""
        # Mock response with wrong count
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"embedding": [0.1, 0.2, 0.3]}
        mock_post.return_value = mock_response

        # Ensure dev mode is off
        if "EMBED_DEV_MODE" in os.environ:
            del os.environ["EMBED_DEV_MODE"]

        with pytest.raises(ValueError, match="Embedding count mismatch"):
            embed_texts(["test1", "test2"], dim=3)

    def test_generate_dummy_embedding(self):
        """Test dummy embedding generation."""
        text = "hello world"
        dim = 10

        result = _generate_dummy_embedding(text, dim)

        assert len(result) == dim
        assert all(0 <= val < 1 for val in result)

        # Same text should produce same embedding
        result2 = _generate_dummy_embedding(text, dim)
        assert result == result2
