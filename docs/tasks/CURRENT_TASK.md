# CURRENT_TASK: TIMU-008 / platform_imu QMI8658 Backend Live Capture

## Goal

Exercise the opt-in `platform_imu` QMI8658 backend on the
ESP32-S3-Touch-AMOLED-2.06 board and capture live evidence that the firmware can
publish non-mock IMU metadata through the existing MQTT/M1 path.

## Scope

- Keep the P0 Waveshare ESP32-S3-SIM7670G-4G firmware default on mock IMU data.
- Use `sdkconfig.qmi8658.defaults` as an explicit, separate live-capture profile.
- Enable the AMOLED-board AXP2101 rails before QMI8658 probe.
- Add a bounded boot-time serial sample window for hardware bring-up.
- Use an independent device id and MQTT topic for AMOLED QMI evidence:
  `ego-link-amoled-qmi8658`.
- Capture UART evidence, MQTT event-log evidence, M1 recording, quality gate,
  and replay.

## Out Of Scope

- No formal IMU acceptance.
- No MotionNet training data claim.
- No product mounting, final calibration, FIFO/DRDY interrupt, wake, or power
  acceptance.
- No microphone, TF/SD, touch/display, battery, fuel-gauge, or SIM7670G power
  control work.
- No change to the default P0 mock IMU firmware path.

## Result

- Added optional AXP2101 rail bring-up behind
  `CONFIG_EGOLINK_PLATFORM_IMU_QMI8658_AXP2101_RAILS`.
- Added boot-capture Kconfig knobs:
  `CONFIG_EGOLINK_PLATFORM_IMU_BOOT_SAMPLE_COUNT` and
  `CONFIG_EGOLINK_PLATFORM_IMU_BOOT_SAMPLE_INTERVAL_MS`.
- Updated `sdkconfig.qmi8658.defaults` with independent device id/topic and a
  40-sample, 50 ms boot capture window.
- Built and flashed the QMI8658 backend profile to `COM9`.
- Captured UART evidence with AXP2101 chip id `0x4a`, QMI8658 WHOAMI `0x05`,
  40 boot samples, and MQTT payloads containing `imu_sample_mock=false`.
- Captured PC-side MQTT evidence: 8 messages, including 4
  `sensor_sample/device_health` rows with `imu_source=qmi8658_i2c`,
  `imu_hardware_present=true`, `imu_driver_enabled=true`, and
  `imu_sample_mock=false`.
- Generated an M1 recording, passed quality gate `0.94`, and replayed 8 inputs
  with `risk_type=none`.

## Done When

- [x] Default config remains mock.
- [x] QMI8658 live profile uses an independent device id and topic.
- [x] AXP2101 rail enable and QMI8658 probe pass on hardware.
- [x] Boot capture emits real QMI8658 samples with `mock=false`.
- [x] MQTT payloads carry QMI8658 IMU fields with `imu_sample_mock=false`.
- [x] PC-side MQTT worker records the live samples from the LAN broker.
- [x] M1 session recorder, quality gate, and replay pass.
- [x] TIMU-008 report and sensor matrix references are updated.

Formal IMU acceptance remains false while product mounting, calibration,
FIFO/DRDY interrupt behavior, low-power wake, current waveform, and final
backend quality gates remain open.
