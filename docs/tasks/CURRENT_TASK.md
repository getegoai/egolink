# CURRENT_TASK: TIMU-003 / QMI8658 Timing Retest

## Goal

Fix the AMOLED bridge sample scheduling problem found by TIMU-002 and prove
that the QMI8658 path can produce a longer 100+ sample window at the requested
20 Hz cadence.

## Scope

- Change `firmware/amoled_bridge` from end-of-loop `vTaskDelay(50ms)` sampling
  to fixed-period `vTaskDelayUntil` scheduling.
- Timestamp each `imu_sample` at sample-start time rather than after read/print
  work.
- Expand the bounded sample window from 40 to 120 samples.
- Emit timing metadata in `amoled_bridge_done`.
- Rebuild, flash, and capture a new live JSONL window from `COM9`.
- Rerun the IMU quality analyzer with `--min-samples 100`.
- Feed the capture through PC Bridge, session recording, quality gate, and
  replay.

## Out Of Scope

- No `platform_imu` real backend switch.
- No source promotion to `verified`.
- No MotionNet training data claim.
- No fall, impact, wear-state, or activity inference.
- No microphone, TF/SD, touch, display, power, or board-to-board UART work.

## Result

- Updated `firmware/amoled_bridge/main/app_main.c`.
- Updated `firmware/amoled_bridge/README.md`.
- Updated `quality_tests/test_amoled_bridge_firmware.py`.
- Captured
  `pc_simulator/runtime/timu003-qmi8658-live-20260623-201436.jsonl`.
- Generated
  `docs/hardware/TIMU_003_QMI8658_TIMING_RETEST_20260623.md`.

Measured result:

- Live JSONL lines: 123.
- `imu_sample` count: 120.
- Firmware timing mode: `vTaskDelayUntil`.
- Missed deadlines: 0.
- Max sample work: 42 ms.
- Expected interval: 50 ms.
- Observed mean interval: about `49.99 ms`.
- Observed sample rate: about `20.00 Hz`.
- Device timing gate: PASS.
- Static orientation gate: PASS, dominant axis `z negative`.
- PC Bridge stored 123 events with 0 skipped lines.
- Session recording produced 120 `imu_motion` frames.
- Quality gate PASS, `quality_score=0.94`.
- Replay PASS, 120 inputs all `risk_type=none`.
- Full repository verification PASS, 144 tests.

Formal IMU acceptance remains false because the source is still intentionally
`bridge_uplink/unverified`. TIMU-003 fixes timing; it does not complete
mounting, calibration, FIFO/interrupt, power, or product backend acceptance.

## Done When

- [x] AMOLED bridge builds.
- [x] AMOLED board flashes over `COM9`.
- [x] Live capture contains at least 100 `imu_sample` records.
- [x] Analyzer timing gate passes.
- [x] PC Bridge ingests the capture without skipped lines.
- [x] Recorder emits 100+ `imu_motion` frames.
- [x] Quality gate passes.
- [x] Replay passes.
- [x] Formal IMU acceptance remains false until later acceptance tasks.
