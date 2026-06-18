from fastapi import APIRouter, Request, HTTPException
from app.models.session import (
    Session,
    CreateSessionRequest,
    UpdateSessionRequest,
    HandoffRequest,
)
from app.services import session_service
from app.services.auth import get_user_identity

router = APIRouter()


def _require_identity(request: Request) -> dict:
    identity = get_user_identity(request)
    if not identity.get("sub"):
        raise HTTPException(status_code=401, detail="Missing or invalid bearer token")
    return identity


@router.post("", response_model=Session, status_code=201)
async def create_session(body: CreateSessionRequest, request: Request):
    identity = _require_identity(request)
    session = await session_service.create_session(
        user_id=identity["sub"],
        email=identity["email"],
        roles=identity["roles"],
        agent=body.agent,
    )
    if body.state:
        session = await session_service.update_session(session.id, {"state": body.state})
    return session


@router.get("/{session_id}", response_model=Session)
async def get_session(session_id: str, request: Request):
    _require_identity(request)
    session = await session_service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.patch("/{session_id}", response_model=Session)
async def update_session(session_id: str, body: UpdateSessionRequest, request: Request):
    _require_identity(request)
    patch: dict = {}
    if body.state is not None:
        patch["state"] = body.state
    if body.current_agent is not None:
        patch["current_agent"] = body.current_agent
    session = await session_service.update_session(session_id, patch)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/{session_id}/handoff", response_model=Session)
async def handoff_session(session_id: str, body: HandoffRequest, request: Request):
    _require_identity(request)
    session = await session_service.handoff_session(session_id, body.target_agent)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.delete("/{session_id}", status_code=204)
async def terminate_session(session_id: str, request: Request):
    _require_identity(request)
    ok = await session_service.terminate_session(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found")
