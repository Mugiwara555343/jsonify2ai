# Web Service

Vite + React + TypeScript frontend for the jsonify2ai memory system.

## Development

```bash
npm run dev
```

## Docker

### Quick Start

```bash
# Start web service (uses existing image if available)
docker compose up -d web
```

### Rebuilding

**Only rebuild when needed:**
- Dockerfile changed
- package.json or package-lock.json changed
- You want to force a fresh build

```bash
# Rebuild and restart web service
docker compose up -d --build web
```

**Note:** First-time builds may take 2-5 minutes to install dependencies. Subsequent builds are much faster thanks to:
- `.dockerignore` excluding `node_modules/` and `dist/`
- BuildKit cache mounts for npm packages
- Layer caching (dependencies only rebuild when package files change)

### Build Performance Tips

1. **Avoid unnecessary rebuilds**: Use `docker compose up -d web` without `--build` unless you've changed dependencies or Dockerfile
2. **First build**: Allow 2-5 minutes for initial dependency installation
3. **Subsequent builds**: Should be fast (seconds) if only source code changed
4. **If builds are slow**: Check that `.dockerignore` is present and excludes `node_modules/`, `dist/`, and build artifacts
