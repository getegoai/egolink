---
id: PROD-001
title: Mass-production requirements definition and module/MCU selection gates
status: paused
priority: high
requires_hardware: false
serves_demo: post-D1
serves_gate: P0-LOC/P0-CALL/P0-SOS
created: 2026-07-03
last_updated: 2026-08-23

context:
  - AGENTS.md
  - docs/AGENTS.md
  - docs/CONTEXT_INDEX.md
  - docs/product/EGO_MASTER_CONTEXT.md
  - docs/product/PRODUCT_CHARTER.md
  - docs/roadmap/V1_PRODUCT_PLAN.md
  - docs/architecture/adr/ADR-0002-v1-ondevice-ai-companion-core.md
  - docs/architecture/adr/ADR-0008-egolink-core-product-direction-reset.md
  - docs/architecture/adr/ADR-0011-first-launch-reliable-location-ego-call-sos.md
  - docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md
  - docs/current/FIRST_LAUNCH_EXECUTION.md
  - docs/hardware/EGOLINK_HARDWARE_PLATFORM_CONTEXT.md
  - docs/hardware/POWER_AND_BATTERY_ENGINEERING_TARGETS.md
  - docs/hardware/HARDWARE_EVALUATION_AND_PROCUREMENT_PLAN.md

allowed_paths:
  - docs/product/
  - docs/hardware/

out_of_scope:
  - selecting a specific module or MCU in this task (that needs quotes and
    the China Mobile module datasheet, both pending)
  - firmware changes
  - committing supplier pricing marked confidential
---

# Problem

Founder statements (2026-07-03): SIM7670G is not the production module; a
mass-production definition must exist before module screening; a China Mobile
4G module is under business contact with details arriving later; no channel
quotes exist yet for ESP32-S3 / STM32U5A5 / Apollo4. Today there is no single
document defining what "production-ready hardware" means, so incoming module
datasheets and quotes cannot be evaluated consistently.

# Expected Result

`docs/product/MASS_PRODUCTION_REQUIREMENTS.md`: the subordinate, fillable
engineering and business gate set for the product direction fixed by
`EGO_MASTER_CONTEXT.md` and ADR-0012, plus two evaluation checklists (cellular
module, MCU). It must preserve the screenless first-launch Reliable Location +
Ego Call + SOS loop, separate native VoLTE/event-camera/advanced-AI reserves
from first-launch gates, and becomes actionable only when exact candidate
documentation, samples and channel evidence arrive.

This packet does not own China pre-compliance execution. `COMPLIANCE-010` is
the active successor to the retained PROD-002 intake. `P0-LOC`, `P0-CALL` and
`P0-SOS` all remain `NOT_RUN`; a requirements worksheet cannot advance them.

# Acceptance Criteria

- [ ] Requirements document covers, each with target value + hard floor +
      rationale: device cost/BOM ceiling; battery life (48h guard mode hard
      target, 7d light-use stretch, with usage-profile definitions); size and
      weight envelope; wearing/mounting form; environmental (IP rating,
      temperature); certification set for China market (SRRC, CCC if
      applicable, network access license / 进网许可, carrier IoT requirements);
      data privacy baseline for a minor/elder wearable.
- [ ] Cellular module evaluation checklist: RAT/bands and exact-SKU evidence for
      China Mobile, China Unicom and China Telecom,
      GNSS (integrated vs external, constellations, cold/warm TTFF spec),
      power states (PSM/eDRX or equivalent, sleep currents), AT/SDK maturity,
      LTE-data/RTC suitability for `P0-CALL` (legacy `G0-EGOCALL`), separately scored native VoLTE
      reserve evidence, module cost, MOQ, lead time, certification status
      carried by the module, and FAE support. Includes a row pre-filled with
      SIM7670G's known values as the comparison baseline.
- [ ] MCU evaluation checklist: active/sleep power, deterministic Safety Kernel
      budget as a launch gate, **on-device AI inference growth budget as a
      first-class scored criterion** (RAM/flash headroom for MotionNet-class
      models, vector/NPU support, sleep-vs-inference power),
      peripherals (I2C/UART/camera IF, microphone path for the companion
      interaction loop), toolchain and existing firmware portability cost
      from ESP32-S3, unit price / 1k price / MOQ / lead time, second-source
      risk.
