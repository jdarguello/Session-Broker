from fastapi import FastAPI
from app.routers import sessions, health
from app.routers import auth, identity

app = FastAPI(
    title="Session Broker",
    description="Tracks user identities and session state across AI Agent and MCP invocations.",
    version="0.2.0",
)

app.include_router(health.router, tags=["health"])
app.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(identity.router, prefix="/identity", tags=["identity"])
