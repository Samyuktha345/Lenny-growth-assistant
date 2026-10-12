import os
import sys
import time
import httpx
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.db.session import SessionLocal
from app.db.models import Chunk, ChatMessage, User, ChatSession
from app.ingestion.ingest import embed_texts
from app.config import get_settings
from sqlalchemy import select

def step1_measure():
    settings = get_settings()
    question = "What are some strategies for improving user retention?"
    print(f"=== STEP 1 MEASUREMENT ===")
    print(f"Question: {question}")
    print(f"Model: {settings.OLLAMA_MODEL}")

    # Stage 1: Query Embedding
    t0 = time.perf_counter()
    embeddings = embed_texts([question], settings.OLLAMA_BASE_URL, settings.EMBED_MODEL)
    t_embed = (time.perf_counter() - t0) * 1000
    query_vector = embeddings[0]

    # Stage 2: pgvector search
    db = SessionLocal()
    try:
        t0 = time.perf_counter()
        dist_expr = Chunk.embedding.cosine_distance(query_vector).label("dist")
        stmt = select(Chunk, dist_expr).order_by(dist_expr.asc()).limit(6)
        rows = db.execute(stmt).all()
        t_search = (time.perf_counter() - t0) * 1000

        retrieved = []
        for chunk, dist in rows:
            if dist is not None and (1.0 - float(dist)) >= 0.4:
                retrieved.append(chunk)

        # Stage 3: Prompt build
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
        t_prompt_build = (time.perf_counter() - t0) * 1000

        prompt_chars = sum(len(m["content"]) for m in messages)
        print(f"Passages count: {len(retrieved)} | Prompt chars: {prompt_chars}")

        # Stage 4: Ollama Time to First Token and Total
        payload = {
            "model": settings.OLLAMA_MODEL,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": 0.2,
                "num_predict": 150, # Capped at 150 to get real ms and tok/s without hitting 180s
            },
        }

        t_llm_start = time.perf_counter()
        t_first_token = None
        output_tokens = 0
        prompt_tokens = 0
        tokens = []

        with httpx.Client(timeout=180.0) as client:
            with client.stream("POST", f"{settings.OLLAMA_BASE_URL}/api/chat", json=payload) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    txt = data.get("message", {}).get("content", "")
                    if txt:
                        if t_first_token is None:
                            t_first_token = time.perf_counter()
                        tokens.append(txt)
                    if data.get("done"):
                        prompt_tokens = data.get("prompt_eval_count", 0)
                        output_tokens = data.get("eval_count", 0)

        t_llm_end = time.perf_counter()
        ttft_ms = (t_first_token - t_llm_start) * 1000 if t_first_token else 0.0
        llm_total_ms = (t_llm_end - t_llm_start) * 1000

        # Stage 5: DB Writes
        t0 = time.perf_counter()
        user = db.query(User).first()
        sess = db.query(ChatSession).first()
        if user and sess:
            msg1 = ChatMessage(session_id=sess.id, role="user", content=question)
            msg2 = ChatMessage(session_id=sess.id, role="assistant", content="".join(tokens))
            db.add(msg1)
            db.add(msg2)
            db.commit()
        t_db = (time.perf_counter() - t0) * 1000

        total_ms = t_embed + t_search + t_prompt_build + llm_total_ms + t_db

        print("\n" + "=" * 55)
        print("          STAGE LATENCY BREAKDOWN (Step 1)")
        print("=" * 55)
        print(f"Query Embedding        : {t_embed:>10.2f} ms")
        print(f"pgvector Search        : {t_search:>10.2f} ms")
        print(f"Prompt Build           : {t_prompt_build:>10.2f} ms")
        print(f"Ollama TTFT            : {ttft_ms:>10.2f} ms")
        print(f"Ollama Total           : {llm_total_ms:>10.2f} ms")
        print(f"DB Writes              : {t_db:>10.2f} ms")
        print("-" * 55)
        print(f"Total Pipeline         : {total_ms:>10.2f} ms ({total_ms/1000:.2f} s)")
        print(f"Prompt Tokens          : {prompt_tokens:>10}")
        print(f"Output Tokens          : {output_tokens:>10}")
        if output_tokens > 0:
            gen_time_s = (t_llm_end - t_first_token)
            speed = output_tokens / gen_time_s if gen_time_s > 0 else 0
            print(f"Generation Speed       : {speed:>10.2f} tok/s")
        print("=" * 55 + "\n")

    finally:
        db.close()

if __name__ == "__main__":
    step1_measure()
