---
id: A0-001
title: IMU six-face calibration pipeline
status: active
priority: critical
requires_hardware: true
created: 2026-08-16
last_updated: 2026-08-17

context:
  - docs/current/EGO_LINK_A_LINE_AI_CONTEXT.md
  - docs/current/ACTIVE_BUILD.md
  - docs/architecture/SYSTEM_OVERVIEW.md
  - docs/architecture/adr/ADR-0009-ai-v0-1-belief-estimation-baseline.md
  - docs/development/DIRECTOR_WORKFLOW.md
  - shared/contracts/README.md

allowed_paths:
  - docs/CONTEXT_INDEX.md
  - docs/architecture/adr/ADR-0009-ai-v0-1-belief-estimation-baseline.md
  - docs/current/EGO_LINK_A_LINE_AI_CONTEXT.md
  - docs/development/IMU_CALIBRATION.md
  - docs/tasks/active/A0-001_IMU_CALIBRATION_PIPELINE.md
  - pc_simulator/imu_six_face_calibration.py
  - quality_tests/test_a0_calibration_repeatability.py
  - quality_tests/test_a0_imu_calibration.py
  - quality_tests/test_a0_six_face_capture.py
  - scripts/compare_a0_imu_calibrations.py
  - scripts/generate_a0_imu_calibration.py
  - scripts/run_a0_six_face_capture.py
  - shared/contracts/README.md
  - shared/contracts/imu_calibrated_window.schema.json
  - shared/contracts/imu_calibration_artifact.schema.json

out_of_scope:
  - flashing firmware or issuing hardware capture commands in this implementation slice
  - changing the current IMU wire protocol, sensor rate, ranges, pins, or firmware behavior
  - model training or changing Location Belief behavior
  - marking A0-001 or A-R0 as passed without a reviewed real six-pose capture artifact
execution_state: queued
owner: unassigned
reviewed_at: 2026-09-22
---

# Problem

The current QMI8658 path can export bounded, cadence-qualified 100-sample
windows at a requested 50 ms interval. Existing calibration code produces only
a conservative three-pose engineering offset estimate: it does not estimate
six-face accelerometer scale or signed stationary gyro bias, and it explicitly
blocks model-training use. A0 cannot promote trustworthy IMU datasets until a
deterministic, versioned six-face calibration artifact exists.

The current `egolink.imu_window.v1` samples are uncalibrated engineering values
in `mg` and `mdps`, converted in firmware from sensor registers. They are not
the original ADC counts. This task must preserve those exact source values and
must not relabel them as raw counts.

# Expected Result

One standard command consumes six explicitly pose-labelled IMU window exports
(`+X/-X/+Y/-Y/+Z/-Z`) plus one independent stationary gyro window, verifies
their source and sample hashes, estimates per-axis accelerometer bias/scale and
stationary gyro bias, and emits:

- a versioned calibration artifact with stable ID, device/sensor/firmware,
  capture, mounting and temperature-availability provenance;
- a calibrated JSONL view that keeps every original uncalibrated sample beside
  calibrated SI values; and
- a human-readable quality report and explicit limitations.

# Acceptance Criteria

- [x] The six-face estimator computes axis bias and scale from opposite-pose
  means and rejects missing, duplicated, mislabeled, unstable, inconsistent or
  integrity-invalid inputs.
- [x] Stationary samples estimate signed `gyro_mdps` bias on all three axes.
- [x] The artifact conforms to a committed JSON Schema, has a deterministic
  `calibration_id`/payload hash, and binds `device_id`, `imu_model`,
  `calibration_time`, `firmware_commit`, source window hashes and optional
  temperature status.
- [x] Materialized output preserves the exact input `accel_mg`/`gyro_mdps`
  values and adds calibrated `m/s^2` and `rad/s`; it explicitly records that
  ADC counts and temperature are unavailable in the current v1 source.
- [x] Automated tests cover valid estimation, deterministic identity,
  schema validation, integrity failure, missing pose, source mismatch and
  raw/calibrated preservation.
- [x] A real bench six-face plus independent gyro capture produced a
  reproducible engineering artifact; the 2026-08-17 integrity review accepts
  it only as `artifact` evidence.
- [ ] A qualifying Field Session must reference the calibration artifact,
  preserve pre-calibration and calibrated values, and expose a shareable
  immutable evidence reference before A0-001 and A-R0-C1 can close.

# Validation Commands

```powershell
python -m unittest quality_tests.test_a0_imu_calibration -v
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
```

# Hardware Validation

- Flashed-image capability: the image currently flashed is FW-007
  `0.1.0-fw007-lte-wifi-failover`. It does not set
  `CONFIG_EGOLINK_WIFI_IMU_WINDOW_COMMAND_ENABLED`, but that switch is only one
  of two ways to obtain the capability. `app_main.c` guards the raw command
  handler with `#if CONFIG_EGOLINK_WIFI_IMU_WINDOW_COMMAND_ENABLED ||
  CONFIG_EGOLINK_LTE_WIFI_FAILOVER_ENABLED`, and the `capture_imu_window`
  branch sits outside the failover-only block. FW-007 sets
  `LTE_WIFI_FAILOVER_ENABLED=y`, so both its LTE command loop and its Wi-Fi
  failover raw command path accept `capture_imu_window`. FIELD-011 captured an
  IMU window over LTE with the Wi-Fi profile switch off, which matches.
  No reflash is currently known to be required.
