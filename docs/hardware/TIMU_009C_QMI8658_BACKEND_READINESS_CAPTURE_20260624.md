# TIMU-009C-A QMI8658 Backend Readiness Capture

Date: 2026-06-24

## Purpose

TIMU-009C-A is a bounded hardware-readiness slice before formal product IMU
acceptance. It reuses the TIMU-008 opt-in QMI8658 `platform_imu` firmware
profile already running on the ESP32-S3-Touch-AMOLED-2.06 board, captures fresh
MQTT payloads from the live QMI8658 backend, and proves the payload still enters
the M1 recorder, quality gate, and replay loop.

This is not a formal product IMU acceptance. Product mounting, final
calibration, FIFO/DRDY interrupt behavior, low-power wake behavior, and
instrumented current waveform evidence remain pending.

## Hardware And Firmware Boundary

- Sensor node: ESP32-S3-Touch-AMOLED-2.06.
- IMU: board QMI8658 on the existing QMI backend path.
- Firmware profile: `firmware/mqtt_heartbeat` with
  `sdkconfig.defaults;sdkconfig.qmi8658.defaults` from TIMU-008.
- Device id: `ego-link-amoled-qmi8658`.
- MQTT broker: LAN broker `192.168.31.250:1883`.
- Firmware reflashed in this task: no.
- Capture method: bounded PC-side MQTT capture, not serial bridge capture.

## Command

```powershell
python pc_simulator\mqtt_worker.py --host 192.168.31.250 --port 1883 --topic ego/link/ego-link-amoled-qmi8658/status --topic ego/link/ego-link-amoled-qmi8658/event --event-log pc_simulator\runtime\timu009c\timu009c-qmi-backend-readiness-20260624-1710.events.jsonl --max-messages 8 --wait-seconds 45
```

Result: PASS, stored 8 MQTT events.

## Captured Data

Event log:

- `pc_simulator/runtime/timu009c/timu009c-qmi-backend-readiness-20260624-1710.events.jsonl`

Summary:

- 8 total MQTT events.
- 4 `sensor_sample/device_health` events.
- 4 `mqtt_status` events.
- `seq` range: `11062` through `11069`.
- Device id: `ego-link-amoled-qmi8658`.
- QMI backend metadata in all sensor samples:
  - `imu_source=qmi8658_i2c`
  - `imu_hardware_present=true`
  - `imu_driver_enabled=true`
  - `imu_sample_mock=false`

Real QMI8658 sample values observed in MQTT payloads:

| seq | accel mg x | accel mg y | accel mg z | gyro mdps x | gyro mdps y | gyro mdps z | dropped samples |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 11062 | 46 | -29 | -1027 | -218 | 1656 | -234 | 5539 |
| 11064 | 46 | -29 | -1027 | -203 | 1531 | -187 | 5540 |
| 11066 | 46 | -29 | -1028 | -218 | 1578 | -109 | 5541 |
| 11068 | 46 | -30 | -1026 | -187 | 1546 | -78 | 5542 |

Status payload boundary:

- `link_type=mock_4g_over_wifi`.
- `modem_state=mock_data_ready`.
- `gnss_state=mock_fix`.
- `battery=87`, `battery_source=mock`.
- `charging=false`, `charging_source=mock`.
- `power_serial_marker_id` advanced from `POWER_MARKER_044254` to
  `POWER_MARKER_044278`.
- RSSI range: `-52` to `-50`.

The IMU backend data is real for the QMI8658 path. The cellular/GNSS/battery
fields in this capture remain mock.

## M1 Closure

Recording command:

```powershell
python scripts\session_recorder.py --event-log pc_simulator\runtime\timu009c\timu009c-qmi-backend-readiness-20260624-1710.events.jsonl --session-id timu009c-qmi-backend-readiness-20260624-1710 --output-dir pc_simulator\runtime\recordings\timu009c-qmi-backend-readiness-20260624-1710 --limit 50 --json
```

Result:

- `source_events=8`.
- `sensor_frames=8`.
- `events=0`.
- `annotations=0`.

Quality gate:

```powershell
python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\timu009c-qmi-backend-readiness-20260624-1710 --json
```

Result: PASS, `quality_score=0.94`, `errors=0`, `warnings=2`.

Replay:

```powershell
python scripts\replay_session_recording.py pc_simulator\runtime\recordings\timu009c-qmi-backend-readiness-20260624-1710 --json
```

Result: PASS, 8 replayed inputs, 8 `risk_type=none` outputs, 0 safety events,
0 base commands.

## Acceptance Boundary

TIMU-009C-A confirms the current opt-in QMI8658 backend is still live and still
feeds M1. It does not close TIMU-009B product acceptance gates.

Still missing before formal IMU acceptance:

- Product mounting direction freeze.
- Six-face or equivalent final accel calibration in the intended mounting.
- Signed static gyro bias capture.
- Temperature drift characterization.
- FIFO/DRDY interrupt validation.
- Low-power wake validation.
- Instrumented current waveform aligned to `POWER_MARKER_<seq>`.
- Accepted backend quality report on the final product configuration.
- M1 recording and replay tied to accepted backend evidence.
- Recalibration trigger review after hardware/enclosure/fixture changes.

## Next Hardware Operation Needed

When ready, the operator should keep the AMOLED QMI8658 board connected and
place it in the intended product mounting orientation or a repeatable temporary
fixture. The next run should capture a final-orientation static window, then
continue into six-face/equivalent calibration and FIFO/DRDY/power evidence.
