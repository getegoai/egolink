# AutoDev Module Instructions

> Retired 2026-07-03 per ADR-0002. The AutoDev loop is no longer an active
> workflow; run/runtime records here are historical evidence only. The active
> execution workflow is `docs/development/DIRECTOR_WORKFLOW.md`.

- Read root `AGENTS.md`, `docs/CONTEXT_INDEX.md`, and `docs/development/AUTODEV.md` before AutoDev work.
- AutoDev task packets must name `context`, `allowed_paths`, validation commands, and completion evidence.
- Do not modify runtime state, runs, or generated outputs unless the active task explicitly allows it.
- Do not assume archive or generated documents are default context.
- Supervisor-owned Git behavior remains outside task execution unless a task explicitly allows repository operations.
