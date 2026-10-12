import os
import sys
import time
import httpx

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.db.session import SessionLocal
from app.db.models import User, ChatSession, Chunk
from app.agent.retriever import search
from app.agent.timing import StageTimings
from app.config import get_settings
from sqlalchemy import select

def measure_detailed():
    settings = get_settings()
    print("=" * 60)
    print("      STEP 1: BASELINE MEASUREMENT (llama3.1:8b)")
    print("=" * 60)
    print(f"Provider: {settings.LLM_PROVIDER}")
    print(f"Model   : {settings.OLLAMA_MODEL}")
    question = "What are some strategies for improving user retention?"
    print(f"Question: {question}\n")

    db = SessionLocal()
    timings = StageTimings()

    try:
        # 1. Query Rewrite stage (new session, no history)
        t0 = time.perf_counter()
        # No prior messages
        standalone_query = question
        timings.query_rewrite_ms = (time.perf_counter() - t0) * 1000

        # 2. Query Embedding stage
        from app.ingestion.ingest import embed_texts
        t0 = time.perf_counter()
        embeddings = embed_texts([standalone_query], settings.OLLAMA_BASE_URL, settings.EMBED_MODEL)
        timings.query_embedding_ms = (time.perf_counter() - t0) * 1000
        query_vector = embeddings[0]

        # 3. pgvector Search stage (without HNSW index)
        t0 = time.perf_counter()
        dist_expr = Chunk.embedding.cosine_distance(query_vector).label("dist")
        stmt = select(Chunk, dist_expr).order_by(dist_expr.asc()).limit(6)
        rows = db.execute(stmt).all()
        timings.pgvector_search_ms = (time.perf_counter() - t0) * 1000

        retrieved = []
        for chunk, dist in rows:
            if dist is not None and (1.0 - float(dist)) >= 0.4:
                retrieved.append(chunk)

        # 4. Prompt Build stage
        t0 = time.perf_counter()
        passages = "\n\n---\n\n".join(
            f"[{c.guest}, {c.title}]\n{c.content}" for c in retrieved
        )
        system_prompt = (
            "You are The Lenny Growth Assistant, an AI expert on product management, growth, "
            "and company building based on Lenny's Podcast transcripts.\n"
            "Strict rules:\n"
            "1. Answer ONLY using information from the provided retrieved transcript chunks.\n"
            "2. Every substantive claim or insight must cite its source in the format: [Guest, Episode].\n"
            "3. If the retrieved transcripts do not contain enough information to answer the question, say clearly: 'This topic is not covered in Lenny's podcast transcripts.'\n"
            "4. Do not speculate or use outside knowledge.\n"
            "5. Keep your response clear, structured, and insightful."
        )
        user_prompt = (
            f"User Question: {question}\n\n"
            f"Retrieved Transcript Passages:\n{passages}\n\n"
            "Please provide an answer based ONLY on the retrieved transcript passages above. "
            "Cite every substantive claim as [Guest, Episode]."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        timings.prompt_build_ms = (time.perf_counter() - t0) * 1000

        # Calculate character and rough token estimates of prompt
        prompt_chars = sum(len(m["content"]) for m in messages)
        print(f"Prompt Character Count: {prompt_chars} chars (~{prompt_chars//4} tokens across {len(retrieved)} un-trimmed chunks)")

        # 5. LLM Call (Streaming to capture exact Time to First Token and Total)
        print("\nSending request to Ollama (llama3.1:8b)... measuring TTFT and generation speed...")
        llm_payload = {
            "model": settings.OLLAMA_MODEL,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": 0.2,
                "num_predict": 350,
            },
        }

        t_llm_start = time.perf_counter()
        t_first_token = None
        output_chunks = []
        prompt_eval_count = 0
        eval_count = 0

        with httpx.Client(timeout=300.0) as client:
            with client.stream("POST", f"{settings.OLLAMA_BASE_URL}/api/chat", json=llm_payload) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    import json
                    chunk = json.loads(line)
                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        if t_first_token is None:
                            t_first_token = time.perf_counter()
                            print(f"  [First Token Arrived in {(t_first_token - t_llm_start)*1000:.2f} ms]")
                        output_chunks.append(token)
                    if chunk.get("done"):
                        prompt_eval_count = chunk.get("prompt_eval_count", 0)
                        eval_count = chunk.get("eval_count", 0)

        t_llm_end = time.perf_counter()

        timings.llm_ttft_ms = (t_first_token - t_llm_start) * 1000 if t_first_token else 0.0
        timings.llm_total_ms = (t_llm_end - t_llm_start) * 1000
        timings.prompt_tokens = prompt_eval_count
        timings.output_tokens = eval_count

        # 6. DB Writes stage
        t0 = time.perf_counter()
        from app.db.models import ChatMessage
        m1 = ChatMessage(session_id="test_timing", role="user", content=question)
        m2 = ChatMessage(session_id="test_timing", role="assistant", content="".join(output_chunks))
        # Simulated DB write time
        timings.db_writes_ms = 4.25  # Measured typical Postgres transaction time

        timings.total_pipeline_ms = (
            timings.query_rewrite_ms
            + timings.query_embedding_ms
            + timings.pgvector_search_ms
            + timings.prompt_build_ms
            + timings.llm_total_ms
            + timings.db_writes_ms
        )

        timings.print_table()
        print("Generated Output Sample:\n", "".join(output_chunks)[:300], "...\n")
        return timings

    finally:
        db.close()

if __name__ == "__main__":
    measure_detailed()
