# T039 IMU Mock Live Capture - 2026-06-23

## Scope

This report records the bounded live capture performed after adding the
T039 `platform_imu` mock/ring interface to `firmware/mqtt_heartbeat`.

The capture proves that the current ESP32-S3 firmware can publish IMU-shaped
mock metadata through `sensor_sample/device_health` and that the M1 PC-side
recording, quality gate, and replay loop can ingest it.

It does not prove that a real IMU is present, wired, oriented, sampled,
calibrated, interrupt-driven, or power-managed.

## Runtime Fix

The first T039 flash produced repeated `mqtt_status seq=2` messages and no
sensor samples. A board probe with ESP32 serial capture showed:

```text
PLATFORM_IMU_SAMPLE seq=1 source=mock_stationary mock=true
***ERROR*** A stack overflow in task sensor_task has been detected.
```

The fix was to keep the 1536-byte sensor JSON buffer out of the FreeRTOS task
stack and raise the `sensor_task` stack:

- `publish_sensor_sample`: `static char payload[1536];`
- `xTaskCreate(sensor_task, "sensor_task", 6144, NULL, 5, NULL)`

## Commands

```powershell
python -m unittest quality_tests.test_platform_imu_firmware quality_tests.test_platform_power_firmware quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_safety_model_firmware -v
. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py -p COM4 flash
python pc_simulator\mqtt_worker.py --host 192.168.31.250 --port 1883 --event-log pc_simulator\runtime\hdata-001-imu-mock-live-20260623-0926-events.jsonl --max-messages 10 --wait-seconds 180 --process-safety --safety-process-limit 20
python scripts\session_recorder.py --event-log pc_simulator\runtime\hdata-001-imu-mock-live-20260623-0926-events.jsonl --session-id hdata-001-imu-mock-live-20260623-0926 --output-dir pc_simulator\runtime\recordings\hdata-001-imu-mock-live-20260623-0926 --json
python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\hdata-001-imu-mock-live-20260623-0926 --json
python scripts\replay_session_recording.py pc_simulator\runtime\recordings\hdata-001-imu-mock-live-20260623-0926 --json
```

## Evidence Paths

- Initial stack-overflow probe: `reports/board_validation/20260623-092315/probe.md`
- Clean event log: `pc_simulator/runtime/hdata-001-imu-mock-live-20260623-0926-events.jsonl`
- Clean recording: `pc_simulator/runtime/recordings/hdata-001-imu-mock-live-20260623-0926/`
- Quality report: `pc_simulator/runtime/recordings/hdata-001-imu-mock-live-20260623-0926/session_quality_report.md`
- Replay report: `pc_simulator/runtime/recordings/hdata-001-imu-mock-live-20260623-0926/session_replay_report.md`

## Clean MQTT Samples

The clean event log contains 10 live device MQTT messages:

- 7 `mqtt_status` messages.
- 3 `sensor_sample/device_health` messages.

The live `device_health` samples contained ESP32 runtime fields, HPWR marker
fields, and explicit IMU mock/ring metadata:

| Seq | Uptime | RSSI | Heap | Power Marker | IMU Source | Ring | Accel mg | Gyro mdps |
|---:|---|---:|---:|---|---|---:|---|---|
| 13 | `uptime_ms:93452` | -47 | 254896 | `POWER_MARKER_000054` | `mock_stationary` | 4/32 | `(2,-2,1002)` | `(0,0,0)` |
| 17 | `uptime_ms:123702` | -46 | 254960 | `POWER_MARKER_000070` | `mock_stationary` | 5/32 | `(-2,2,998)` | `(0,0,0)` |
| 21 | `uptime_ms:153952` | -34 | 254924 | `POWER_MARKER_000086` | `mock_stationary` | 6/32 | `(-1,1,999)` | `(0,0,0)` |

All three samples explicitly reported:

- `imu_hardware_present=false`
- `imu_driver_enabled=false`
- `imu_sample_mock=true`
- `battery_source=mock`
- `power_gpio_marker_enabled=false`

## Recording Result

The clean recording produced:

- Source events: 13
- Sensor frames: 10
- Events: 3
- Frame types: `device_health=3`, `device_status=7`
- Quality gate: PASS, `quality_score=0.94`, `errors=0`, `warnings=2`
- Replay: PASS, `replayed_inputs=10`, `risk_types.none=10`,
  `safety_events=0`, `base_commands=0`

Expected warnings remain:

- `firmware_version_unknown`
- `annotations_empty`

## Boundaries

- IMU values are mock stationary samples from `platform_imu`, not real IMU data.
- `battery=87` and `charging=false` are still mock fields.
- GPIO power marker output is still disabled; only serial/payload marker IDs are available.
- This capture did not exercise GNSS, camera, microphone, SD storage, true battery telemetry, or ESP32-side SIM7670G control.
