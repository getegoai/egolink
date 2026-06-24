# CURRENT_TASK: TIMU-007 / platform_imu QMI8658 Backend Boundary

## Goal

Move `firmware/mqtt_heartbeat/components/platform_imu` from a mock-only
skeleton to a backend boundary that can dispatch through a default mock backend
or an explicitly configured QMI8658 I2C backend.

## Scope

- Keep the P0 Waveshare ESP32-S3-SIM7670G-4G firmware default on mock IMU data.
- Add a `platform_imu_sample()` backend-neutral API and make `app_main.c` call
  that API instead of `platform_imu_sample_mock()`.
- Add ESP-IDF Kconfig selection for `mock` versus `qmi8658`.
- Add an opt-in QMI8658 defaults file for compile-only validation without
  changing the default P0 firmware configuration.
- Add a minimal QMI8658 I2C probe/read path behind
  `CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_QMI8658`.
- Preserve `imu_hardware_present=false`, `imu_driver_enabled=false`, and
  `imu_sample_mock=true` in the default firmware path.
- Document that the AMOLED-board QMI8658 evidence remains bridge evidence until
  a separate real-backend live capture is flashed and accepted.

## Out Of Scope

- No default source promotion to `imu_hardware_present=true`.
- No product IMU mounting, calibration, FIFO, interrupt, wake, or power
  acceptance.
- No MotionNet training data claim.
- No board-to-board UART transport.
- No microphone, TF/SD, touch/display, battery, fuel-gauge, or SIM7670G power
  control work.

## Result

- Added `platform_imu_backend_t`, backend metadata fields, and
  `platform_imu_sample()`.
- Added `firmware/mqtt_heartbeat/components/platform_imu/Kconfig.projbuild`.
- Added opt-in QMI8658 I2C constants, WHOAMI probe, accel/gyro conversion, and
  read-sample path behind `CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_QMI8658`.
- Updated `firmware/mqtt_heartbeat/sdkconfig.defaults` with
  `CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_MOCK=y`.
- Added `firmware/mqtt_heartbeat/sdkconfig.qmi8658.defaults` for opt-in
  QMI8658 compile validation.
- Updated `firmware/mqtt_heartbeat/main/app_main.c` so sensor publishing calls
  the backend-neutral `platform_imu_sample()`.
- Updated firmware static tests and README boundary text.
- Default `firmware/mqtt_heartbeat` ESP-IDF build passed with mock backend.

## Done When

- [x] Default config remains mock.
- [x] Business firmware no longer directly calls `platform_imu_sample_mock()`.
- [x] QMI8658 code is opt-in behind Kconfig.
- [x] Static firmware tests cover the backend boundary.
- [x] Default `mqtt_heartbeat` firmware build passes.
- [x] Opt-in QMI8658 backend build passes without flashing.
- [x] Full repository verification passes.
- [x] TIMU-007 report and sensor matrix references are updated.

Formal IMU acceptance remains false while the source is not a product-mounted,
calibrated, FIFO/interrupt/power-validated real backend capture.
