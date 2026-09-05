---
id: HW-020
title: P0 A0 architecture baseline and candidate constraints
status: accepted_for_transition
priority: critical
lane: D
execution_state: completed
depends_on: []
serves_gate: P0-LOC/P0-CALL/P0-SOS
requires_hardware: false
created: 2026-08-23
last_updated: 2026-08-23

context:
  - docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md
  - docs/development/EGO_CALL.md
  - docs/product/MASS_PRODUCTION_REQUIREMENTS.md
  - docs/hardware/HARDWARE_EVALUATION_AND_PROCUREMENT_PLAN.md
  - docs/tasks/active/CALL-020_LTE_DATA_VOICE_POC.md
  - docs/tasks/active/CALL-021_EMBEDDED_LTE_RTC_MEDIA.md

allowed_paths:
  - docs/tasks/active/HW-020_PRODUCT_ARCHITECTURE_FREEZE.md
  - docs/hardware/P0_PRODUCT_ARCHITECTURE.md
  - docs/hardware/HARDWARE_EVALUATION_AND_PROCUREMENT_PLAN.md
  - docs/product/MASS_PRODUCTION_REQUIREMENTS.md

out_of_scope:
  - purchasing, PCB ordering or claiming a production-frozen BOM
  - adding sensors outside the P0 scope
  - treating development-board capability as product evidence
---

# Goal

Freeze the reviewable P0 block/interface baseline and candidate BOM
constraints for Cat.1/GNSS, MCU, IMU, microphone, speaker, PA/codec, SIM,
battery, USB-C, SOS key, LTE/GNSS antennas and optional camera interface.

# Acceptance

- [x] Block diagram assigns power, data, clock, audio, RF, debug and ownership.
- [x] Candidate table separates must-have P0 parts from reserve/growth options
      and cites exact official/measurement evidence or `unknown`.
- [x] Audio is core; camera AI is not. Native VoLTE is reserve only.
- [x] The architecture provides a credible route from CALL-020's explicit PC
      bridge to CALL-021's independent-power, embedded LTE-data media path.
- [x] Battery/RF/antenna/audio/enclosure constraints feed an A0->A1 re-test
      matrix and COMPLIANCE-010 questions.
- [x] Development evidence proxies and integrated product targets are
      separated; all unknown part, pin, rail and RF facts remain explicit.

# Validation Commands

```powershell
python scripts/context_lint.py
git diff --check
```

# Completion Evidence

- Changed file: `docs/hardware/P0_PRODUCT_ARCHITECTURE.md`.
- Validation: independent document review, `context_lint` and targeted
  `git diff --check` passed on 2026-08-23.
- Hardware: not required and not performed; this is an interface baseline.
- Remaining risk: no production BOM, schematic, PCB, RF, acoustic, power or
  compliance freeze exists. Exact candidates still require measured evidence.

# Builder Prompt

```text
Read docs/tasks/active/HW-020_PRODUCT_ARCHITECTURE_FREEZE.md in
D:\pywork\egolink. Load only AGENTS.md, docs/CONTEXT_INDEX.md, and this packet's
context. Independently review the P0 interface baseline against official named
candidate evidence. Keep audio core, camera optional, Native VoLTE reserve and
the CALL-020 PC bridge explicitly transitional. Close only facts supported by
official or measured evidence; leave exact parts, pins, rails, RF, antenna,
acoustic, battery and enclosure facts unknown/unverified otherwise. Do not buy,
order PCB or call the BOM/architecture production-frozen. Run every validation
command and return changed files, sources, unresolved decisions and A0-to-A1
retest triggers. Keep execution_state in_review until accepted.
```
