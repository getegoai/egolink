---
id: HW-022
title: Integrated P0 prototype build and bring-up
status: active
priority: critical
lane: D
execution_state: queued
depends_on:
  - HW-021
  - CALL-030
serves_gate: P0-LOC/P0-CALL/P0-SOS
requires_hardware: true
created: 2026-08-23
last_updated: 2026-08-23

context:
  - docs/architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md
  - docs/hardware/P0_PRODUCT_ARCHITECTURE.md
  - docs/tasks/active/HW-021_EXACT_INTEGRATED_PROTOTYPE_DESIGN.md
  - docs/tasks/active/CALL-030_NATIVE_CELLULAR_FEASIBILITY.md
  - docs/tasks/active/COMPLIANCE-010_CHINA_PRECOMPLIANCE.md

allowed_paths:
  - docs/tasks/active/HW-022_INTEGRATED_PROTOTYPE_BUILD.md

out_of_scope:
  - purchasing, fabrication, assembly, power-up, flash or RF/audio drive
    without explicit founder/operator intent
  - claiming A0 bring-up is a saleable product or production BOM freeze
---

## 2026-09-22 primary-cellular dependency alignment

ADR-0016 replaces the old RTC primary-path dependency with CALL-030 feasibility
and CALL-031 native cellular product evidence. CALL-020/021 remain paused RTC
assets. The criteria below retain their reliability/privacy/product invariants;
current references to Ego Call mean native cellular primary, with RTC auxiliary.
Historical implementation checkpoints remain dated evidence, not a new result.
No Gate or hardware state advances from this dependency update.


# Goal

Build and bring up one independently powered integrated prototype that gives
CALL-031, LOC-021 and SOS-010 a real PC/USB-free execution target.

# Acceptance

- [ ] Fabricated/assembled unit and every rework are bound to design/BOM/CPL,
      serial/revision, date, owner and private evidence paths.
- [ ] Power sequencing, brownout recovery, MCU/modem bearer, GNSS/LTE, audio
      RX/TX, persistent storage, SOS key and local feedback pass bounded
      bring-up without borrowing split-development-board evidence.
- [ ] USB is absent from product media/control evidence; independent power and
      debug boundaries are explicit.
- [ ] CALL-030 cellular/audio/power interface inputs and current pre-compliance
      constraints are traced into the built revision or recorded as blockers.
- [ ] Failures remain visible; this task alone cannot pass any P0 Gate.

# Dispatch Boundary

At dispatch, amend `allowed_paths` with the exact design, build record and
private evidence locations plus bounded commands. Procurement, fab release,
power-up, flash, SIM traffic and audio/RF activity each require explicit
founder/operator intent.

# Validation

```powershell
python scripts/context_lint.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1
git diff --check
```

# Completion Evidence

- Build, hardware and evidence: `NOT_RUN`.
- Remaining risks: no exact integrated prototype exists yet.
