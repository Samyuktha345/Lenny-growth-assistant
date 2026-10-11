import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collections.abc import Generator
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from app.agent.retriever import SearchResult
from app.db.models import Base
from app.db.session import get_db
from app.llm.base import LLMResponse, ToolCall
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
Base.metadata.tables["artifacts"].create(bind=sqlite_engine)


def override_get_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def run_verification():
    print("=== Step 9 Verification: Artifact Support & HTML Sanitization ===\n")

    # 1. Create Session
    res = client.post("/sessions", json={"user_name": "Product Builder"})
    assert res.status_code == 201
    session_id = res.json()["id"]
    print(f"1. Created test session: {session_id}")

    # 2. Test HTML Artifact Creation & Backend Sanitization via create_artifact tool
    print("\n2. Testing HTML Artifact creation and backend sanitization...")
    mock_llm = MagicMock()
    mock_llm.chat.return_value = LLMResponse(
        content="Here is the Founder Mode framework card.",
        tool_calls=[
            ToolCall(
                id="call_card",
                name="create_artifact",
                arguments={
                    "type": "html",
                    "title": "Founder Mode Framework Card",
                    "content": (
                        "<div class='framework-card'>"
                        "<h2>Founder Mode Breakdown</h2>"
                        "<script>alert('xss vulnerability')</script>"
                        "<img src='icon.png' onerror='malicious()' alt='Icon' />"
                        "<p>Detail obsession beats conventional delegation.</p>"
                        "</div>"
                    ),
                },
            )
        ],
    )
    mock_chunk = SearchResult(
        text="Founders must stay in details.",
        episode_title="Founder Mode",
        guest="Brian Chesky",
        source_file="brian.md",
        similarity_score=0.9,
    )

    with (
        patch("app.agent.agent.search_transcripts", return_value=[mock_chunk]),
        patch("app.agent.agent.get_llm", return_value=mock_llm),
    ):
        chat_res = client.post(
            f"/sessions/{session_id}/chat",
            json={"message": "Give me a framework card for Founder Mode in HTML"},
        )
        assert chat_res.status_code == 200, f"Chat failed: {chat_res.text}"
        chat_data = chat_res.json()
        assert len(chat_data["artifacts"]) == 1
        html_artifact = chat_data["artifacts"][0]
        html_id = html_artifact["id"]

        print(f"   Created HTML artifact ID: {html_id}")
        print(f"   Title: {html_artifact['title']}")
        print(f"   Type: {html_artifact['type']}")

        # Verify sanitization stripped <script> and onerror
        assert "<script>" not in html_artifact["content"]
        assert "alert" not in html_artifact["content"]
        assert "onerror" not in html_artifact["content"]
        assert "<h2>Founder Mode Breakdown</h2>" in html_artifact["content"]
        assert "alt=\"Icon\"" in html_artifact["content"]
        print("   [PASS] HTML sanitization successfully stripped harmful tags and attributes.")

    # 3. Test GET /artifacts/{id}
    print("\n3. Testing GET /artifacts/{id} endpoint...")
    get_art_res = client.get(f"/artifacts/{html_id}")
    assert get_art_res.status_code == 200
    art_payload = get_art_res.json()
    assert art_payload["id"] == html_id
    assert art_payload["title"] == "Founder Mode Framework Card"
    assert art_payload["type"] == "html"
    print(f"   [PASS] Retrieved artifact {html_id} matches expected schema.")

    # 4. Test GET /artifacts/{id} 404 error shape
    print("\n4. Testing GET /artifacts/99999 not-found error envelope...")
    err_res = client.get("/artifacts/99999")
    assert err_res.status_code == 404
    err_json = err_res.json()
    assert "error" in err_json
    assert err_json["error"]["code"] == "NOT_FOUND"
    print(f"   [PASS] 404 envelope: {err_json}")

    # 5. Test Ship 30 Essay returned as a markdown artifact
    print("\n5. Testing Ship 30 essay returned as Markdown artifact...")
    mock_essay_text = (
        "# The Founder Mode Playbook\n\n"
        "Most management advice fails.\n\n"
        "## The Framework\nAccording to [Brian Chesky, Founder Mode], inspect pixels.\n\n"
        "## The 1 Key Takeaway\nStay in details.\n\n"
        "## Sources\n- [Brian Chesky, Founder Mode]"
    )
    with patch(
        "app.agent.agent.write_ship30_essay",
        return_value=(mock_essay_text, [{"guest": "Brian Chesky", "episode_title": "Founder Mode"}]),
    ):
        essay_chat_res = client.post(
            f"/sessions/{session_id}/chat",
            json={"message": "Write a Ship 30 essay on founder mode"},
        )
        assert essay_chat_res.status_code == 200
        essay_data = essay_chat_res.json()
        assert len(essay_data["artifacts"]) == 1
        md_artifact = essay_data["artifacts"][0]
        assert md_artifact["type"] == "markdown"
        assert "Ship 30 Essay" in md_artifact["title"]
        assert "## The 1 Key Takeaway" in md_artifact["content"]
        print(f"   Created Markdown artifact ID: {md_artifact['id']}")
        print(f"   Title: {md_artifact['title']}")
        print("   [PASS] Essay returned as Markdown artifact.")

    # 6. Verify Session message history contains artifacts
    print("\n6. Verifying message history contains artifacts...")
    hist_res = client.get(f"/sessions/{session_id}/messages")
    assert hist_res.status_code == 200
    msgs = hist_res.json()
    assert len(msgs) == 4  # 2 user + 2 assistant
    assistant_1_artifacts = msgs[1]["artifacts"]
    assistant_2_artifacts = msgs[3]["artifacts"]
    assert len(assistant_1_artifacts) == 1
    assert assistant_1_artifacts[0]["type"] == "html"
    assert len(assistant_2_artifacts) == 1
    assert assistant_2_artifacts[0]["type"] == "markdown"
    print("   [PASS] Message history properly linked and returns artifacts.")

    print("\n=== STEP 9 VERIFICATION COMPLETE: ALL CHECKS PASSED ===")


if __name__ == "__main__":
    run_verification()
