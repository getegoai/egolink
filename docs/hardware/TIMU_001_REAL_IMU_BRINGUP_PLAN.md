# TIMU-001 Real IMU Bring-Up Plan

> Date: 2026-06-23  
> Status: planning and evidence gate only  
> Target scope: real accelerometer/gyroscope data for M1, without changing the
> current `platform_imu` mock backend yet

## Current Conclusion

The current Waveshare ESP32-S3-SIM7670G-4G P0 board has no repo-backed evidence
of a real IMU that is already present, wired, sampled, oriented, calibrated, or
power-managed.

The current firmware can publish IMU-shaped mock metadata through
`platform_imu`, and T039-live proved that the mock payload reaches MQTT,
recording, quality gate, and replay. That is useful for the M1 data shape, but
it is not real motion data.

## Evidence Reviewed

| Source | Finding | Boundary |
|---|---|---|
| `docs/modeling/HARDWARE_SENSOR_MATRIX.md` | Real IMU remains `missing_or_unknown`; T039 `platform_imu` is `mock_only`. | Matrix supports continuing development, not a real IMU claim. |
| `docs/hardware/PLATFORM_COUPLING_AUDIT.md` | HARCH-001 listed IMU as no confirmed part, bus, pins, mounting direction, driver, samples, or ring buffer at audit time. | T039 added the ring/mock boundary, but not hardware. |
| `docs/hardware/T039_IMU_MOCK_LIVE_CAPTURE_20260623.md` | Live MQTT samples contained `imu_source=mock_stationary`, `imu_hardware_present=false`, `imu_driver_enabled=false`, `imu_sample_mock=true`. | Live pipeline works; real IMU remains unverified. |
| `docs/hardware/HARDWARE_EVALUATION_AND_PROCUREMENT_PLAN.md` | First-batch procurement includes a wearable multisensor node or low-power six-axis IMU board. | Procurement intent is not arrival or wiring evidence. |
| `docs/hardware/EGOLINK_硬件开发采购清单_v1.xlsx` | Sheet entries include `ST STEVAL-MKI227KA（LSM6DSV16X）` for IMU evaluation and `SensorTile.box PRO` as an early real-data option. | Candidate hardware only; no checked-in arrival, wiring, or capture report. |

## Candidate Path

Preferred first real-data path:

1. Use a standalone IMU evaluation board before assuming any board-integrated
   IMU exists.
2. Start with the procurement candidate `ST STEVAL-MKI227KA（LSM6DSV16X）` or
   `SensorTile.box PRO` if already available and easier for immediate capture.
3. Treat the candidate as a bring-up target, not a frozen product part.
4. Keep `platform_imu` mock as the default firmware backend until hardware
   probe and live capture pass.

## Bring-Up Inputs Required

Before writing a real driver, record these facts in a follow-up report:

| Required fact | Why it matters |
|---|---|
| Exact IMU board and sensor part number | Prevents guessing register maps and WHOAMI values. |
| Datasheet and evaluation-board schematic/source URL or local copy | Required for bus, power, interrupt, and orientation decisions. |
| Bus choice: I2C or SPI | Determines ESP-IDF driver, pullups, CS handling, throughput, and timing. |
| ESP32-S3 pins for SCL/SDA or SCLK/MOSI/MISO/CS | Needed before any firmware pin config. |
| INT1/INT2 pins, if wired | Required for data-ready, FIFO watermark, wake, and power tests. |
| IO voltage and pullups | Avoids damaging modules and explains bus failures. |
| Physical mounting orientation | Required before accel/gyro axes can be used by MotionNet. |
| Target ODR and full-scale ranges | Required for comparable data windows. |
| FIFO/data-ready strategy | Required for sample-rate and missing-frame accounting. |
| Power mode and measurement plan | Required before using IMU in battery-life estimates. |

## Firmware PoC Acceptance

A later TIMU firmware PoC may set `imu_hardware_present=true` only after all
of the following are true:

- The real backend is explicitly selected; mock remains available for tests.
- The selected bus initializes with known pins and voltage assumptions.
- The sensor answers a documented identity or WHOAMI check.
- At least one bounded sample window is read without crashing the firmware.
- Each sample has monotonic timestamp, accel, gyro, sequence, and source.
- Ring-buffer count, overflow/dropped samples, and readout path are visible.
- `imu_sample_mock=false` appears in live MQTT only for the real backend.
- Firmware logs distinguish probe failure, bus failure, and read failure.
- The build and focused firmware tests pass.

## Live Data Acceptance

A later real IMU capture may be marked M1-usable only after it produces a clean
recording with:

| Gate | Minimum result |
|---|---|
| Static orientation sample | Stationary board shows plausible 1 g axis after orientation mapping. |
| Motion sanity sample | Manual rotation or tap produces a visible accel/gyro change. |
| Sample-rate report | Target ODR, observed rate, jitter, and missing-frame count recorded. |
| Ring-buffer report | Capacity, count, and dropped-sample count recorded. |
| MQTT payload | `imu_hardware_present=true`, `imu_driver_enabled=true`, `imu_sample_mock=false`, real source name. |
| Quality gate | Session quality PASS with source marked real only for the verified IMU fields. |
| Replay | Replay PASS and no automatic fall/impact safety claim unless a rule explicitly supports it. |

## Explicit Non-Claims

- Do not claim the Waveshare P0 board has a real usable IMU until a part,
  bus/pins, and capture report exist.
- Do not train or score MotionNet with T039 mock samples.
- Do not infer fall, impact, activity, or wear state from mock samples.
- Do not use the IMU in power budget claims until instrumented current data is
  captured with power markers.
- Do not combine microphone, SD, camera, battery, or SIM7670G driver work into
  the first real IMU bring-up task.

## Recommended Next Task

Original recommendation before the AMOLED board live capture:

TIMU-002 should be a hardware I/O task only after an IMU board is physically
available:

1. Record exact board/sensor, wiring, voltage, and orientation.
2. Add a minimal probe or bus scanner for only the confirmed pins.
3. Read identity and one sample window.
4. Produce a bounded live capture report.

Only after TIMU-002 passes should `platform_imu` gain a real backend.

## Follow-Up Status After HDBRIDGE-002 / TIMU-002

HDBRIDGE-002 made the ESP32-S3-Touch-AMOLED-2.06 QMI8658 path physically
available enough for a bounded live capture:

- QMI8658 WHOAMI returned `0x05`.
- A 40-sample accel/gyro window was captured over USB JSONL.
- PC Bridge, recording, quality gate, and replay all accepted the window while
  keeping the source marked `bridge_uplink/unverified`.

TIMU-002 then analyzed that capture and kept formal IMU acceptance false:

- Identity, completeness, QMI timestamp monotonicity, static 1g orientation,
  and warm gyro sanity passed.
- Device timing failed: requested `50 ms / 20 Hz`, observed about
  `82.31 ms / 12.15 Hz`.

Updated next task: TIMU-003 should fix AMOLED bridge sample timing and rerun a
100+ sample window before `platform_imu` gains a real QMI8658 backend.
