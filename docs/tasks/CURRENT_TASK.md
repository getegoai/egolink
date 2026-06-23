# CURRENT_TASK: TIMU-002 / QMI8658 Sample Quality Gate

## Goal

Turn the HDBRIDGE-002 AMOLED QMI8658 short-window capture into a repeatable
measurement gate for IMU identity, completeness, timing, static orientation,
gyro sanity, and source-boundary status.

The purpose is to decide whether the current QMI8658 samples are ready to be
treated as formal M1 IMU data. They are not ready yet.

## Scope

- Add a PC-side QMI8658 JSONL analyzer.
- Parse `imu_whoami`, `imu_sample`, and `amoled_bridge_done` records.
- Report identity, sample count, seq/sample-index continuity, read errors,
  not-ready count, device monotonic interval, QMI timestamp monotonicity,
  static 1g orientation, warm gyro sanity, and source status.
- Keep `bridge_uplink/unverified` as a hard boundary.
- Generate a TIMU-002 Markdown evidence report from the HDBRIDGE-002 live
  capture.

## Out Of Scope

- No firmware timing fix in this task.
- No `platform_imu` real backend switch.
- No MotionNet training data claim.
- No fall, impact, wear-state, or activity inference.
- No microphone, TF/SD, touch, display, power, or board-to-board UART work.

## Result

- Added `pc_simulator/imu_quality.py`.
- Added `scripts/analyze_imu_quality.py`.
- Added `quality_tests/test_imu_quality.py`.
- Generated
  `docs/hardware/TIMU_002_QMI8658_SAMPLE_QUALITY_20260623.md`.
- Analyzed
  `pc_simulator/runtime/hdb002-amoled-live-20260623-194454.jsonl`.

Measured result:

- QMI8658 WHOAMI: `5`, expected `5` - PASS.
- Sample count: 40 - PASS.
- Sample index / seq continuity - PASS.
- Completion record: `read_errors=0`, `not_ready_count=0` - PASS.
- Static accel orientation: dominant `z` negative, mean magnitude about
  `1031.43 mg` - PASS.
- Warm gyro sanity: mean absolute rate about `502.42 mdps` - PASS.
- Device timing: expected `50 ms`, observed mean `82.31 ms`, observed
  `12.15 Hz` - FAIL.
- Source boundary: `bridge_uplink/unverified` - PASS as a boundary, not as
  formal acceptance.

## Done When

- [x] Analyzer can parse AMOLED QMI8658 JSONL captures.
- [x] Analyzer reports identity, completeness, timing, orientation, gyro, and
  source-boundary gates.
- [x] Analyzer refuses to treat `source_status=verified` as acceptable input
  before formal acceptance.
- [x] Existing HDBRIDGE-002 capture is analyzed.
- [x] Evidence report records the timing failure and keeps formal IMU
  acceptance false.
- [x] Focused tests pass.
