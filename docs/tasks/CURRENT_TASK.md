# CURRENT_TASK: TIMU-009C-B1 / QMI8658 Temporary Fixture Static Capture

## Goal

Capture the first hardware-observed IMU data after the AMOLED/QMI8658 board was
fixed to a repeatable temporary fixture, then record it as partial mounting
evidence without weakening the formal TIMU-009B/TIMU-009C acceptance gates.

## Scope

- Use the existing ESP32-S3-Touch-AMOLED-2.06 `firmware/mqtt_heartbeat`
  QMI8658 backend profile already running on the board.
- Capture bounded MQTT status/event traffic through the LAN broker.
- Summarize static accel/gyro stability for the paper-box temporary fixture.
- Generate an evidence manifest and preflight report using the existing
  TIMU-009B/TIMU-009C gate semantics.
- Derive an M1 recording, run quality inspection, and replay the recording.
- Update status, matrix, integration, and current-task documentation.

Out of scope: final product enclosure acceptance, six-face or equivalent final
calibration, FIFO/DRDY interrupt validation, current waveform measurement,
low-power wake, microphone/TF/touch validation, MotionNet training, and formal
IMU product acceptance.

## Result

- User fixed the AMOLED/QMI8658 board to a paper box with double-sided tape.
- Captured `16` MQTT events from `ego-link-amoled-qmi8658`:
  - `8` QMI8658 `sensor_sample/device_health` events.
  - `8` `mqtt_status` events.
  - Sequence range `11728..11743`.
  - `imu_source=qmi8658_i2c`.
  - `imu_sample_mock=false`.
- Static accel magnitude was stable:
  - mean `1024.98 mg`;
  - min `1024.40 mg`;
  - max `1025.58 mg`;
  - span `1.18 mg`.
- Main gravity direction for this temporary fixture was negative Z:
  - accel mean `[25.38, 92.25, -1020.50] mg`.
- M1 closure passed:
  - recording produced `16` sensor frames;
  - quality gate PASS, `quality_score=0.94`, `errors=0`, `warnings=2`;
  - replay PASS, `16` outputs all `risk_type=none`.
- Generated:
  - `docs/hardware/TIMU_009C_B1_QMI8658_TEMPORARY_FIXTURE_STATIC_CAPTURE_20260624.md`
  - `docs/hardware/TIMU_009C_B1_QMI8658_TEMPORARY_FIXTURE_EVIDENCE_20260624.json`
  - `docs/hardware/TIMU_009C_B1_QMI8658_TEMPORARY_FIXTURE_PREFLIGHT_20260624.json`
  - `docs/hardware/TIMU_009C_B1_QMI8658_TEMPORARY_FIXTURE_PREFLIGHT_20260624.md`

## Boundary

- This is hardware-observed partial evidence for a repeatable temporary fixture.
- It is not final product mounting evidence because the target enclosure and
  wearable orientation are not frozen.
- The preflight remains expected FAIL:
  - partial gates do not pass formal acceptance;
  - six-face/equivalent accel calibration is pending;
  - signed production gyro bias is pending;
  - temperature drift is pending;
  - FIFO/DRDY is pending;
  - power current waveform is pending;
  - TIMU-009A calibration profile is still `stage=engineering`.
- `formal_imu_acceptance=false`.
- `motionnet_training_enabled=false`.

## Done When

- [x] Bounded live MQTT data captured from the QMI8658 backend.
- [x] Static accel/gyro summary written.
- [x] Evidence manifest records temporary fixture gates as partial or pending.
- [x] Preflight report preserves formal acceptance failure.
- [x] M1 recording, quality gate, and replay pass for the temporary fixture data.
- [x] Status, matrix, integration report, and task record are updated.

Next hardware step: keep the board on the paper-box fixture, add visible
orientation labels such as `TOP`, `OUT`, and `USB/CABLE`, then capture the next
static/calibration window from the same repeatable orientation.
