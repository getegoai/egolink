---
id: PROD-002
title: China pre-compliance classification and A0 design inputs
status: superseded
priority: archived
lane: D
execution_state: superseded
superseded_by: COMPLIANCE-010
do_not_dispatch: true
requires_hardware: false
created: 2026-08-23
last_updated: 2026-08-23

context:
  - docs/architecture/adr/ADR-0011-first-launch-reliable-location-ego-call-sos.md
  - docs/product/EGO_MASTER_CONTEXT.md
  - docs/product/MASS_PRODUCTION_REQUIREMENTS.md
  - docs/roadmap/V1_PRODUCT_PLAN.md

allowed_paths:
  - docs/tasks/active/PROD-002_CHINA_PRECOMPLIANCE_AND_A0_INPUTS.md
  - docs/product/MASS_PRODUCTION_REQUIREMENTS.md
  - docs/product/MASS_PRODUCTION_FOUNDER_DECISION_SHEET.md
  - docs/hardware/HARDWARE_EVALUATION_AND_PROCUREMENT_PLAN.md
  - docs/hardware/POWER_AND_BATTERY_ENGINEERING_TARGETS.md
  - docs/compliance/

out_of_scope:
  - treating web research as legal or laboratory approval
  - freezing a modem, MCU, PCB, enclosure, battery, antenna, or supplier
  - purchasing, contracting, or submitting a certification application
---

# Goal

This packet is retained for lineage. `COMPLIANCE-010` now owns the single
China pre-compliance/classification intake; do not dispatch both packets.

Obtain a named professional pre-compliance/product-classification opinion and
translate it, the Ego Call route, and the native-VoLTE reserve into explicit A0
electrical, RF, acoustic, security, test, and documentation inputs.

# Serves

China first launch and A0-to-A1 migration; runs in parallel with software.

# Acceptance Criteria

- [ ] A qualified lab/consultant response identifies applicable product class,
      SRRC/进网/CCC/SAR and child-product questions, applicant/manufacturer
      assumptions, required samples, lead-time inputs, and unresolved items.
- [ ] Every statement is tagged source/date/status; unknown remains unknown.
- [ ] A0 input matrix separates Ego Call launch needs from
      `G0V-VOLTE-RESERVE`, while preserving audio/power/RF migration options.
- [ ] Founder decisions needed for carry form, size/weight, battery/use profile,
      ingress target, privacy/listening, guardian policy, channel, and
      certificate applicant are reduced to a bounded decision sheet.
- [ ] No BOM or purchase list is called frozen from this task.

# Validation Commands

```powershell
python scripts/context_lint.py
git diff --check
```

# Completion Evidence

- Changed files: pending external evidence and implementation.
- Test result: pending.
- Hardware result: not required.
- Remaining risks: authoritative classification requires a qualified external
  party and exact product configuration.

# Builder Prompt

```text
DO NOT DISPATCH PROD-002. This packet is retained only as superseded lineage.
Dispatch docs/tasks/active/COMPLIANCE-010_CHINA_PRECOMPLIANCE.md instead; it is
the sole owner of China pre-compliance/classification intake. Historical
acceptance items above remain unchecked and must not be used as an active work
queue or Gate claim.
```
