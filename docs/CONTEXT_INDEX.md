---
document_status: authoritative
last_verified: 2026-06-26
verified_by: codex
---

# Context Index

Use this file as the first stop for Codex, Codex CLI, VS Code Codex, and AutoDev context loading.

## Default Minimal Context

Always load:

- `AGENTS.md`
- `docs/CONTEXT_INDEX.md`
- `docs/product/PRODUCT_CHARTER.md`
- `docs/product/P0_SCOPE.md`
- `docs/current/STATUS.md`
- `docs/current/ACTIVE_BUILD.md`

Do not load `docs/archive/`, `docs/generated/`, `reports/`, `model_artifacts/`, or runtime directories by default.

## Task Routing

| Task type | Required context | Optional context |
|---|---|---|
| Product or P0 scope | `docs/product/PRODUCT_CHARTER.md`, `docs/product/P0_SCOPE.md` | `docs/roadmap/P0_TO_PRODUCT_MIGRATION.md` |
| Current status or acceptance | `docs/current/STATUS.md`, `docs/current/ACTIVE_BUILD.md` | `docs/generated/CONTEXT_MIGRATION_REPORT.md` |
| Dual-board / PC Bridge architecture | `docs/architecture/SYSTEM_OVERVIEW.md`, `docs/architecture/DUAL_BOARD_PC_BRIDGE_ARCHITECTURE.md` | `docs/architecture/adr/` |
| Firmware change | `firmware/AGENTS.md`, `docs/current/ACTIVE_BUILD.md`, `docs/hardware/BOARD_MATRIX.md` | Named firmware README only |
| Hardware validation | `firmware/AGENTS.md`, `docs/hardware/BOARD_MATRIX.md`, `docs/current/ACTIVE_BUILD.md`, `docs/hardware/validation/` | Named evidence report |
| PC simulator or bridge | `pc_simulator/AGENTS.md`, `docs/architecture/SYSTEM_OVERVIEW.md`, `shared/contracts/` | Named runtime fixture |
| Model or Safety Companion | `model_lab/AGENTS.md`, `docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md`, `docs/safety/SAFETY_CONTRACT.md`, `shared/contracts/` | `docs/modeling/MODEL_ARCHITECTURE.md` |
| Quality tests | `quality_tests/AGENTS.md`, task-specific source docs | Existing related tests |
| AutoDev | `autodev/AGENTS.md`, `docs/development/AUTODEV.md`, `docs/development/AUTODEV_MONITORING.md` | Active task packet |
| Documentation-only | `docs/AGENTS.md`, this index, affected target docs | Archive sources named by the task |

## Authority Rules

- Current physical setup is authoritative only in `docs/current/ACTIVE_BUILD.md` and `docs/hardware/BOARD_MATRIX.md`.
- Product intent is authoritative only in `docs/product/PRODUCT_CHARTER.md` and `docs/product/P0_SCOPE.md`.
- Architecture changes require an ADR under `docs/architecture/adr/`.
- Protocol and model schemas are authoritative in `shared/contracts/`.
- Archive files are historical evidence and must not be cited as current authority.

## Active Task Packet Rules

Task packets live under `docs/tasks/active/` while in progress and `docs/tasks/done/` after completion. A task packet should declare:

- `context`
- `allowed_paths`
- `out_of_scope`
- validation commands
- completion evidence

Run `python scripts/context_lint.py` after editing task packets or context routing.
