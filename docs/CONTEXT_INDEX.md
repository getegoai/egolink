---
document_status: authoritative
last_verified: 2026-08-14
verified_by: codex
---

# Context Index

Use this file as the first stop for Claude Code, Codex, Codex CLI, VS Code Codex, and any builder-agent context loading.

## Default Minimal Context

Always load:

- `AGENTS.md`
- `docs/product/NORTH_STAR.md` (goal + guiding principles; check its date
  every session to sense direction changes)
- `docs/product/EGO_MASTER_CONTEXT.md` (current sales-product direction,
  system roles, first-generation requirements, and release gates)
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
| Project/product direction or system roles | `docs/product/NORTH_STAR.md`, `docs/product/EGO_MASTER_CONTEXT.md`, `docs/architecture/adr/ADR-0008-egolink-core-product-direction-reset.md` | `docs/roadmap/P0_TO_PRODUCT_MIGRATION.md`, `docs/product/MASS_PRODUCTION_REQUIREMENTS.md` |
| P0 scope or current development promise | `docs/product/PRODUCT_CHARTER.md`, `docs/product/P0_SCOPE.md` | `docs/roadmap/P0_TO_PRODUCT_MIGRATION.md`, `docs/product/EGO_MASTER_CONTEXT.md` |
| P0 development flow or task planning | `docs/development/DEV_FLOW.md`, `docs/current/ROADMAP_EGOLINK_P0.md` | `docs/development/VPS_MESSAGE_HUB.md`, `docs/development/FIELD_TEST.md`, `docs/development/LOCATION_ENGINE.md`, `docs/development/LOCATION_DATASET.md`, `docs/development/LTE_TRANSPORT.md` |
| Current status or acceptance | `docs/current/STATUS.md`, `docs/current/ACTIVE_BUILD.md` | `docs/current/KEY_RELEASES.md`, `docs/generated/CONTEXT_MIGRATION_REPORT.md` |
| Key release or release gate | `docs/current/KEY_RELEASES.md`, `docs/current/STATUS.md`, `docs/current/ACTIVE_BUILD.md` | `docs/current/key_releases/`, `docs/tasks/done/`, named release gate report under `reports/key_releases/` |
| Dual-board / PC Bridge architecture | `docs/architecture/SYSTEM_OVERVIEW.md`, `docs/architecture/DUAL_BOARD_PC_BRIDGE_ARCHITECTURE.md` | `docs/architecture/adr/` |
| VPS message hub or USB-Free field testing | `docs/development/DEV_FLOW.md`, `docs/development/VPS_MESSAGE_HUB.md`, `docs/development/PROTOCOL.md`, `docs/development/FIELD_TEST.md`, `docs/architecture/adr/ADR-0001-usb-free-vps-message-hub.md` | `docs/current/ROADMAP_EGOLINK_P0.md`, `docs/development/LOCATION_ENGINE.md`, `docs/development/LTE_TRANSPORT.md` |
| Location fusion or dataset planning | `docs/development/LOCATION_ENGINE.md`, `docs/development/LOCATION_DATASET.md`, `docs/development/LOCATION_FUSION_ALGORITHM.md`, `docs/architecture/adr/ADR-0004-p0-rule-location-and-transitional-vps-memory.md`, `shared/contracts/` | `docs/architecture/adr/ADR-0007-gnss-denied-personal-location-memory.md`, `docs/development/PROTOCOL.md`, `docs/current/KEY_RELEASES.md`, `docs/tasks/done/DATA-001_LOCATION_FUSION_DATASET_BASELINE.md`, `docs/tasks/done/ALG-000_LOCATION_FUSION_ALGORITHM_DESIGN.md` |
| A-line AI, data platform, multisource localization or state understanding | `docs/current/EGO_LINK_A_LINE_AI_CONTEXT.md`, `docs/architecture/adr/ADR-0009-ai-v0-1-belief-estimation-baseline.md` | `docs/development/UNIFIED_TIMESTAMP.md`, `docs/development/FIELD_SESSION_SCHEMA.md`, `docs/development/LOCATION_ENGINE.md`, `docs/development/LOCATION_DATASET.md`, `shared/contracts/` |
| Firmware change | `firmware/AGENTS.md`, `docs/current/ACTIVE_BUILD.md`, `docs/hardware/BOARD_MATRIX.md` | Named firmware README only |
| Hardware validation | `firmware/AGENTS.md`, `docs/hardware/BOARD_MATRIX.md`, `docs/current/ACTIVE_BUILD.md`, `docs/hardware/validation/` | Named evidence report |
| Current sales-product hardware selection or procurement | `docs/product/EGO_MASTER_CONTEXT.md`, `docs/architecture/adr/ADR-0008-egolink-core-product-direction-reset.md`, `docs/product/MASS_PRODUCTION_REQUIREMENTS.md` | `docs/hardware/HARDWARE_EVALUATION_AND_PROCUREMENT_PLAN.md`, `docs/hardware/POWER_AND_BATTERY_ENGINEERING_TARGETS.md`; ADR-0005/0006 and `V1_PRO_EVT_PROCUREMENT_BASELINE.md` are superseded history only |
| Current sales-product enclosure, PCB envelope or industrial design | `docs/product/EGO_MASTER_CONTEXT.md`, `docs/architecture/adr/ADR-0008-egolink-core-product-direction-reset.md` | `docs/product/MASS_PRODUCTION_REQUIREMENTS.md`; `V1_PRO_FORM_FACTOR_BASELINE.md` and its SVG are superseded history only |
| PC simulator or bridge | `pc_simulator/AGENTS.md`, `docs/architecture/SYSTEM_OVERVIEW.md`, `shared/contracts/` | Named runtime fixture |
| Model or Safety Companion | `model_lab/AGENTS.md`, `docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md`, `docs/safety/SAFETY_CONTRACT.md`, `shared/contracts/` | `docs/modeling/MODEL_ARCHITECTURE.md` |
| Quality tests | `quality_tests/AGENTS.md`, task-specific source docs | Existing related tests |
| Builder task execution | `docs/development/DIRECTOR_WORKFLOW.md`, the active task packet | `docs/tasks/TEMPLATE.md` |
| Product planning | `docs/product/EGO_MASTER_CONTEXT.md`, `docs/roadmap/V1_PRODUCT_PLAN.md`, `docs/architecture/adr/ADR-0002-v1-ondevice-ai-companion-core.md`, `docs/architecture/adr/ADR-0008-egolink-core-product-direction-reset.md` | `docs/roadmap/P0_TO_PRODUCT_MIGRATION.md` |
| Documentation-only | `docs/AGENTS.md`, this index, affected target docs | Archive sources named by the task |

