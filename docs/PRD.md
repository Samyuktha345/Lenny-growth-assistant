# Product Requirements Document (PRD)

## Product: The Lenny Growth Assistant

### 1. Executive Summary & Discovery Brief
"The Lenny Growth Assistant" is an AI-powered full-stack Retrieval-Augmented Generation (RAG) chat application built over Lenny's Podcast transcripts. It empowers product managers, growth leaders, founders, and operators to query actionable frameworks, benchmarks, tactical playbooks, and guest wisdom from over 300+ podcast episodes.

---

### 2. User & Problem Statement

#### Target Users
- **Startup Founders & CEOs**: Navigating product-market fit, pricing models, and organizational scaling (e.g. Founder Mode vs. Manager Mode).
- **Product Managers & VPs of Product**: Looking for proven frameworks on roadmapping, retention diagnostics, customer interviews, and metrics prioritization.
- **Growth Practitioners**: Searching for concrete loops (PLG, sales-led, content loops) and tactical advice from seasoned practitioners (Elena Verna, Casey Winters, Brian Balfour, etc.).

#### Problem Statement
- **Information Trapped in Transcripts**: Lenny's Podcast contains thousands of hours of high-signal interviews, but the archive is difficult to search semantically.
- **Hallucinations in Generic LLMs**: Standard foundation models invent growth metrics or misattribute advice. Users need grounded answers with explicit citations.
- **Lack of Synthesized Output**: Operators often need more than brief answers—they need structured executive summaries, framework cards, and publication-ready atomic essays (Ship 30 for 30 style).

---

### 3. Success Metrics

| Metric | Target | Description |
| :--- | :--- | :--- |
| **Citation Rate** | $\ge 95\%$ | Percentage of answers to covered growth questions that cite explicit `[Guest, Episode]` sources. |
| **"Not Covered" Precision** | $\ge 95\%$ | Accuracy of immediately recognizing out-of-scope or ungrounded questions without hallucinating. |
| **Fast-Path Latency** | $< 350\text{ ms}$ | Time to reply when retrieval yields 0 matching chunks (skipping LLM inference entirely). |
| **Essay Word Count Compliance** | $1,100 - 1,400\text{ words}$ | Adherence to Ship 30 for 30 atomic essay length with automated 1-shot retry logic. |
| **Provider Switch Friction** | 0 Code Changes | Seamless switching between local Ollama and cloud Anthropic via `.env`. |

---

### 4. Key Assumptions

1. **Local Demo Guarantee**: The system must run locally and self-contained using Ollama (`llama3` + `nomic-embed-text`) with zero reliance on cloud APIs if desired.
2. **PostgreSQL + pgvector**: Vector embeddings (768 dimensions for `nomic-embed-text`) and conversation state are persisted in PostgreSQL.
3. **Structured & Semi-Structured Transcripts**: Transcript files in `data/transcripts/` contain speaker turns (`Speaker: ...`) and frontmatter metadata (`title`, `guest`).
4. **Deterministic Security**: All generated HTML artifacts must be sanitized on the backend prior to persistence and rendered inside sandboxed iframes on the client.

---

### 5. Scope

#### Included in Scope
- **Storage & Vector Indexing**:
  - PostgreSQL schema with pgvector extension enabled.
  - Chunking pipeline preserving speaker turns (~500 tokens with 80 token overlap).
  - SHA-256 file hashing for re-runnable, idempotent ingestion.
- **Switchable LLM Architecture**:
  - Single `.env` switch between `ollama` and `anthropic`.
  - Automatic fallback to Ollama with a warning log if Anthropic API key is omitted.
  - Health check endpoint (`GET /health`) exposing active provider and model.
- **Agent & Reasoning Layer**:
  - Semantic retriever with cosine similarity thresholding (`min_score`).
  - Strict system prompt requiring answers derived ONLY from transcripts with `[Guest, Episode]` citations.
  - Conversational query rewriting for multi-turn pronoun resolution.
  - Fast-path short-circuit: immediately return `"This topic is not covered in Lenny's podcast transcripts."` if retrieval returns 0 chunks.
- **Artifacts Engine**:
  - Standalone artifact storage linked to messages.
  - `create_artifact` tool supporting one-pagers and framework cards (`markdown` or `html`).
  - Backend HTML sanitization using `bleach`.
  - Ship 30 for 30 essay generation tool (`write_ship30_essay`) adhering to [`backend/app/agent/skills/ship30.md`](file:///d:/oogway/backend/app/agent/skills/ship30.md) and returning as markdown artifacts.
- **React Frontend**:
  - Sidebar with session history and "+ New Chat" button.
  - Rich chat stream with markdown rendering and transcript source cards.
  - "Write Ship 30 essay from this answer" one-click action.
  - Right-side Artifact Pane with native Markdown viewer, sandboxed HTML iframe, clipboard copy, and file download.
  - Dynamic header badge showing active LLM provider and model.

#### Excluded from Scope
- Raw audio speech-to-text processing (transcripts are provided in `.md`/`.txt`).
- Multi-user authentication, JWT sessions, or payment gateways.
- Real-time streaming audio playback or video embedding.
- External web scraping outside the local transcript repository.
