# CURRENT_TASK: TIMU-004B / QMI8658 Manual Three-Pose Capture

## Goal

Capture and verify manual QMI8658 multi-pose evidence on the
ESP32-S3-Touch-AMOLED-2.06 board without claiming formal IMU acceptance.

## Scope

- Use the bounded PowerShell capture helper for AMOLED bridge JSONL windows.
- Capture labeled static poses with real physical board movement.
- Keep the source boundary at `bridge_uplink/unverified`.
- Reuse the existing TIMU-004A pose/motion analyzer.
- Run PC Bridge, M1 session recording, quality gate, and replay.
- Document the operator protocol, measured pose results, and acceptance boundary.

## Out Of Scope

- No optional motion-window claim.
- No `platform_imu` real backend switch.
- No source promotion to `verified`.
- No MotionNet training data claim.
- No fall, impact, wear-state, or activity inference.
- No microphone, TF/SD, touch, display, power, FIFO/interrupt, or board-to-board
  UART work.

## Result

- Added `scripts/capture_amoled_qmi8658_pose_set.ps1`.
- Added `quality_tests/test_amoled_pose_capture_script.py`.
- Added `docs/hardware/TIMU_004B_QMI8658_MANUAL_CAPTURE_20260623.md`.
- The helper captures finite COM9 windows, writes UTF-8 JSONL without BOM, and
  waits for `amoled_bridge_done`.
- The helper can call:
  - `scripts/analyze_imu_pose_quality.py`
  - `scripts/board_bridge.py`
  - `scripts/session_recorder.py`
  - `scripts/inspect_session_recording.py`
  - `scripts/replay_session_recording.py`
- Fixed the helper to filter ESP-IDF boot logs so captured `.jsonl` files
  contain only JSON objects.
- Ran a bounded live preflight on `COM9`:
  `timu004b-qmi8658-preflight-live-20260623-205520`.
- Live preflight captured 123 JSONL records, including 120 `imu_sample`
  records, `imu_whoami`, and `amoled_bridge_done`.
- Single-pose `z_negative` static quality, label match, calibration offset, and
  source-boundary gates passed.
- Overall TIMU-004 pose/motion quality still failed by design because only one
  pose was captured and no motion window was supplied.
- PC Bridge/M1 recording/quality/replay passed for the preflight:
  120 `imu_motion` frames, quality score `0.94`, replay 120 `none` outputs.
- Captured two additional manually positioned static poses:
  - `x_positive`:
    `pc_simulator/runtime/timu004b/timu004b-qmi8658-manual-pose1-20260623-2100-x_positive.jsonl`
  - `y_positive`:
    `pc_simulator/runtime/timu004b/timu004b-qmi8658-manual-pose2-20260623-2108-y_positive.jsonl`
- Combined three-pose analyzer input:
  `z_negative`, `x_positive`, and `y_positive`.
- Three-pose analyzer result: `quality_gates_passed=true`.
- Pose gates passed: static quality, pose count, axis coverage, label match,
  calibration offset, pose-or-motion evidence, and source boundary.
- Optional `motion_sanity` remained false because no motion window was supplied.
- Formal IMU acceptance remains false with reason `source_status_unverified`.
- PC Bridge stored 369 events with 0 skipped lines for the three-pose set.
- M1 recording produced 360 `imu_motion` frames.
- M1 quality gate PASS, `quality_score=0.91`, `errors=0`, `warnings=3`.
- Replay PASS, 360 inputs all `risk_type=none`.
- `seq_decrease` warning is expected because each bounded capture window resets
  the device sequence.

## Done When

- [x] Capture helper exists and uses bounded serial reads.
- [x] Helper supports labeled static pose windows.
- [x] Helper supports an optional motion window.
- [x] Helper can run the pose/motion analyzer.
- [x] Helper can run PC Bridge, M1 recording, quality gate, and replay.
- [x] Protocol report explains operator steps and acceptance boundaries.
- [x] Static contract tests cover the helper.
- [x] Live COM9 preflight has been run in this task.
- [x] Multi-pose quality gate passes with real physical movement.

Formal IMU acceptance remains false while the source is still
`bridge_uplink/unverified` and mounting, calibration, FIFO/interrupt, power, and
real backend validation are pending.
