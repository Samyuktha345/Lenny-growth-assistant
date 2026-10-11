# The Lenny Growth Assistant

A full-stack RAG chat application over **Lenny's Podcast transcripts**, built with **Python 3.11**, **FastAPI**, **SQLAlchemy 2.0**, **PostgreSQL + pgvector**, and a **React (Vite) + Tailwind CSS** frontend.

Features Claude Agent SDK-style tool-calling with two core tools:
1. `search_transcripts`: Semantic search with pgvector cosine distance over podcast chunks.
2. `write_ship30_essay`: Publication-ready 1,250-word atomic essays adhering to the **Ship 30 for 30** methodology, returned as interactive markdown artifacts.

---

## Architecture & Layout

```
.
├── backend/
│   ├── app/
│   │   ├── config.py          # pydantic-settings configuration
│   │   ├── main.py            # FastAPI entry point, CORS, error handling
│   │   ├── db/                # SQLAlchemy models & pgvector connection
│   │   ├── ingestion/         # Transcript parser, speaker turn chunker & embedder
│   │   ├── llm/               # Switchable LLM layer (Ollama / Anthropic Claude)
│   │   ├── agent/             # Agent loop, retriever, essay tool & HTML sanitizer
│   │   └── api/               # Pydantic schemas and REST routes
│   └── tests/                 # Automated pytest suite (35+ unit & integration tests)
├── frontend/                  # React (Vite) + Tailwind CSS UI
├── data/
│   └── transcripts/           # .md and .txt transcript archive
├── evals/
│   ├── questions.json         # 20 evaluation questions (16 covered, 4 out-of-scope)
│   └── run_eval.py            # Evaluation harness (citation rate & not-covered accuracy)
├── docs/
│   └── PRD.md                 # Product Requirements Document & Discovery Brief
└── docker-compose.yml         # PostgreSQL 16 with pgvector extension
```

---

## 1. Quickstart & Setup

### Prerequisites
- **Python 3.11+**
- **Node.js 18+** & npm
- **Docker Desktop** (for PostgreSQL + pgvector)
- **Ollama** (for local demo embedding & inference)

### 1.1 Start PostgreSQL with pgvector
From the repository root:
```bash
docker compose up -d
```
*(Postgres runs on port `5432`, DB `lenny_growth`, user/password `postgres:postgres`)*

### 1.2 Backend Environment Setup
```bash
cd backend

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

## 2. Ollama Setup & Commands (Local Demo)

The application uses Ollama locally for both text embeddings (`nomic-embed-text`, 768 dimensions) and text generation (`llama3`).

### 2.1 Install & Start Ollama
Download and install Ollama from [ollama.com](https://ollama.com). Ensure the service is running:
```bash
ollama serve
```

### 2.2 Pull Required Models
```bash
# Embedding model for pgvector (mandatory for ingestion and retrieval)
ollama pull nomic-embed-text

# Generation model (for local chat and Ship 30 essays)
ollama pull llama3
```

---

## 3. Transcript Ingestion

The ingestion pipeline parses `.md` and `.txt` files from `data/transcripts/`, extracts guest and episode metadata, chunks content into ~500 token windows preserving speaker turns, computes vector embeddings, and stores them in PostgreSQL with pgvector.

### 3.1 Run Ingestion
From the `backend` directory:
```bash
python -m app.ingestion.ingest
```

### 3.2 How to Refresh Transcripts
1. Clone or copy new transcript files (`.md` or `.txt`) into `data/transcripts/`.
2. Re-run `python -m app.ingestion.ingest`.
3. **Re-runnable & Idempotent**: The ingest script computes a SHA-256 hash for every file. Unchanged files are automatically skipped, while updated files have their old chunks replaced seamlessly.

---

## 4. Switching LLM Providers & Fallback Behavior

The LLM layer is dynamically switchable via `.env` without any code changes.

### 4.1 Local Ollama (Default)
In `backend/.env`:
```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3
EMBED_MODEL=nomic-embed-text
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/lenny_growth
```

### 4.2 Cloud Anthropic Claude
To switch to Claude:
```env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-api03-...
ANTHROPIC_MODEL=claude-3-5-sonnet-20241022
```

### 4.3 Automatic Fallback Behavior
If `LLM_PROVIDER=anthropic` is configured but `ANTHROPIC_API_KEY` is missing or blank:
- The system logs a warning:
  `WARNING: Anthropic selected as LLM_PROVIDER but ANTHROPIC_API_KEY is not set. Falling back to Ollama.`
- It automatically falls back to `OllamaClient` to ensure zero downtime.
- Check active provider and model anytime at `GET /health`.

---

## 5. Running the Application

### 5.1 Start Backend (FastAPI)
```bash
cd backend
.venv\Scripts\uvicorn.exe app.main:app --reload --port 8000
```
API Documentation is available at:
- **Swagger UI**: `http://localhost:8000/docs`
- **Health Check**: `http://localhost:8000/health`

### 5.2 Start Frontend (React + Vite)
In a separate terminal:
```bash
cd frontend
npm install
npm run dev
```
Open **http://localhost:5173** in your browser.

---

## 6. Testing & Evaluation

### 6.1 Backend Test Suite
Run the comprehensive automated pytest suite covering health, sessions, chat, retriever, LLM factory, Ship 30 essay, and HTML sanitizer:
```bash
cd backend
pytest -v
```

### 6.2 Running the Handover Evaluation Suite
Run the 20-question evaluation benchmark (16 in-scope growth questions, 4 out-of-scope questions):
```bash
# Standalone evaluation simulation:
python evals/run_eval.py

# Live evaluation against running backend & database:
python evals/run_eval.py --live
```
Metrics reported:
- **Citation Rate (Covered)**: Verifies answers cite `[Guest, Episode]`.
- **"Not Covered" Accuracy**: Verifies out-of-scope questions cleanly trigger the fast-path `"This topic is not covered in Lenny's podcast transcripts."` without hallucinating.
