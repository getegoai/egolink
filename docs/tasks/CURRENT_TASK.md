# CURRENT_TASK: TIMU-009C-A / QMI8658 Backend Readiness Capture

## Goal

Capture a fresh bounded live data slice from the current QMI8658
`platform_imu` backend and prove it still enters the M1 recorder, quality gate,
and replay loop, while keeping product IMU acceptance explicitly false.

## Scope

- Reuse the TIMU-008 QMI8658 MQTT backend profile already running on the
  ESP32-S3-Touch-AMOLED-2.06 board.
- Capture a finite MQTT window from the LAN broker.
- Record the raw accel/gyro values observed in the QMI8658 payloads.
- Convert the event log into an M1 recording.
- Run session quality gate and replay.
- Update status, matrix, and integration documentation.
- Keep product mounting, final calibration, FIFO/DRDY implementation,
  PPK2/Otii measurement, and MotionNet training out of scope for this run.

## Result

- Added `docs/hardware/TIMU_009C_QMI8658_BACKEND_READINESS_CAPTURE_20260624.md`.
- Captured:
  - `pc_simulator/runtime/timu009c/timu009c-qmi-backend-readiness-20260624-1710.events.jsonl`
  - 8 MQTT events total
  - 4 `sensor_sample/device_health` events
  - 4 `mqtt_status` events
  - `seq=11062..11069`
- Observed real IMU backend metadata:
  - `imu_source=qmi8658_i2c`
  - `imu_hardware_present=true`
  - `imu_driver_enabled=true`
  - `imu_sample_mock=false`
- M1 closure:
  - recording generated 8 sensor frames
  - quality gate PASS, `quality_score=0.94`
  - replay PASS, 8 `risk_type=none` outputs

## Boundary

- Real in this task: QMI8658 backend accel/gyro values over MQTT.
- Still mock in this task: 4G data path, GNSS, battery, charging.
- Still not accepted: product-mounted IMU, production calibration, FIFO/DRDY,
  low-power wake, and instrumented current waveform.

## Done When

- [x] Fresh QMI8658 MQTT data is captured with bounded timeout.
- [x] Raw accel/gyro samples are recorded in a durable hardware report.
- [x] M1 recording is generated from the capture.
- [x] Session quality gate passes.
- [x] Replay passes.
- [x] Status, matrix, and integration report are updated.

Formal IMU acceptance remains false. The next hardware step needs the operator
to place the AMOLED QMI8658 board in the intended product orientation or a
repeatable fixture so final mounting/calibration evidence can be captured.
