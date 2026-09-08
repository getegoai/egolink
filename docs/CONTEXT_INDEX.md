---
document_status: authoritative
decision_updated: 2026-09-05
last_verified: 2026-09-03
verified_by: founder/codex
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
- `docs/architecture/adr/ADR-0011-first-launch-reliable-location-ego-call-sos.md`
  (latest accepted first-launch priority and communications decision)
- `docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md`
  (sellable P0 Gates, device Location Engine/Sensor Policy and scope freeze)
- `docs/architecture/adr/ADR-0014-runtime-convergence.md` (accepted bounded
  runtime convergence, local degradation, event time and scoped recovery)
- `docs/tasks/active/P0-CONVERGENCE-20260905.md` (current implementation packet)
- `docs/current/FIRST_LAUNCH_EXECUTION.md` (current parallel execution and
  integration order)
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
| Runtime convergence, single-source live Location or degraded SOS | `docs/architecture/adr/ADR-0014-runtime-convergence.md`, `docs/tasks/active/P0-CONVERGENCE-20260905.md`, `docs/current/FIRST_LAUNCH_EXECUTION.md`, affected module AGENTS | `docs/archive/reviews/20260905_input_snapshots/README.md` (migration lineage only) |
| Project/product direction or system roles | `docs/product/NORTH_STAR.md`, `docs/product/EGO_MASTER_CONTEXT.md`, `docs/architecture/adr/ADR-0008-egolink-core-product-direction-reset.md`, `docs/architecture/adr/ADR-0011-first-launch-reliable-location-ego-call-sos.md`, `docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md` | `docs/current/FIRST_LAUNCH_EXECUTION.md`, `docs/roadmap/P0_TO_PRODUCT_MIGRATION.md`, `docs/product/MASS_PRODUCTION_REQUIREMENTS.md` |
| First-launch execution, cross-lane planning, or reprioritization | `docs/current/FIRST_LAUNCH_EXECUTION.md`, `docs/architecture/adr/ADR-0011-first-launch-reliable-location-ego-call-sos.md`, `docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md`, `docs/development/DIRECTOR_WORKFLOW.md` | `docs/roadmap/V1_PRODUCT_PLAN.md`, current packet in each affected lane |
| P0 scope or current development promise | `docs/product/PRODUCT_CHARTER.md`, `docs/product/P0_SCOPE.md` | `docs/roadmap/P0_TO_PRODUCT_MIGRATION.md`, `docs/product/EGO_MASTER_CONTEXT.md` |
| P0 development flow or task planning | `docs/development/DEV_FLOW.md`, `docs/current/ROADMAP_EGOLINK_P0.md` | `docs/development/VPS_MESSAGE_HUB.md`, `docs/development/FIELD_TEST.md`, `docs/development/LOCATION_ENGINE.md`, `docs/development/LOCATION_DATASET.md`, `docs/development/LTE_TRANSPORT.md` |
| Current status or acceptance | `docs/current/STATUS.md`, `docs/current/ACTIVE_BUILD.md` | `docs/current/KEY_RELEASES.md`, `docs/generated/CONTEXT_MIGRATION_REPORT.md` |
| Key release or release gate | `docs/current/KEY_RELEASES.md`, `docs/current/STATUS.md`, `docs/current/ACTIVE_BUILD.md`, `docs/tasks/active/P0-RELEASE-010_SALEABLE_P0_REVIEW.md` | `docs/current/key_releases/`, `docs/tasks/done/`, named release gate report under `reports/key_releases/` |
| Dual-board / PC Bridge architecture | `docs/architecture/SYSTEM_OVERVIEW.md`, `docs/architecture/DUAL_BOARD_PC_BRIDGE_ARCHITECTURE.md` | `docs/architecture/adr/` |
| VPS message hub or USB-Free field testing | `docs/development/DEV_FLOW.md`, `docs/development/VPS_MESSAGE_HUB.md`, `docs/development/PROTOCOL.md`, `docs/development/FIELD_TEST.md`, `docs/architecture/adr/ADR-0001-usb-free-vps-message-hub.md` | `docs/current/ROADMAP_EGOLINK_P0.md`, `docs/development/LOCATION_ENGINE.md`, `docs/development/LTE_TRANSPORT.md` |
| Location Engine, Sensor Policy, replay, fusion or dataset planning | `docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md`, `docs/development/LOCATION_ENGINE.md`, `docs/development/LOCATION_DATASET.md`, `docs/development/LOCATION_FUSION_ALGORITHM.md`, `docs/architecture/adr/ADR-0004-p0-rule-location-and-transitional-vps-memory.md`, `shared/contracts/` | `docs/architecture/adr/ADR-0003-low-power-location-state-machine.md`, `docs/architecture/adr/ADR-0007-gnss-denied-personal-location-memory.md`, `docs/development/PROTOCOL.md`, current LOC/POLICY/REPLAY packet |
| A-line AI, data platform, multisource localization or state understanding | `docs/current/EGO_LINK_AI_CURRENT_CONTEXT.md`, `docs/architecture/adr/ADR-0010-asynchronous-observation-timeline-and-store-forward.md`, `docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md` | `docs/current/EGO_LINK_A_LINE_AI_CONTEXT.md`, `docs/architecture/adr/ADR-0009-ai-v0-1-belief-estimation-baseline.md`, `docs/development/UNIFIED_TIMESTAMP.md`, `docs/development/FIELD_SESSION_SCHEMA.md`, `docs/development/LOCATION_ENGINE.md`, `docs/development/LOCATION_DATASET.md`, `shared/contracts/`; Sprint 1 AI is data/replay first and non-blocking |
| Ego Call, Guardian calling, or first-launch communications | `docs/architecture/adr/ADR-0011-first-launch-reliable-location-ego-call-sos.md`, `docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md`, `docs/current/FIRST_LAUNCH_EXECUTION.md`, the current CALL packet | `docs/architecture/adr/ADR-0013-call020-single-usb-phase-handoff.md` (proposed only), `docs/product/EGO_MASTER_CONTEXT.md`, `docs/development/VPS_MESSAGE_HUB.md`, `shared/contracts/` |
| Physical SOS, guardian alert, or Call/SOS orchestration | `docs/architecture/adr/ADR-0011-first-launch-reliable-location-ego-call-sos.md`, `docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md`, `docs/current/FIRST_LAUNCH_EXECUTION.md`, `docs/safety/SAFETY_CONTRACT.md`, the named active SOS packet when present | `docs/development/PROTOCOL.md`, `docs/architecture/adr/ADR-0010-asynchronous-observation-timeline-and-store-forward.md`, `shared/contracts/` |
| Firmware change | `firmware/AGENTS.md`, `docs/current/ACTIVE_BUILD.md`, `docs/hardware/BOARD_MATRIX.md` | Named firmware README only |
| Hardware validation | `firmware/AGENTS.md`, `docs/hardware/BOARD_MATRIX.md`, `docs/current/ACTIVE_BUILD.md`, `docs/hardware/validation/` | Named evidence report |
| Current sales-product hardware selection or procurement | `docs/product/EGO_MASTER_CONTEXT.md`, `docs/architecture/adr/ADR-0008-egolink-core-product-direction-reset.md`, `docs/architecture/adr/ADR-0011-first-launch-reliable-location-ego-call-sos.md`, `docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md`, `docs/product/MASS_PRODUCTION_REQUIREMENTS.md`, `docs/hardware/P0_PRODUCT_ARCHITECTURE.md`, `docs/hardware/P0_INTEGRATED_PROTOTYPE_DESIGN.md`, the current HW-021/HW-022 packet | `docs/current/FIRST_LAUNCH_EXECUTION.md`, `docs/hardware/HARDWARE_EVALUATION_AND_PROCUREMENT_PLAN.md`, `docs/hardware/POWER_AND_BATTERY_ENGINEERING_TARGETS.md`; `hardware/p0_a0/` is a conditional design-input pack, not a fabrication release; ADR-0005/0006 and `V1_PRO_EVT_PROCUREMENT_BASELINE.md` are superseded history only |
| China pre-compliance, product classification, or A0 launch readiness | `docs/current/FIRST_LAUNCH_EXECUTION.md`, `docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md`, `docs/product/EGO_MASTER_CONTEXT.md`, `docs/product/MASS_PRODUCTION_REQUIREMENTS.md`, `docs/tasks/active/COMPLIANCE-010_CHINA_PRECOMPLIANCE.md` | `docs/tasks/done/PROD-002_CHINA_PRECOMPLIANCE_AND_A0_INPUTS.md` (superseded legacy intake only), `docs/hardware/HARDWARE_EVALUATION_AND_PROCUREMENT_PLAN.md`, `docs/hardware/POWER_AND_BATTERY_ENGINEERING_TARGETS.md` |
| Current sales-product enclosure, PCB envelope or industrial design | `docs/product/EGO_MASTER_CONTEXT.md`, `docs/architecture/adr/ADR-0008-egolink-core-product-direction-reset.md` | `docs/product/MASS_PRODUCTION_REQUIREMENTS.md`; `V1_PRO_FORM_FACTOR_BASELINE.md` and its SVG are superseded history only |
| PC simulator or bridge | `pc_simulator/AGENTS.md`, `docs/architecture/SYSTEM_OVERVIEW.md`, `shared/contracts/` | Named runtime fixture |
| Model or Safety Companion | `model_lab/AGENTS.md`, `docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md`, `docs/safety/SAFETY_CONTRACT.md`, `shared/contracts/` | `docs/modeling/MODEL_ARCHITECTURE.md` |
| Quality tests | `quality_tests/AGENTS.md`, task-specific source docs | Existing related tests |
| Builder task execution | `docs/development/DIRECTOR_WORKFLOW.md`, `docs/current/FIRST_LAUNCH_EXECUTION.md`, the active task packet | `docs/tasks/TEMPLATE.md` |
| Product planning | `docs/product/EGO_MASTER_CONTEXT.md`, `docs/roadmap/V1_PRODUCT_PLAN.md`, `docs/architecture/adr/ADR-0002-v1-ondevice-ai-companion-core.md`, `docs/architecture/adr/ADR-0008-egolink-core-product-direction-reset.md`, `docs/architecture/adr/ADR-0011-first-launch-reliable-location-ego-call-sos.md`, `docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md`, `docs/current/FIRST_LAUNCH_EXECUTION.md` | `docs/roadmap/P0_TO_PRODUCT_MIGRATION.md` |
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
- Location-engine planning is authoritative in `docs/development/LOCATION_ENGINE.md`: the device owns minimum operational Location Engine/Sensor Policy state. `docs/development/LOCATION_FUSION_ALGORITHM.md` is the server-derived fusion/replay baseline, not sole live-state authority. Location-fusion dataset planning is authoritative in `docs/development/LOCATION_DATASET.md`; ADR-0007 records the proposed GNSS-denied personal-memory extension pending founder review; SIM7670G LTE transport planning is authoritative in `docs/development/LTE_TRANSPORT.md`.
- Architecture changes require an ADR under `docs/architecture/adr/`.
- The current A-line execution baseline is authoritative in
  `docs/current/EGO_LINK_AI_CURRENT_CONTEXT.md`; ADR-0010 freezes independent
  asynchronous acquisition, server-side event-time reconstruction and bounded
  persistent Store-and-Forward. The broader A-line baseline and ADR-0009 remain
  authoritative for the v0.1 estimator architecture, two-layer A0/A1-A2
  sequencing and A-R0 numbering where they do not conflict with the current
  execution baseline. None of these documents advances an evidence Gate.
