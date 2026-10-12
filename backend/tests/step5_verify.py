import json
import re
import sys
import time
from pathlib import Path
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

API_BASE = "http://localhost:8000"

def run_step5_verification():
    print("=" * 70)
    print("STEP 5 VERIFICATION: LATENCY, GROUNDING, STREAMING & FALLBACK")
    print("=" * 70)

    # 1. Login user
    login_res = httpx.post(f"{API_BASE}/users/login", json={"name": "Perf Verifier", "email": "perf@growth.co"}, timeout=10.0)
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    user = login_res.json()
    user_id = user["id"]
    headers = {"X-User-Id": user_id}
    print(f"Logged in user: {user['name']} (ID: {user_id})\n")

    # 2. Test Questions
    # Session 1: Q1, Q2 (with follow-up Q3)
    sess1_res = httpx.post(f"{API_BASE}/sessions", json={}, headers=headers, timeout=10.0)
    sess1_id = sess1_res.json()["id"]

    # Session 2: Out of scope
    sess2_res = httpx.post(f"{API_BASE}/sessions", json={}, headers=headers, timeout=10.0)
    sess2_id = sess2_res.json()["id"]

    # Session 3: Elena Verna
    sess3_res = httpx.post(f"{API_BASE}/sessions", json={}, headers=headers, timeout=10.0)
    sess3_id = sess3_res.json()["id"]

    queries = [
        {"session_id": sess1_id, "label": "Q1: User Retention", "question": "What are some strategies for improving user retention?", "is_oos": False},
        {"session_id": sess1_id, "label": "Q2: Follow-up Pronoun", "question": "What did the second guest say?", "is_oos": False},
        {"session_id": sess2_id, "label": "Q3: Out of Scope", "question": "What is quantum gravity and string theory?", "is_oos": True},
        {"session_id": sess3_id, "label": "Q4: Founder Mode", "question": "What did Brian Chesky say about founder mode?", "is_oos": False},
        {"session_id": sess3_id, "label": "Q5: Elena Verna PLG Loops", "question": "How does Elena Verna recommend structuring product-led growth loops?", "is_oos": False},
    ]

    results = []

    for item in queries:
        s_id = item["session_id"]
        q = item["question"]
        label = item["label"]
        print(f"--- Running {label} ---")
        print(f"Question: \"{q}\"")

        t0 = time.perf_counter()
        ttft = None
        full_text = ""
        sources = []
        first_token_time = None

        with httpx.Client(timeout=90.0) as client:
            with client.stream(
                "POST",
                f"{API_BASE}/sessions/{s_id}/chat",
                json={"message": q, "stream": True},
                headers={**headers, "Accept": "text/event-stream"},
            ) as response:
                assert response.status_code == 200, f"Chat stream failed: {response.status_code}"

                for line in response.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if not data_str:
                        continue
                    try:
                        ev = json.loads(data_str)
                        ev_type = ev.get("type")
                        if ev_type == "token":
                            tok = ev.get("token", "")
                            if first_token_time is None and tok.strip():
                                first_token_time = time.perf_counter()
                                ttft = (first_token_time - t0) * 1000
                                print(f"[First token at {ttft/1000:.2f}s] ", end="", flush=True)
                            print(tok, end="", flush=True)
                            full_text += tok
                        elif ev_type == "sources":
                            sources = ev.get("sources", [])
                        elif ev_type == "done":
                            if not full_text:
                                full_text = ev.get("reply", "")
                            if not sources:
                                sources = ev.get("sources", [])
                    except Exception as e:
                        print("JSON parse error:", e)

        total_time_ms = (time.perf_counter() - t0) * 1000
        if ttft is None:
            ttft = total_time_ms

        # Check citations
        has_numbered_citations = bool(re.search(r"\[\d+\]", full_text))
        has_sources_section = "### Sources" in full_text or "Sources" in full_text
        has_guest_ep_citations = bool(re.search(r"\[[\w\s\.\-']+,[\w\s\.\-']+\]", full_text))

        ttft_s = ttft / 1000.0
        total_s = total_time_ms / 1000.0
        pass_ttft = ttft_s < 10.0
        pass_total = total_s < 60.0

        print(f"TTFT: {ttft_s:.2f}s | Total: {total_s:.2f}s | TTFT Target (<10s): {'PASS' if pass_ttft else 'FAIL'} | Total Target (<60s): {'PASS' if pass_total else 'FAIL'}")
        print(f"Sources count: {len(sources)} | Numbered Citations: {has_numbered_citations} | Sources Section: {has_sources_section}")
        print(f"Snippet: {full_text[:120].replace(chr(10), ' ')}...\n")

        results.append({
            "label": label,
            "question": q,
            "ttft_ms": round(ttft, 1),
            "total_ms": round(total_time_ms, 1),
            "ttft_s": round(ttft_s, 2),
            "total_s": round(total_s, 2),
            "pass_ttft": pass_ttft,
            "pass_total": pass_total,
            "sources_count": len(sources),
            "has_numbered_citations": has_numbered_citations,
            "full_reply": full_text,
        })

    # 3. Stopped Ollama Fallback Simulation
    print("--- Testing Stopped Ollama Fallback Simulation ---")
    from app.agent.agent import build_extractive_fallback, search_transcripts
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        retrieved = search_transcripts("What are retention strategies?", db=db, k=3)
        fallback_reply = build_extractive_fallback(retrieved)
        print("Fallback generated successfully:")
        print(fallback_reply[:200].replace("\n", " "))
        assert "extractive quick summary" in fallback_reply
        assert "### Sources" in fallback_reply
        assert "[1]" in fallback_reply
        print("Fallback test: PASS\n")
    finally:
        db.close()

    return results

if __name__ == "__main__":
    run_step5_verification()
