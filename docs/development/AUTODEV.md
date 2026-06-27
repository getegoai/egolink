---
document_status: authoritative
last_verified: 2026-06-26
verified_by: codex
---

# AutoDev Context

AutoDev uses the same context hierarchy as Codex and VS Code Codex.

## Required Task Packet Fields

- `context`
- `allowed_paths`
- `out_of_scope`
- validation commands
- completion evidence

## Execution Rules

- Load `AGENTS.md` and `docs/CONTEXT_INDEX.md` first.
- Load only the active task packet and its declared context.
- Do not use `docs/archive/`, `docs/generated/`, `reports/`, `model_artifacts/`, or runtime folders as default context.
- Do not modify paths outside the active task's `allowed_paths`.
- Do not treat build success as hardware capability evidence.

## Legacy Sources

The pre-refactor AutoDev documents were preserved without deletion:

- `docs/archive/autodev/AUTODEV_GUIDE_legacy.md`
- `docs/archive/autodev/AUTODEV_MONITORING_legacy.md`
- `docs/archive/autodev/AUTODEV_V0_2_UPGRADE_legacy.md`
- `docs/archive/autodev/EGO_LINK_AGENTIC_DEV_PLAN_legacy.md`