- ADR-0008 accepts the screenless modular EgoLink Core sales-product direction
  and supersedes the conflicting V1 Pro decisions in ADR-0005/0006. Named A0
  candidates are not a production-frozen BOM until later accepted decisions.
- ADR-0011 partially supersedes ADR-0008 for first-launch capability priority
  and the communications release path, and partially supersedes ADR-0002
  clauses 1/3 where advanced learned-model work was an unconditional launch
  blocker. Minimum deterministic local Safety Kernel behavior and the long-term
  on-device-intelligence direction remain accepted. `P0-LOC`, `P0-CALL`, and
  `P0-SOS` are the three mandatory first-launch capability Gates; native VoLTE remains unverified and is
  retained as the independent `G0V-VOLTE-RESERVE` A0 migration/fallback Gate.
  ADR-0008's screenless modular form, A0-to-A1 path, people-first scope, and
  product-assurance requirements remain in force. `G0V-VOLTE-RESERVE` is a
  non-blocking A0 design review/reserve result, not a P0 sales-release Gate.
- ADR-0012 freezes Productization Sprint 1: `P0-LOC`, `P0-CALL`, and `P0-SOS`
  are the only blocking user-capability Gates; device Location Engine/Sensor
  Policy owns minimum offline operational state while the server mirrors and
  replays it. It partially supersedes ADR-0004's server-only live ownership
  and refines ADR-0003/ADR-0011 without weakening their evidence, privacy or
  product-assurance boundaries.
