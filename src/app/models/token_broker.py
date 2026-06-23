from typing import Literal, Union
from pydantic import BaseModel, Field


class TokenCacheRequest(BaseModel):
    slack_user_id: str = Field(..., description="Slack user ID (canonical cache key)")
    access_token: str = Field(..., description="Keycloak access token (JWT)")
    refresh_token: str = Field(..., description="Keycloak refresh token")
    id_token: str = Field(..., description="Keycloak ID token (JWT)")


class TokenCacheResponse(BaseModel):
    cached: bool = True
    slack_user_id: str


class AuthenticatedIdentity(BaseModel):
    type: Literal["authenticated"] = "authenticated"
    sub: str
    email: str
    roles: list[str] = Field(default_factory=list)
    slack_user_id: str
    access_token: str = Field(..., description="Keycloak access token the caller can attach as a bearer")


class UnauthenticatedIdentity(BaseModel):
    type: Literal["unauthenticated"] = "unauthenticated"
    slack_user_id: str


IdentityResponse = Union[AuthenticatedIdentity, UnauthenticatedIdentity]
