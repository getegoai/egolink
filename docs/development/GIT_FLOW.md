---
document_status: authoritative
last_verified: 2026-07-10
verified_by: codex
---

# GitHub Flow Policy

Ego Link uses a GitHub Flow style adapted for a small founder/operator plus
Codex development loop.

## Branch Model

- `main` is the release line. It must stay buildable, runnable, and honest
  about product claims.
- `egolink-p0` is the current P0 engineering-alpha candidate branch.
- Task branches may be created from `main` or `egolink-p0` when a narrower
  review boundary is useful: `task/<TASK-ID>-short-name`.
- A branch that cannot be run like the current engineering product must not be
  merged to `main`.

## Remote

- Remote: `origin`
- URL: `https://git.example.invalid/ego/egolink.git`
- Remote `main` is the protected integration target.

## Merge Gate

Before merging into `main`:

```powershell
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

The release candidate must also have:

- a clear current-state note in `docs/current/STATUS.md`;
- a runnable path in `README.md`;
- no uncommitted tracked files;
- no secrets, runtime databases, private logs, large build outputs, or raw
  private device logs committed;
- explicit non-claims for unverified location accuracy, calling/SMS, model
  performance, and battery life.

## Release Tags

Use `v0.x.y` tags only for founder-visible engineering-alpha checkpoints.

For v0.1.0 Engineering Alpha, the release meaning is:

```text
4G board -> LTE -> Message Hub -> Web Dashboard
          -> field evidence summaries -> D2/D5 location data flywheel
```

This is not a mass-production or commercial product-readiness claim.

## Push Policy

- Push branches for review or backup when useful.
- Do not force-push `main`.
- Prefer merging `egolink-p0` to `main` only when the release gate is green.
- Delete short-lived task branches after merge when no longer needed.
