---
document_status: authoritative
decision_updated: 2026-09-23
last_verified: 2026-09-09
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
- `docs/architecture/adr/ADR-0017-ai-native-ego-state-flywheel.md`
  (AI-native state estimation, self-supervised data flywheel, and decoupled model OTA)
- `docs/architecture/AI_NATIVE_EGO_STATE_FLYWHEEL.md`
  (system architecture and execution specification for continuous learning flywheel)
- `docs/architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md`
  (current product/communications/private-endpoint decision and rule-state truth)
- `docs/architecture/adr/ADR-0011-first-launch-reliable-location-ego-call-sos.md`
  (retained three-Gate lineage; RTC-primary/native-reserve clauses superseded)
- `docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md`
  (sellable P0 Gates, device Location Engine/Sensor Policy and scope freeze)
- `docs/architecture/adr/ADR-0014-runtime-convergence.md` (accepted bounded
  runtime convergence, local degradation, event time and scoped recovery)
- `docs/architecture/adr/ADR-0015-single-4g-board-camera-field-milestone.md`
  (current single-connectivity-board A-line and Camera collection milestone;
  CALL/SOS retained but paused for this milestone)
- `docs/tasks/active/P0-CONVERGENCE-20260905.md` (Gemini collection/recovery/route/field packet)
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
| Rule-state truth, current decision alignment or Codex/Gemini ownership | `docs/architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md`, `docs/tasks/done/ALIGN-STATE-010_DECISION_AND_STATE_TRUTH.md`, `docs/current/CODEX_GEMINI_HANDOFF_20260922.md`, affected module AGENTS | `docs/archive/decisions/20260922/README.md` (explicit migration lineage only) |
| Native cellular primary call | `docs/architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md`, `docs/tasks/active/CALL-030_NATIVE_CELLULAR_FEASIBILITY.md`, `docs/tasks/active/CALL-031_NATIVE_CELLULAR_PRODUCT_LOOP.md`, `docs/current/ACTIVE_BUILD.md`, `docs/hardware/BOARD_MATRIX.md` | RTC CALL-020/021 remain paused assets |
| Minimum private Ego Base endpoint | `docs/architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md`, `docs/tasks/active/BASE-010_LOCAL_FIRST_MINIMUM.md`, `docs/architecture/SYSTEM_OVERVIEW.md` | `docs/product/PRODUCT_DEMO_PRIVACY_BOUNDARY.md`, `shared/contracts/` |
| Runtime convergence, single-source live Location or degraded SOS | `docs/architecture/adr/ADR-0014-runtime-convergence.md`, `docs/tasks/active/P0-CONVERGENCE-20260905.md`, `docs/current/FIRST_LAUNCH_EXECUTION.md`, affected module AGENTS | `docs/archive/reviews/20260905_input_snapshots/README.md` (migration lineage only) |
| Single-4G-board field collection, Camera capture/upload or 2026-09-09 A-line milestone | `docs/architecture/adr/ADR-0015-single-4g-board-camera-field-milestone.md`, `docs/architecture/SYSTEM_OVERVIEW.md`, `docs/tasks/active/P0-CONVERGENCE-20260905.md`, `docs/current/FIRST_LAUNCH_EXECUTION.md`, `docs/current/EGO_LINK_AI_CURRENT_CONTEXT.md`, `docs/product/PRODUCT_DEMO_PRIVACY_BOUNDARY.md`, affected module AGENTS | `docs/hardware/TCAM_001_CAMERA_SMOKE_LIVE_CAPTURE_20260623.md`, `docs/hardware/CAMERA_MEDIA_RANGE_PREFLIGHT_20260909.md`, `docs/tasks/active/FIELD-020_L1_FIELD_DATASET.md`, `docs/current/ACTIVE_BUILD.md`, `docs/hardware/BOARD_MATRIX.md`, `docs/roadmap/P0_TO_PRODUCT_MIGRATION.md` |
| Project/product direction or system roles | `docs/architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md`, `docs/product/NORTH_STAR.md`, `docs/product/EGO_MASTER_CONTEXT.md`, `docs/architecture/adr/ADR-0008-egolink-core-product-direction-reset.md`, `docs/architecture/adr/ADR-0011-first-launch-reliable-location-ego-call-sos.md`, `docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md` | `docs/current/FIRST_LAUNCH_EXECUTION.md`, `docs/roadmap/P0_TO_PRODUCT_MIGRATION.md`, `docs/product/MASS_PRODUCTION_REQUIREMENTS.md` |
| First-launch execution, cross-lane planning, or reprioritization | `docs/architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md`, `docs/current/FIRST_LAUNCH_EXECUTION.md`, `docs/architecture/adr/ADR-0011-first-launch-reliable-location-ego-call-sos.md`, `docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md`, `docs/development/DIRECTOR_WORKFLOW.md` | `docs/roadmap/V1_PRODUCT_PLAN.md`, current packet in each affected lane |
| P0 scope or current development promise | `docs/architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md`, `docs/product/PRODUCT_CHARTER.md`, `docs/product/P0_SCOPE.md` | `docs/roadmap/P0_TO_PRODUCT_MIGRATION.md`, `docs/product/EGO_MASTER_CONTEXT.md` |
| P0 development flow or task planning | `docs/development/DEV_FLOW.md`, `docs/current/ROADMAP_EGOLINK_P0.md` | `docs/development/VPS_MESSAGE_HUB.md`, `docs/development/FIELD_TEST.md`, `docs/development/LOCATION_ENGINE.md`, `docs/development/LOCATION_DATASET.md`, `docs/development/LTE_TRANSPORT.md` |
| Current status or acceptance | `docs/current/STATUS.md`, `docs/current/ACTIVE_BUILD.md` | `docs/current/KEY_RELEASES.md`, `docs/generated/CONTEXT_MIGRATION_REPORT.md` |
| Key release or release gate | `docs/current/KEY_RELEASES.md`, `docs/current/STATUS.md`, `docs/current/ACTIVE_BUILD.md`, `docs/tasks/active/P0-RELEASE-010_SALEABLE_P0_REVIEW.md` | `docs/current/key_releases/`, `docs/tasks/done/`, named release gate report under `reports/key_releases/` |
| Historical dual-board / PC Bridge architecture | `docs/architecture/SYSTEM_OVERVIEW.md`, `docs/architecture/DUAL_BOARD_PC_BRIDGE_ARCHITECTURE.md`, `docs/architecture/adr/ADR-0015-single-4g-board-camera-field-milestone.md` | `docs/hardware/双板开发架构.md`, `docs/hardware/EGOLINK_HARDWARE_PLATFORM_CONTEXT.md`, `docs/architecture/adr/`; both hardware documents are historical for the current A-line topology |
| VPS message hub or USB-Free field testing | `docs/development/DEV_FLOW.md`, `docs/development/VPS_MESSAGE_HUB.md`, `docs/development/PROTOCOL.md`, `docs/development/FIELD_TEST.md`, `docs/architecture/adr/ADR-0001-usb-free-vps-message-hub.md` | `docs/current/ROADMAP_EGOLINK_P0.md`, `docs/development/LOCATION_ENGINE.md`, `docs/development/LTE_TRANSPORT.md` |
| Location Engine, Sensor Policy, replay, fusion or dataset planning | `docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md`, `docs/development/LOCATION_ENGINE.md`, `docs/development/LOCATION_DATASET.md`, `docs/development/LOCATION_FUSION_ALGORITHM.md`, `docs/architecture/adr/ADR-0004-p0-rule-location-and-transitional-vps-memory.md`, `shared/contracts/` | `docs/architecture/adr/ADR-0003-low-power-location-state-machine.md`, `docs/architecture/adr/ADR-0007-gnss-denied-personal-location-memory.md`, `docs/development/PROTOCOL.md`, current LOC/POLICY/REPLAY packet |
| A-line AI, data platform, multisource localization or state understanding | `docs/architecture/adr/ADR-0017-ai-native-ego-state-flywheel.md`, `docs/architecture/AI_NATIVE_EGO_STATE_FLYWHEEL.md`, `docs/architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md`, `docs/current/EGO_LINK_AI_CURRENT_CONTEXT.md`, `docs/architecture/adr/ADR-0010-asynchronous-observation-timeline-and-store-forward.md`, `docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md` | `docs/current/EGO_LINK_A_LINE_AI_CONTEXT.md`, `docs/architecture/adr/ADR-0009-ai-v0-1-belief-estimation-baseline.md`, `docs/development/UNIFIED_TIMESTAMP.md`, `docs/development/FIELD_SESSION_SCHEMA.md`, `docs/development/LOCATION_ENGINE.md`, `docs/development/LOCATION_DATASET.md`, `shared/contracts/`; Sprint 1 AI is data/replay first and non-blocking |
| Ego Call, Guardian calling, or first-launch communications | `docs/architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md`, `docs/architecture/adr/ADR-0011-first-launch-reliable-location-ego-call-sos.md`, `docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md`, `docs/current/FIRST_LAUNCH_EXECUTION.md`, the current CALL packet | `docs/architecture/adr/ADR-0013-call020-single-usb-phase-handoff.md` (proposed only), `docs/product/EGO_MASTER_CONTEXT.md`, `docs/development/VPS_MESSAGE_HUB.md`, `shared/contracts/` |
| Physical SOS, guardian alert, or Call/SOS orchestration | `docs/architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md`, `docs/architecture/adr/ADR-0011-first-launch-reliable-location-ego-call-sos.md`, `docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md`, `docs/current/FIRST_LAUNCH_EXECUTION.md`, `docs/safety/SAFETY_CONTRACT.md`, the named active SOS packet when present | `docs/development/PROTOCOL.md`, `docs/architecture/adr/ADR-0010-asynchronous-observation-timeline-and-store-forward.md`, `shared/contracts/` |
| Firmware change | `firmware/AGENTS.md`, `docs/current/ACTIVE_BUILD.md`, `docs/hardware/BOARD_MATRIX.md` | Named firmware README only |
| Hardware validation | `firmware/AGENTS.md`, `docs/hardware/BOARD_MATRIX.md`, `docs/current/ACTIVE_BUILD.md`, `docs/hardware/validation/` | Named evidence report |
| Current sales-product hardware selection or procurement | `docs/architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md`, `docs/product/EGO_MASTER_CONTEXT.md`, `docs/architecture/adr/ADR-0008-egolink-core-product-direction-reset.md`, `docs/architecture/adr/ADR-0011-first-launch-reliable-location-ego-call-sos.md`, `docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md`, `docs/product/MASS_PRODUCTION_REQUIREMENTS.md`, `docs/hardware/P0_PRODUCT_ARCHITECTURE.md`, `docs/hardware/P0_INTEGRATED_PROTOTYPE_DESIGN.md`, the current HW-021/HW-022 packet | `docs/current/FIRST_LAUNCH_EXECUTION.md`, `docs/hardware/HARDWARE_EVALUATION_AND_PROCUREMENT_PLAN.md`, `docs/hardware/POWER_AND_BATTERY_ENGINEERING_TARGETS.md`; `hardware/p0_a0/` is a conditional design-input pack, not a fabrication release; ADR-0005/0006 and `V1_PRO_EVT_PROCUREMENT_BASELINE.md` are superseded history only |
| China pre-compliance, product classification, or A0 launch readiness | `docs/architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md`, `docs/current/FIRST_LAUNCH_EXECUTION.md`, `docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md`, `docs/product/EGO_MASTER_CONTEXT.md`, `docs/product/MASS_PRODUCTION_REQUIREMENTS.md`, `docs/tasks/active/COMPLIANCE-010_CHINA_PRECOMPLIANCE.md` | `docs/tasks/done/PROD-002_CHINA_PRECOMPLIANCE_AND_A0_INPUTS.md` (superseded legacy intake only), `docs/hardware/HARDWARE_EVALUATION_AND_PROCUREMENT_PLAN.md`, `docs/hardware/POWER_AND_BATTERY_ENGINEERING_TARGETS.md` |
| Current sales-product enclosure, PCB envelope or industrial design | `docs/product/EGO_MASTER_CONTEXT.md`, `docs/architecture/adr/ADR-0008-egolink-core-product-direction-reset.md` | `docs/product/MASS_PRODUCTION_REQUIREMENTS.md`; `V1_PRO_FORM_FACTOR_BASELINE.md` and its SVG are superseded history only |
| PC simulator or bridge | `pc_simulator/AGENTS.md`, `docs/architecture/SYSTEM_OVERVIEW.md`, `shared/contracts/` | Named runtime fixture |
| Model or Safety Companion | `model_lab/AGENTS.md`, `docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md`, `docs/safety/SAFETY_CONTRACT.md`, `shared/contracts/` | `docs/modeling/MODEL_ARCHITECTURE.md` |
| Quality tests | `quality_tests/AGENTS.md`, task-specific source docs | Existing related tests |
| Builder task execution | `docs/development/DIRECTOR_WORKFLOW.md`, `docs/current/FIRST_LAUNCH_EXECUTION.md`, the active task packet | `docs/tasks/TEMPLATE.md` |
| Product planning | `docs/architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md`, `docs/product/EGO_MASTER_CONTEXT.md`, `docs/roadmap/V1_PRODUCT_PLAN.md`, `docs/architecture/adr/ADR-0002-v1-ondevice-ai-companion-core.md`, `docs/architecture/adr/ADR-0008-egolink-core-product-direction-reset.md`, `docs/architecture/adr/ADR-0011-first-launch-reliable-location-ego-call-sos.md`, `docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md`, `docs/current/FIRST_LAUNCH_EXECUTION.md` | `docs/roadmap/P0_TO_PRODUCT_MIGRATION.md` |
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
- P0 development flow is authoritative in `docs/development/DEV_FLOW.md`; R0-R4 evidence families remain in `docs/current/ROADMAP_EGOLINK_P0.md`, subject to ADR-0016 and the current parallel execution graph.
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
- ADR-0017 is the accepted architectural decision for AI-Native Ego-State Estimation and the continuous learning data flywheel. Heuristic rules serve as the initial safety and evaluation baseline; multi-modal sensor cross-supervision (GNSS velocity, cellular/Wi-Fi transitions, power state) drives automated pseudo-labeling. TinyML operates on ESP32-S3 (<=30KB INT8), while heavier sequence modeling and semantic diaries belong to Ego Base. Safety Kernel determinism is absolute and cannot be vetoed by AI. Model weights are decoupled into an independent flash partition for lightweight OTA.
- ADR-0016 is the current accepted product decision, recording the founder's
  2026-09-19 direction and 2026-09-22 implementation instruction. Native
  cellular is the primary P0-CALL route; RTC is optional fallback. Exact
  modem/firmware/operator and two-way audio remain unverified until measured.
  G0V-VOLTE-RESERVE is historical design/evidence lineage, not satisfaction
  of the new primary-call obligation. CALL-030 -> HW-022 -> CALL-031 is the
  native task path; CALL-020/021 remain paused RTC assets.
