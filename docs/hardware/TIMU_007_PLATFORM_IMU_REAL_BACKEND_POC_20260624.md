# TIMU-007 platform_imu Real Backend PoC Boundary

Date: 2026-06-24

## Summary

TIMU-007 adds a real-backend boundary to `platform_imu` without promoting the P0
4G main board to a verified IMU source.

The default `firmware/mqtt_heartbeat` configuration remains:

- backend: `mock`
- `imu_source=mock_stationary`
- `imu_hardware_present=false`
- `imu_driver_enabled=false`
- `imu_sample_mock=true`

An opt-in QMI8658 backend now exists behind
`CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_QMI8658`. It can initialize I2C, probe
QMI8658 WHOAMI, configure accel/gyro registers, read one accel/gyro sample, and
push that sample through the existing 32-sample IMU ring buffer. If probe or
read fails, the API falls back to mock data instead of silently claiming real
sensor availability.

## Changed Files

- `firmware/mqtt_heartbeat/components/platform_imu/include/platform_imu.h`
- `firmware/mqtt_heartbeat/components/platform_imu/platform_imu.c`
- `firmware/mqtt_heartbeat/components/platform_imu/Kconfig.projbuild`
- `firmware/mqtt_heartbeat/components/platform_imu/CMakeLists.txt`
- `firmware/mqtt_heartbeat/main/app_main.c`
- `firmware/mqtt_heartbeat/sdkconfig.defaults`
- `firmware/mqtt_heartbeat/sdkconfig.qmi8658.defaults`
- `firmware/mqtt_heartbeat/README.md`
- `quality_tests/test_platform_imu_firmware.py`

## Architecture Boundary

`app_main.c` now calls `platform_imu_sample()` rather than
`platform_imu_sample_mock()`. That keeps the application payload path stable
while the IMU component owns backend selection.

Backend selection is explicit:

- `CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_MOCK=y` is the default.
- `CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_QMI8658=y` is opt-in.
- QMI8658 defaults use the AMOLED bridge pin map: I2C port 0, SDA GPIO15,
  SCL GPIO14, address decimal `107` (`0x6B`), WHOAMI decimal `5` (`0x05`),
  and nominal sample interval 50 ms.

This boundary does not add AXP2101 rail management, board-to-board transport,
FIFO/DRDY interrupt handling, calibration, product mounting, or power
measurement. Those remain separate gates.

## Verification

```powershell
python -m unittest quality_tests.test_platform_imu_firmware -v
```

Result: PASS, 7 tests.

```powershell
. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py build
```

Result: PASS for `firmware/mqtt_heartbeat` default mock backend. App binary
size: `0xd9170`.

```powershell
. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py -B build/qmi -D SDKCONFIG=build/qmi/sdkconfig -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.qmi8658.defaults" build
```

Result: PASS for compile-only opt-in QMI8658 backend. App binary size:
`0xde340`. This was not flashed and does not validate live QMI8658 sampling.

Additional repository verification is tracked in `docs/current/STATUS.md`.

```powershell
python -m unittest quality_tests.test_platform_imu_firmware quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_hardware_sensor_matrix -v
```

Result: PASS, 15 tests.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1
```

Result: PASS, 158 tests.

## Acceptance State

Formal IMU acceptance remains false.

Reasons:

- The P0 4G main board still has no verified onboard IMU.
- The AMOLED-board QMI8658 evidence is still bridge evidence unless a later
  task explicitly builds, flashes, captures, and accepts the `platform_imu`
  QMI8658 backend.
- Product mounting, calibration, FIFO/interrupt, wake behavior, and power
  impact are still unverified.

## Recommended Next Task

TIMU-008 should perform an explicit real-backend live capture if we decide to
exercise this backend on hardware. That task should select the target board,
set `CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_QMI8658=y`, build and flash the
firmware, capture payloads showing `imu_sample_mock=false`, and then run the M1
recording, quality gate, and replay checks without changing formal acceptance
until mounting/power/FIFO gates are closed.
