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


# ── POST /auth/login/start ───────────────────────────────────────────────────


@patch("app.services.oauth_service._dapr_save", new_callable=AsyncMock)
def test_login_start_returns_authorize_url(mock_save, monkeypatch):
    """login/start must return an authorize_url containing all required OAuth params."""
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", TEST_KEY)
    monkeypatch.setenv("KEYCLOAK_ISSUER_URL", "https://keycloak.example.com/realms/demo")
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "session-broker")
    monkeypatch.setenv("KEYCLOAK_REDIRECT_URI", "https://broker.example.com/auth/callback")
    monkeypatch.setenv("KEYCLOAK_SCOPES", "openid email profile offline_access")
    mock_save.return_value = None

    resp = client.post("/auth/login/start", json={"slack_user_id": "U42"})
    assert resp.status_code == 200
    body = resp.json()

    assert "authorize_url" in body
    assert "state" in body

    url = body["authorize_url"]
    nonce = body["state"]

    # Required OAuth/PKCE params must appear in the URL
    assert "response_type=code" in url
    assert "client_id=session-broker" in url
    assert "redirect_uri=" in url
    assert "scope=" in url
    assert f"state={nonce}" in url
    assert "code_challenge=" in url
    assert "code_challenge_method=S256" in url

    # Dapr save must have been called with login:{nonce}
    mock_save.assert_called_once()
    call_key = mock_save.call_args[0][0]
    assert call_key == f"login:{nonce}"


@patch("app.services.oauth_service._dapr_save", new_callable=AsyncMock)
def test_login_start_stores_nonce_with_ttl(mock_save, monkeypatch):
    """login/start must store the nonce with a 5-minute TTL."""
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", TEST_KEY)
    monkeypatch.setenv("KEYCLOAK_ISSUER_URL", "https://keycloak.example.com/realms/demo")
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "session-broker")
    monkeypatch.setenv("KEYCLOAK_REDIRECT_URI", "https://broker.example.com/auth/callback")
    mock_save.return_value = None

    resp = client.post("/auth/login/start", json={"slack_user_id": "U99"})
    assert resp.status_code == 200

    # TTL must be 300 seconds
    call_ttl = mock_save.call_args[1].get("ttl_seconds") or mock_save.call_args[0][2]
    assert call_ttl == 300

    # Stored value must contain slack_user_id and code_verifier (but not the tokens)
    stored_value = mock_save.call_args[0][1]
    assert stored_value["slack_user_id"] == "U99"
    assert "code_verifier" in stored_value


# ── GET /auth/callback ───────────────────────────────────────────────────────


@patch("app.services.token_service._dapr_save", new_callable=AsyncMock)
@patch("app.services.oauth_service._dapr_delete", new_callable=AsyncMock)
@patch("app.services.oauth_service._dapr_get", new_callable=AsyncMock)
@patch("app.routers.auth.exchange_code_for_tokens", new_callable=AsyncMock)
def test_callback_happy_path(
    mock_exchange, mock_get, mock_delete, mock_save, monkeypatch
):
    """
    callback happy path:
    - Dapr get returns the stored nonce record.
    - Dapr delete is called (single-use).
    - Keycloak token exchange is called and returns tokens.
    - cache_token persists the token set under slack:{slack_user_id}.
    """
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", TEST_KEY)
    monkeypatch.setenv("KEYCLOAK_ISSUER_URL", "https://keycloak.example.com/realms/demo")
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "session-broker")
    monkeypatch.setenv("KEYCLOAK_CLIENT_SECRET", "s3cr3t")
    monkeypatch.setenv("KEYCLOAK_REDIRECT_URI", "https://broker.example.com/auth/callback")

    access_tok = _access_token(sub="kc-user-1", email="user@corp.com")
    mock_get.return_value = {"slack_user_id": "U55", "code_verifier": "verifier-abc"}
    mock_delete.return_value = None
    mock_exchange.return_value = {
        "access_token": access_tok,
        "refresh_token": "rt-xyz",
        "id_token": "id-xyz",
    }
    mock_save.return_value = None

    resp = client.get("/auth/callback?code=authcode123&state=nonce-xyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["slack_user_id"] == "U55"
    assert body["cached"] is True

    # Nonce must have been consumed (deleted)
    mock_delete.assert_called_once()
    delete_key = mock_delete.call_args[0][0]
    assert delete_key == "login:nonce-xyz"

    # Token must be persisted under slack:{slack_user_id}
    mock_save.assert_called_once()
    save_key = mock_save.call_args[0][0]
    assert save_key == "slack:U55"


@patch("app.services.oauth_service._dapr_get", new_callable=AsyncMock)
def test_callback_unknown_state_returns_400(mock_get, monkeypatch):
    """callback with an unknown or already-consumed state nonce must return 400."""
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", TEST_KEY)
    mock_get.return_value = None

    resp = client.get("/auth/callback?code=irrelevant&state=bad-nonce")
    assert resp.status_code == 400


@patch("app.services.token_service._dapr_save", new_callable=AsyncMock)
@patch("app.services.oauth_service._dapr_delete", new_callable=AsyncMock)
@patch("app.services.oauth_service._dapr_get", new_callable=AsyncMock)
@patch("app.routers.auth.exchange_code_for_tokens", new_callable=AsyncMock)
def test_callback_nonce_is_single_use(
    mock_exchange, mock_get, mock_delete, mock_save, monkeypatch
):
    """The nonce must be deleted on first read so it cannot be replayed."""
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", TEST_KEY)
    monkeypatch.setenv("KEYCLOAK_ISSUER_URL", "https://keycloak.example.com/realms/demo")
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "session-broker")
    monkeypatch.setenv("KEYCLOAK_CLIENT_SECRET", "s3cr3t")
    monkeypatch.setenv("KEYCLOAK_REDIRECT_URI", "https://broker.example.com/auth/callback")

    access_tok = _access_token()
    mock_get.return_value = {"slack_user_id": "U77", "code_verifier": "cv"}
    mock_delete.return_value = None
    mock_exchange.return_value = {
        "access_token": access_tok,
        "refresh_token": "rt",
        "id_token": "id",
    }
    mock_save.return_value = None

    resp = client.get("/auth/callback?code=c&state=once-nonce")
    assert resp.status_code == 200

    # _dapr_delete must be called exactly once with the login key
    mock_delete.assert_called_once_with("login:once-nonce")


@patch("app.services.oauth_service._dapr_delete", new_callable=AsyncMock)
@patch("app.services.oauth_service._dapr_get", new_callable=AsyncMock)
@patch("app.routers.auth.exchange_code_for_tokens", new_callable=AsyncMock)
def test_callback_keycloak_failure_returns_502(
    mock_exchange, mock_get, mock_delete, monkeypatch
):
    """Non-2xx from Keycloak token endpoint must result in HTTP 502."""
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", TEST_KEY)
    monkeypatch.setenv("KEYCLOAK_ISSUER_URL", "https://keycloak.example.com/realms/demo")
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "session-broker")
    monkeypatch.setenv("KEYCLOAK_CLIENT_SECRET", "s3cr3t")
    monkeypatch.setenv("KEYCLOAK_REDIRECT_URI", "https://broker.example.com/auth/callback")

    mock_get.return_value = {"slack_user_id": "U88", "code_verifier": "cv2"}
    mock_delete.return_value = None
    mock_exchange.side_effect = Exception("Keycloak unavailable")

    resp = client.get("/auth/callback?code=bad-code&state=nonce-abc")
    assert resp.status_code == 502
