from fastapi import APIRouter, HTTPException, Request
from app.models.token_broker import AuthenticatedIdentity, UnauthenticatedIdentity, IdentityResponse
from app.services.token_service import resolve_identity, TokenExpiredError

router = APIRouter()


@router.post("/resolve", response_model=IdentityResponse)
async def identity_resolve(request: Request):
    """
    Resolve the workflow identity for a Slack user.

    Reads the cached token material from Redis (via Dapr), validates expiry,
    decrypts the token set, and returns a minimal identity contract for
    downstream agent and MCP authorization.

    Requires the `X-Slack-User-Id` header. Returns a partial unauthenticated
    identity when no cached token exists for the user.
    """
    slack_user_id = request.headers.get("X-Slack-User-Id", "").strip()
    if not slack_user_id:
        raise HTTPException(status_code=400, detail="X-Slack-User-Id header is required")

    try:
        identity = await resolve_identity(slack_user_id)
    except TokenExpiredError:
        raise HTTPException(status_code=401, detail="Cached token has expired — re-authentication required")

    if identity is None:
        return UnauthenticatedIdentity(slack_user_id=slack_user_id)

    return AuthenticatedIdentity(**identity)
