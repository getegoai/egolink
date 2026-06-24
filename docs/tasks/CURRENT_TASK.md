# CURRENT_TASK: TIMU-005 / QMI8658 Motion Window Capture

## Goal

Capture and verify a real QMI8658 motion window on the
ESP32-S3-Touch-AMOLED-2.06 board, reusing the TIMU-004B three-pose evidence and
without claiming formal IMU acceptance.

## Scope

- Extend the bounded AMOLED capture helper with `-MotionOnly` and
  `-ExistingPose LABEL=PATH` support.
- Reuse the existing `z_negative`, `x_positive`, and `y_positive` static pose
  windows from TIMU-004B.
- Capture one operator-driven rotation/light-tap motion window on `COM9`.
- Run the pose/motion analyzer, PC Bridge, M1 session recording, quality gate,
  and replay.
- Keep the source boundary at `bridge_uplink/unverified`.

## Out Of Scope

- No `platform_imu` real backend switch.
- No source promotion to `verified`.
- No MotionNet training data claim.
- No fall, impact, wear-state, or activity inference.
- No microphone, TF/SD, touch, display, power, FIFO/interrupt, or board-to-board
  UART work.

## Result

- Updated `scripts/capture_amoled_qmi8658_pose_set.ps1` with motion-only capture
  and existing pose source reuse.
- Updated `quality_tests/test_amoled_pose_capture_script.py`.
- Added `docs/hardware/TIMU_005_QMI8658_MOTION_WINDOW_20260624.md`.
- Captured:
  `pc_simulator/runtime/timu005/timu005-qmi8658-motion-live-20260624-0001-motion.jsonl`.
- Motion capture contained 123 JSONL records and 120 `imu_sample` records.
- Motion timing cross-check passed at about `49.99 ms / 20.00 Hz`.
- Motion analyzer saw 115 samples after warmup discard.
- Accel magnitude range: about `490.04 mg`.
- Gyro peak: about `201921 mdps`.
- `motion_sanity`: PASS.
- Three-pose + motion overall quality gates: PASS.
- Formal IMU acceptance remains false with reason `source_status_unverified`.
- PC Bridge stored 492 events with 0 skipped lines.
- M1 recording produced 480 `imu_motion` frames.
- M1 quality gate PASS, `quality_score=0.91`, `errors=0`, `warnings=3`.
- Replay PASS, 480 inputs all `risk_type=none`.
- `seq_decrease` warning is expected because the evidence set combines multiple
  bounded capture windows after independent bridge resets.

## Done When

- [x] Capture helper supports motion-only capture.
- [x] Capture helper can reuse existing pose evidence.
- [x] Live motion window is captured on `COM9`.
- [x] Motion sanity gate passes.
- [x] Pose/motion overall quality gate passes.
- [x] PC Bridge ingests pose + motion evidence with 0 skipped lines.
- [x] M1 recording quality gate passes.
- [x] Replay passes.
- [x] Formal IMU acceptance remains false.

Formal IMU acceptance remains false while the source is still
`bridge_uplink/unverified` and mounting, calibration, FIFO/interrupt, power, and
real backend validation are pending.
