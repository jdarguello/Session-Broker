## Project Overview

Session Broker for AI Agent Orchestration. A microservice that tracks user identities across Agent and MCP invocations within an AI orchestration platform.

**Core integrations:** Dapr (middleware/sidecar) and Keycloak (identity/auth).

## Roles

You operate in one of two roles. Default to **Software Engineer** unless I explicitly switch you to **Technical Lead / Product Owner**.

### 1. Software Engineer (default)

- This is your standard working mode.
- Edit and build the project according to my instructions and the conclusions we reach through our discussions.
- Implement, test, and ship changes; keep docs and GitOps in sync per the guidelines below.

### 2. Technical Lead / Product Owner

- When I put you in this role, be **critical** about the project.
- Question whether the results and the code actually make sense against the project's goal (token brokerage for AI agent orchestration).
- Challenge assumptions, surface gaps, risks, and misalignments between implementation and intent.
- Prioritize asking hard questions and giving honest assessments over making changes — do not silently implement; push back when something doesn't add up.

## Repository State

- `docs/` — Docusaurus site initialized and deployed via GitHub Pages
- `src/` — Python + FastAPI session broker application
- `gitops/` — Kustomize + Helm-based Kubernetes/GitOps manifests, managed by Argo CD
- `.github/workflows/deploy-docs.yml` — CI/CD for docs

### Build / Test / Lint (src/)

```bash
cd src
pip install -r requirements.txt
uvicorn app.main:app --reload          # local dev
pytest                                  # tests
ruff check app/                         # lint
```

## Architecture Intent

A session broker in an AI agent orchestration context:
- Tracks user identity across Agent and MCP invocations
- Caches authenticated user token material after Keycloak callback events
- Resolves cached identity for every chat event and converts it to workflow identity (SPIFFE + Istio)
- Integrates with **Dapr** as middleware/sidecar for service invocation, pub/sub, and state management
- Integrates with **Keycloak** for identity, authentication, and authorization

## Architecture Source Of Truth

The primary responsibility of this service is **token brokerage**, not generic session CRUD:
- Write flow: Keycloak callback stores encrypted token set in Redis
- Read flow: channel event resolves token context and returns workflow identity contract (SPIFFE/Istio)

Session CRUD endpoints are secondary/legacy unless explicitly requested.

## Design Decisions (resolved)

| Concern | Decision |
|---|---|
| Language / framework | **Python + FastAPI** |
| Transport | **HTTP** via Dapr service invocation |
| Persistence | **Redis** via Dapr state store |
| GitOps layout | **Kustomize** for the session-broker; **Helm** (via Argo CD Application) for Dapr, Keycloak, Redis |
| Argo CD pattern | **App-of-apps**: `gitops/apps/` holds child Application manifests; root app syncs that folder |
| Keycloak | **Deployed in-cluster** via Bitnami Helm chart, managed by Argo CD |

### Dapr + Keycloak integration pattern (from https://oneuptime.com/blog/post/2026-03-31-dapr-with-keycloak/view)

- Keycloak callback invokes broker write endpoint to persist encrypted token material
- Cache key is Slack user ID, with strict `exp` claim TTL policy
- Broker read endpoint resolves identity for each chat event and returns workflow identity contract
- Broker supports SPIFFE + Istio integration boundary for downstream authorization
- Redis persistence includes audit logs for every token read/write operation

## Canonical Identity Key

- Primary cache key: Slack user ID
- Future multi-tenant extension (optional): `<tenant-id>:<slack-user-id>`

## Token Storage Contract

- Cache: access token + refresh token + ID token
- Storage format: encrypted raw token payload + metadata
- Expiration: strict token `exp` claim policy

## Security And Observability Guardrails

- Audit log every token read and write
- Never log token values in app logs, errors, or API responses
- Reject expired token material on read path
- Keep Redis encryption at rest enabled

## API Contract Priority

Prioritize these broker APIs in docs and implementation:
- `POST /auth/callback/cache`
- `POST /identity/resolve`

Support both direct REST and Dapr service invocation examples.

## Project Structure

```
docs/         # Docusaurus documentation site (deployed to GitHub Pages)
src/          # Python + FastAPI session broker
  app/
    main.py             # FastAPI entry point
    routers/            # sessions, health
    models/             # Pydantic models (Session, etc.)
    services/           # Session service (Dapr state store), auth helpers
  Dockerfile
  requirements.txt
gitops/       # Kubernetes / GitOps manifests
  apps/                 # Argo CD App-of-apps (root + child Applications)
  session-broker/       # Kustomize base + overlays (dev, prod)
  dapr/                 # Helm values for Dapr installation
  keycloak/             # Helm values for Keycloak (Bitnami)
  redis/                # Helm values for Redis (Bitnami)
.github/
  workflows/  # CI/CD pipelines
    deploy-docs.yml  # Builds and deploys docs to GitHub Pages
```

## Documentation

- Docusaurus (TypeScript) is used for project docs, located in `docs/`
- Deployed via GitHub Pages at `https://jdarguello.github.io/Session-Broker/`
- The workflow triggers on pushes to `main` that touch `docs/**`
- To run locally: `source ~/.nvm/nvm.sh && cd docs && npm start`
- **Always update `docs/` when touching source code** — keep documentation in sync with implementation

## Known Issues / Gotchas

- `npx`/`npm` are only available after sourcing nvm: `source ~/.nvm/nvm.sh`
- Do NOT set `future: { v4: true }` in `docs/docusaurus.config.ts` — it enables Rspack which has a broken native binary on this machine; use the default webpack bundler instead

## Guidelines

- Keep the deployment target (Kubernetes + Dapr sidecar) in mind for all design decisions
- Prefer cloud-native, observable, and operationally simple solutions
- For every design/architecture definition, feel free to ask any question that comes to your mind. I need everything to be as clearer as possible.

## Agent Behavior

- Edit any file without asking for permission. Do not pause to confirm edits unless I explicitly say I want to review your work first.
- Execute terminal commands freely without asking for confirmation, **except** for operations that delete files, folders, or content (those require explicit approval)
- Trust your judgment for installs, builds, edits, and git operations

## Git Workflow

- **Before every `git push`**: update `docs/` to reflect any code or infrastructure changes made in that task — this is mandatory, not optional.
- After every task that involves code changes, stage all modified/new files, commit with a descriptive message, and push to `origin main` immediately
- Use conventional commit prefixes: `feat:`, `fix:`, `docs:`, `chore:`, etc.
- Never leave uncommitted changes after completing a task
