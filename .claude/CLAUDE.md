## Project Overview

Session Broker for AI Agent Orchestration. A microservice that brokers user identity from enterprise chat channels into workflow identity for Agents and MCPs.

## Repository State

- `docs/` — Docusaurus docs deployed via GitHub Pages
- `src/` — Python + FastAPI session broker application
- `gitops/` — Kustomize + Helm Kubernetes/GitOps manifests managed by Argo CD
- `.github/workflows/deploy-docs.yml` — docs CI/CD

### Build / Test / Lint (src/)

```bash
cd src
pip install -r requirements.txt
uvicorn app.main:app --reload
pytest
ruff check app/
```

## Architecture Intent

Session Broker is centered on two workflows:
- Write flow: Keycloak callback stores encrypted token set in Redis
- Read flow: channel event resolves token context and returns workflow identity contract (SPIFFE/Istio)

### Identity model

- User types: `unauthenticated` and `authenticated`
- Unauthenticated users still preserve channel identity (for example Slack user ID)
- Authenticated users are authorized by Keycloak realm roles and client scopes

### Canonical key and storage

- Canonical cache key: Slack user ID
- Store access token + refresh token + ID token
- Persist encrypted raw token payload + metadata
- TTL policy: strict token `exp` claim

### API contract priority

Prioritize these endpoints in docs and implementation:
- `POST /auth/callback/cache` (write)
- `POST /identity/resolve` (read + identity conversion)

Support both direct REST and Dapr invocation examples.

### Security and observability

- Audit log every token read/write operation
- Do not log raw token values
- Reject expired token material during read path
- Keep Redis encryption at rest enabled

### Clarification behavior for architecture/design

For every design/architecture definition, feel free to ask any question that comes to your mind. I need everything to be as clearer as possible.

### Deployment model

- Transport: HTTP via Dapr service invocation
- Persistence: Redis via Dapr state store
- Delivery: Argo CD app-of-apps with manifests in `gitops/apps/`