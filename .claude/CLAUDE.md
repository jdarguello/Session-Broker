## Project Overview

Session Broker for AI Agent Orchestration. The concept is a broker that manages session state and routing for AI agents in an orchestration system.

## Repository State

This project is in its earliest stages (initial commit only). There is no source code yet — only a README and Apache 2.0 license. The `.github/workflows/` directory exists but is empty.

When adding code, establish the language/framework choice first and update this file with build, test, and lint commands accordingly.

## Architecture Intent

A session broker in an AI agent orchestration context typically:
- Maintains session state across agent invocations
- Routes requests to the appropriate agent or sub-agent
- Manages lifecycle (creation, handoff, termination) of agent sessions

Design decisions about transport (HTTP/gRPC/message queue), persistence (in-memory/Redis/DB), and deployment target (Kubernetes-native given the ArgoCon context) have not yet been made and should be discussed before implementation begins.