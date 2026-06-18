## Project Overview

Session Broker for AI Agent Orchestration. A microservice that tracks user identities across Agent and MCP invocations within an AI orchestration platform.

**Core integrations:** Dapr (middleware/sidecar) and Keycloak (identity/auth).

## Repository State

- `docs/` — Docusaurus site initialized and deployed via GitHub Pages
- `src/` — application source code (language/framework not yet decided)
- `gitops/` — Kubernetes/GitOps manifests (empty, structure not yet decided)
- `.github/workflows/deploy-docs.yml` — CI/CD for docs

When adding source code, establish the language/framework first and update build, test, and lint commands in this file.

## Architecture Intent

A session broker in an AI agent orchestration context:
- Tracks user identity across Agent and MCP invocations
- Maintains session state across agent invocations
- Routes requests to the appropriate agent or sub-agent
- Manages lifecycle (creation, handoff, termination) of agent sessions
- Integrates with **Dapr** as middleware/sidecar for service invocation, pub/sub, and state management
- Integrates with **Keycloak** for identity, authentication, and authorization

## Design Decisions (pending)

The following have not yet been decided and should be discussed before implementation begins:
- **Language/framework**: for `src/`
- **Transport**: HTTP, gRPC, or message queue (via Dapr)
- **Persistence**: in-memory, Redis, or a database (via Dapr state store)
- **GitOps structure**: Helm, Kustomize, or raw manifests in `gitops/`

## Project Structure

```
docs/         # Docusaurus documentation site (deployed to GitHub Pages)
src/          # Application source code
gitops/       # Kubernetes / GitOps manifests
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

- Discuss architecture and language/framework choices before writing code
- Keep the deployment target (Kubernetes + Dapr sidecar) in mind for all design decisions
- Prefer cloud-native, observable, and operationally simple solutions

## Agent Behavior

- Execute terminal commands freely without asking for confirmation, **except** for operations that delete files, folders, or content (those require explicit approval)
- Trust your judgment for installs, builds, edits, and git operations

## Git Workflow

- After every task that involves code changes, stage all modified/new files, commit with a descriptive message, and push to `origin main` immediately
- Use conventional commit prefixes: `feat:`, `fix:`, `docs:`, `chore:`, etc.
- Never leave uncommitted changes after completing a task
