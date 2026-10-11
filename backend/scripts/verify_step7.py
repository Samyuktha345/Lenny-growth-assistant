import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collections.abc import Generator
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from app.agent.agent import NOT_COVERED_REPLY, rewrite_query
from app.agent.retriever import SearchResult
from app.db.models import Base, ChatMessage
from app.db.session import get_db
from app.llm.base import LLMResponse
from app.main import app

sqlite_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=sqlite_engine
)
Base.metadata.tables["chat_sessions"].create(bind=sqlite_engine)
Base.metadata.tables["chat_messages"].create(bind=sqlite_engine)


def override_get_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def run_verification():
    print("--- 1. Testing Session Creation ---")
    res = client.post("/sessions", json={"user_name": "Growth Lead"})
    assert res.status_code == 201, f"Expected 201, got {res.status_code}"
    session_id = res.json()["id"]
    print(f"Created session: {session_id}")

    print("\n--- 2. Testing Empty Retrieval Fast-Path (Skip LLM) ---")
    with patch("app.agent.agent.search_transcripts", return_value=[]):
        res = client.post(
            f"/sessions/{session_id}/chat",
            json={"message": "What is quantum gravity?"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["reply"] == NOT_COVERED_REPLY
        assert data["sources"] == []
        print(f"Reply: {data['reply']}")
        print(f"Sources count: {len(data['sources'])} (LLM call skipped)")

    print("\n--- 3. Testing Follow-up Query Rewriting ---")
    history = [
        ChatMessage(id=1, session_id=session_id, role="user", content="Tell me about Brian Chesky"),
        ChatMessage(id=2, session_id=session_id, role="assistant", content="Brian Chesky is the CEO of Airbnb."),
    ]
    mock_llm = MagicMock()
    mock_llm.chat.return_value = LLMResponse(content="What did Brian Chesky say about founder mode?")
    rewritten = rewrite_query("What did he say about founder mode?", history, mock_llm)
    assert rewritten == "What did Brian Chesky say about founder mode?"
    print(f"Original: 'What did he say about founder mode?'")
    print(f"Rewritten query: '{rewritten}'")

    print("\n--- 4. Testing Retrieval with Citations & Sources Persistence ---")
    mock_chunk = SearchResult(
        text="Founders must stay in the details of the product, especially during crucial inflection points.",
        episode_title="Founder Mode",
        guest="Brian Chesky",
        source_file="brian.md",
        similarity_score=0.91,
    )
    with (
        patch("app.agent.agent.search_transcripts", return_value=[mock_chunk]),
        patch(
            "app.llm.ollama.OllamaClient.chat",
            return_value=LLMResponse(
                content="According to [Brian Chesky, Founder Mode], founders need to stay in product details.",
            ),
        ),
    ):
        res = client.post(
            f"/sessions/{session_id}/chat",
            json={"message": "What is founder mode?"},
        )
        assert res.status_code == 200
        data = res.json()
        assert "[Brian Chesky, Founder Mode]" in data["reply"]
        assert len(data["sources"]) == 1
        assert data["sources"][0]["guest"] == "Brian Chesky"
        print(f"Reply: {data['reply']}")
        print(f"Source cited: [{data['sources'][0]['guest']}, {data['sources'][0]['episode_title']}]")

    print("\n--- 5. Verifying Message History Persistence ---")
    res = client.get(f"/sessions/{session_id}/messages")
    assert res.status_code == 200
    messages = res.json()
    assert len(messages) == 4  # 2 user messages + 2 assistant messages
    print(f"Persisted total messages in DB: {len(messages)}")
    for i, m in enumerate(messages, 1):
        has_sources = bool(m.get("sources"))
        print(f"  {i}. [{m['role']}] {m['content'][:60]}... (sources={has_sources})")

    print("\nALL STEP 7 VERIFICATIONS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    run_verification()
