PROJECT INSTRUCTION SCHEMA

(Use <PROJECT_NAME> until we lock a name)
0) Mission (one line)

Ingest mixed‑media data → normalize to structured JSON → embed → store → search & ask privately using local/edge LLMs.

Non‑goals (MVP): multi‑tenant auth, billing, fine‑tuning loops, heavy GPU training.
1) Roles & Operating Mode

    You (Mau): Product lead. Approves scope, kicks off tasks, runs docker, posts errors/logs.

    Me (Planner/Brain): Architecture, sequencing, guardrails, reviews. I write the prompts you feed to Cursor/Continue.

    Cursor / Continue.dev: Code generation + edits. Follows our prompts exactly; no scope creep.

    Reality checks: After each milestone, run smoke tests; paste logs to me for next moves.

2) System Boundaries (MVP)

    web/ (React + TS): upload, search, ask, preview sources.

    api/ (Go + Gin/Fiber): REST; owns Postgres/Qdrant/Ollama clients; orchestrates worker jobs.

    worker/ (Python + FastAPI): AI tasks (note2json parsing, image captioning, embeddings).

    Data stores: Postgres (metadata), Qdrant (vectors).

    Local LLM: Ollama (llama3.1‑8B) via HTTP.

Dataflow:
Upload → API saves → API calls Worker → Worker parses/captions/embeds → Postgres/Qdrant → Search/Ask via API → UI.
3) Tech Choices

    Embeddings: BAAI/bge-small-en-v1.5 (dim=384) or all-MiniLM-L6-v2.

    Image→Text: Salesforce/blip-image-captioning-base.

    Text parsing: your note2json as a library.

    Infra: Docker Compose; reuse your existing ollama, qdrant, postgres volumes.

4) Repo Layout

<PROJECT_NAME>/
  docker-compose.yml
  .env.example
  Makefile
  api/        # Go service
  worker/     # Python FastAPI service
  web/        # React + TS
  db/migrations/  # SQL
  docs/      # ADRs, decisions, API spec, runbooks

5) Environment & Wiring

    Reuse existing containers:

        OLLAMA_URL=http://host.docker.internal:11434

        QDRANT_URL=http://host.docker.internal:6333

        POSTGRES_URL=postgres://user:pass@host.docker.internal:5432/dbname?sslmode=disable

    Or run our own via compose if yours aren’t up.

Rule: They’re env‑driven; no hardcoded URLs.
6) Definition of Done (per feature)

    Code compiles, container builds, service starts.

    Unit test or smoke test added.

    API contracts documented in docs/api.md.

    Manual demo path recorded in docs/demo.md (copy‑paste commands).

    No secrets in repo; .env only.

