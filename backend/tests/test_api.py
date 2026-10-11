from collections.abc import Generator
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from app.db.models import Base
from app.db.session import get_db
from app.main import app

sqlite_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=sqlite_engine
)

Base.metadata.tables["users"].create(bind=sqlite_engine)
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


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "provider" in data
    assert "model" in data


def test_user_login_creation_and_last_seen():
    # 1. New user registration via login
    payload = {"name": "Alice Operator", "email": "alice@example.com"}
    res = client.post("/users/login", json=payload)
    assert res.status_code == 200
    user_data = res.json()
    assert user_data["name"] == "Alice Operator"
    assert user_data["email"] == "alice@example.com"
    assert "id" in user_data
    assert "last_seen_at" in user_data
    user_id = user_data["id"]

    # 2. Re-login returns existing user and updates last_seen_at
    payload2 = {"name": "Alice Renamed", "email": "alice@example.com"}
    res2 = client.post("/users/login", json=payload2)
    assert res2.status_code == 200
    user_data2 = res2.json()
    assert user_data2["id"] == user_id
    assert user_data2["name"] == "Alice Renamed"


def test_missing_and_invalid_x_user_id_header():
    # Missing header on session list
    res_missing = client.get("/sessions")
    assert res_missing.status_code == 401
    err_missing = res_missing.json()
    assert err_missing["error"]["code"] == "UNAUTHORIZED"
    assert "Missing X-User-Id header" in err_missing["error"]["message"]

    # Unknown user id on session list
    res_unknown = client.get("/sessions", headers={"X-User-Id": "non-existent-user-id"})
    assert res_unknown.status_code == 401
    err_unknown = res_unknown.json()
    assert err_unknown["error"]["code"] == "UNAUTHORIZED"
    assert "Unknown or invalid X-User-Id" in err_unknown["error"]["message"]

    # Missing header on chat endpoint
    res_chat = client.post("/sessions/some-id/chat", json={"message": "hello"})
    assert res_chat.status_code == 401
    assert res_chat.json()["error"]["code"] == "UNAUTHORIZED"


def test_two_users_cannot_see_each_others_sessions():
    # Register User A
    user_a = client.post(
        "/users/login", json={"name": "User Alpha", "email": "alpha@example.com"}
    ).json()
    user_a_id = user_a["id"]
    headers_a = {"X-User-Id": user_a_id}

    # Register User B
    user_b = client.post(
        "/users/login", json={"name": "User Beta", "email": "beta@example.com"}
    ).json()
    user_b_id = user_b["id"]
    headers_b = {"X-User-Id": user_b_id}

    # User A creates Session A
    sess_a = client.post(
        "/sessions", json={"user_name": "Alpha Session"}, headers=headers_a
    ).json()
    sess_a_id = sess_a["id"]

    # User B creates Session B
    sess_b = client.post(
        "/sessions", json={"user_name": "Beta Session"}, headers=headers_b
    ).json()
    sess_b_id = sess_b["id"]

    # User A lists sessions -> should ONLY see Session A
    list_a = client.get("/sessions", headers=headers_a).json()
    assert any(s["id"] == sess_a_id for s in list_a)
    assert not any(s["id"] == sess_b_id for s in list_a)

    # User B lists sessions -> should ONLY see Session B
    list_b = client.get("/sessions", headers=headers_b).json()
    assert any(s["id"] == sess_b_id for s in list_b)
    assert not any(s["id"] == sess_a_id for s in list_b)

    # User A tries to view User B's messages -> 404 NOT_FOUND
    res_a_view_b = client.get(
        f"/sessions/{sess_b_id}/messages", headers=headers_a
    )
    assert res_a_view_b.status_code == 404
    assert res_a_view_b.json()["error"]["code"] == "NOT_FOUND"

    # User A tries to chat in User B's session -> 404 NOT_FOUND
    res_a_chat_b = client.post(
        f"/sessions/{sess_b_id}/chat",
        json={"message": "intruder message"},
        headers=headers_a,
    )
    assert res_a_chat_b.status_code == 404
    assert res_a_chat_b.json()["error"]["code"] == "NOT_FOUND"

    # User B tries to view User A's messages -> 404 NOT_FOUND
    res_b_view_a = client.get(
        f"/sessions/{sess_a_id}/messages", headers=headers_b
    )
    assert res_b_view_a.status_code == 404
    assert res_b_view_a.json()["error"]["code"] == "NOT_FOUND"

    # User B tries to chat in User A's session -> 404 NOT_FOUND
    res_b_chat_a = client.post(
        f"/sessions/{sess_a_id}/chat",
        json={"message": "intruder message"},
        headers=headers_b,
    )
    assert res_b_chat_a.status_code == 404
    assert res_b_chat_a.json()["error"]["code"] == "NOT_FOUND"


