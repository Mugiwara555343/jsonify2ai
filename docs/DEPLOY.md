# Deploy Modes

| Mode | How to run | API base | Notes |
|---|---|---|---|
| Local laptop (default) | `scripts/start_all.ps1` or `scripts/start_all.sh` | auto-detect → `http://localhost:8082` | No env override needed. **This is the default for demos.** |
| All-in-Docker (no host browser) | `docker compose -f docker-compose.yml -f docker-compose.docker.yml up -d` | `http://api:8082` | Copy `docker-compose.docker.yml.sample` to `docker-compose.docker.yml` |
| Remote/Company domain | Behind reverse proxy | Set `VITE_API_URL=https://your.domain/api` | Align CORS for your origins. **Strict mode + externalized Docker configs are the path to multi-user / company deployment.** |

## Tokens

- On first run, `ensure_tokens` generates `API_AUTH_TOKEN` and `WORKER_AUTH_TOKEN` into `.env`.

- Web uses `VITE_API_TOKEN=${API_AUTH_TOKEN}`.

- API authenticates clients with `API_AUTH_TOKEN` and talks to Worker with `WORKER_AUTH_TOKEN`.

## Auth Modes

- **`AUTH_MODE=local`** (default): No bearer authentication is enforced by the API. Browser uploads and UI actions work with zero configuration. Perfect for local demos, recruiters, and single-user setups. You can still set tokens, but they're not required in this mode.

- **`AUTH_MODE=strict`**: All protected endpoints require a valid `Authorization: Bearer <API_AUTH_TOKEN>` header. Use this for production deployments, multi-user setups, or when you need strict access control.

## Ollama host

- Host install: `OLLAMA_HOST=http://host.docker.internal:11434`

- Docker service: `OLLAMA_HOST=http://ollama:11434`

## Optional: Local LLM

The app works without an LLM—semantic search and exports are fully functional. LLM synthesis is optional and only enhances the "Ask" feature.

To enable:

1. Install Ollama from [ollama.com](https://ollama.com)
2. Pull a model: `ollama pull qwen2.5:3b-instruct-q4_K_M`
3. Set environment variables:
   - `LLM_PROVIDER=ollama`
   - `OLLAMA_HOST=http://host.docker.internal:11434` (host install) or `http://ollama:11434` (Docker service)
   - `OLLAMA_MODEL=qwen2.5:3b-instruct-q4_K_M`
4. Restart worker: `docker compose restart worker`

See [README.md](../README.md#optional-local-llm) for full setup instructions and UI chip states.

## Smoke test

**PowerShell**

```powershell
scripts\smoke_verify.ps1
```

**Bash**

```bash
./scripts/smoke_verify.sh
```

Or use the lightweight diagnostic:

```bash
python scripts/ingest_diagnose.py
```

Expect JSON with `"api_upload_ok": true` and `"inferred_issue": "ok"`.
