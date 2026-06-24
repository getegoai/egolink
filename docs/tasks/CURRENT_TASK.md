# CURRENT_TASK: TIMU-006 / QMI8658 Long Window Capture

## Goal

Capture and verify a longer real QMI8658 window on the
ESP32-S3-Touch-AMOLED-2.06 board, using the bridge path only and without
claiming formal IMU acceptance.

## Scope

- Make the AMOLED bridge sample count and interval configurable through ESP-IDF
  project configuration.
- Use a 600-sample, 50 ms window for about 30 seconds of QMI8658 data.
- Add a PC-side `--long-window` timing/jitter/drop quality mode.
- Capture one live long window on `COM9`.
- Run PC Bridge, M1 session recording, quality gate, and replay.
- Keep the source boundary at `bridge_uplink/unverified`.

## Out Of Scope

- No `platform_imu` real backend switch.
- No source promotion to `verified`.
- No MotionNet training data claim.
- No fall, impact, wear-state, or activity inference.
- No microphone, TF/SD, touch, display, power, FIFO/interrupt, or board-to-board
  UART work.

## Result

- Added `firmware/amoled_bridge/main/Kconfig.projbuild`.
- Updated `firmware/amoled_bridge` defaults:
  `CONFIG_EGOLINK_AMOLED_SAMPLE_COUNT=600` and
  `CONFIG_EGOLINK_AMOLED_SAMPLE_INTERVAL_MS=50`.
- Updated `pc_simulator/imu_quality.py` with `long_window_timing` mode and
  `device_jitter` gate.
- Updated `scripts/capture_amoled_qmi8658_pose_set.ps1` with `-M1Limit` so long
  windows are not truncated by the recorder.
- Added `docs/hardware/TIMU_006_QMI8658_LONG_WINDOW_20260624.md`.
- Built `firmware/amoled_bridge` successfully with ESP-IDF v5.4.2.
- Flashed `firmware/amoled_bridge` to `COM9` successfully.
- Captured:
  `pc_simulator/runtime/timu006/timu006-qmi8658-long-window-live-20260624-0001-motion.jsonl`.
- Long-window capture contained 603 JSONL records and 600 `imu_sample` records.
- Completion payload reported `samples_emitted=600`, `read_errors=0`,
  `not_ready_count=0`, `missed_deadlines=0`, and `max_sample_work_ms=42`.
- Long-window analyzer PASS:
  - observed mean interval about `49.9983 ms`
  - observed sample rate about `20.0007 Hz`
  - max interval deviation `1.0 ms`
  - jitter limit `10.0 ms`
  - QMI timestamp monotonic
- PC Bridge stored 603 events with 0 skipped lines.
- M1 recording produced 600 `imu_motion` frames.
- M1 quality gate PASS, `quality_score=0.94`, `errors=0`, `warnings=2`.
- Replay PASS, 600 inputs all `risk_type=none`.
- Formal IMU acceptance remains false with reason `source_status_unverified`.

## Done When

- [x] Firmware supports configurable long-window sample count and interval.
- [x] Firmware builds.
- [x] Firmware flashes to `COM9`.
- [x] Live 600-sample long window is captured on `COM9`.
- [x] Long-window timing gate passes.
- [x] Long-window jitter gate passes.
- [x] PC Bridge ingests the capture with 0 skipped lines.
- [x] M1 recording quality gate passes.
- [x] Replay passes.
- [x] Formal IMU acceptance remains false.

Formal IMU acceptance remains false while the source is still
`bridge_uplink/unverified` and product mounting, FIFO/interrupt, power, and real
backend validation are pending.