def test_session_not_found_error_shape():
    user = client.post(
        "/users/login", json={"name": "Alice", "email": "alice_test@example.com"}
    ).json()
    headers = {"X-User-Id": user["id"]}

    res = client.get("/sessions/nonexistent-id/messages", headers=headers)
    assert res.status_code == 404
    data = res.json()
    assert "error" in data
    assert data["error"]["code"] == "NOT_FOUND"
    assert "nonexistent-id" in data["error"]["message"]


def test_chat_validation_error_shape():
    user = client.post(
        "/users/login", json={"name": "Alice", "email": "alice_test2@example.com"}
    ).json()
    headers = {"X-User-Id": user["id"]}

    # Empty message should trigger 422
    res = client.post("/sessions/some-id/chat", json={"message": ""}, headers=headers)
    assert res.status_code == 422
    data = res.json()
    assert "error" in data
    assert data["error"]["code"] == "VALIDATION_ERROR"


def test_chat_and_persist_messages_and_artifacts():
    user = client.post(
        "/users/login", json={"name": "Alice", "email": "alice_artifact@example.com"}
    ).json()
    headers = {"X-User-Id": user["id"]}

    create_res = client.post("/sessions", json={}, headers=headers)
    assert create_res.status_code == 201
    session_id = create_res.json()["id"]

    mock_sources = [
        {
            "guest": "Brian Chesky",
            "episode_title": "Founder Mode",
            "source_file": "brian.md",
            "similarity_score": 0.88,
            "text": "Founders must stay in the details.",
        }
    ]

    mock_artifacts = [
        {
            "type": "html",
            "title": "Founder Mode Card",
            "content": "<div><h2>Founder Mode</h2><script>alert('xss')</script><p>Stay in details</p></div>",
        }
    ]

    with patch(
        "app.api.routes.run_agent",
        return_value=(
            "According to [Brian Chesky, Founder Mode], stay in details.",
            mock_sources,
            mock_artifacts,
        ),
    ):
        chat_res = client.post(
            f"/sessions/{session_id}/chat",
            json={"message": "What did Brian say?"},
            headers=headers,
        )
        assert chat_res.status_code == 200
        data = chat_res.json()
        assert data["session_id"] == session_id
        assert "[Brian Chesky, Founder Mode]" in data["reply"]
        assert len(data["sources"]) == 1
        assert len(data["artifacts"]) == 1

        artifact = data["artifacts"][0]
        assert artifact["title"] == "Founder Mode Card"
        assert artifact["type"] == "html"
        # Verify sanitization stripped <script>
        assert "<script>" not in artifact["content"]
        assert "alert" not in artifact["content"]
        assert "<h2>Founder Mode</h2>" in artifact["content"]

        artifact_id = artifact["id"]

    # Test GET /artifacts/{id}
    art_res = client.get(f"/artifacts/{artifact_id}")
    assert art_res.status_code == 200
    art_data = art_res.json()
    assert art_data["id"] == artifact_id
    assert art_data["title"] == "Founder Mode Card"
    assert "<script>" not in art_data["content"]

    # Test GET /artifacts/99999 (not found)
    art_not_found = client.get("/artifacts/99999")
    assert art_not_found.status_code == 404
    assert art_not_found.json()["error"]["code"] == "NOT_FOUND"

    # Test message history includes artifacts
    history_res = client.get(f"/sessions/{session_id}/messages", headers=headers)
    assert history_res.status_code == 200
    msgs = history_res.json()
    assert len(msgs) == 2
    assert len(msgs[1]["artifacts"]) == 1
    assert msgs[1]["artifacts"][0]["title"] == "Founder Mode Card"


def test_cors_headers():
    res = client.options(
        "/sessions",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert res.headers.get("access-control-allow-origin") == "http://localhost:5173"
