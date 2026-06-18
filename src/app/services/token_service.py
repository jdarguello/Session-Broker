import os
import json
import base64
import logging
from datetime import datetime, timezone

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.services.auth import extract_jwt_claims

DAPR_HTTP_PORT = os.getenv("DAPR_HTTP_PORT", "3500")
STATE_STORE_NAME = os.getenv("DAPR_STATE_STORE", "redis")
DAPR_STATE_URL = f"http://localhost:{DAPR_HTTP_PORT}/v1.0/state/{STATE_STORE_NAME}"

audit_logger = logging.getLogger("audit")


class TokenExpiredError(Exception):
    pass


def _get_encryption_key() -> bytes:
    key_b64 = os.getenv("TOKEN_ENCRYPTION_KEY")
    if not key_b64:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY environment variable is not set")
    key = base64.b64decode(key_b64)
    if len(key) != 32:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY must encode a 32-byte (256-bit) key")
    return key


def _encrypt(data: dict) -> str:
    key = _get_encryption_key()
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, json.dumps(data).encode(), None)
    return base64.b64encode(nonce + ciphertext).decode()


def _decrypt(encrypted: str) -> dict:
    key = _get_encryption_key()
    raw = base64.b64decode(encrypted)
    nonce, ciphertext = raw[:12], raw[12:]
    aesgcm = AESGCM(key)
    return json.loads(aesgcm.decrypt(nonce, ciphertext, None))


async def _dapr_get(key: str) -> dict | None:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{DAPR_STATE_URL}/{key}")
        if resp.status_code == 204 or not resp.content:
            return None
        resp.raise_for_status()
        return resp.json()


async def _dapr_save(key: str, value: dict, ttl_seconds: int | None = None) -> None:
    entry: dict = {"key": key, "value": value}
    if ttl_seconds is not None and ttl_seconds > 0:
        entry["metadata"] = {"ttlInSeconds": str(ttl_seconds)}
    async with httpx.AsyncClient() as client:
        resp = await client.post(DAPR_STATE_URL, json=[entry])
        resp.raise_for_status()


async def cache_token(
    slack_user_id: str,
    access_token: str,
    refresh_token: str,
    id_token: str,
) -> None:
    """Encrypt and persist a Keycloak token set in Redis, keyed by Slack user ID."""
    claims = extract_jwt_claims(access_token)
    exp = claims.get("exp")
    now = int(datetime.now(timezone.utc).timestamp())
    ttl = int(exp - now) if exp else None

    token_data = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "id_token": id_token,
        "exp": exp,
    }
    encrypted = _encrypt(token_data)
    record = {
        "encrypted_tokens": encrypted,
        "exp": exp,
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }

    cache_key = f"slack:{slack_user_id}"
    await _dapr_save(cache_key, record, ttl_seconds=ttl)
    # Audit — never log token values
    audit_logger.info("token_write key=%s exp=%s", cache_key, exp)


async def resolve_identity(slack_user_id: str) -> dict | None:
    """
    Resolve the cached identity for a Slack user.

    Returns:
        None if no cached token exists (unauthenticated).
        A dict with type, sub, email, roles, slack_user_id for authenticated users.

    Raises:
        TokenExpiredError if cached token material has expired.
    """
    cache_key = f"slack:{slack_user_id}"
    record = await _dapr_get(cache_key)

    if record is None:
        audit_logger.info("token_read_miss key=%s", cache_key)
        return None

    exp = record.get("exp")
    now = int(datetime.now(timezone.utc).timestamp())
    if exp and now >= exp:
        audit_logger.warning("token_read_expired key=%s exp=%s", cache_key, exp)
        raise TokenExpiredError(f"Cached token for {slack_user_id} has expired")

    token_data = _decrypt(record["encrypted_tokens"])
    access_claims = extract_jwt_claims(token_data["access_token"])

    audit_logger.info("token_read key=%s exp=%s", cache_key, exp)
    return {
        "type": "authenticated",
        "sub": access_claims.get("sub", ""),
        "email": access_claims.get("email", ""),
        "roles": access_claims.get("realm_access", {}).get("roles", []),
        "slack_user_id": slack_user_id,
    }