## Authority Rules

- Current physical setup is authoritative only in `docs/current/ACTIVE_BUILD.md` and `docs/hardware/BOARD_MATRIX.md`.
- Engineering key releases are authoritative in `docs/current/KEY_RELEASES.md`
  and their manifests under `docs/current/key_releases/`.
- Highest-level purpose and guiding principles are authoritative in
  `docs/product/NORTH_STAR.md`. Current sales-product direction, system roles,
  first-generation product requirements, and release gates are authoritative
  in `docs/product/EGO_MASTER_CONTEXT.md`, subject to accepted ADRs.
- `docs/product/PRODUCT_CHARTER.md` and `docs/product/P0_SCOPE.md` remain
  authoritative for the current P0 development promise and validation scope;
  they do not define the final sales-product PCB, enclosure, or BOM.
- P0 development flow is authoritative in `docs/development/DEV_FLOW.md`; near-term R0-R4 sequencing is authoritative in `docs/current/ROADMAP_EGOLINK_P0.md`.
- Location-engine planning is authoritative in `docs/development/LOCATION_ENGINE.md`; location-fusion dataset planning is authoritative in `docs/development/LOCATION_DATASET.md`; ADR-0007 records the proposed GNSS-denied personal-memory extension pending founder review; SIM7670G LTE transport planning is authoritative in `docs/development/LTE_TRANSPORT.md`.
- Architecture changes require an ADR under `docs/architecture/adr/`.
- The A-line AI baseline is authoritative in
  `docs/current/EGO_LINK_A_LINE_AI_CONTEXT.md`; ADR-0009 freezes the v0.1
  estimator architecture, two-layer A0/A1-A2 sequencing and current A-R0 task
  numbering without advancing any evidence Gate.
- ADR-0008 accepts the screenless modular EgoLink Core sales-product direction
  and supersedes the conflicting V1 Pro decisions in ADR-0005/0006. Named A0
  candidates are not a production-frozen BOM until later accepted decisions.
- `docs/product/V1_PRO_FORM_FACTOR_BASELINE.md`, its drawing, and
  `docs/hardware/V1_PRO_EVT_PROCUREMENT_BASELINE.md` are superseded historical
  references and must not drive new tooling, schematic, or purchasing.
- Product sequencing is maintained in `docs/roadmap/V1_PRODUCT_PLAN.md`, which
  must conform to the Master Context, ADR-0002, and ADR-0008. Near-term P0
  execution remains separate.
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
