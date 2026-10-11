from datetime import datetime
import uuid
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.agent.agent import run_agent
from app.agent.sanitizer import sanitize_html
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


@router.post("/sessions/{session_id}/chat", response_model=ChatResponse)
def chat_session(
    session_id: str,
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    session = db.get(ChatSession, session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session with ID '{session_id}' not found.",
        )

    user_msg = ChatMessage(
        session_id=session.id,
        role="user",
        content=payload.message,
    )
    db.add(user_msg)
    db.commit()

    reply, sources, artifacts_data = run_agent(
        session.id, payload.message, db=db
    )

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

    return ChatResponse(
        reply=reply,
        session_id=session.id,
        sources=sources,
        artifacts=[
            ArtifactResponse.model_validate(a) for a in assistant_msg.artifacts
        ],
        user_message=MessageResponse.model_validate(user_msg),
        assistant_message=MessageResponse.model_validate(assistant_msg),
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
