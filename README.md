# Session Broker

Session Broker is the identity bridge between EnterpriseClaw chat channels (Slack and Microsoft Teams), Keycloak, and your agent execution plane.

Current implementation focus:

1. Authenticated session lifecycle APIs (`/sessions`).
2. Session state persistence in Redis via Dapr state API.

Planned roadmap focus:

1. Write operation: cache user tokens after Keycloak callback.
2. Read operation: resolve cached identity for each chat event and convert it to workflow identity (SPIFFE + Istio contract).

## Why this service exists

EnterpriseClaw preserves channel identity even before authentication. Users can be:

- Unauthenticated: known channel identity (for example Slack user ID) but no privileged token.
- Authenticated: completed Google IdP auth through Keycloak and allowed to consume some or all Agents/MCPs.

When a user attempts a privileged action (ticket creation, DB creation, etc.), authentication is handled externally via Keycloak. After successful login, Keycloak calls this broker directly, and the broker stores encrypted token material in Redis.

## Core workflows

### 0) Current implementation

- Input source: authenticated callers with bearer token.
- Session identity source: JWT claims (`sub`, `email`, `realm_access.roles`).
- API surface: `POST/GET/PATCH/DELETE /sessions`, `POST /sessions/{id}/handoff`, `GET /health`.
- Persistence: Redis via Dapr state store (`redis`).

### 1) Token cache write (post-auth callback)

- Input source: direct HTTP callback from Keycloak.
- Stored values: encrypted raw tokens + metadata (access, refresh, ID token) with auditing.
- Canonical cache key: Slack user ID.
- TTL policy: strict token exp claim.

### 2) Token cache read + workflow identity conversion

- Trigger: every chat event from Slack/Teams routed through your gateway.
- Broker action: read token data from Redis, validate expiration, and convert channel identity into workflow identity.
- Output: broker mints/requests workflow identity token (SPIFFE + Istio integration contract) for downstream Agent/MCP authorization.

## Technology stack

- Runtime: Python + FastAPI
- Sidecar/middleware: Dapr (HTTP, state store abstraction)
- Identity provider: Keycloak (Google IdP federation)
- Cache/store: Redis
- Platform: Kubernetes + Istio
- Delivery: Argo CD (app-of-apps)

## Security controls

- Redis encryption at rest.
- Audit log for every read/write operation.
- Token expiration enforcement using exp claim.
- No raw token leakage in API responses.

## Repository layout

```
src/          Python + FastAPI broker service
gitops/       Kubernetes and Argo CD manifests
docs/         Docusaurus documentation site
```

## Local development

```bash
cd src
pip install -r requirements.txt
uvicorn app.main:app --reload
pytest
```