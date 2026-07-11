---
id: D2-005
title: QMI8658 4G-board configuration and motion-data readiness
status: done
priority: high
requires_hardware: false
serves_demo: D2
created: 2026-07-11
last_updated: 2026-07-11
completed: 2026-07-11

context:
  - docs/product/NORTH_STAR.md
  - docs/architecture/adr/ADR-0004-p0-rule-location-and-transitional-vps-memory.md
  - docs/development/LOCATION_DATASET.md
  - docs/hardware/QMI8658_4G_MODULE_INTEGRATION.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md

allowed_paths:
  - scripts/prepare_fw001_hw_config.ps1
  - scripts/assess_motion_data_readiness.py
  - quality_tests/test_fw001_hw_config.py
  - quality_tests/test_motion_data_readiness.py
  - docs/current/
  - docs/development/
  - docs/hardware/
  - docs/tasks/
  - docs/generated/
  - reports/motion_data_readiness/

out_of_scope:
  - firmware flashing or hardware control
  - new wire-protocol fields or continuous IMU sampler implementation
  - model training or deployment
  - location, motion-model, or battery-life performance claims
---

This task serves D2 and its D5 data follow-up. The current lowest unfinished
Demo is D2; this task directly removes the product-topology IMU evidence
blocker while FIELD-003 waits for operator field work.

# Goal

Make external QMI8658 firmware configuration reproducible and quantify whether
bounded field evidence is sufficient for motion-model dataset work.

# Acceptance

- QMI8658 can be enabled in the existing local firmware config generator with
  explicit I2C pins/address and AMOLED-only AXP2101 rails disabled.
- MAX17048 plus QMI8658 rejects mismatched I2C bus settings.
- A bounded analyzer reports real/mock IMU coverage, cadence, GNSS speed-label
  coverage, and blockers without writing coordinates or training rows.
- Historical VPS evidence is assessed honestly.
- Focused tests, context lint, and full verification pass.

# Result

- QMI8658/MAX17048 shared-I2C local configuration is reproducible and guarded.
- A no-flash V2-pin/`0x6B` placeholder firmware profile compiled successfully;
  the binary is ignored local build output and is not hardware evidence.
- Historical VPS readiness is WARN: 1081 messages, 118 mock IMU metadata
  events, 0 real six-axis samples, 79 good-fix speed samples, and 0 joined
  samples. No coordinates, raw messages, or training rows were written.
- Next hardware step is module identity/address/pin probe. The next firmware
  step is a bounded high-rate IMU window uplink only after that probe.

# Validation

- Focused tests: pass.
- `python scripts/context_lint.py`: pass.
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`: pass, 561
  tests.
