# API Service

Go-based API service for the jsonify2ai memory system.

## Endpoints

- `GET /health` - Health check endpoint
- `POST /upload` - File upload and processing endpoint
- `GET /search?q=<query>` - Semantic search endpoint using vector embeddings

## Environment Variables

- `POSTGRES_DSN` - PostgreSQL connection string
- `QDRANT_URL` - Qdrant vector database URL (default: http://host.docker.internal:6333)
- `OLLAMA_URL` - Ollama service URL (default: http://host.docker.internal:11434)
- `WORKER_BASE` - Worker service base URL (default: http://worker:8090)
- `QDRANT_COLLECTION` - Qdrant collection name (default: jsonify2ai_chunks)
- `EMBEDDINGS_MODEL` - Ollama embeddings model (default: nomic-embed-text)
- `SEARCH_TOPK` - Number of search results to return (default: 5)

## Development

```bash
make run
```

## Docker

```bash
docker compose up api
```

## Troubleshooting

### Search Endpoint Fails with 404 from Ollama

If the `/search` endpoint fails with a 404 error from Ollama, the model may not be available. Pull the required model:

```bash
curl -X POST http://host.docker.internal:11434/api/pull -H "Content-Type: application/json" -d '{ "name": "nomic-embed-text" }'
```

This will download the `nomic-embed-text` model that's used for generating embeddings.
