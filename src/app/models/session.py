from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field


class SessionStatus(str, Enum):
    active = "active"
    terminated = "terminated"


class Session(BaseModel):
    id: str
    user_id: str
    user_email: str
    roles: list[str] = Field(default_factory=list)
    current_agent: str
    state: dict = Field(default_factory=dict)
    status: SessionStatus = SessionStatus.active
    created_at: datetime
    updated_at: datetime


class CreateSessionRequest(BaseModel):
    agent: str = Field(..., description="Name of the agent that owns this session initially")
    state: dict = Field(default_factory=dict, description="Optional initial session state")


class UpdateSessionRequest(BaseModel):
    state: dict | None = None
    current_agent: str | None = None


class HandoffRequest(BaseModel):
    target_agent: str = Field(..., description="Agent to hand the session off to")
