<p align="center">
  <img src="docs/jsonify2ai_logo.png" alt="Jsonify2AI logo" width="165"/>
</p>

<h3 align="center">Your data. Your models. Your machine.</h3>

<p align="center">
  A local-first RAG engine that transforms messy files into searchable, AI-synthesized intelligence, running entirely on your hardware with zero cloud dependency.
</p>

---

[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
![OS](https://img.shields.io/badge/tested-Linux%20%7C%20macOS%20%7C%20Windows-lightblue)
[![CI](https://github.com/Mugiwara555343/jsonify2ai/actions/workflows/ci.yml/badge.svg)](https://github.com/Mugiwara555343/jsonify2ai/actions/workflows/ci.yml)
[![GitHub](https://img.shields.io/badge/GitHub-Follow-black?logo=github)](https://github.com/Mugiwara555343)

---

## 🔒 Why This Exists: Data Sovereignty

Most AI tools require sending your documents to a cloud API. Every query, every file, every conversation, routed through someone else's servers.

**Jsonify2ai takes the opposite approach:**

- **Nothing leaves your machine.** Every embedding, every search query, every LLM response is computed locally.
- **No API keys required.** No OpenAI, no cloud credits, no usage caps. You own the entire pipeline.
- **Full provenance.** Every chunk is SHA-256 hashed, timestamped, and traceable back to its source file.
- **Deterministic & idempotent.** Re-ingesting the same file produces zero duplicates — guaranteed by UUID5 deterministic document IDs.

---

## ⚡ The 400K Milestone

Most local RAG implementations break down after a few pages. Jsonify2ai was engineered to handle **massive local datasets** without precision loss:

| Metric | Value |
|--------|-------|
| **Tested corpus size** | 400,000+ characters (~100K tokens) |
| **Embedding model** | `nomic-embed-text` (768 dimensions) |
| **Vector similarity** | Cosine distance via Qdrant |
| **Chunk strategy** | 800-char sliding window, 100-char overlap, whitespace-aware cuts |
| **Deduplication** | SHA-256 file hash → UUID5 deterministic IDs |
| **Batch ingestion** | 64 embeddings / 128 upserts per batch |

The pipeline is designed so that ingestion never blocks retrieval. You can search and ask questions while new documents are still being indexed.

---

## 🧠 Architecture: Spine-and-Worker

The system is built as a distributed microservice stack, a **Go API spine** for stability and concurrency, with a **Python worker** for the heavy AI/RAG logic.

| Service | Stack | Role |
|---------|-------|------|
| **API** | Go / Gin | Auth, rate limiting, CORS, reverse-proxy to Worker |
| **Worker** | Python / FastAPI | Ingestion, chunking, embedding, semantic search, LLM synthesis |
| **Qdrant** | Vector DB | 768-dim cosine similarity search with payload indexing |
| **Web UI** | React / Vite / TypeScript | Dark-mode interface with drag-and-drop, ask panel, document drawer |
| **Watcher** | Python daemon | Auto-ingests files dropped into `data/dropzone/` |

All five services are orchestrated via Docker Compose with health checks on every container.

---

## 🛠 Features

### Ingestion

- 📄 **Multi-format support** — TXT, MD, CSV, TSV, JSON, JSONL, HTML, PDF, DOCX
- 🎤 **Audio transcription** — WAV, MP3, M4A, FLAC, OGG via Whisper *(optional module)*
- 🖼️ **Image captioning** — BLIP-based caption extraction *(optional module)*
- 💬 **ChatGPT export parsing** — Dedicated parser for conversation-aware chunking
- 🗣️ **Transcript detection** — Auto-detects and structures dialogue formats
- 📂 **Dropzone watcher** — Daemon auto-ingests new files with configurable polling interval

### Search & Retrieval

- 🔍 **Semantic search** — Embedding-based similarity search across your entire corpus
- 🎯 **Scoped queries** — Filter by document, file path, content kind, or time range
- 🤖 **LLM synthesis** — Ollama-backed "Ask" mode with multi-source cross-referencing
- 🔧 **Model selection** — Choose any Ollama model for synthesis directly from the UI
- 📊 **Configurable depth** — Adjustable retrieval depth (`k`) for precision vs. breadth

### Data Management

- 📋 **Document inventory** — Browse, inspect, and manage all indexed documents
- 🗑️ **Deletion** — Remove documents from both chunk and image collections
- 📦 **Export** — Download indexed data as JSONL or ZIP archives
- 🔐 **Auth** — Bearer token authentication with `local` (open) and `strict` modes + rate limiting

### Developer Experience

- 🖥️ **Dark-mode-first UI** — Markdown-native rendering with theme toggle
- 📡 **Full-stack health checks** — `/health/full` verifies the entire API → Worker → Qdrant chain
- 📝 **Telemetry** — Structured JSONL logging with rotation and ingest activity tracking
- 🧪 **Smoke tests** — End-to-end and pre-commit validation scripts

---

## ⚡ Quickstart

### Prerequisites

- [Docker](https://www.docker.com/) and Docker Compose
- [Ollama](https://ollama.com/) running locally (for LLM synthesis)

**Pull the embedding model:**

```bash
ollama pull nomic-embed-text
```

### 1. Clone & Start

```bash
git clone https://github.com/Mugiwara555343/jsonify2ai.git
cd jsonify2ai
docker compose up --build -d
```

### 2. Access

| Endpoint | URL |
|----------|-----|
| **Web UI** | [http://localhost:5173](http://localhost:5173) |
| **API** | [http://localhost:8082](http://localhost:8082) |
| **Qdrant Dashboard** | [http://localhost:6333/dashboard](http://localhost:6333/dashboard) |

### 3. Verify

```bash
# Check full-stack health
curl http://localhost:8082/health/full

# Expected: {"ok":true,"api":true,"worker":true}
```

### 4. Ingest Your First File

Drop any supported file into `data/dropzone/` — the watcher daemon picks it up automatically. Or drag-and-drop directly in the Web UI.

---

## 🗺️ Roadmap

> Features that exist in code but are not yet polished, or are planned for future development.

| Feature | Status |
|---------|--------|
| Audio transcription (Whisper STT) | ⚙️ Code complete, requires optional deps (`requirements.audio.txt`) |
| Image captioning (BLIP) | ⚙️ Code complete, behind `IMAGES_CAPTION` flag |
| Hybrid search (vector + keyword) | 🔬 Qdrant text indexes created, full hybrid ranking in progress |
| Context depth slider in UI | 📐 Backend `k` parameter wired, UI slider planned |
| Multi-collection federation | 📐 Separate chunk/image collections exist, unified query coming |
| Streaming LLM responses | 📐 Planned |

---

## 📖 Philosophy

This project is the result of a **7-month solo intensive** at the intersection of local AI and data privacy. It represents a belief that consumer hardware not cloud APIs should be the default substrate for personal AI.

By treating LLMs as architectural partners rather than syntax generators, the focus has been on **system design, reliability, and scalability** over manual implementation.

The goal: prove that a single builder, using the right tools, can deploy production-grade AI infrastructure that rivals enterprise cloud solutions in accuracy, while keeping every byte on the user's machine.

---

## 📂 Documentation

- **[API Reference](docs/API.md)** — Endpoints, request/response schemas, auth
- **[Architecture Deep-Dive](docs/ARCHITECTURE.md)** — Service topology, data flow, design decisions
- **[Data Model](docs/DATA_MODEL.md)** — Chunk schema, Qdrant collections, payload structure
- **[Contracts](docs/contracts.md)** — API/Worker interface contracts
- **[Golden Path](docs/golden_path.md)** — End-to-end verification runbook

---

## ⚖️ License

MIT — Hack it, extend it, keep it local.
