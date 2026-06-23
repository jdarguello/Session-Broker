import logging

from fastapi import APIRouter, HTTPException, Query

from app.models.token_broker import (
    CallbackResponse,
    LoginStartRequest,
    LoginStartResponse,
    TokenCacheRequest,
    TokenCacheResponse,
)
from app.services.oauth_service import (
    consume_nonce,
    exchange_code_for_tokens,
    mint_login_nonce,
)
from app.services.token_service import cache_token

router = APIRouter()

logger = logging.getLogger(__name__)


@router.post("/login/start", response_model=LoginStartResponse, status_code=200)
async def login_start(body: LoginStartRequest):
    """
    (Internal-only) Initiate an OAuth Authorization-Code login flow for a Slack user.

    Mints a one-time opaque nonce (OAuth `state`) and a PKCE code_verifier/challenge
    pair, stores login:{nonce} -> {slack_user_id, code_verifier} in Redis with a
    5-minute TTL, and returns the Keycloak /authorize URL that the caller should
    deliver to the user (e.g. via Slack DM).

    This endpoint must only be reachable from the internal EnterpriseClaw gateway
    (enforced by mTLS at the infrastructure layer — not enforced here for the demo).
    """
    nonce, authorize_url = await mint_login_nonce(body.slack_user_id)
    return LoginStartResponse(authorize_url=authorize_url, state=nonce)


@router.get("/callback", response_model=CallbackResponse, status_code=200)
async def auth_callback(
    code: str = Query(..., description="Authorization code returned by Keycloak"),
    state: str = Query(..., description="One-time nonce (OAuth state) minted by login/start"),
):
    """
    Keycloak OAuth Authorization-Code callback (browser-reachable via AWS ALB Ingress).

    Runs three steps:
    1. IDENTIFY  — consume the one-time nonce (state) and recover slack_user_id +
                   code_verifier.  The nonce is deleted on first read (single-use).
    2. EXCHANGE  — POST the code to the Keycloak token endpoint to obtain access,
                   refresh, and ID tokens (broker as confidential OAuth client + PKCE).
    3. STORE     — encrypt the token set and persist it in Redis keyed by
                   slack:{slack_user_id}.

    Supersedes POST /auth/callback/cache (which is retained only as a test shim).
    """
    # Step 1 — IDENTIFY
    try:
        nonce_record = await consume_nonce(state)
    except KeyError:
        raise HTTPException(status_code=400, detail="Invalid or already-consumed state nonce")

    slack_user_id = nonce_record["slack_user_id"]
    code_verifier = nonce_record["code_verifier"]

    # Step 2 — EXCHANGE
    try:
        tokens = await exchange_code_for_tokens(code, code_verifier)
    except Exception as exc:
        logger.error("Keycloak token exchange failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Token exchange with Keycloak failed")

    # Step 3 — STORE (audit-logged inside cache_token)
    await cache_token(
        slack_user_id=slack_user_id,
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        id_token=tokens["id_token"],
    )

    return CallbackResponse(slack_user_id=slack_user_id)


@router.post("/callback/cache", response_model=TokenCacheResponse, status_code=200)
async def auth_callback_cache(body: TokenCacheRequest):
    """
    SUPERSEDED TEST SHIM — retained only for scripted tests/CI. Remove at go-live.

    Trusted raw-token write: accepts a pre-formed token set and caches it directly
    without performing the OAuth Authorization-Code exchange.  The real write path
    is GET /auth/callback (OAuth Authorization-Code + PKCE via Keycloak).

    Do NOT use this endpoint in production or in the demo narrative.
    """
    await cache_token(
        slack_user_id=body.slack_user_id,
        access_token=body.access_token,
        refresh_token=body.refresh_token,
        id_token=body.id_token,
    )
    return TokenCacheResponse(slack_user_id=body.slack_user_id)
