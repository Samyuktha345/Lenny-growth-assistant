from datetime import datetime
import json
import time
import uuid
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.agent.agent import run_agent, run_agent_stream
from app.agent.sanitizer import sanitize_html
from app.agent.timing import StageTimings
from app.api.schemas import (
    ArtifactResponse,
    ChatRequest,
    ChatResponse,
    CreateSessionRequest,
    LoginRequest,
    MessageResponse,
    SessionResponse,
    UserResponse,
)
from app.db.models import Artifact, ChatMessage, ChatSession, User
from app.db.session import get_db
from app.llm.factory import get_llm

router = APIRouter()


def get_current_user(
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> User:
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-User-Id header.",
        )
    user = db.get(User, x_user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unknown or invalid X-User-Id.",
        )
    return user


@router.get("/health")
def health() -> dict[str, str]:
    llm = get_llm()
    return {
        "status": "ok",
        "provider": llm.provider,
        "model": llm.model,
    }


@router.post(
    "/users/login",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
)
def login_user(
    payload: LoginRequest,
    db: Session = Depends(get_db),
) -> User:
    email = payload.email.strip().lower()
    name = payload.name.strip()
    stmt = select(User).where(User.email == email)
    user = db.scalars(stmt).first()
    now = datetime.utcnow()
    if user:
        user.name = name or user.name
        user.last_seen_at = now
        db.commit()
        db.refresh(user)
        return user

    user = User(
        id=str(uuid.uuid4()),
        email=email,
        name=name,
        created_at=now,
        last_seen_at=now,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post(
    "/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    payload: CreateSessionRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatSession:
    user_name = (
        payload.user_name if payload and payload.user_name else None
    ) or current_user.name
    session_id = str(uuid.uuid4())
    session = ChatSession(
        id=session_id,
        user_id=current_user.id,
        user_name=user_name,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/sessions", response_model=list[SessionResponse])
def list_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ChatSession]:
    stmt = (
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.created_at.desc())
    )
    return list(db.scalars(stmt).all())


@router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
def get_session_messages(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ChatMessage]:
    session = db.get(ChatSession, session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session with ID '{session_id}' not found.",
        )
    return list(session.messages)


@router.post("/sessions/{session_id}/chat")
async def chat_session(
    request: Request,
    session_id: str,
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = db.get(ChatSession, session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session with ID '{session_id}' not found.",
        )

    want_stream = (
        payload.stream
        or request.headers.get("accept") == "text/event-stream"
        or request.query_params.get("stream") == "true"
    )

    t0_db = time.perf_counter()
    user_msg = ChatMessage(
        session_id=session.id,
        role="user",
        content=payload.message,
    )
    db.add(user_msg)
    db.commit()
    db.refresh(user_msg)
    db_writes_ms = (time.perf_counter() - t0_db) * 1000

    if want_stream:
        async def sse_generator():
            from app.db.session import SessionLocal
            stream_db = SessionLocal()
            try:
                full_reply = ""
                final_sources = []
                final_artifacts = []
                for event in run_agent_stream(session.id, payload.message, db=stream_db):
                    ev_type = event.get("event")
                    ev_data = event.get("data", {})
                    if ev_type == "sources":
                        final_sources = ev_data.get("sources", [])
                    elif ev_type == "token":
                        full_reply += ev_data.get("token", "")
                    elif ev_type == "done":
                        final_sources = ev_data.get("sources", final_sources)
                        final_artifacts = ev_data.get("artifacts", [])
                        if not full_reply:
                            full_reply = ev_data.get("reply", "")

                    yield f"data: {json.dumps({'type': ev_type, **ev_data})}\n\n"

                # Persist assistant message and artifacts
                asst_msg = ChatMessage(
                    session_id=session.id,
                    role="assistant",
                    content=full_reply,
                    sources=final_sources,
                )
                stream_db.add(asst_msg)
                stream_db.flush()

                for art in final_artifacts:
                    art_content = art.get("content", "")
                    if art.get("type") == "html":
                        art_content = sanitize_html(art_content)
                    db_art = Artifact(
                        message_id=asst_msg.id,
                        type=art.get("type", "markdown"),
                        title=art.get("title", "Artifact"),
                        content=art_content,
                    )
                    stream_db.add(db_art)

                stream_db.commit()
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            finally:
                stream_db.close()

        origin = request.headers.get("origin")
        cors_headers = {}
        if origin:
            cors_headers["Access-Control-Allow-Origin"] = origin
            cors_headers["Access-Control-Allow-Credentials"] = "true"

        return StreamingResponse(
            sse_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                **cors_headers,
            },
        )

    timings = StageTimings()
    reply, sources, artifacts_data = run_agent(
        session.id, payload.message, db=db, timings=timings
    )

    t0_db2 = time.perf_counter()
    assistant_msg = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=reply,
        sources=sources,
    )
    db.add(assistant_msg)
    db.flush()

    for art in artifacts_data:
        art_content = art["content"]
        if art.get("type") == "html":
            art_content = sanitize_html(art_content)
        db_artifact = Artifact(
            message_id=assistant_msg.id,
            type=art.get("type", "markdown"),
            title=art.get("title", "Artifact"),
            content=art_content,
        )
        db.add(db_artifact)

    db.commit()
    db.refresh(user_msg)
    db.refresh(assistant_msg)
    db_writes_ms += (time.perf_counter() - t0_db2) * 1000

    timings.db_writes_ms = db_writes_ms
    timings.total_pipeline_ms = (
        timings.query_rewrite_ms
        + timings.query_embedding_ms
        + timings.pgvector_search_ms
        + timings.prompt_build_ms
        + timings.llm_total_ms
        + timings.db_writes_ms
    )
    timings.print_table()

    return ChatResponse(
        reply=reply,
        session_id=session.id,
        sources=sources,
        artifacts=[
            ArtifactResponse.model_validate(a) for a in assistant_msg.artifacts
        ],
        user_message=MessageResponse.model_validate(user_msg),
        assistant_message=MessageResponse.model_validate(assistant_msg),
        timings=timings.to_dict(),
    )


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    session = db.get(ChatSession, session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session with ID '{session_id}' not found.",
        )
    db.delete(session)
    db.commit()
    return {"status": "deleted", "id": session_id}


@router.get("/artifacts/{artifact_id}", response_model=ArtifactResponse)
def get_artifact(
    artifact_id: int, db: Session = Depends(get_db)
) -> Artifact:
    artifact = db.get(Artifact, artifact_id)
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact with ID '{artifact_id}' not found.",
        )
    return artifact
