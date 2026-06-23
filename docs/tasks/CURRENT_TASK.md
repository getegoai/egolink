# CURRENT_TASK: TIMU-004B-Prep / QMI8658 Manual Pose Capture Flow

## Goal

Make the next QMI8658 multi-pose or motion capture repeatable on the
ESP32-S3-Touch-AMOLED-2.06 board without claiming formal IMU acceptance.

## Scope

- Add a bounded PowerShell capture helper for AMOLED bridge JSONL windows.
- Support labeled static poses and an optional motion window.
- Keep the source boundary at `bridge_uplink/unverified`.
- Reuse the existing TIMU-004A pose/motion analyzer.
- Optionally run PC Bridge, M1 session recording, quality gate, and replay.
- Document the operator protocol and acceptance boundary.

## Out Of Scope

- No claim that TIMU-004 multi-pose/motion evidence is complete unless the board
  is physically moved during capture.
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

## Done When

- [x] Capture helper exists and uses bounded serial reads.
- [x] Helper supports labeled static pose windows.
- [x] Helper supports an optional motion window.
- [x] Helper can run the pose/motion analyzer.
- [x] Helper can run PC Bridge, M1 recording, quality gate, and replay.
- [x] Protocol report explains operator steps and acceptance boundaries.
- [x] Static contract tests cover the helper.
- [x] Live COM9 preflight has been run in this task.
- [ ] Multi-pose or motion quality gate passes with real physical movement.

Formal IMU acceptance remains false while the source is still
`bridge_uplink/unverified` and mounting, calibration, FIFO/interrupt, power, and
real backend validation are pending.