- The `1..4` successful-commands-per-boot cap belongs to the dedicated Wi-Fi
  profile only: its `_Static_assert` sits in the `#else` branch of
  `#if CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED`. Failover depends
  on that loop, so FW-007 takes the other branch and the cap does not apply.
  The practical per-boot bound there is the poll-attempt limit instead.
- Board: connectivity-node ESP32-S3-SIM7670G with external QMI8658A
- Capture performed 2026-08-16 on the already-flashed FW-007 image; no reflash,
  no firmware change, no configuration change was needed or made.
- Firmware commit `e9ca7a4673f434697e0ae0e6b2faca2ba1467784`, image SHA-256
  `8f3508c6...39283799`, fw_version `0.1.0-fw007-lte-wifi-failover`
- Connection: bounded `capture_imu_window` over LTE via the Message Hub, one
  operator-confirmed command per pose, seven commands total in boot `26946`
- Result: seven windows, all cadence-qualified, zero invalid, zero mock
- Evidence path: `reports/imu_calibration/A0-001-REAL-20260816-001/`
  (`reports/` is gitignored, so the artifact stays local by repository convention)

# Decisions

- A0-001 is the current primary A-line task. A0-002 through A0-004 follow; AI
  architecture design proceeds in parallel without training on unqualified
  data.
- The engineering estimator is axis-aligned and diagonal in v0.1. Full
  cross-axis misalignment, temperature drift and production fixture
  calibration remain later validation work.
- `50 Hz / 2-4 s` is an M1 model-design starting point, not a claim about the
  current 20 Hz / 100-sample capture contract.

# Completion Evidence

- Static implementation: `pc_simulator/imu_six_face_calibration.py` and
  `scripts/generate_a0_imu_calibration.py`
- Contracts: `shared/contracts/imu_calibration_artifact.schema.json` and
  `shared/contracts/imu_calibrated_window.schema.json`
- Documentation: `docs/development/IMU_CALIBRATION.md`, ADR-0009 and the
  control-contract index entries
- Focused calibration/capture/repeatability tests passed 36/36 on 2026-08-17.
- Repository validation: `python scripts/context_lint.py` passed and
  `scripts/verify.ps1` passed 708/708 on 2026-08-17.
- Capture feasibility: the Wi-Fi-only `1..4` successful-command cap does not
  apply to the FW-007 LTE command loop. The real run captured all seven windows
  in boot `26946`; cross-boot capture remains allowed and explicitly recorded.
- Independent review 2026-08-16 closed four fail-open gaps found in `c779881`:
  a rotating window was accepted and recorded as gyro bias, `boot_count` was
  exported but never bound, `window_id` was not checked against its own
  `capture_cmd_id`/`boot_count` derivation, and all-zero placeholder firmware
  and software hashes were accepted. Real `scripts/export_imu_windows.py`
  output is now exercised end to end rather than only a hand-shaped fixture.
- Hardware result 2026-08-16: the real six-face plus independent stationary
  gyro capture is complete. Calibration `imucal-e6e1c71fc02a239c8372fabc`,
  payload SHA-256 `a2bd6598b90872a4cc909a3e5a2527d440d3031820684254ae8c7f40d987969e`,
  run `A0-001-REAL-20260816-001`, all seven windows from boot `26946` over LTE.
  Accel bias mg `[5.09, 67.98, -25.78]`, sensitivity mg/g
  `[993.82, 997.99, 994.14]`, signed gyro bias mdps
  `[-1863.83, -2367.87, 22.07]`. Max cross-window gyro delta `166.64` mdps
  against a `2000` bound; max calibrated off-axis residual `85.51` mg against a
  `150` bound. All 700 materialized samples preserve their source
  `accel_mg`/`gyro_mdps` exactly, and the source JSONL was not modified.
- The 2026-08-17 integrity review accepts the result as engineering `artifact`
  evidence. Control Plane commit `2fa3402` records it and is deployed. A0-001
  stays `active` and A-R0 stays `0/8`; this bench run is not a Field Session,
  training-ready evidence, production calibration or Gate PASS.
- Founder direction on 2026-08-17 closes further calibration expansion. The
  artifact is `engineering-ready / awaiting field verification` and may be
  referenced by the first real Field Session, while the task and Gate remain
  `active`. FW-007 preserves QMI8658 sensor XYZ without software remapping;
  sensor-to-module-PCB/main-PCB/body mapping remains `unrecorded` until one
  bounded +Z/+X/+Y body-up physical confirmation is captured after the board
  returns. Repeatability, temperature, cross-axis and production calibration
  are not current blockers.
- The existing `z_negative` window remains accepted for this engineering
  artifact: its raw equivalent tilt is about `8.045°`, bias-corrected residual
  about `4.354°`, while `y_positive` has the larger calibrated residual angle
  at about `4.965°`. A replacement is optional only if it is effectively free
  during the body-axis confirmation; it does not block the Field Session.
- Evidence gaps: p3-p6 lack independent operator receipts; the raw Message Hub
  DB was not retained with the package; `reports/` is gitignored; independent
  repeatability, body-axis mapping, temperature, sample UTC, raw ADC counts,
  temperature drift and production calibration remain unavailable.
- `calibration_software_commit` records `f1439fe`; the report-footer wording
  was committed later in `c54ed7d`. The algorithm and machine artifacts remain
  reproducible, but the report provenance is not fully identified by the
  recorded software commit.
