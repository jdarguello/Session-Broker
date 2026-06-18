from fastapi import APIRouter
from app.models.token_broker import TokenCacheRequest, TokenCacheResponse
from app.services.token_service import cache_token

router = APIRouter()


@router.post("/callback/cache", response_model=TokenCacheResponse, status_code=200)
async def auth_callback_cache(body: TokenCacheRequest):
    """
    Keycloak post-authentication callback.

    Encrypts the token set (access + refresh + ID) with AES-256-GCM and
    persists it in Redis via Dapr, keyed by Slack user ID, with a TTL
    derived from the access token's `exp` claim.
    """
    await cache_token(
        slack_user_id=body.slack_user_id,
        access_token=body.access_token,
        refresh_token=body.refresh_token,
        id_token=body.id_token,
    )
    return TokenCacheResponse(slack_user_id=body.slack_user_id)
