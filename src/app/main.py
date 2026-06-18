from fastapi import FastAPI
from app.routers import sessions, health

app = FastAPI(
    title="Session Broker",
    description="Tracks user identities and session state across AI Agent and MCP invocations.",
    version="0.1.0",
)

app.include_router(health.router, tags=["health"])
app.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
