import base64
import json
import logging
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.token_service import _encrypt

client = TestClient(app)

# ── Helpers ─────────────────────────────────────────────────────────────────

TEST_KEY = base64.b64encode(b"0" * 32).decode()


def _fake_jwt(claims: dict) -> str:
    """Build a fake (unsigned) JWT from a claims dict."""
    header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"{header}.{payload}.fakesig"


def _access_token(
    sub: str = "user-123",
    email: str = "user@example.com",
    roles: list | None = None,
    exp_offset: int = 3600,
) -> str:
    exp = int(datetime.now(timezone.utc).timestamp()) + exp_offset
    return _fake_jwt(
        {
            "sub": sub,
            "email": email,
            "realm_access": {"roles": roles or []},
            "exp": exp,
        }
    )


# ── POST /auth/callback/cache ────────────────────────────────────────────────


@patch("app.services.token_service._dapr_save", new_callable=AsyncMock)
def test_auth_callback_cache_ok(mock_save, monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", TEST_KEY)
    mock_save.return_value = None

    resp = client.post(
        "/auth/callback/cache",
        json={
            "slack_user_id": "U12345",
            "access_token": _access_token(),
            "refresh_token": "refresh-tok",
            "id_token": "id-tok",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["cached"] is True
    assert body["slack_user_id"] == "U12345"
    mock_save.assert_called_once()


def test_auth_callback_cache_missing_fields():
    resp = client.post("/auth/callback/cache", json={"slack_user_id": "U12345"})
    assert resp.status_code == 422


# ── POST /identity/resolve ───────────────────────────────────────────────────


@patch("app.services.token_service._dapr_get", new_callable=AsyncMock)
def test_identity_resolve_authenticated(mock_get, monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", TEST_KEY)

    access_tok = _access_token(sub="user-abc", email="abc@corp.com", roles=["agent-user"])
    exp = int(datetime.now(timezone.utc).timestamp()) + 3600
    token_data = {
        "access_token": access_tok,
        "refresh_token": "refresh-tok",
        "id_token": "id-tok",
        "exp": exp,
    }
    mock_get.return_value = {
        "encrypted_tokens": _encrypt(token_data),
        "exp": exp,
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }

    resp = client.post("/identity/resolve", headers={"X-Slack-User-Id": "U12345"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "authenticated"
    assert body["sub"] == "user-abc"
    assert body["email"] == "abc@corp.com"
    assert "agent-user" in body["roles"]
    assert body["slack_user_id"] == "U12345"
    # Token Storage Contract: access_token must be returned so the caller can
    # attach it as a bearer to downstream requests.
    assert "access_token" in body
    assert body["access_token"] == access_tok


@patch("app.services.token_service._dapr_get", new_callable=AsyncMock)
def test_identity_resolve_unauthenticated(mock_get, monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", TEST_KEY)
    mock_get.return_value = None

    resp = client.post("/identity/resolve", headers={"X-Slack-User-Id": "U99999"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "unauthenticated"
    assert body["slack_user_id"] == "U99999"


@patch("app.services.token_service._dapr_get", new_callable=AsyncMock)
def test_identity_resolve_expired_token(mock_get, monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", TEST_KEY)

    past_exp = int(datetime.now(timezone.utc).timestamp()) - 60
    access_tok = _access_token(exp_offset=-60)
    token_data = {
        "access_token": access_tok,
        "refresh_token": "r",
        "id_token": "i",
        "exp": past_exp,
    }
    mock_get.return_value = {
        "encrypted_tokens": _encrypt(token_data),
        "exp": past_exp,
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }

    resp = client.post("/identity/resolve", headers={"X-Slack-User-Id": "U12345"})
    assert resp.status_code == 401


def test_identity_resolve_missing_header():
    resp = client.post("/identity/resolve")
    assert resp.status_code == 400


@patch("app.services.token_service._dapr_get", new_callable=AsyncMock)
def test_identity_resolve_no_token_values_in_audit_log(mock_get, monkeypatch, caplog):
    """Audit log lines must record only key and exp — never token values."""
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", TEST_KEY)

    access_tok = _access_token(sub="user-xyz", email="xyz@corp.com")
    exp = int(datetime.now(timezone.utc).timestamp()) + 3600
    token_data = {
        "access_token": access_tok,
        "refresh_token": "secret-refresh-tok",
        "id_token": "secret-id-tok",
        "exp": exp,
    }
    mock_get.return_value = {
        "encrypted_tokens": _encrypt(token_data),
        "exp": exp,
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }

    with caplog.at_level(logging.INFO, logger="audit"):
        resp = client.post("/identity/resolve", headers={"X-Slack-User-Id": "U77777"})

    assert resp.status_code == 200
    # Guardrail: token strings must never appear in any log record
    for record in caplog.records:
        assert access_tok not in record.getMessage(), "access_token leaked into audit log"
        assert "secret-refresh-tok" not in record.getMessage(), "refresh_token leaked into audit log"
        assert "secret-id-tok" not in record.getMessage(), "id_token leaked into audit log"
