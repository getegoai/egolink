---
document_status: authoritative
last_verified: 2026-06-27
verified_by: codex
---

# Git Flow Policy

EGOLINK currently uses a local GitHub Flow style.

## Current Integration Line

- Current integration branch: `autodev/egolink-p0`
- Remote status: no remote is currently configured.
- Until a remote is configured, push, pull request, and remote merge steps are
  represented by local branch, local review, validation, and local merge/commit
  discipline.

## Branch Rules

- Use one task branch per task.
- Preferred task branch pattern: `task/<TASK-ID>-short-name`.
- Keep task branches short-lived and scoped to one task packet.
- Do not mix firmware, simulator, modeling, and documentation work in one branch
  unless the active task explicitly allows those paths.
- Do not commit local secrets, API keys, runtime logs, large build artifacts, or
  private device logs.

## Task Rules

Each task should have a task packet or equivalent report that records:

- objective;
- context;
- allowed paths;
- out-of-scope boundaries;
- validation commands;
- completion evidence;
- remaining risks.

Completed task packets should live under `docs/tasks/done/`. Active task packets
should live under `docs/tasks/active/`.

## Merge Gate

Before merging a task branch into the integration line, run:

```powershell
python scripts/context_lint.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1
```

If a task is documentation-only and does not affect repository behavior,
`python scripts/context_lint.py` is the minimum gate. If there is any reasonable
chance repository behavior changed, run the full verification command too.

## Local GitHub Flow Until Remote Exists

Without a remote, the local equivalent is:

1. Start from `autodev/egolink-p0`.
2. Create `task/<TASK-ID>-short-name`.
3. Implement only the task scope.
4. Run the declared validation commands.
5. Review the diff.
6. Commit the task.
7. Merge or fast-forward into `autodev/egolink-p0` after validation.

When a remote is configured, replace local review/merge with pull request review
and protected-branch merge rules.
