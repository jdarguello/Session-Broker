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

## Cluster Operations

- The GitOps stack runs on a **local kubeadm cluster inside a UTM VM**, managed by Argo CD. `kubectl` is **not** installed on the Mac — run cluster commands via `ssh controlplane kubectl …` (access specifics, e.g. the dedicated user/key, live in session memory).
- `gitops/bootstrap.yaml` is **not** fully turnkey on a bare cluster: it has three out-of-band prerequisites it cannot provide — a **default StorageClass** (the kubeadm cluster ships with none, so all PVCs hang Pending); the **pre-created Secrets** (`redis-secret` in both `redis` and `session-broker`, `keycloak-admin-secret`, `keycloak-postgresql-secret`, `session-broker-secret` in `session-broker`, and `keycloak-realm-secrets` in `keycloak`; plaintext secrets are intentionally not committed); and the **`keycloak-hostnames` ConfigMap(s)** carrying the tenant's external hostnames (EnterpriseClaw creates these on the cloud deploy; on a bare/local cluster pre-create at least the `keycloak`-namespace copy with localhost values, or Keycloak's pod stays `CreateContainerConfigError` and the realm import fails to resolve `$(env:BROKER_EXTERNAL_URL)`). All are documented in [`docs/docs/gitops/deployment.mdx`](docs/docs/gitops/deployment.mdx).
- ⚠️ **Hostnames are externalized, not hardcoded.** The Keycloak workload + realm import (`gitops/keycloak/values.yaml`, via `extraEnvVarsCM: keycloak-hostnames` and `$(env:BROKER_EXTERNAL_URL)` in the `session-broker` client) and the cloud session-broker overlay (`gitops/session-broker/overlays/aws`, via `envFrom`) all consume the `keycloak-hostnames` ConfigMap. `gitops/bootstrap.yaml`'s `session-broker` element points at `overlays/aws` (cloud); the app-of-apps (`gitops/apps/session-broker.yaml`) still points at `overlays/dev` (local SSH-tunnel). The two entrypoints are **no longer interchangeable** for the broker overlay. Chart 22.2.3 ships **Keycloak 25** (hostname v1 → `KC_HOSTNAME_URL`/`KC_HOSTNAME_ADMIN_URL` valid); `proxyHeaders: xforwarded` handles the edge-TLS ALB.
- ⚠️ **Secret coupling:** `keycloak-realm-secrets/SESSION_BROKER_CLIENT_SECRET` **must equal** `session-broker-secret/keycloak-client-secret` (the broker and Keycloak must agree on the confidential-client secret — keycloak-config-cli writes the realm's client secret from that env). `keycloak-realm-secrets` also holds `GOOGLE_CLIENT_SECRET` (supplied out-of-band — Keycloak masks IdP/client secrets on read, so they can't be recovered from the cluster) and `ALICE_PASSWORD` (demo user).
- Dependency images are pinned to `docker.io/bitnamilegacy/*` because Broadcom retired the free `docker.io/bitnami/*` versioned tags (2025-08-28). `bitnamilegacy` is a frozen, unmaintained mirror — fine for the demo, revisit for production.

## Scope & Boundaries (IMPORTANT)

This repo is **only** the session-broker microservice plus the dependencies it owns (Dapr, Keycloak, Redis). It does **not** contain — and must not try to add — the orchestration around it:

- **Argo Events, Argo Workflows, the agents-gateway, and Istio** all live in the **EnterpriseClaw main project**, not here.
- This service does **not** mint SPIFFE IDs or emit an Istio identity contract. Istio (in EnterpriseClaw) propagates the user's token downstream for authorization and auditability. The broker's job stops at storing and returning the token.

Do not reintroduce SPIFFE/Istio "workflow identity contract" language into this repo's code or docs — that was an earlier misconception, now corrected.

## Architecture Intent

A token broker in an AI agent orchestration context. Two conceptual roles (see below):
- **Stores** the user's token material after the Keycloak callback (user authenticates via Google IdP → Keycloak → callback delivers token data here).
- **Returns** the cached user token to an authorized caller so that caller can act as the user when invoking downstream agents.
- Integrates with **Dapr** as middleware/sidecar for state management (Redis).
- Integrates with **Keycloak** for identity/auth (write path only).

## The Two Roles (target design)

The broker is conceived as two security-isolated roles. **Currently implemented as a single combined service; the split is deferred to the production phase (see Demo Scope).**

