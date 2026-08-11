---
document_status: operator_guide
last_verified: 2026-08-11
verified_by: codex
---

# QMI8658 Module On The 4G Board

> Status: module identity and bounded real sampling are observed on the 4G
> board. D2-007 also passed startup identity and idle-stop checks, but its first
> LTE-window attempt stopped before capture because the SIM was not ready.
> D2-008 then observed a low-rate real six-axis Wi-Fi uplink. The operator
> reports the module is fixed. D2-009 then passed one bounded 100 x 50 ms
> real-QMI window and explicit export over Wi-Fi. D5-002 subsequently passed
> three independently commanded windows in one boot, exported all three, and
> bound them to one operator-confirmed flat-on-table stationary session. Axis
> mapping, calibration, labels for other activities or poses, mechanical
> retention, LTE window transport, and product acceptance remain pending.
> FIELD-011 later passed the joint image's QMI identity/idle-stop startup gate,
> but its inserted-SIM attempt still stopped before capture because LTE
> registration and PDP readiness were not established.

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
  V1 SDA GPIO3/SCL GPIO2. The active board has no visible `VER2.0` silkscreen,
  so its revision remains unknown; D2-006 nevertheless observed this external
  module operating on GPIO15/GPIO16.
- Put QMI8658 and MAX17048 on the same I2C bus only when both firmware backends
  use the same port, SDA, SCL, and bus frequency. Their addresses do not
  conflict: MAX17048 is `0x36`; QMI8658 is normally `0x6A` or `0x6B`.
- Confirm the purchased module address with a bounded I2C probe before flash.
- Enable `CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_QMI8658` and set its I2C address
  and pins explicitly.
- Disable `CONFIG_EGOLINK_PLATFORM_IMU_QMI8658_AXP2101_RAILS`; that switch is
  only for the AMOLED-board power path.
- Identity/data-path acceptance requires QMI8658 WHOAMI `0x05`, real non-mock
  samples, and a named evidence path. Dataset use additionally requires source
  status `observed`, fixed mounting orientation, calibration review, and a
  bounded capture contract.

Do not flash until the module is physically connected, polarity and voltage
are checked, the board revision is recorded, and the operator explicitly
starts the hardware task.

## Prepared Build Profile

`scripts/prepare_fw001_hw_config.ps1` now accepts
`-EnableQmi8658Imu`, explicit QMI I2C pins/address, sample interval, and a
bounded boot sample count. When MAX17048 and QMI8658 are enabled together the
generator rejects different I2C port/SDA/SCL settings. It always disables
`EGOLINK_PLATFORM_IMU_QMI8658_AXP2101_RAILS` for this external-module path.
`-EnableWifiImuWindowCommand` selects the dedicated bounded raw-command
profile, rejects simultaneous SIM7670 modes, and does not start periodic
heartbeat or single-sample telemetry tasks.

Example for the GPIO15/GPIO16 path and the installed module confirmed at
`0x6A` by D2-006:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\prepare_fw001_hw_config.ps1 `
  -HostName <message-hub-host> `
  -TokenFile <local-token-file> `
  -ConfigPath firmware\mqtt_heartbeat\sdkconfig.qmi-4g.local `
  -TestRunId QMI-4G-YYYYMMDD-001 `
  -EnableSim7670Gnss -EnableSim7670LocationObservation `
  -EnableD1PeriodicLocation -EnableMax17048Power -EnableQmi8658Imu `
  -Qmi8658I2CAddress 106 -Qmi8658BootSampleCount 100 -Build -Json
```

Use GPIO3/2 only after recording a V1 board. A 2026-07-11 no-flash profile
compiled with QMI8658, MAX17048, GNSS, LTE, and periodic location enabled;
this remains static evidence only and does not prove the shared bus works.

The 2026-08-10 D2-006 bench probe tested both candidate addresses. `0x6B`
failed at reset and fell back to mock. `0x6A` returned WHOAMI `0x05`, reset
result `0x80`, and 100/100 real non-mock samples with no sample failure. The
observed boot-record interval was 70 ms, not the configured 50 ms delay, so
this path is not yet a 20 Hz sampling claim. Evidence:
`reports/board_validation/20260810-qmi8658-probe/qmi8658_probe_report.md`.

