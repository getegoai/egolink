---
document_status: archived
last_verified: 2026-07-03
verified_by: claude
---

> Archived 2026-07-03 by ENG-007 per ADR-0002: this workflow did not work in
> practice. Use `docs/development/DIRECTOR_WORKFLOW.md`. Historical evidence only.

# Dual Codex Workflow

This workflow is for controlled collaboration between two authorized Codex
sessions or accounts. It is not a method for bypassing service usage limits.

## Roles

- Account A: Planner / Integrator / Reviewer
- Account B: Builder / Tester

Account A owns task definition, context boundaries, integration review, final
validation, and merge decisions. Account B may implement or test a clearly scoped
task branch.

## Required Isolation

- Each account must use an independent Git worktree.
- Do not let two accounts modify the same filesystem working tree at the same
  time.
- Do not share account credentials, API keys, session tokens, cookies, or local
  configuration files between accounts.
- Do not use multiple accounts or sessions to evade usage limits, rate limits,
  product terms, or billing boundaries.

## Worktree Pattern

Example:

```powershell
git worktree add ..\egolink-builder task/ENG-XXX-builder
```

The Planner/Integrator remains in the integration worktree. The Builder/Tester
works only in the builder worktree and returns a diff, commit, or branch for
review.

## Handoff Rules

- The Planner gives the Builder one task packet, allowed paths, and validation
  commands.
- The Builder must not expand scope without explicit Planner approval.
- The Builder reports changed files, validation results, evidence paths, and
  remaining risks.
- The Planner reviews the diff, reruns required validation, and decides whether
  to merge, request changes, or split the task.

## Conflict Rules

- If both accounts need the same file, stop and serialize the work.
- If a task fails because the parent task is wrong or under-specified, escalate
  back to the Planner instead of widening the implementation silently.
- If hardware action is needed, only one operator/session should own that action
  at a time, and the task must explicitly allow it.
