# jsonify2ai – Live Demo Script

A step-by-step guide to demonstrate jsonify2ai in ~5–7 minutes.

---

## Prereqs

- Git installed
- Docker Desktop installed and running
- Terminal/command prompt ready

**Clone and enter:**
```bash
git clone https://github.com/Mugiwara555343/jsonify2ai.git
cd jsonify2ai
```

---

## Start the system

**Windows (PowerShell):**
```powershell
scripts/start_all.ps1
```

**macOS / Linux:**
```bash
./scripts/start_all.sh
```

**Wait for services to start** (about 30–60 seconds). You should see:
- Web UI: http://localhost:5173
- API: http://localhost:8082

**Note:** In `AUTH_MODE=local` (default), no API tokens are required. Everything works out of the box.

---

## Load demo data (fast path)

1. Open http://localhost:5173 in your browser
2. Scroll to the upload section
3. Click **"Load demo data"** button
4. Wait for the toast messages: "Loading demo doc 1/3...", "Loading demo doc 2/3...", "Loading demo doc 3/3..."
5. You should see: "Demo data loaded ✓"

**What gets created:**
- `demo_qdrant.md` – Explains Qdrant usage (vector DB, 768-dim embeddings, semantic search)
- `demo_export.md` – Describes Export JSON and Export ZIP features
- `demo_env_toggles.md` – Lists environment variables for dev/testing

These three tiny docs are now indexed and searchable, just like any uploaded file.

---

## Inspect the JSON

1. Scroll down to the **Documents** section
2. You should see 3 documents (or more if you had existing data)
3. Find one of the demo docs (look for `demo_qdrant.md`, `demo_export.md`, or `demo_env_toggles.md` in the path)
4. Click **"Preview JSON"** on that document

**What you'll see:**
- A preview panel showing 5 lines of JSONL
- Each line is one chunk with fields:
  - `id`: Unique chunk identifier
  - `document_id`: Links chunks to the source document
  - `kind`: Content type (text, image, etc.)
  - `path`: Source file path
  - `idx`: Chunk index within the document
  - `text`: The actual chunk content
  - `meta`: Additional metadata

**Key point:** This is exactly what gets stored in Qdrant. The JSON preview shows you the raw data structure.

---

## Ask your data

1. Scroll to the **Ask** section
2. Click one of the example questions:
   - "What is Qdrant used for in this repo?"
   - "Which env toggles enable dev modes?"
   - "How do I export a ZIP for a document?"
3. Or type your own question
4. Press **Ask** (or Enter)

**What you'll see:**

**If LLM is enabled (Ollama running):**
- **Answer** block with a synthesized answer and "local (ollama)" badge
- **Sources** section below showing matching snippets with:
  - Filename (e.g., `demo_qdrant.md`)
  - Document ID (truncated)
  - Score (relevance score)
  - Snippet text

**If LLM is disabled:**
- **Answer** block with "Top matches below" badge (or summary)
- **Sources** section showing matching snippets (same as above)

**Key point:** Ask works even without LLM. It returns semantic search results (sources) as the baseline. LLM synthesis is a bonus that adds a natural-language answer on top.

---

## Export

1. In the **Documents** section, find a demo document
2. Click **"Export JSON"**
   - Downloads `chunks.jsonl` (or `images.jsonl` for images)
   - Open it in a text editor to see all chunks
3. Click **"Export ZIP"**
   - Downloads `export_<document_id>.archive.zip`
   - Extract it to see:
     - `export_<document_id>.jsonl` – All chunks
     - `manifest.json` – Document metadata (paths, counts, kinds)
     - Original source file (if available)

**Key point:** Export gives you a complete snapshot of what's indexed. The manifest.json shows document-level metadata, while the JSONL shows chunk-level data.

---

## Shut down

**Windows (PowerShell):**
```powershell
scripts/stop_all.ps1
```

**macOS / Linux:**
```bash
./scripts/stop_all.sh
```

**Optional:** To wipe all data (start fresh):
```powershell
# Windows
scripts/stop_all.ps1 --wipe
```

```bash
# macOS / Linux
./scripts/stop_all.sh --wipe
```

---

## Quick Tips

- **No data?** Use "Load demo data" to get started instantly
- **Want to see raw data?** Use Preview JSON on any document
- **Testing Ask?** The example questions are designed to match the demo docs
- **Local mode:** No tokens needed – everything works immediately after `start_all`
- **LLM optional:** Ask returns sources even without Ollama; LLM just adds synthesis

---

**Total demo time:** ~5–7 minutes

**Next steps:** Upload your own files, try different search queries, or explore the API at http://localhost:8082 (see `docs/API.md` for details).
