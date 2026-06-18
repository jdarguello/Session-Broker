import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from app.main import app

client = TestClient(app)


def _auth_header(sub="user-123", email="user@example.com", roles=None):
    """Build a fake (unsigned) JWT header for tests. Dapr validation is mocked."""
    import base64
    import json

    header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
    payload_data = {"sub": sub, "email": email, "realm_access": {"roles": roles or []}}
    payload = (
        base64.urlsafe_b64encode(json.dumps(payload_data).encode()).rstrip(b"=").decode()
    )
    token = f"{header}.{payload}.fakesig"
    return {"Authorization": f"Bearer {token}"}


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@patch("app.services.session_service._dapr_save", new_callable=AsyncMock)
@patch("app.services.session_service._dapr_get", new_callable=AsyncMock)
def test_create_session(mock_get, mock_save):
    mock_save.return_value = None
    resp = client.post(
        "/sessions",
        json={"agent": "agent-alpha"},
        headers=_auth_header(),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["user_id"] == "user-123"
    assert data["current_agent"] == "agent-alpha"
    assert data["status"] == "active"


@patch("app.services.session_service._dapr_get", new_callable=AsyncMock)
def test_get_session_not_found(mock_get):
    mock_get.return_value = None
    resp = client.get("/sessions/nonexistent", headers=_auth_header())
    assert resp.status_code == 404


def test_missing_token():
    resp = client.post("/sessions", json={"agent": "agent-alpha"})
    assert resp.status_code == 401
