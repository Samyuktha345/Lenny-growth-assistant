from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    email: str = Field(..., min_length=3, max_length=256)


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    created_at: datetime
    last_seen_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CreateSessionRequest(BaseModel):
    user_name: str | None = Field(default=None, max_length=128)


class SessionResponse(BaseModel):
    id: str
    user_id: str | None = None
    user_name: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ArtifactResponse(BaseModel):
    id: int
    message_id: int
    type: str
    title: str
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    id: int
    session_id: str
    role: str
    content: str
    sources: list[dict] | None = None
    artifacts: list[ArtifactResponse] = Field(default_factory=list)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    sources: list[dict] = Field(default_factory=list)
    artifacts: list[ArtifactResponse] = Field(default_factory=list)
    user_message: MessageResponse
    assistant_message: MessageResponse


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