- ADR-0014 accepts runtime convergence: first reuse LOC-021 A-S for bounded
  real-device Location -> verified authenticated secure transport -> Guardian;
  advance real bidirectional CALL and embedded-bearer validation in parallel,
  then join physical SOS and recovery. T0/T1 do not block isolated S smoke or
  finite single-source live proof. Original concurrent-ingress and recovery
  promises remain until their invariants or a reviewed equivalent pass.
  Local state/recognized-input feedback must expose storage failure separately
  from durable/received claims; strict ACK, single modem ownership, true source
  event time and no resurrection of ended calls remain mandatory. ADR-0013
  stays proposed. Decision dates are independent from `last_verified`.
- `P0-LOC`, `P0-CALL`, and `P0-SOS` all require `PASS` for the sellable P0.
  Their current states are all `NOT_RUN`; no current schema, build, replay,
  PC bridge or development-board smoke advances them. Legacy `G0-EGOCALL`
  references map to `P0-CALL`. `COMPLIANCE-010` is the active successor to
  the retained PROD-002 intake.
  `L2-AI` is best effort/non-blocking and `L3` is outside the launch critical
  path. Cross-cutting power, reliability, waterproof/acoustic, RF, NPI,
  security/privacy and China-compliance assurance still constrain those three
  capability Gates and converge in `P0-RELEASE-010`.
