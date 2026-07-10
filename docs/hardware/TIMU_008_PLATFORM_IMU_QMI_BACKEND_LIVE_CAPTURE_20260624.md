# TIMU-008 platform_imu QMI8658 Backend Live Capture

Date: 2026-06-24

Status: real QMI8658 backend live capture passed on the
ESP32-S3-Touch-AMOLED-2.06 board; formal IMU acceptance remains false.

## Summary

TIMU-008 exercised the opt-in `platform_imu` QMI8658 backend added in TIMU-007
on real hardware. The target was the ESP32-S3-Touch-AMOLED-2.06 board on
`COM9`, using the AMOLED-board QMI8658 pin map and AXP2101 power rail bring-up.

This task proves that the `firmware/mqtt_heartbeat` application can initialize
QMI8658 through `platform_imu`, emit bounded boot samples, and publish MQTT
`sensor_sample/device_health` payloads with:

- `imu_source=qmi8658_i2c`
- `imu_hardware_present=true`
- `imu_driver_enabled=true`
- `imu_sample_mock=false`

The default P0 product firmware path remains mock unless the QMI8658 backend is
explicitly selected through `sdkconfig.qmi8658.defaults`.

## Firmware Changes

- Added optional AXP2101 DC1/ALDO1 rail enable before QMI8658 probing.
- Added a bounded boot-time IMU capture window:
  `CONFIG_EGOLINK_PLATFORM_IMU_BOOT_SAMPLE_COUNT`.
- Updated `sdkconfig.qmi8658.defaults` to use an independent AMOLED test device
  identity and topic:
  `ego-link-amoled-qmi8658`.
- Kept the default `sdkconfig.defaults` mock backend unchanged.

## Live Hardware Evidence

UART capture:

- `pc_simulator/runtime/timu008/timu008-platform-imu-qmi-boot-window-uart.log`
- Captured lines: `313`
- Boot identity:
  - `device_id=ego-link-amoled-qmi8658`
  - `event_topic=ego/link/ego-link-amoled-qmi8658/event`
- Power and IMU probe:
  - `PLATFORM_IMU_AXP2101_RAILS_OK chip_id=0x4a`
  - `PLATFORM_IMU_QMI8658_PROBE_OK whoami=0x05 expected=0x05 revision=0x7c`
- Boot samples:
  - `PLATFORM_IMU_BOOT_CAPTURE_START count=40 interval_ms=50`
  - `40` lines of `PLATFORM_IMU_BOOT_CAPTURE_SAMPLE`
  - each boot sample used `source=qmi8658_i2c`, `hardware_present=true`,
    `driver_enabled=true`, `mock=false`
  - example stable sample: `accel_mg=52,7,-1030`,
    `gyro_mdps=62,1703,-187`
- Network:
  - `sta ip: 192.168.31.208`
  - `MQTT_HEARTBEAT_MQTT_CONNECTED broker=mqtt://192.168.31.250:1883`
- MQTT payload:
  - repeated `MQTT_SENSOR_PUBLISH_OK`
  - payloads included `imu_sample_mock=false` and QMI8658 accel/gyro fields.

PC-side MQTT event log:

- `pc_simulator/runtime/timu008/timu008-platform-imu-qmi-backend-live-20260624-0900.events.jsonl`
- Subscribed through the LAN broker `192.168.31.250:1883`.
- Captured `8` messages:
  - `4` `mqtt_status`
  - `4` `sensor_sample/device_health`
- All `sensor_sample` rows used `device_id=ego-link-amoled-qmi8658`,
  `imu_source=qmi8658_i2c`, `imu_hardware_present=true`,
  `imu_driver_enabled=true`, and `imu_sample_mock=false`.

M1 recording:

- `pc_simulator/runtime/recordings/timu008-platform-imu-qmi-backend-live-20260624-0900/`
- `session_recorder`: `8` source events, `8` sensor frames.
- `inspect_session_recording`: PASS, `quality_score=0.94`, `errors=0`,
  `warnings=2`.
- `replay_session_recording`: PASS, `8` replayed inputs, `8` outputs with
  `risk_type=none`, no `safety_event`, no `base_command`.

## Commands

Build:

```powershell
. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py -B build/timu008 -D SDKCONFIG=build/timu008/sdkconfig -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.qmi8658.defaults" build
```

Result: PASS. App binary size: `0xde6d0`.

Flash:

```powershell
. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py -B build/timu008 -D SDKCONFIG=build/timu008/sdkconfig -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.qmi8658.defaults" -p COM9 flash
```

Result: PASS on ESP32-S3 MAC `02:00:00:00:00:01`.

MQTT capture:

```powershell
python pc_simulator\mqtt_worker.py --host 192.168.31.250 --port 1883 --topic ego/link/ego-link-amoled-qmi8658/status --topic ego/link/ego-link-amoled-qmi8658/event --event-log pc_simulator\runtime\timu008\timu008-platform-imu-qmi-backend-live-20260624-0900.events.jsonl --max-messages 8 --wait-seconds 45
```

Result: PASS, stored `8` MQTT events.

Recording and replay:

```powershell
python scripts\session_recorder.py --event-log pc_simulator\runtime\timu008\timu008-platform-imu-qmi-backend-live-20260624-0900.events.jsonl --session-id timu008-platform-imu-qmi-backend-live-20260624-0900 --output-dir pc_simulator\runtime\recordings\timu008-platform-imu-qmi-backend-live-20260624-0900 --limit 50 --json
python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\timu008-platform-imu-qmi-backend-live-20260624-0900 --json
python scripts\replay_session_recording.py pc_simulator\runtime\recordings\timu008-platform-imu-qmi-backend-live-20260624-0900 --json
```

Result: PASS for recording, quality gate, and replay.

## Acceptance State

TIMU-008 closes the "real backend live capture" gap from TIMU-007.

Formal IMU acceptance is still false because these gates remain open:

- product mounting direction and final calibration
- FIFO/DRDY interrupt behavior
- low-power wake behavior
- current waveform and power-state impact
- backend long-window quality gate in the final product topology
- trainable dataset policy and labels

Distance to formal IMU acceptance is now roughly in the 75-80 percent range for
the engineering bring-up path. The largest remaining risk is no longer basic
QMI8658 readability; it is product integration: mounting, interrupts, power,
and final data-quality policy.