The 2026-08-10 D2-007 combined image was then deployed and flashed once. Its
20-second startup log again observed `WHO_AM_I=0x05` and readback-confirmed
that the measurement engine was stopped. The single bounded command was never
polled or executed because SIM7670 reported `LTE_SIM_NOT_READY`, registration
`not_registered`, and PDP `unknown` through the 120-second readiness gate. The
server received zero raw frames, the exporter produced zero windows, and the
command was safely timed out without a device ACK. This is not an uplink or
20 Hz cadence pass. Evidence:
`reports/board_validation/20260810-d2007-imu-lte/d2_007_hardware_report.md`.

The 2026-08-11 D2-008 smoke reused the existing Wi-Fi JSON telemetry path with
no firmware-source, server, schema, or protocol change. Its test run retained
26/26 real non-mock QMI8658 `sensor_sample` messages and 26 distinct six-axis
tuples. The nominal event period was five seconds, and the app was then stopped
in ROM download mode. This proves the first real sensor-to-VPS data slice, not
a high-rate window or training dataset. Evidence:
`reports/board_validation/20260811-d2008-wifi-imu/d2_008_wifi_imu_report.md`.

The 2026-08-11 D2-009 run reused the D2-007 bounded window contract through a
dedicated Wi-Fi raw-command profile. Command `wifi-imu-001` captured 100/100
real samples after ten warm-ups, reported zero read failures, mock samples, or
deadline misses, stopped measurement before upload, and retained ten chunks,
one manifest, and one matching ACK. The explicit export reconstructed one
complete window with observed intervals 49749/49999/50292 us
minimum/mean/maximum and engineering cadence `qualified`; training remains
disabled. Evidence:
`reports/board_validation/20260811-d2009-wifi-imu-window/d2_009_wifi_imu_window_report.md`.

The 2026-08-11 D5-002 run flashed `v0.1.0-27-gab218af` and used the same
bounded contract with a three-success command limit. Commands `d5002-s1` to
`d5002-s3` produced 300 real samples, 30 chunks, three manifests, and three
matching `ok` ACKs with zero read failures, mock substitutions, or deadline
misses. A single read-only export reconstructed three valid cadence-qualified
windows and zero invalid windows. The planned bench action was stationary,
and the operator subsequently confirmed that the board remained flat and
stationary on the table for all three windows. A separate sidecar binds that
observation one-to-one to the three window/sample hashes; the resulting
one-session labelled seed remains split `unassigned`,
`training_allowed=false`, and `training_ready=false`. Evidence:
`reports/board_validation/20260811-d5002-imu-seed/d5_002_hardware_report.md`.

The 2026-08-11 FIELD-011 joint image then enabled QMI8658, SIM7670G LTE raw
commands, GNSS, location observation, and 60-second periodic location in one
existing-code profile. Its one COM3 flash and 20-second startup gate passed
QMI identity (`WHO_AM_I=0x05`, revision `0x7c`, reset result `0x80`) and
readback-confirmed idle stop. With a SIM inserted, the AT channel was
reachable, but the readiness loop ended with registration `not_registered`,
PDP `unknown`, and `ready=false`. Command `f011-bench-1` remained pending;
there was no capture start, sample, chunk, manifest, GNSS event, LTE upload, or
ACK. The read-only API export contained zero messages and zero raw frames.
This preserves the QMI startup evidence but does not advance LTE-window or
joint field acceptance. Evidence:
`reports/field_validation/FIELD-011-20260811-001/field011_bench_report.md`.

The engineering corpus therefore contains four uploaded bounded high-cadence
Wi-Fi windows across D2-009 and D5-002, including three operator-confirmed
stationary windows in one session. Next data work must freeze axes/calibration
and add independent stationary, walking, and vehicle sessions while training
remains disabled until consent, retention, quality, data-volume, and split
gates are explicitly satisfied. Do not turn this bench profile into a
permanent always-on stream.

## Pilot Readiness Sequence

1. Bench probe and sample the external module on the 4G board. D2-006 passed
   this identity/data-path step at address `0x6A`; formal mounting and
   calibration remain pending.
2. Freeze mounting axes and expand independent stationary, walking, and
   vehicle labelled runs.
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
