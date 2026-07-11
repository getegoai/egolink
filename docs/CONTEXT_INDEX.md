---
document_status: authoritative
last_verified: 2026-06-30
verified_by: codex
---

# Context Index

Use this file as the first stop for Claude Code, Codex, Codex CLI, VS Code Codex, and any builder-agent context loading.

## Default Minimal Context

Always load:

- `AGENTS.md`
- `docs/product/NORTH_STAR.md` (goal + guiding principles; check its date
  every session to sense direction changes)
- `docs/CONTEXT_INDEX.md`
- `docs/product/PRODUCT_CHARTER.md`
- `docs/product/P0_SCOPE.md`
- `docs/current/STATUS.md`
- `docs/current/ACTIVE_BUILD.md`
- `docs/development/DEV_FLOW.md`

Do not load `docs/archive/`, `docs/generated/`, `reports/`, `model_artifacts/`, or runtime directories by default.

## Task Routing

| Task type | Required context | Optional context |
|---|---|---|
| Product or P0 scope | `docs/product/PRODUCT_CHARTER.md`, `docs/product/P0_SCOPE.md` | `docs/roadmap/P0_TO_PRODUCT_MIGRATION.md` |
| P0 development flow or task planning | `docs/development/DEV_FLOW.md`, `docs/current/ROADMAP_EGOLINK_P0.md` | `docs/development/VPS_MESSAGE_HUB.md`, `docs/development/FIELD_TEST.md`, `docs/development/LOCATION_ENGINE.md`, `docs/development/LOCATION_DATASET.md`, `docs/development/LTE_TRANSPORT.md` |
| Current status or acceptance | `docs/current/STATUS.md`, `docs/current/ACTIVE_BUILD.md` | `docs/current/KEY_RELEASES.md`, `docs/generated/CONTEXT_MIGRATION_REPORT.md` |
| Key release or release gate | `docs/current/KEY_RELEASES.md`, `docs/current/STATUS.md`, `docs/current/ACTIVE_BUILD.md` | `docs/current/key_releases/`, `docs/tasks/done/`, named release gate report under `reports/key_releases/` |
| Dual-board / PC Bridge architecture | `docs/architecture/SYSTEM_OVERVIEW.md`, `docs/architecture/DUAL_BOARD_PC_BRIDGE_ARCHITECTURE.md` | `docs/architecture/adr/` |
| VPS message hub or USB-Free field testing | `docs/development/DEV_FLOW.md`, `docs/development/VPS_MESSAGE_HUB.md`, `docs/development/PROTOCOL.md`, `docs/development/FIELD_TEST.md`, `docs/architecture/adr/ADR-0001-usb-free-vps-message-hub.md` | `docs/current/ROADMAP_EGOLINK_P0.md`, `docs/development/LOCATION_ENGINE.md`, `docs/development/LTE_TRANSPORT.md` |
| Location fusion or dataset planning | `docs/development/LOCATION_ENGINE.md`, `docs/development/LOCATION_DATASET.md`, `docs/development/LOCATION_FUSION_ALGORITHM.md`, `docs/architecture/adr/ADR-0004-p0-rule-location-and-transitional-vps-memory.md`, `shared/contracts/` | `docs/development/PROTOCOL.md`, `docs/current/KEY_RELEASES.md`, `docs/tasks/done/DATA-001_LOCATION_FUSION_DATASET_BASELINE.md`, `docs/tasks/done/ALG-000_LOCATION_FUSION_ALGORITHM_DESIGN.md` |
| Firmware change | `firmware/AGENTS.md`, `docs/current/ACTIVE_BUILD.md`, `docs/hardware/BOARD_MATRIX.md` | Named firmware README only |
| Hardware validation | `firmware/AGENTS.md`, `docs/hardware/BOARD_MATRIX.md`, `docs/current/ACTIVE_BUILD.md`, `docs/hardware/validation/` | Named evidence report |
| PC simulator or bridge | `pc_simulator/AGENTS.md`, `docs/architecture/SYSTEM_OVERVIEW.md`, `shared/contracts/` | Named runtime fixture |
| Model or Safety Companion | `model_lab/AGENTS.md`, `docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md`, `docs/safety/SAFETY_CONTRACT.md`, `shared/contracts/` | `docs/modeling/MODEL_ARCHITECTURE.md` |
| Quality tests | `quality_tests/AGENTS.md`, task-specific source docs | Existing related tests |
| Builder task execution | `docs/development/DIRECTOR_WORKFLOW.md`, the active task packet | `docs/tasks/TEMPLATE.md` |
| V1 product planning | `docs/roadmap/V1_PRODUCT_PLAN.md`, `docs/architecture/adr/ADR-0002-v1-ondevice-ai-companion-core.md` | `docs/roadmap/P0_TO_PRODUCT_MIGRATION.md` |
| Documentation-only | `docs/AGENTS.md`, this index, affected target docs | Archive sources named by the task |

## Authority Rules

- Current physical setup is authoritative only in `docs/current/ACTIVE_BUILD.md` and `docs/hardware/BOARD_MATRIX.md`.
- Engineering key releases are authoritative in `docs/current/KEY_RELEASES.md`
  and their manifests under `docs/current/key_releases/`.
- Product intent is authoritative only in `docs/product/PRODUCT_CHARTER.md` and `docs/product/P0_SCOPE.md`.
- P0 development flow is authoritative in `docs/development/DEV_FLOW.md`; near-term R0-R4 sequencing is authoritative in `docs/current/ROADMAP_EGOLINK_P0.md`.
- Location-engine planning is authoritative in `docs/development/LOCATION_ENGINE.md`; location-fusion dataset planning is authoritative in `docs/development/LOCATION_DATASET.md`; SIM7670G LTE transport planning is authoritative in `docs/development/LTE_TRANSPORT.md`.
- Architecture changes require an ADR under `docs/architecture/adr/`.
- V1 product sequencing is authoritative in `docs/roadmap/V1_PRODUCT_PLAN.md`;
  where it conflicts with `docs/roadmap/P0_TO_PRODUCT_MIGRATION.md`, ADR-0002
  governs.
- The active execution workflow is GitHub Flow plus interactive
  founder/Codex collaboration, documented in `docs/development/GIT_FLOW.md`
  and `docs/development/DIRECTOR_WORKFLOW.md`; archived autonomous-queue
  documents are historical evidence only.
- Machine-readable model schemas are authoritative in `shared/contracts/`; the P0 message-hub protocol baseline is documented in `docs/development/PROTOCOL.md` until matching schemas are added.
- Archive files are historical evidence and must not be cited as current authority.

## Active Task Packet Rules

Task packets live under `docs/tasks/active/` while in progress and `docs/tasks/done/` after completion. A task packet should declare:

- `context`
- `allowed_paths`
- `out_of_scope`
- validation commands
- completion evidence

Run `python scripts/context_lint.py` after editing task packets or context routing.
