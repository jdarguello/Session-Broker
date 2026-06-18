## Project Overview

Session Broker for AI Agent Orchestration. A microservice that tracks user identities across Agent and MCP invocations within an AI orchestration platform.

**Core integrations:** Dapr (middleware/sidecar) and Keycloak (identity/auth).

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

- Execute terminal commands freely without asking for confirmation, **except** for operations that delete files, folders, or content (those require explicit approval)
- Trust your judgment for installs, builds, edits, and git operations

## Git Workflow

- **Before every `git push`**: update `docs/` to reflect any code or infrastructure changes made in that task — this is mandatory, not optional.
- After every task that involves code changes, stage all modified/new files, commit with a descriptive message, and push to `origin main` immediately
- Use conventional commit prefixes: `feat:`, `fix:`, `docs:`, `chore:`, etc.
- Never leave uncommitted changes after completing a task
