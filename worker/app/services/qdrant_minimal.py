import requests
import logging
from typing import Optional, Tuple
from ..config import settings

logger = logging.getLogger(__name__)

def ensure_collection_minimal(name: str, dim: int) -> Tuple[bool, Optional[str]]:
    """
    Ensure Qdrant collection exists with correct dimensions using minimal HTTP requests.
    
    Args:
        name: Collection name
        dim: Expected vector dimension
    
    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    try:
        # Check if collection exists
        url = f"{settings.QDRANT_URL}/collections/{name}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            # Collection exists, verify dimensions
            try:
                data = response.json()
                # Extract only the essential fields, ignore optimizer_config entirely
                vectors_config = data.get("config", {}).get("params", {}).get("vectors", {})
                current_dim = vectors_config.get("size")
                distance = vectors_config.get("distance")
                
                if current_dim is None:
                    return False, f"Collection '{name}' exists but has no vector size configuration"
                
                if current_dim != dim:
                    return False, f"Collection '{name}' exists with dimension {current_dim}, but model expects {dim}"
                
                logger.info(f"Collection '{name}' verified: size={current_dim}, distance={distance}")
                return True, None
                
            except (KeyError, TypeError) as e:
                return False, f"Collection '{name}' exists but has invalid configuration: {str(e)}"
                
        elif response.status_code == 404:
            # Collection doesn't exist, create it
            create_url = f"{settings.QDRANT_URL}/collections/{name}"
            create_data = {
                "vectors": {
                    "size": dim,
                    "distance": "Cosine"
                }
            }
            
            create_response = requests.put(create_url, json=create_data, timeout=10)
            
            if create_response.status_code == 200:
                logger.info(f"Collection '{name}' created: size={dim}, distance=Cosine")
                return True, None
            else:
                error_msg = f"Failed to create collection '{name}': status {create_response.status_code}"
                try:
                    body = create_response.text.strip()
                    if body:
                        error_msg += f", response: {body}"
                except:
                    pass
                return False, error_msg
                
        else:
            # Unexpected status code
            error_msg = f"Unexpected response checking collection '{name}': status {response.status_code}"
            try:
                body = response.text.strip()
                if body:
                    error_msg += f", response: {body}"
            except:
                pass
            return False, error_msg
            
    except requests.exceptions.RequestException as e:
        return False, f"Request error ensuring collection '{name}': {str(e)}"
    except Exception as e:
        return False, f"Unexpected error ensuring collection '{name}': {str(e)}"
