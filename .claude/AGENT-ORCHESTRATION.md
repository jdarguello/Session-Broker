# Agent Orchestration — Manager / Coder / Reviewer

Three project subagents in `.claude/agents/` implement a review→code→review loop
for the Session Broker, with a human approval gate between loops.

| Agent      | Model            | Effort | Role |
|------------|------------------|--------|------|
| `manager`  | claude-opus-4-8  | max    | Orchestrates one loop: get findings → split into disjoint-file tasks → dispatch ≤3 coders → merge → re-review → report + ask for approval. Does not write feature code. |
| `coder`    | claude-sonnet-4-6| medium | Implements ONE scoped task in an isolated git worktree, commits, reports its SHA. Demo scope only. |
| `reviewer` | claude-opus-4-8  | high   | Read-only. Compares AS-IS repo to TO-BE (`.claude/CLAUDE.md`), **demo scope only**, returns findings + CONVERGED/NEEDS_WORK. |

## Why the outer loop lives in the main session

A subagent **cannot pause mid-run to ask you for approval** — it runs to
completion and returns one result. So "let me know the differences and wait for
my approval before the next loop" cannot live inside the manager. The manager
runs **one** cycle and returns a `LOOP REPORT` + `APPROVAL REQUEST`; the **main
Claude session** is what shows you the diff, waits for your decision, and
re-invokes the manager for the next loop.

## How to run it

1. In the main session, say: **"Run the manager loop on the session broker."**
   The main session invokes the `manager` subagent (no prior findings ⇒ it starts
   with a reviewer pass).
2. The manager returns a `LOOP REPORT` (what changed, the `git diff --stat`,
   test/lint results, the re-review verdict, new findings) and an
   `APPROVAL REQUEST`.
3. The main session surfaces this to you. **You decide:**
   - **Approve** → the main session re-invokes the manager, passing the approved
     findings list so it skips the redundant initial review and goes straight to
     dispatch → merge → re-review.
   - **Stop** → the loop ends; commit/push as usual per the Git Workflow.
4. Repeat until the reviewer returns `CONVERGED`.

## Design choices baked in

- **Scope = demo only.** The reviewer ignores the deferred production backlog
  (writer/reader split, Redis ACLs, OAuth `code→token` flow, refresh, ingress,
  HA) so the loop actually converges. Change the reviewer's scope section to widen
  it later.
- **Parallelism = isolated git worktrees.** Each coder works in its own worktree
  (`isolation: worktree`), commits, and reports a SHA; the manager merges each SHA
  into the working tree. Tasks are also partitioned by disjoint file sets so
  merges stay clean.
- **Max 3 coders in parallel**, enforced by the manager's prompt (batches of ≤3).
- **Separation of duties.** Manager: no Edit/Write (orchestrates + merges).
  Coder: Edit/Write in its worktree. Reviewer: read-only.

## Known operational notes

- `git worktree remove` deletes a directory; per project policy deletions may
  prompt for approval in the main session. If denied, the manager leaves the
  worktree and notes it.
- Coders run `ruff check app/` and `pytest -q` in `src/`; source `.venv` if
  needed. The manager re-runs them on the merged tree before re-reviewing.
- Nested subagents are supported up to 5 levels deep; this design uses 2
  (main → manager → coder/reviewer), well within the limit.
