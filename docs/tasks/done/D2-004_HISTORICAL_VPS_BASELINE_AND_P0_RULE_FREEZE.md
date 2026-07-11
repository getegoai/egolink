---
id: D2-004
title: Historical VPS baseline and P0 location rule freeze
status: done
priority: high
requires_hardware: false
serves_demo: D2
created: 2026-07-11
completed: 2026-07-11

context:
  - docs/product/NORTH_STAR.md
  - docs/development/LOCATION_ENGINE.md
  - docs/development/LOCATION_DATASET.md
  - docs/development/VPS_MESSAGE_HUB.md
  - docs/tasks/active/D2-001_LOCATION_ACCURACY_BASELINE.md

allowed_paths:
  - scripts/
  - server/
  - quality_tests/
  - docs/architecture/
  - docs/development/
  - docs/hardware/
  - docs/current/
  - docs/tasks/
  - reports/location_accuracy/

out_of_scope:
  - learned model training or deployment
  - firmware changes or flashing
  - product location accuracy or battery-life claims
  - raw coordinate publication
---

This task serves D2. The current lowest unfinished Demo is D2; this task
directly establishes historical evidence and freezes the P0 algorithm scope.

# Result

- Added a read-only historical VPS baseline generator over explicitly named,
  bounded field-observer windows.
- Produced `D2-historical-vps-baseline-20260711`: 203 unique location-report
  events, 96 fix, 107 no-fix, provisional event fix rate `0.472906`.
- Kept median/P90 position error and TTFF as not measurable because historical
  evidence has no external reference truth or GNSS attempt boundaries.
- Allowed curated D2 JSON/Markdown summaries in the VPS Dashboard deployment
  package without copying raw coordinates or messages.
- Accepted ADR-0004: P0 location stays rule/statistics based; the only current
  learned candidate is IMU motion state; VPS personal location memory is
  transitional.
- Added the external QMI8658-on-4G-board integration plan and 18650 test
  boundary without changing or flashing firmware.

# Validation

- Focused unit tests: pass.
- `python scripts/context_lint.py`: pass.
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`: pass, 554
  tests.
