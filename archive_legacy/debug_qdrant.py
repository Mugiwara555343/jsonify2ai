import qdrant_client
from qdrant_client import QdrantClient
import inspect

try:
    print(f"Version: {qdrant_client.__version__}")
except Exception:
    print("Version not found in module")

try:
    sig = inspect.signature(QdrantClient.query_points)
    print(f"query_points signature: {sig}")
except AttributeError:
    print("query_points not found")
except Exception as e:
    print(f"Error checking query_points: {e}")