- [ ] Both checklists state their decision rule (which criteria are
      disqualifying vs scored) so a selection can later be recorded as an ADR.
- [ ] Explicit open-items section: awaiting China Mobile module datasheet,
      awaiting MCU channel quotes — so the document is honest about what it
      cannot decide yet.
- [ ] `python scripts/context_lint.py` passes.

# Validation Commands

```powershell
python scripts/context_lint.py
```

# Hardware Validation

- Not applicable (definition document task).

# Decisions

- Requirements are owned by the founder; the builder drafts, the founder
  fills business-sensitive numbers (cost ceiling, MOQ tolerance) and approves.
- 2026-08-14: Rebased under `EGO_MASTER_CONTEXT.md` and ADR-0008. Product
  direction work proceeds in parallel with D2/D5; this packet remains paused
  only because exact candidate supplier documentation, samples, non-confidential
  quotes and unresolved founder/business parameters are still missing.
- 2026-08-23: ADR-0011 rebases voice and intelligence selection semantics.
  The legacy `G0-EGOCALL` evidence family maps to the `P0-CALL` release Gate;
  native VoLTE becomes
  the independent `G0V-VOLTE-RESERVE`; deterministic Safety Kernel resources
  remain a gate while advanced inference/camera resources are scored growth
  criteria unless a later accepted ADR promotes them.
- 2026-08-23: ADR-0012 freezes Productization Sprint 1. Device operational
  Location Engine/Sensor Policy, event-time lineage, P0 call/audio/media support
  and durable SOS support are production-selection inputs. AI remains
  data/replay first, camera is optional/non-blocking, and PROD-002 is legacy
  intake superseded for execution by `COMPLIANCE-010`.

# Completion Evidence

- review1 (2026-07-03, director): Codex draft accepted.
  `docs/product/MASS_PRODUCTION_REQUIREMENTS.md` created with requirement
  matrix, usage-profile definitions, module checklist (SIM7670G baseline +
  China Mobile candidate rows), MCU checklist (deterministic Safety Kernel
  gate plus on-device AI growth scoring), decision rules, open items, and
  pre-selection evidence list. `context_lint` PASS (builder run + director
  re-run). Packet stays active until the founder fills `TBD(founder)` values
  and approves; then it moves to done.
- review2 (2026-07-03, codex): added
  `docs/product/MASS_PRODUCTION_FOUNDER_DECISION_SHEET.md` as a
  founder-facing fill-in worksheet for the unresolved business/product values
  without recording confidential supplier pricing. Linked it from
  `docs/product/MASS_PRODUCTION_REQUIREMENTS.md`.
- Changed files:
  - `docs/product/MASS_PRODUCTION_REQUIREMENTS.md`
  - `docs/product/MASS_PRODUCTION_FOUNDER_DECISION_SHEET.md`
- Test result: python scripts/context_lint.py PASS
- Remaining risks: all business values pending founder; China Mobile module
  datasheet and MCU quotes outstanding (tracked in section 7 Open Items).

# Builder Prompt

```text
Read docs/tasks/active/PROD-001_MASS_PRODUCTION_REQUIREMENTS.md in
D:\pywork\egolink. Load only AGENTS.md, docs/CONTEXT_INDEX.md, and the files
in this packet's `context`. Do only this task; obey `allowed_paths` and
`out_of_scope`. Draft the requirements document and both evaluation
checklists under ADR-0012; mark every value the founder must confirm with
`TBD(founder)`. Keep P0-CALL as the first-launch voice gate and native VoLTE,
advanced inference, and event camera as separately evidenced reserves unless
an accepted later ADR promotes them.
Run the validation command before finishing. If any acceptance criterion
cannot be met, stop and report the blocker. Return: changed files,
validation output, evidence paths. Do not update docs/current/STATUS.md and
do not move this packet to done/.
```