1. **Token storage (writer)** — receives the user's token from the Keycloak callback and stores it in Redis. Internet-adjacent (linked to Keycloak, which is exposed). Target: dedicated service account + Redis permissions that allow **storing tokens only**, nothing else.
2. **Token reception (reader)** — **private** service. Different service account, **not** integrated with Keycloak (must not call it in any way). Gated by **mTLS** so only a specific Argo Workflows step (with a specific service account, defined in EnterpriseClaw) can call it. Returns the user's token so the workflow can use the user's identity when calling agents.

## Architecture Source Of Truth

The primary responsibility of this service is **token brokerage**, not generic session CRUD:
- Write flow: Keycloak callback stores encrypted token set in Redis.
- Read flow: authorized caller resolves the cached token and **the reader returns the user's access token** (plus identity claims) — not a SPIFFE/Istio contract.

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
| Keycloak realm configuration | **Declarative via [keycloak-config-cli](https://github.com/adorsys/keycloak-config-cli)** (RESOLVED 2026-06-26), bundled in the Bitnami chart and run as an in-cluster **post-upgrade Helm hook** → Argo-driven, reconciles on every sync. The realm is inlined in [`gitops/keycloak/values.yaml`](gitops/keycloak/values.yaml) under `keycloakConfigCli.configuration`. Runs **additive / no-delete** (`IMPORT_MANAGED_*=no-delete`) so it never prunes Keycloak built-ins. Secrets via `$(env:...)` from the pre-created `keycloak-realm-secrets`. No more manual Admin-UI/kcadm steps. To change the realm safely, use the **`keycloak-realm` skill**. |
| Authorization model | **Claims-only** (RESOLVED 2026-06-26): the broker **carries** the user's permissions in the token but does **not** enforce them — downstream EnterpriseClaw agents enforce. Model = **groups (org placement) + per-agent client roles**: realm roles `agent-user` (baseline) / `senior-engineer` (composite → `infra-provisioner:db:provision:dev`); `bearerOnly` agent clients `issue-tracker` + `infra-provisioner` holding client roles (token `resource_access.<agent>.roles`); groups `/engineering` → `/engineering/seniors`. Full catalog + a per-user claims table live in [`docs/docs/architecture/dapr-keycloak.mdx`](docs/docs/architecture/dapr-keycloak.mdx). |
| Slack↔Keycloak identity binding | **Signed one-time `state` (nonce)** in the OAuth Authorization-Code flow; broker mints `login:{nonce}→slack_user_id` and recovers it at callback (see Identity Correlation & Write Path) |
| Token provenance (write path) | **Broker is the confidential OAuth client and performs the `code→token` exchange itself** — it no longer trusts raw tokens posted by the caller. **Promoted to demo scope (2026-06-23):** the ArgoCon demo now ships this real flow; the trusted `POST /auth/callback/cache` is **superseded** (kept only as a labeled test shim). |
| Writer browser exposure | **Owned by EnterpriseClaw, not this repo (CHANGED 2026-06-30).** EnterpriseClaw's **shared platform AWS ALB + Istio Gateway/VirtualService** route `broker.<tenant-domain>/auth/callback` to the broker Service; the user's browser reaches Keycloak + the broker callback through that. This repo **no longer ships its own callback Ingress** — a broker-owned ALB Ingress was redundant with EnterpriseClaw's exposure and, on the cloud deploy, never got an ACM cert for its placeholder host (`broker.session-broker.example.com`), so the AWS LB Controller never built an ALB and Argo CD's Ingress health check pinned the app in **Progressing** forever (the broker workload itself was healthy). Removing it also respects the scope boundary (Istio/edge routing live in EnterpriseClaw). ⚠️ Prereq: the EnterpriseClaw platform cluster (shared ALB + Istio). The local kubeadm-in-UTM cluster has **no** ingress controller — `overlays/dev` reaches the broker through an **SSH tunnel** instead. |
| Keycloak URL split by channel (write path) | **Two URLs, chosen by *who makes the request*, not by where the pod sits.** **Front-channel** (consumed by the user's *browser*: the `/authorize` URL the broker builds, and the `redirect_uri` callback) uses Keycloak's **external** hostname → `KEYCLOAK_ISSUER_URL`. **Back-channel** (the `code→token` exchange, an outbound call the **broker pod itself** makes) uses the **in-cluster** Keycloak Service → `KEYCLOAK_TOKEN_URL` (e.g. `http://keycloak.keycloak.svc.cluster.local/realms/enterpriseclaw/protocol/openid-connect/token`). Rationale: the broker only *builds* the authorize URL (a string a browser later clicks) but *calls* the token endpoint itself, so the exchange must not hairpin out through the ALB. The writer pod stays in a **private** subnet, reachable from the internet only on `/auth/callback` via the ALB while retaining east-west reach to Keycloak/Redis — internet-exposure and backend-reach are not in tension. ⚠️ Keycloak must have `KC_HOSTNAME`/frontend-url pinned to the **external** value so issued tokens' `iss` stays consistent regardless of which host the broker POSTs to. `KEYCLOAK_TOKEN_URL` falls back to deriving from `KEYCLOAK_ISSUER_URL` when unset (back-compat / single-cluster). |
| Demo IdP | **Google Workspace federation behind Keycloak.** The broker only ever talks to Keycloak; Google is Keycloak's upstream IdP, transparent to the broker's code. |
| Slack→Keycloak user model | **Single Google Workspace domain; email matches across Slack and Google.** Used as a defense-in-depth cross-check at callback, **not** as the cache key (cross-check itself deferred to hardening — see Demo Scope) |

### Dapr + Keycloak integration pattern (from https://oneuptime.com/blog/post/2026-03-31-dapr-with-keycloak/view)

- Keycloak redirects the browser to the broker's `GET /auth/callback`; the broker exchanges the `code` for tokens and persists the encrypted token material
- Cache key is Slack user ID, with strict `exp` claim TTL policy
- Broker read endpoint resolves the cached token and returns the user's access token + claims
- Workload trust boundary is **mTLS** (enforced by Istio in EnterpriseClaw), not an in-app SPIFFE/Istio contract
- Redis persistence includes audit logs for every token read/write operation

## Canonical Identity Key

- Primary cache key: Slack user ID
- Future multi-tenant extension (optional): `<tenant-id>:<slack-user-id>`
- **Binding mechanism** (how the Slack ID is established at write time): the caller never supplies a raw `slack_user_id` at the callback. It is established via a broker-minted one-time `state` nonce — see **Identity Correlation & Write Path**.

## Identity Correlation & Write Path (DEMO SCOPE as of 2026-06-23, RESOLVED)

How a Slack user ID binds to the Keycloak/Google identity, and how token provenance is guaranteed. Resolved 2026-06-22; **promoted from go-live to demo scope 2026-06-23** — the ArgoCon demo now ships this real flow, not the trusted-token shortcut.

**Decision: signed one-time `state` (nonce) in the OAuth Authorization-Code flow, with the broker as the confidential OAuth client.** The broker mints the binding and performs the `code→token` exchange itself — it no longer trusts a raw token or a raw `slack_user_id` supplied by the caller.

Flow:
1. **`POST /auth/login/start { slack_user_id }`** (internal-only). An "open" agent (EnterpriseClaw) hits an authorization wall and needs the user to log in, so it calls this.
2. Broker mints a **one-time opaque nonce** + a **PKCE `code_verifier`**, stores `login:{nonce} → { slack_user_id, code_verifier }` in Redis with a short TTL (~5 min), builds the Keycloak `/authorize?...&state={nonce}&code_challenge=…` URL (the **broker constructs the URL** — Keycloak does not "produce" it) from the **external** `KEYCLOAK_ISSUER_URL` (this URL is consumed by the user's *browser*, so it must be browser-reachable), and returns it.
3. Agent posts the URL to the user in Slack. User authenticates via **Google → Keycloak**.
4. Keycloak redirects the browser (through **EnterpriseClaw's shared ALB + Istio Gateway**) to the broker callback `GET /auth/callback?code=&state={nonce}`.
5. The callback runs **three internal steps** (the structure defined 2026-06-23):
   - **(1) Identify** — consume the nonce (**single use — delete on read**) → recover `slack_user_id` (+ `code_verifier`); capture the `code`.
   - **(2) Exchange** — POST the `code` (+ `client_id`/`client_secret` + PKCE `code_verifier`) to Keycloak's token endpoint → receive access + refresh + ID tokens (provenance guaranteed). This is a **back-channel** call the broker pod makes itself, so it targets the **in-cluster** `KEYCLOAK_TOKEN_URL`, not the external host (see *Keycloak URL split by channel* in Design Decisions).
   - **(3) Store** — encrypt the token set and persist it in Redis keyed by `slack:{slack_user_id}` (reuses the existing `cache_token`).

Why this design: it closes both security holes with one flow — **binding** (the Slack ID rides as an unguessable, single-use, broker-owned nonce; the caller never supplies it at the callback) and **provenance** (the broker mints tokens via the `code` exchange, so cached tokens are guaranteed Keycloak-issued). It keeps Slack user ID as the cache key, so the reader path is unchanged.

Broker as confidential OAuth client: needs `client_id` + `client_secret` (K8s Secret), a registered `redirect_uri`, scopes `openid email profile` + **`offline_access`** (so a refresh token is actually issued), and **PKCE**.

**Two risks this design introduces — both must be handled:**
1. **Identity-injection on `login/start`.** The nonce proves "a login I initiated," not "the right person finished it." An attacker who can call `login/start` for a victim's Slack ID and then authenticate as *himself* would poison the victim's cache key. Defenses (use both): (a) gate `login/start` to the EnterpriseClaw gateway only (mTLS / internal-only); (b) **email cross-check at callback** — resolve the nonce's `slack_user_id` to its corporate email (Slack `users.info`, scope `users:read.email`) and require the Keycloak token's verified `email` to match; reject on mismatch. The cross-check is the robust backstop and is **viable because every user is one verified `@corp.com` Google Workspace identity, with matching email across Slack and Google** (confirmed 2026-06-22). **Demo (2026-06-23): only defense (a) — gating `login/start` internal-only — ships; the email cross-check is deferred to hardening.**
2. **The callback `redirect_uri` must be browser-reachable.** The user's browser is redirected to `/auth/callback`, so the writer is exposed via **EnterpriseClaw's shared platform ALB + Istio Gateway/VirtualService** (CHANGED 2026-06-30 — this repo no longer ships its own callback Ingress; the broker-owned ALB Ingress was redundant and broke Argo health on the placeholder host — see *Writer browser exposure* in Design Decisions), and the `redirect_uri` (supplied via `keycloak-hostnames`) is registered in Keycloak. ⚠️ That exposure only exists on the EnterpriseClaw platform cluster; the local kubeadm-in-UTM cluster has no ingress controller, so `overlays/dev` uses an SSH tunnel instead — track as a demo prerequisite.

**Email is a cross-check, not the binding.** Do not key the cache by email (it is mutable and would force a Slack→email resolution on every read). Use the matching-email fact only to validate the binding at callback and for audit.

**Unresolved tension (decide before building reader-side refresh):** refreshing an expired access token requires calling Keycloak, which contradicts the rule that the reader never touches Keycloak. Storing the refresh token now (via `offline_access`) is free, but *using* it means either the reader calls Keycloak (breaks the role split) or a third internal component owns refresh. Flagged, not solved.

## Token Storage Contract

- Cache: access token + refresh token + ID token
- Storage format: encrypted raw token payload + metadata
- Expiration: strict token `exp` claim policy
- **Read contract:** `/identity/resolve` returns the user's **access token** (so the caller can attach it as a bearer) alongside identity claims. Returning only flattened claims is insufficient — the caller needs a usable token.

## Demo Scope vs Production Backlog (IMPORTANT)

Current target is an **ArgoCon demo** that works *reasonably*, not a production deployment. Time is limited. Do not over-engineer; prefer the smallest change that makes the flow work.

**In scope for the demo (these are functional, not hardening — they block the demo if missing):**
- **Real OAuth Authorization-Code write path** (promoted 2026-06-23): `POST /auth/login/start` mints the nonce + PKCE + authorize URL; `GET /auth/callback` runs the three steps (identify → exchange → store). Requires a Keycloak **confidential client** with a `client_secret` (new K8s Secret), **Google federation** behind Keycloak, a registered `redirect_uri`, and **EnterpriseClaw's shared ALB + Istio Gateway** fronting the callback (this repo no longer ships its own Ingress). The `code→token` exchange uses the **in-cluster** `KEYCLOAK_TOKEN_URL` (back-channel), while the authorize URL/`redirect_uri` use the **external** `KEYCLOAK_ISSUER_URL` (front-channel) — see *Keycloak URL split by channel* in Design Decisions.
- The reader (`/identity/resolve`) must **return the user's access token**, not just claims. (Today it drops the token — must fix.)
- The Dapr **bearer middleware must not break the read path**. It points at Keycloak and 401s callers with no user bearer; remove it from the reader path or confirm the call path bypasses it. The reader must not be forced to contact Keycloak.
- `exp=None → no TTL` and missing httpx timeouts are cheap correctness fixes worth doing.

**Deferred to the production phase (do NOT spend demo time on these unless I ask):**
- Splitting writer/reader into separate Deployments + service accounts (`BROKER_ROLE` router-gating).
- Separate Redis ACL users (write-only / read-only) and two Dapr state-store components. **Landmine:** Dapr's Redis state store uses Lua/EVAL + etag reads even on writes, so a strict write-only ACL likely breaks Dapr saves — must be tested before relying on it.
- Refresh-token usage (broker refreshing expired access tokens on read). **Design tension unresolved** — see Identity Correlation & Write Path (reader must not touch Keycloak, but refresh requires it).
- Write-path authentication & Slack↔Keycloak binding — **PROMOTED TO DEMO SCOPE (2026-06-23).** The demo now ships the broker-minted signed-`state` OAuth Authorization-Code flow (broker as confidential OAuth client): `POST /auth/login/start` + the real `GET /auth/callback` (3 steps: identify → exchange → store), Google federation behind Keycloak, with the callback fronted by EnterpriseClaw's shared ALB + Istio Gateway (see **Identity Correlation & Write Path**). The trusted `POST /auth/callback/cache` is **superseded** — retained only as a clearly-labeled test shim. **Still deferred to hardening:** the email cross-check at callback.
- HA (Dapr/Redis/Keycloak), Redis replication + encryption-at-rest, image build CI, secret provisioning automation, NetworkPolicies, non-root container, monitoring.

When the project reaches "production-mind" status we revisit all deferred items together.

## Security And Observability Guardrails

- Audit log every token read and write
- Never log token values in app logs, errors, or API responses
- Reject expired token material on read path
- Keep Redis encryption at rest enabled

## API Contract Priority

Prioritize these broker APIs in docs and implementation:

**Demo (current target — real OAuth write path, as of 2026-06-23):**
- `POST /auth/login/start` — mint one-time `state` nonce + PKCE `code_verifier`, store `login:{nonce}→{slack_user_id, code_verifier}`, return the Keycloak authorize URL (internal-only)
- `GET /auth/callback` — **(1)** recover `slack_user_id` from `state` + capture `code`, **(2)** exchange `code`→tokens at Keycloak (client_secret + PKCE), **(3)** store the encrypted token set in Redis. Browser-reachable via EnterpriseClaw's shared ALB + Istio Gateway (no broker-owned Ingress). **Supersedes** `POST /auth/callback/cache`.
- `POST /identity/resolve` — returns the user's **access token** + identity claims

**Retained as a test shim (not the demo narrative):**
- `POST /auth/callback/cache` — trusted raw-token write; kept only for scripted tests/CI, clearly labeled. Remove at go-live.

**Deferred to hardening:**
- Email cross-check at callback; writer/reader split; refresh-token usage.

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
- **keycloak-config-cli realm (`gitops/keycloak/values.yaml`):** (1) `$(env:...)` substitution runs over the **whole file including comments** — never put a literal `$(env:...)` in a realm comment or the import dies with `Cannot resolve variable 'env:...'` (write "env substitution" in prose instead). (2) Always run **`IMPORT_MANAGED_*=no-delete`** (additive) so it doesn't prune realm built-ins / unrelated clients (`account`, `broker`, `realm-management`, …). (3) Keycloak **masks IdP/client secrets on read** — they can't be recovered from the cluster; supply via `keycloak-realm-secrets`. (4) The realm is **`enterpriseclaw`** (not `session-broker`). (5) Validate every realm change with a one-off kc-config-cli Job **before pushing** — see the `keycloak-realm` skill.
- **`sudo` is blocked on the `controlplane` node** for the `claude` user (canned HAL-style refusal on stderr, non-zero exit). `sudo crictl`/`journalctl`/`ss` produce no output — with `2>/dev/null` this silently looks like "nothing found" (once caused a false "cluster is down" read). Use `kubectl` for all node introspection; never sudo.

## Guidelines

- Keep the deployment target (Kubernetes + Dapr sidecar) in mind for all design decisions
- Prefer cloud-native, observable, and operationally simple solutions
- For every design/architecture definition, feel free to ask any question that comes to your mind. I need everything to be as clearer as possible.

## Agent Behavior

- Edit any file without asking for permission. Do not pause to confirm edits unless I say that I want to review your work first.
- Execute terminal commands freely without asking for confirmation, **except** for operations that delete files, folders, or content (those require explicit approval)
- Trust your judgment for installs, builds, edits, and git operations

## Git Workflow

- **Before every `git push`**: update `docs/` to reflect any code or infrastructure changes made in that task — this is mandatory, not optional.
- After every task that involves code changes, stage all modified/new files, commit with a descriptive message, and push to `origin main` immediately
- Use conventional commit prefixes: `feat:`, `fix:`, `docs:`, `chore:`, etc.
- Never leave uncommitted changes after completing a task
