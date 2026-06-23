# CURRENT_TASK: TIMU-004A / QMI8658 Single-Pose Quality Gate

## Goal

Add a repeatable QMI8658 pose/motion quality gate and run it against the
currently connected ESP32-S3-Touch-AMOLED-2.06 board without claiming formal
IMU acceptance.

## Scope

- Add a PC-side pose/motion analyzer for labeled QMI8658 JSONL captures.
- Check static pose quality, axis/sign label matching, conservative calibration
  offset, optional motion sanity, and source boundary.
- Keep TIMU-003 timing analysis unchanged.
- Capture a fresh live QMI8658 window from `COM9`.
- Feed the capture through PC Bridge, session recording, quality gate, and
  replay.
- Preserve `bridge_uplink/unverified` source status.

## Out Of Scope

- No `platform_imu` real backend switch.
- No source promotion to `verified`.
- No MotionNet training data claim.
- No fall, impact, wear-state, or activity inference.
- No microphone, TF/SD, touch, display, power, FIFO/interrupt, or board-to-board
  UART work.
- No claim that TIMU-004 total multi-pose acceptance is complete.

## Result

- Added `pc_simulator/imu_pose_quality.py`.
- Added `scripts/analyze_imu_pose_quality.py`.
- Added `quality_tests/test_imu_pose_quality.py`.
- Updated JSONL consumers to tolerate Windows UTF-8 BOM captures.
- Captured
  `pc_simulator/runtime/timu004-qmi8658-single-pose-live-20260623-203238.jsonl`.
- Generated
  `docs/hardware/TIMU_004_QMI8658_POSE_QUALITY_20260623.md`.

Measured result:

- Live JSONL lines: 123.
- `imu_sample` count: 120.
- Firmware timing mode: `vTaskDelayUntil`.
- Missed deadlines: 0.
- Max sample work: 42 ms.
- Expected interval: 50 ms.
- Observed mean interval: about `49.99 ms`.
- Observed sample rate: about `20.00 Hz`.
- Pose label: `z_negative`.
- Measured dominant axis: `z negative`.
- Mean axes: about `[56.63, 22.98, -1030.48] mg`.
- Conservative calibration offset estimate: about `[56.6, 23.0, -30.5] mg`.
- Static pose quality: PASS.
- Pose label match: PASS.
- Calibration offset gate: PASS.
- Pose count / axis coverage / motion sanity: FAIL because only one static pose
  was captured and no rotation/tap window was supplied.
- PC Bridge stored 123 events with 0 skipped lines.
- Session recording produced 120 `imu_motion` frames.
- Quality gate PASS, `quality_score=0.94`.
- Replay PASS, 120 inputs all `risk_type=none`.
- Full repository verification PASS, 151 tests.

Formal IMU acceptance remains false because the source is still intentionally
`bridge_uplink/unverified`, multi-pose/motion evidence is incomplete, and
mounting, full calibration, FIFO/interrupt, power, and product backend
acceptance are still pending.

## Done When

- [x] Pose/motion analyzer exists and is unit-tested.
- [x] Analyzer accepts labeled `LABEL=JSONL` pose windows.
- [x] Analyzer reports static quality, label match, calibration offset, motion
      sanity, and source boundary.
- [x] Windows UTF-8 BOM JSONL captures do not break analyzer or PC Bridge.
- [x] AMOLED board flashes over `COM9`.
- [x] Live capture contains at least 100 `imu_sample` records.
- [x] Timing cross-check passes.
- [x] Single current static pose is analyzed and reported.
- [x] PC Bridge ingests the capture without skipped lines.
- [x] Recorder emits 100+ `imu_motion` frames.
- [x] Quality gate passes.
- [x] Replay passes.
- [x] TIMU-004 total multi-pose/motion acceptance remains false until manual
      pose or rotation/tap capture is performed.
