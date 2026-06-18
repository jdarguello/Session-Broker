import json
import base64
from fastapi import Request


def extract_jwt_claims(token: str) -> dict:
    """
    Decode the JWT payload from a raw token string.

    Dapr's bearer middleware has already validated the token signature
    and expiry before this service receives the request. We only need
    to decode the payload segment to read the claims.
    """
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    payload = parts[1]
    # Re-pad to a valid base64 length
    payload += "=" * (-len(payload) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


def extract_claims(request: Request) -> dict:
    """
    Decode the JWT payload from the Authorization header.

    Dapr's bearer middleware has already validated the token signature
    and expiry before this service receives the request. We only need
    to decode the payload segment to read the claims.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return {}
    token = auth[len("Bearer "):]
    return extract_jwt_claims(token)


def get_user_identity(request: Request) -> dict:
    """Return the core identity fields from the JWT claims."""
    claims = extract_claims(request)
    return {
        "sub": claims.get("sub", ""),
        "email": claims.get("email", ""),
        "roles": claims.get("realm_access", {}).get("roles", []),
    }
