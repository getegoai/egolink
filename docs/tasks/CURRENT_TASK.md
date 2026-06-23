# CURRENT_TASK: HDBRIDGE-002 / AMOLED USB CDC QMI8658 Live Window

## Goal

Exercise the `ESP32-S3-Touch-AMOLED-2.06` board as the wearable sensor-node
candidate by flashing a minimal ESP-IDF firmware, emitting newline-delimited
JSON over native USB serial, and proving that QMI8658 identity plus a bounded
sample window can pass through PC Bridge, session recording, quality gate, and
replay.

## Scope

- Add a dedicated `firmware/amoled_bridge` ESP-IDF app.
- Use the vendor I2C pin map: SDA GPIO15, SCL GPIO14.
- Bring up AXP2101 conservatively without disabling unrelated rails.
- Probe QMI8658 at address `0x6B` and require WHOAMI `0x05`.
- Emit `hello`, `imu_whoami`, bounded `imu_sample`, and
  `amoled_bridge_done` JSONL records.
- Keep all QMI8658 records marked `source_availability=bridge_uplink` and
  `source_status=unverified`.
- Feed the captured JSONL through PC Bridge, recording, quality gate, and
  replay.
- Document the live evidence and remaining validation boundary.

## Out Of Scope

- No formal IMU acceptance claim.
- No ODR, jitter, drop-rate, orientation, mounting, calibration, FIFO, or
  interrupt validation.
- No microphone capture, AudioGate, TF/SD, display UI, or touch command path.
- No board-to-board UART direct connection.
- No battery, fuel-gauge, charger, or power-consumption validation.
- No MotionNet training or real fall-detection claim.

## Result

- Added `firmware/amoled_bridge/`.
- Added `quality_tests/test_amoled_bridge_firmware.py`.
- Flashed `egolink_amoled_bridge.bin` to the AMOLED board on `COM9`.
- Captured 43 JSONL records at
  `pc_simulator/runtime/hdb002-amoled-live-20260623-194454.jsonl`.
- Observed AXP2101 chip id `0x4A` and QMI8658 WHOAMI `0x05`.
- Captured 40 `imu_sample` records with `read_errors=0` and
  `not_ready_count=0`.
- PC Bridge stored 43 events with 0 skipped lines.
- Session recording produced 40 `imu_motion` sensor frames.
- Quality gate passed with `quality_score=0.94`.
- Replay passed with 40 replayed inputs, all `risk_type=none`.
- Evidence report:
  `docs/hardware/HDBRIDGE_002_AMOLED_QMI8658_LIVE_CAPTURE_20260623.md`.

## Done When

- [x] AMOLED firmware builds.
- [x] AMOLED board flashes over native USB Serial/JTAG.
- [x] USB serial JSONL includes `hello`.
- [x] QMI8658 WHOAMI returns expected `0x05`.
- [x] Bounded IMU sample window emits real I2C accel/gyro values.
- [x] PC Bridge ingests the JSONL without skipped lines.
- [x] Recorder emits `imu_motion` frames from the captured samples.
- [x] Quality gate passes without marking IMU as verified.
- [x] Replay passes from the resulting recording.
