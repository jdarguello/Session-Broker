## Project Overview

Session Broker for AI Agent Orchestration. This is a broker that manages session state and routing for AI agents in an orchestration system.

## Repository State

This project is in its earliest stages. There is no source code yet — only a README and Apache 2.0 license. The `.github/workflows/` directory exists but is empty.

When adding code, establish the language/framework choice first and update build, test, and lint commands in this file accordingly.

## Architecture Intent

A session broker in an AI agent orchestration context typically:
- Maintains session state across agent invocations
- Routes requests to the appropriate agent or sub-agent
- Manages lifecycle (creation, handoff, termination) of agent sessions

## Design Decisions (pending)

The following have not yet been decided and should be discussed before implementation begins:
- **Transport**: HTTP, gRPC, or message queue
- **Persistence**: in-memory, Redis, or a database
- **Deployment target**: Kubernetes-native (ArgoCon context)

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
- To run locally: `cd docs && npm start`

## Guidelines

- Discuss architecture and language/framework choices before writing code
- Keep the deployment target (Kubernetes) in mind for all design decisions
- Prefer cloud-native, observable, and operationally simple solutions
