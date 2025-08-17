import pytest
from unittest.mock import patch, Mock
from app.services.qdrant_minimal import ensure_collection_minimal

class TestQdrantMinimal:
    
    @patch('requests.get')
    @patch('requests.put')
    def test_ensure_collection_existing_success(self, mock_put, mock_get):
        """Test successful verification of existing collection"""
        # Mock existing collection response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "config": {
                "params": {
                    "vectors": {
                        "size": 768,
                        "distance": "Cosine"
                    }
                }
            }
        }
        mock_get.return_value = mock_response
        
        success, error = ensure_collection_minimal("test_collection", 768)
        
        assert success is True
        assert error is None
        mock_get.assert_called_once()
        mock_put.assert_not_called()
    
    @patch('requests.get')
    @patch('requests.put')
    def test_ensure_collection_existing_dimension_mismatch(self, mock_put, mock_get):
        """Test dimension mismatch in existing collection"""
        # Mock existing collection with wrong dimension
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "config": {
                "params": {
                    "vectors": {
                        "size": 512,
                        "distance": "Cosine"
                    }
                }
            }
        }
        mock_get.return_value = mock_response
        
        success, error = ensure_collection_minimal("test_collection", 768)
        
        assert success is False
        assert "dimension 512, but model expects 768" in error
        mock_get.assert_called_once()
        mock_put.assert_not_called()
    
    @patch('requests.get')
    @patch('requests.put')
    def test_ensure_collection_create_new(self, mock_put, mock_get):
        """Test creating new collection"""
        # Mock collection not found
        mock_get_response = Mock()
        mock_get_response.status_code = 404
        mock_get.return_value = mock_get_response
        
        # Mock successful creation
        mock_put_response = Mock()
        mock_put_response.status_code = 200
        mock_put.return_value = mock_put_response
        
        success, error = ensure_collection_minimal("test_collection", 768)
        
        assert success is True
        assert error is None
        mock_get.assert_called_once()
        mock_put.assert_called_once()
        
        # Verify PUT call arguments
        put_call = mock_put.call_args
        assert put_call[0][0].endswith("/collections/test_collection")
        assert put_call[1]["json"] == {
            "vectors": {
                "size": 768,
                "distance": "Cosine"
            }
        }
    
    @patch('requests.get')
    @patch('requests.put')
    def test_ensure_collection_create_failure(self, mock_put, mock_get):
        """Test failure when creating collection"""
        # Mock collection not found
        mock_get_response = Mock()
        mock_get_response.status_code = 404
        mock_get.return_value = mock_get_response
        
        # Mock creation failure
        mock_put_response = Mock()
        mock_put_response.status_code = 500
        mock_put_response.text = "Internal server error"
        mock_put.return_value = mock_put_response
        
        success, error = ensure_collection_minimal("test_collection", 768)
        
        assert success is False
        assert "Failed to create collection" in error
        assert "status 500" in error
        assert "Internal server error" in error
    
    @patch('requests.get')
    def test_ensure_collection_request_exception(self, mock_get):
        """Test handling of request exceptions"""
        mock_get.side_effect = Exception("Connection error")
        
        success, error = ensure_collection_minimal("test_collection", 768)
        
        assert success is False
        assert "Unexpected error" in error
        assert "Connection error" in error
