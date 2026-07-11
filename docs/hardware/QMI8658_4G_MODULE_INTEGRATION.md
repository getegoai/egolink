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

