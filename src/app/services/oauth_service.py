"""
OAuth Authorization-Code helpers for the Session Broker write path.

Responsibilities:
- Mint a one-time nonce (OAuth `state`) + PKCE code_verifier/challenge pair.
- Build the Keycloak /authorize URL so the user can authenticate.
- Exchange an authorization code for tokens at the Keycloak token endpoint.

All Redis I/O is delegated to token_service helpers (_dapr_save, _dapr_get,
_dapr_delete) — this module never re-implements Dapr HTTP plumbing.
"""

import hashlib
import os
import secrets
import logging
from base64 import urlsafe_b64encode
from urllib.parse import urlencode

import httpx

from app.services.token_service import _dapr_save, _dapr_get, _dapr_delete

audit_logger = logging.getLogger("audit")

NONCE_TTL_SECONDS = 300  # 5 minutes


def _keycloak_issuer() -> str:
    url = os.getenv("KEYCLOAK_ISSUER_URL", "")
    if not url:
        raise RuntimeError("KEYCLOAK_ISSUER_URL is not set")
    return url.rstrip("/")


def _pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) using S256 method."""
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = urlsafe_b64encode(digest).rstrip(b"=").decode()
    return code_verifier, code_challenge


async def mint_login_nonce(slack_user_id: str) -> tuple[str, str]:
    """
    Mint a one-time nonce and PKCE pair, store them in Redis, and return
    (nonce, authorize_url).

    The nonce is stored under login:{nonce} with a 5-minute TTL.
    """
    nonce = secrets.token_urlsafe(32)
    code_verifier, code_challenge = _pkce_pair()

    login_key = f"login:{nonce}"
    await _dapr_save(
        login_key,
        {"slack_user_id": slack_user_id, "code_verifier": code_verifier},
        ttl_seconds=NONCE_TTL_SECONDS,
    )
    # Audit — log the key and Slack ID but never token values
    audit_logger.info("login_start key=%s slack_user_id=%s", login_key, slack_user_id)

    authorize_url = _build_authorize_url(nonce, code_challenge)
    return nonce, authorize_url


def _build_authorize_url(nonce: str, code_challenge: str) -> str:
    issuer = _keycloak_issuer()
    client_id = os.getenv("KEYCLOAK_CLIENT_ID", "")
    redirect_uri = os.getenv("KEYCLOAK_REDIRECT_URI", "")
    scopes = os.getenv("KEYCLOAK_SCOPES", "openid email profile offline_access")

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scopes,
        "state": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{issuer}/protocol/openid-connect/auth?{urlencode(params)}"


async def consume_nonce(state: str) -> dict:
    """
    Retrieve and delete (single-use) the nonce record stored under login:{state}.

    Returns the stored dict: {"slack_user_id": ..., "code_verifier": ...}
    Raises KeyError if the nonce is not found or already consumed.
    """
    login_key = f"login:{state}"
    record = await _dapr_get(login_key)
    if record is None:
        raise KeyError(f"Nonce not found or already consumed: {login_key}")
    await _dapr_delete(login_key)
    return record


async def exchange_code_for_tokens(code: str, code_verifier: str) -> dict:
    """
    Exchange an authorization code for tokens at the Keycloak token endpoint.

    Returns a dict with access_token, refresh_token, id_token.
    Raises httpx.HTTPStatusError on non-2xx from Keycloak.
    """
    issuer = _keycloak_issuer()
    token_url = f"{issuer}/protocol/openid-connect/token"

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": os.getenv("KEYCLOAK_REDIRECT_URI", ""),
        "client_id": os.getenv("KEYCLOAK_CLIENT_ID", ""),
        "client_secret": os.getenv("KEYCLOAK_CLIENT_SECRET", ""),
        "code_verifier": code_verifier,
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
        resp = await client.post(token_url, data=data)
        resp.raise_for_status()

    payload = resp.json()
    return {
        "access_token": payload["access_token"],
        "refresh_token": payload.get("refresh_token", ""),
        "id_token": payload.get("id_token", ""),
    }