- ADR-0016 places minimum BASE-010 private Session ingest/persistence/replay/
  report/lifecycle in parallel development. Cloud duties are reachability,
  signaling and bounded temporary relay. Current VPS collection/media is an
  authorized engineering transition, not proof of local-first or encryption.
  No data migration/deletion follows automatically. Full Base AI and advanced
  learned L2/L3 do not create a fourth launch capability Gate.
- ADR-0011's three-Gate and minimum deterministic safety structure remains;
  its RTC-primary/native-reserve clauses are partially superseded. ADR-0012
  retains device Location/Sensor Policy operational ownership, source time,
  privacy and product assurance. Existing deterministic ego-state truth is
  current engineering acceptance under ALIGN-STATE-010, separate from learned
  accuracy: missing/stale/future/mock/invalid evidence cannot become confident
  normal; DEVICE/canonical/API/Web projections must be explicit and compatible.
- ADR-0014 local advancement under persistence failure, prompt recognized SOS
  feedback, one modem owner, exact authenticated ACK, source-event time and
  no resurrection of settled alerts/ended calls remain. T0/T1 do not globally
  block finite single-source proof; original concurrent recovery invariants
  or a reviewed behavioral equivalent remain required. ADR-0013 stays proposed.
- ADR-0015 retains the identified single-board Camera/IMU/power/antenna
  collection, recovery, real Wi-Fi/LTE transition and short carry/FIELD scope.
  Gemini owns that implementation; Codex owns decision/current-state/task
  management and bounded ego-state truth. Camera is not a fourth Gate or a
  Location/SOS decision source. CALL-020/021 and full SOS remain paused in
  this field milestone; hardware/compliance inputs proceed independently.
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
  must conform to the Master Context and accepted ADRs, including ADR-0016's
  explicit partial supersession and retained ADR-0008/0011/0012 invariants. The current four-lane WIP and integration
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