7) Git & CI Discipline

    Branch per task: feat/*, chore/*, fix/*.

    Conventional commits.

    PR template with: Goal, Changes, How to test, Screenshots/logs.

    CI (later): build api/worker/web, run unit tests, docker compose config lint.

8) Prompt Patterns (for Cursor/Continue)

Use these patterns to keep Cursor focused.
A. Scaffold service

    Create a Go Gin service in api/ with GET /health. Read env for POSTGRES_URL, QDRANT_URL, OLLAMA_URL. Add clients with interfaces and stubs. Provide Dockerfile and make run.

B. Implement endpoint with contract

    Modify api/internal/routes/upload.go: implement POST /upload accepting multipart file. Save to /data/documents/<uuid>/. Detect mime. Insert into Postgres (documents table). Return {document_id}. Add unit test for mime detection.

C. Worker job

    Add worker/app/routers/process.py endpoints:

        POST /process/text {document_id, text, path} → call note2json lib → chunk (~800 chars, 100 overlap) → embed → upsert Qdrant (collection <PROJECT_NAME>_chunks, cosine, dim=384).

        POST /process/image {document_id, path} → BLIP caption → embed caption → upsert Qdrant (collection <PROJECT_NAME>_images).
        Return IDs written. Include minimal error handling and logging.

D. Search

    Add GET /search?q= in api/:

        Embed query in Go (call worker /embed or embed client if we keep it in worker).

        Query Qdrant top-k (k=5).

        Return {results:[{kind, score, text, caption, snippet, document_id, source_path}]}.

E. Ask

    Add POST /ask:

        Body {query} → call /search (k=8) → build prompt with citations → stream answer from Ollama → return {answer, sources}.

        Provide a system prompt template in api/internal/prompts/ask.tmpl.

F. Web UI wiring

    Create Vite React app with pages: Upload, Search, Ask.

        Upload: drag&drop → POST /upload → polls status.

        Search: list results with snippet + open source.

        Ask: shows streaming answer + sources.

G. LORA export (stretch)

    Add POST /export/lora with selection of images → produce JSONL {image_path, caption} and zip download.

9) Database Schema (SQL migration)

-- 0001_init.sql
CREATE TABLE documents (
  id UUID PRIMARY KEY,
  filename TEXT NOT NULL,
  kind TEXT CHECK (kind IN ('text','image','pdf','audio')) NOT NULL,
  size_bytes BIGINT,
  mime TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE chunks (
  id UUID PRIMARY KEY,
  document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
  idx INT NOT NULL,
  text TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE images (
  id UUID PRIMARY KEY,
  document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
  path TEXT NOT NULL,
  caption TEXT,
  tags TEXT[],
  created_at TIMESTAMPTZ DEFAULT now()
);

(Vectors stored in Qdrant; keep IDs in Postgres.)
10) Initial Backlog (strict order)

Phase 0 – Boot skeleton (Day 0–1)

    Repo + compose + env + Makefile.

    api/ health; worker/ health; web/ hello; verify all three containers talk to existing Postgres/Qdrant/Ollama.

Phase 1 – Ingest + Text path (Day 2–4)
3. /upload saves text/md/txt; inserts documents.
4. Worker /process/text: note2json → chunk → embed → upsert Qdrant.
5. GET /search returns hits.
6. POST /ask streams Ollama response with sources.
7. Web: Upload + Search + Ask minimal.

Phase 2 – Images (Day 5–7)
8. /upload accepts images; images table.
9. Worker /process/image: BLIP caption → embed → upsert.
10. Web: preview captions; filter kind.

Phase 3 – UX polish + LORA export (Week 2)
11. Batch ingest folder; progress.
12. Export JSONL for LORA (image_path, caption).
13. Source preview (open file), copy citations.

Phase 4 – PDFs & Whisper (Week 3–4, stretch)
14. PDF text + page images pipeline.
15. Whisper small for audio → text → same path as text.
11) Smoke Tests (copy/paste)

After Phase 1:

# text
curl -F "file=@README.md" http://localhost:8080/upload
# => {"document_id":"..."}
curl "http://localhost:8080/search?q=installation"
curl -X POST http://localhost:8080/ask -H "content-type: application/json" -d '{"query":"How do I install it?"}'

After Phase 2:

# image
curl -F "file=@sample.jpg" http://localhost:8080/upload
curl "http://localhost:8080/search?q=cat with sunglasses"

12) Coding Standards / Guardrails

    Go: idiomatic, context-aware, structured logs, no global singletons; interfaces over concrete types for clients.

    Python: FastAPI, pydantic models, lazy model loading, batch embedding endpoints.

    React: shadcn/ui, TanStack Query, fetch wrapper, .env‑driven API base.

    Error handling: return typed JSON errors; never panic/print stack to client.

    Security: no user auth (MVP), but never execute user prompts as code; path traversal safe file writes.

13) Devil’s Advocate (keep us honest)

    Is Qdrant necessary? Yes, because semantic search is core; Postgres FTS won’t cover images/embeddings.

    Will CPU models be too slow? Acceptable for MVP; we choose small models; can swap to GPU later.

    Is Ollama sufficient for Q&A quality? For private/local MVP, yes; we can add an OpenAI/Bedrock toggle later.

14) Handshake Loop (how we work)

    You paste the relevant Prompt Pattern to Cursor/Continue.

    Run docker compose up -d and smoke test.

    Paste failures/logs here; I triage and give the next surgical prompt.

    Merge small PRs often; keep momentum.

15) Name (placeholder)

Keep <PROJECT_NAME> for now. We’ll lock a short, brandable name before we publish the repo. (Candidates we liked: note2vec, file2facts, doc2mind, vectorize, Loom.)
Ready-to-Start Prompts (use these first)

Init the repo & compose

    Create a monorepo with web/, api/, worker/, db/migrations/, root docker-compose.yml, .env.example, and Makefile. Compose should reference existing local services via host.docker.internal unless env overrides are provided. Add placeholder Dockerfiles for each service and a README in each folder explaining how to run it locally.

API health + Upload skeleton

    In api/, scaffold a Go service with Gin, GET /health returning OK. Add env config for POSTGRES_URL, QDRANT_URL, OLLAMA_URL. Implement POST /upload (multipart) that saves the file to /data/documents/<uuid>/ and inserts a row into documents. Return {document_id}. Provide Dockerfile and make run.

Worker health + text process

    In worker/, scaffold FastAPI with GET /health. Implement POST /process/text which accepts {document_id, text, path}; call note2json (library) to normalize; chunk; embed with BAAI/bge-small-en-v1.5; upsert vectors to Qdrant; write chunks to Postgres. Return IDs written. Provide Dockerfile and uvicorn run cmd.