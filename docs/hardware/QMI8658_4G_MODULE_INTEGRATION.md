---
document_status: operator_guide
last_verified: 2026-07-11
verified_by: codex
---

# QMI8658 Module On The 4G Board

> Status: integration plan. This is not live hardware evidence.

## Purpose

Move IMU sensing onto `connectivity-node-001` so a locator-only pilot unit can
use the 4G board, one 18650 cell, an external QMI8658 module, and an enclosure
without carrying the AMOLED development board.

Removing the AMOLED board also removes its screen and touch interaction. A
pilot that needs local SOS or confirmation must retain a display or add a
separate button, LED, buzzer, or other reviewed interaction path.

## Module Selection

Buy two or three I2C QMI8658 breakout modules with:

- documented 3.3 V power and logic compatibility;
- exposed `VCC`, `GND`, `SDA`, `SCL`, and preferably `INT`;
- documented or configurable I2C address (`0x6A` or `0x6B`);
- mounting holes or a rigid way to freeze sensor orientation;
- local decoupling and a schematic from the module vendor.

The QMI8658 device itself accepts 1.71-3.6 V supplies and supports I2C, I3C,
SPI, and a FIFO. A breakout may add a regulator or pull-ups, so the purchased
module schematic remains authoritative.

## Wiring And Firmware Boundary

- Confirm the physical 4G board revision before choosing I2C pins. Current
  Waveshare documentation lists MAX17048 pins as V2 SDA GPIO15/SCL GPIO16 and
  V1 SDA GPIO3/SCL GPIO2.
- Put QMI8658 and MAX17048 on the same I2C bus only when both firmware backends
  use the same port, SDA, SCL, and bus frequency. Their addresses do not
  conflict: MAX17048 is `0x36`; QMI8658 is normally `0x6A` or `0x6B`.
- Confirm the purchased module address with a bounded I2C probe before flash.
- Enable `CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_QMI8658` and set its I2C address
  and pins explicitly.
- Disable `CONFIG_EGOLINK_PLATFORM_IMU_QMI8658_AXP2101_RAILS`; that switch is
  only for the AMOLED-board power path.
- Acceptance requires QMI8658 WHOAMI `0x05`, real non-mock samples, source
  status `observed`, fixed mounting orientation, and a named evidence path.

Do not flash until the module is physically connected, polarity and voltage
are checked, the board revision is recorded, and the operator explicitly
starts the hardware task.

## Prepared Build Profile

`scripts/prepare_fw001_hw_config.ps1` now accepts
`-EnableQmi8658Imu`, explicit QMI I2C pins/address, sample interval, and a
bounded boot sample count. When MAX17048 and QMI8658 are enabled together the
generator rejects different I2C port/SDA/SCL settings. It always disables
`EGOLINK_PLATFORM_IMU_QMI8658_AXP2101_RAILS` for this external-module path.

Example for the documented V2 pin map and a module confirmed at `0x6B`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\prepare_fw001_hw_config.ps1 `
  -HostName <message-hub-host> `
  -TokenFile <local-token-file> `
  -ConfigPath firmware\mqtt_heartbeat\sdkconfig.qmi-4g.local `
  -TestRunId QMI-4G-YYYYMMDD-001 `
  -EnableSim7670Gnss -EnableSim7670LocationObservation `
  -EnableD1PeriodicLocation -EnableMax17048Power -EnableQmi8658Imu `
  -Qmi8658I2CAddress 107 -Qmi8658BootSampleCount 100 -Build -Json
```

Change the address to decimal `106` only after confirming `0x6A`. Use GPIO3/2
only after recording a V1 board. A 2026-07-11 no-flash profile compiled with
QMI8658, MAX17048, GNSS, LTE, and periodic location enabled; this is static
evidence only and does not prove the external module or shared bus works.

The current LTE field corpus contains IMU source metadata but no uploaded
six-axis windows. The existing 30-second sensor-status cadence is not a model
training cadence. After module probe, use the readiness report to decide the
smallest bounded high-rate capture mode instead of enabling a permanent
always-on stream.

## Pilot Readiness Sequence

1. Bench probe and sample the external module on the 4G board.
2. Freeze mounting axes and collect static plus walking/vehicle labelled runs.
3. Run LTE/GNSS/QMI/MAX17048 together and check bus, reset, and upload health.
4. Run the 24-hour battery baseline with the final sensor cadence.
5. Print an enclosure that prevents battery movement, antenna obstruction,
   pin shorts, and IMU orientation changes.
6. Start a consented small pilot with device IDs, retention limits, deletion
   handling, and explicit `training_allowed` review.

## References

- Waveshare board documentation: https://docs.waveshare.com/ESP32-S3-SIM7670G-4G
- QST QMI8658 product page: https://www.qstcorp.com/en_imu_prod/QMI8658
- QST QMI8658C datasheet: https://qstcorp.com/upload/pdf/202202/QMI8658C%20datasheet%20rev%200.9.pdf