- `docs/product/V1_PRO_FORM_FACTOR_BASELINE.md`, its drawing, and
  `docs/hardware/V1_PRO_EVT_PROCUREMENT_BASELINE.md` are superseded historical
  references and must not drive new tooling, schematic, or purchasing.
- Product sequencing is maintained in `docs/roadmap/V1_PRODUCT_PLAN.md`, which
  must conform to the Master Context and accepted ADRs, including ADR-0011's
  partial supersession of ADR-0008 and ADR-0002. The current four-lane WIP and integration
  order are authoritative in `docs/current/FIRST_LAUNCH_EXECUTION.md`;
  near-term P0 evidence remains a parallel input rather than a global serial
  prerequisite.
- The active execution workflow is GitHub Flow plus interactive
  founder/Codex collaboration, documented in `docs/development/GIT_FLOW.md`
  and `docs/development/DIRECTOR_WORKFLOW.md`; archived autonomous-queue
  documents are historical evidence only.
- Machine-readable model schemas are authoritative in `shared/contracts/`; the P0 message-hub protocol baseline is documented in `docs/development/PROTOCOL.md` until matching schemas are added. Source event time plus boot-scoped monotonic/clock-mapping lineage controls replay ordering; receive/ingest time is transport evidence, not a substitute event clock.
- Archive files are historical evidence and must not be cited as current authority.

## Active Task Packet Rules

Task packets live under `docs/tasks/active/` while in progress and `docs/tasks/done/` after completion. A task packet should declare:

- `context`
- `allowed_paths`
- `out_of_scope`
- validation commands
- completion evidence

Run `python scripts/context_lint.py` after editing task packets or context routing.
