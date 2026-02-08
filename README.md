<p align="center">
  <img src="docs/jsonify2ai_logo.png" alt="Jsonify2AI logo" width="165"/>
</p>

### Local-First AI Memory Architecture & High-Capacity RAG Pipeline

---

[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
![OS](https://img.shields.io/badge/tested-Linux%20%7C%20macOS%20%7C%20Windows-lightblue)
[![CI](https://github.com/Mugiwara555343/jsonify2ai/actions/workflows/ci.yml/badge.svg)](https://github.com/Mugiwara555343/jsonify2ai/actions/workflows/ci.yml)
[![GitHub](https://img.shields.io/badge/GitHub-Follow-black?logo=github)](https://github.com/Mugiwara555343)

**Jsonify2ai** is a high-performance system designed to solve the "local memory" problem for LLMs. It transforms fragmented, messy local data into a structured, searchable, and synthesized intelligence layer—running entirely on consumer hardware with zero cloud dependency.

---

## 🚀 The Engineering Challenge: Scaling Local RAG
Most RAG implementations fail when the dataset exceeds a few pages. This project was built to push the limits of local retrieval:
- **The 400K Milestone:** Successfully engineered to ingest and process **400,000+ character datasets** (~100k tokens) locally without precision loss.
- **Multi-Source Synthesis:** Orchestrates the LLM to cross-reference multiple disparate documents simultaneously to generate high-fidelity, grounded responses.
- **Microservice Orchestration:** Built as a distributed system with a **Go API** for high-concurrency stability and a **Python/FastAPI worker** for specialized AI/RAG logic.

---

## 🧠 Technical Architecture
The system is built on a "Spine-and-Worker" model, ensuring that ingestion doesn't block retrieval performance.



1. **API (Go):** Handles the stable HTTP surface, authentication, and upload proxying.
2. **Worker (Python):** Manages the heavy lifting—type detection, chunking, 768-dim embedding, and Qdrant I/O.
3. **Vector Core (Qdrant):** Provides semantic retrieval with deterministic IDs, ensuring the system is **idempotent** (re-ingesting the same file produces zero duplicates).
4. **Local Runtime (Ollama):** Optional synthesis layer for fully offline "Ask" workflows.

---

## 🛠 Features for Real-World Data
- ** Advanced Ingestion:** Support for TXT, MD, PDF, CSV, HTML, and DOCX, with optional modules for Audio and Images.
- ** Chat-Aware Processing:** Specialized parsers for ChatGPT exports and generic transcripts, allowing the LLM to understand conversational context.
- ** Production-Grade Reliability:** Built-in **smoke verify scripts** and health checks to ensure API, worker, and database liveness.
- ** Local Sovereignty:** Data never leaves your hardware. Full control over models and provenance.

---

## ⚡ Quickstart: Docker Compose
The recommended way to run the stack for environment parity and consistent service communication.

### 1. Clone & Initialize
```bash
git clone [https://github.com/Mugiwara555343/jsonify2ai.git](https://github.com/Mugiwara555343/jsonify2ai.git)
cd jsonify2ai
```
### 2. Start the Stack
Windows:
```
.\scripts\start_all.ps1  
```
Linux/macOS: 
```
./scripts/start_all.sh
```
### 3. Access

Web UI: 
```
http://localhost:5173
```
Verify Liveness: 
```
.\scripts\smoke_verify.ps1
```

---

## 📝 Philosophy & Build Journey
This project is the result of a **7-month solo intensive** focused on the intersection of local AI and data privacy. 

It represents a transition from "traditional" coding to **AI-Collaborative Engineering**. By treating LLMs as high-level architectural partners, I’ve bypassed manual syntax grinding to focus on **System Design, Reliability, and Scalability**. 

The goal was to prove that a single builder, using the right tools, can deploy production-grade AI infrastructure that rivals enterprise cloud solutions in accuracy and privacy.

---

## 📂 Documentation
- **[API Reference](docs/API.md)** | **[Architecture Deep-Dive](docs/ARCHITECTURE.md)** | **[Data Model](docs/DATA_MODEL.md)**

## ⚖️ License
MIT — Hack it, extend it, keep it local.
  