# Database Design

## Architecture

The jsonify2ai memory system uses a hybrid database approach:

- **PostgreSQL**: Stores metadata for documents, chunks, and images
- **Qdrant**: Stores vector embeddings for semantic search

## Rationale

### Why PostgreSQL for Metadata?

PostgreSQL is ideal for structured metadata because:
- ACID compliance for data integrity
- Rich querying capabilities with SQL
- Excellent support for JSON fields and arrays
- Mature ecosystem with robust tooling

### Why Qdrant for Vectors?

Qdrant is specialized for vector operations:
- Optimized for similarity search
- Supports multiple distance metrics
- Efficient indexing for high-dimensional vectors
- Built-in support for metadata filtering

## Schema Overview

### Documents Table
Stores metadata about uploaded files:
- File information (name, type, size)
- Content type classification
- Timestamps for tracking

### Chunks Table
Stores text segments extracted from documents:
- Links to parent document
- Sequential indexing for reconstruction
- Text content for processing

### Images Table
Stores metadata about images extracted from documents:
- File paths for storage
- Captions and tags for searchability
- Links to parent document

## Data Flow

1. Documents are uploaded and metadata stored in PostgreSQL
2. Content is processed into chunks/images
3. Chunks are vectorized and stored in Qdrant
4. Search queries use Qdrant for similarity, PostgreSQL for filtering
