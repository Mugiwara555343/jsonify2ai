# Manual Smoke Tests

This document outlines manual testing steps to verify the jsonify2ai memory system is working correctly.

## Prerequisites

1. External services running:
   - PostgreSQL on `host.docker.internal:5432`
   - Qdrant on `host.docker.internal:6333`
   - Ollama on `host.docker.internal:11434`

2. Environment configured:
   ```bash
   cp .env.example .env
   # Edit .env with your actual connection details
   ```

## Test Steps

### 1. Start All Services

```bash
make up
```

Wait for all containers to start and be healthy.

### 2. Check Service Health

Visit the web interface: http://localhost:5173

You should see:
- ✅ API Service: Healthy
- ✅ Worker Service: Healthy

### 3. Test API Health Endpoint

```bash
curl http://localhost:8080/health
```

Expected response:
```json
{"ok": true}
```

### 4. Test Worker Health Endpoint

```bash
curl http://localhost:8090/health
```

Expected response:
```json
{"ok": true}
```

### 5. Test Worker Root Endpoint

```bash
curl http://localhost:8090/
```

Expected response:
```json
{"message": "jsonify2ai Worker Service"}
```

### 6. Verify Database Connection

Check that the API service can connect to PostgreSQL by looking at the logs:

```bash
make logs api
```

You should see startup messages without connection errors.

### 7. Verify External Service Connectivity

Check that services can reach external dependencies:

```bash
# Test PostgreSQL connection
docker compose exec api ping host.docker.internal

# Test Qdrant connection
docker compose exec worker ping host.docker.internal
```

## Troubleshooting

### Services Not Starting

1. Check if external services are running
2. Verify `.env` file configuration
3. Check Docker logs: `make logs`

### Health Checks Failing

1. Verify ports are not already in use
2. Check container logs for specific errors
3. Ensure external services are accessible from Docker

### Database Connection Issues

1. Verify PostgreSQL is running and accessible
2. Check connection string in `.env`
3. Ensure database `jsonify2ai` exists

## Cleanup

```bash
make down
```

This will stop all services and remove containers.
