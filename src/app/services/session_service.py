import os
import uuid
import httpx
from datetime import datetime, timezone
from app.models.session import Session, SessionStatus

DAPR_HTTP_PORT = os.getenv("DAPR_HTTP_PORT", "3500")
STATE_STORE_NAME = os.getenv("DAPR_STATE_STORE", "redis")
DAPR_STATE_URL = f"http://localhost:{DAPR_HTTP_PORT}/v1.0/state/{STATE_STORE_NAME}"


async def _dapr_get(key: str) -> dict | None:
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
        resp = await client.get(f"{DAPR_STATE_URL}/{key}")
        if resp.status_code == 204 or not resp.content:
            return None
        resp.raise_for_status()
        return resp.json()


async def _dapr_save(key: str, value: dict) -> None:
    payload = [{"key": key, "value": value}]
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
        resp = await client.post(DAPR_STATE_URL, json=payload)
        resp.raise_for_status()


async def _dapr_delete(key: str) -> None:
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
        resp = await client.delete(f"{DAPR_STATE_URL}/{key}")
        resp.raise_for_status()


async def create_session(user_id: str, email: str, roles: list[str], agent: str) -> Session:
    session = Session(
        id=str(uuid.uuid4()),
        user_id=user_id,
        user_email=email,
        roles=roles,
        current_agent=agent,
        status=SessionStatus.active,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await _dapr_save(session.id, session.model_dump(mode="json"))
    return session


async def get_session(session_id: str) -> Session | None:
    data = await _dapr_get(session_id)
    if data is None:
        return None
    return Session(**data)


async def update_session(session_id: str, patch: dict) -> Session | None:
    data = await _dapr_get(session_id)
    if data is None:
        return None
    data.update(patch)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    await _dapr_save(session_id, data)
    return Session(**data)


async def handoff_session(session_id: str, target_agent: str) -> Session | None:
    return await update_session(session_id, {"current_agent": target_agent})


async def terminate_session(session_id: str) -> bool:
    data = await _dapr_get(session_id)
    if data is None:
        return False
    data["status"] = SessionStatus.terminated.value
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    await _dapr_save(session_id, data)
    return True
