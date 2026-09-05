---
id: PWR-020
title: Integrated P0 power and 48-hour guard matrix
status: active
priority: critical
lane: C
execution_state: queued
depends_on:
  - HW-022
  - LOC-021
  - CALL-021
  - SOS-010
serves_gate: G3-POWER
requires_hardware: true
created: 2026-08-23
last_updated: 2026-08-23

context:
  - docs/hardware/POWER_AND_BATTERY_ENGINEERING_TARGETS.md
  - docs/tasks/active/HW-022_INTEGRATED_PROTOTYPE_BUILD.md
  - docs/tasks/active/FIELD-020_L1_FIELD_DATASET.md
  - docs/tasks/active/CALL-021_EMBEDDED_LTE_RTC_MEDIA.md
  - docs/tasks/active/SOS-010_SOS_WALKING_SKELETON.md

allowed_paths:
  - docs/tasks/active/PWR-020_P0_48H_POWER_MATRIX.md

out_of_scope:
  - extrapolating product life from development-board or idle-only current
  - changing location/call/SOS policy merely to manufacture a passing number
  - starting an unattended run without reviewed safety and operator intent
---

# Goal

Measure the integrated prototype across guard, moving/uncertain location,
Ego Call and SOS loads, including one uninterrupted 48-hour guard-profile run.

# Acceptance

- [ ] Rail/current instrumentation, battery identity, calibration, firmware,
      policy/media config and environmental conditions are bound to the run.
- [ ] No brownout/reset occurs under declared modem TX + GNSS + audio peaks;
      failures and emergency low-battery behavior remain visible.
- [ ] Per-mode energy and transition cost are measured, and the 48-hour guard
      profile passes on the same integrated revision used for release review.
- [ ] Results are measured evidence, not estimates from capacity arithmetic.

# Hardware Boundary

Add exact commands and private evidence paths at dispatch. Battery charging,
unattended operation, hardware control and stress runs require explicit
operator intent and a reviewed stop condition.

# Validation

```powershell
python scripts/context_lint.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1
git diff --check
```

# Completion Evidence

- Hardware/evidence: `NOT_RUN`.
- PWR-001 remains useful development-board baseline only and cannot close this
  product task.
