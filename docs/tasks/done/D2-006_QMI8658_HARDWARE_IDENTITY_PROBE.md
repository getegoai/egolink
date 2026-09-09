---
id: D2-006
title: QMI8658 external-module hardware identity probe
status: done
priority: high
requires_hardware: true
serves_demo: D2
created: 2026-08-10
last_updated: 2026-09-09

context:
  - docs/product/NORTH_STAR.md
  - docs/development/DIRECTOR_WORKFLOW.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - docs/hardware/QMI8658_4G_MODULE_INTEGRATION.md
  - docs/hardware/validation/P0_BOARD_VALIDATION.md
  - docs/tasks/done/D2-005_QMI8658_MOTION_DATA_READINESS.md
  - firmware/AGENTS.md

allowed_paths:
  - firmware/mqtt_heartbeat/sdkconfig.*.local
  - firmware/mqtt_heartbeat/build_*
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - docs/hardware/QMI8658_4G_MODULE_INTEGRATION.md
  - docs/tasks/done/D2-006_QMI8658_HARDWARE_IDENTITY_PROBE.md
  - reports/board_validation/

out_of_scope:
  - firmware logic, public protocol, model, or pin-assignment changes
  - SIM7670 firmware, AT commands, GNSS, LTE, VPS, or AMOLED operations
  - continuous IMU uplink, model training, or edge deployment
  - IMU accuracy, calibration, mounting-orientation, power, or product-readiness claims
---

# Problem

The external ATK-NB018 V1.0 QMI8658A module is wired to the connectivity-node
ESP32-S3, but its fixed I2C address and real-device firmware path have not been
verified. Build-only evidence cannot establish hardware presence or real
six-axis sampling.

# Expected Result

Identify whether the module responds at candidate address `0x6B` or `0x6A`,
verify `WHO_AM_I=0x05`, and collect a bounded boot window containing real,
non-mock six-axis samples without exercising unrelated board functions.

# Acceptance Criteria

- [x] Operator explicitly authorizes flashing `COM3` and bounded sensor probing.
- [x] `COM3` is re-identified as the connectivity-node CH343 ESP32 console.
- [x] Isolated ESP32-S3 probe images for `0x6B` and `0x6A` are built and hashed.
- [x] Flash `0x6B` first; flash `0x6A` only if the first candidate cannot probe the sensor.
- [x] A bounded capture records `WHO_AM_I=0x05` and multiple
      `source=qmi8658_i2c mock=false` samples, or records an honest failure.
- [x] Evidence records board, connection, firmware commit/version/image/hash,
      timestamps, command boundary, and remaining non-claims.
- [x] Context lint passes and the task result is recorded.

# Validation Commands

```powershell
python -m unittest quality_tests.test_platform_imu_firmware quality_tests.test_fw001_hw_config -v
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
python scripts/context_lint.py
git diff --check
```

# Hardware Validation

- Board: Waveshare ESP32-S3 + SIM7670G-4G connectivity node; PCB has no
  `VER2.0` silkscreen and remains revision-unverified.
- Sensor: ATK-NB018 V1.0, QMI8658A candidate;
  `VCC->3V3`, `GND->GND`, `SDA->GPIO15`, `SCL->GPIO16`, `INT` disconnected.
- Firmware commit: `e7e7e85`; image project version `v0.1.0-22-ge7e7e85`.
- Candidate `0x6B` image:
  `firmware/mqtt_heartbeat/build_qmi_probe_6b/egolink_mqtt_heartbeat.bin`,
  SHA-256 `F2CF2B92F082D6CA7D30F9F634E6E06BF2E3AB7CD27B7092A6F15F1605A4E205`.
- Candidate `0x6A` image:
  `firmware/mqtt_heartbeat/build_qmi_probe_6a/egolink_mqtt_heartbeat.bin`,
  SHA-256 `A736109B758A4EE8F8A077B4415360C61F30D26856EE06CC85EF01F1A13B2945`.
- Connection: CH343 USB serial `COM3`; SIM7670 USB interfaces are out of scope.
- Expected output: `PLATFORM_IMU_QMI8658_PROBE_OK whoami=0x05`, followed by
  bounded boot samples with `hardware_present=true`, `driver_enabled=true`,
  and `mock=false`.
- Evidence path: `reports/board_validation/20260810-qmi8658-probe/`.

# Decisions

- 2026-08-10: The operator explicitly authorized flashing `COM3` and a
  bounded sensor probe.
- Probe `0x6B` first because it is the repository's prepared external-module
  candidate; failure does not prove `0x6A` until the second image is tested.
- At most two flashes are allowed: one `0x6B` attempt and, only when it does
  not produce `WHO_AM_I=0x05`, one `0x6A` attempt. Each image gets at most one
  20-second capture; one additional reset-only 20-second capture is allowed
  only when the boot log was missed. Indefinite monitoring is prohibited.
- The probe initializes and writes QMI8658 control registers; it is not a
  read-only address scan.
- Stop after the bounded boot window; do not start LTE, GNSS, VPS, or long
  serial observation.
- Abort immediately on an abnormal PWR LED, heat, odor, repeated USB
  disconnects, or suspected 3V3/GND fault. Do not move powered jumpers.
- Flashing replaces the ESP32 application recorded in `ACTIVE_BUILD` as the
  MODEL-DEVICE-006 image. Restoring that image is outside this task; after the
  probe, the board remains on the last probe image flashed.

# Completion Evidence

Administrative closure: moved from `active` to `done` on 2026-09-09 because
all acceptance items and the recorded bounded hardware result had already
completed on 2026-08-10. This does not extend the original evidence scope.

- Changed files: this task packet, `docs/current/ACTIVE_BUILD.md`,
  `docs/hardware/BOARD_MATRIX.md`, and
  `docs/hardware/QMI8658_4G_MODULE_INTEGRATION.md`.
- Test result: focused tests 20/20 pass; full repository tests 564/564 pass;
  post-evidence context lint and `git diff --check` pass.
- Hardware result: PASS for identity and bounded real sampling. `0x6B` failed
  with `qmi8658_reset_failed`; `0x6A` returned `WHO_AM_I=0x05`, reset result
  `0x80`, and 100/100 real non-mock boot samples with no sample failure.
  Evidence:
  `reports/board_validation/20260810-qmi8658-probe/qmi8658_probe_report.md`.
- Current image: `0x6A` isolated probe image; the prior MODEL-DEVICE-006 image
  was replaced.
- Remaining risks: formal board revision, electrical characterization,
  mounting orientation, calibration, accuracy, interrupt/FIFO behavior,
  sustained cadence, shared-bus operation, LTE upload, and power remain
  unverified.

# Builder Prompt

```text
Read docs/tasks/done/D2-006_QMI8658_HARDWARE_IDENTITY_PROBE.md in
D:\pywork\egolink. This is a completed historical packet: do not rerun its
obsolete bounded COM3 probe. Use the current active milestone packet instead.
The old execution boundary and builder instructions retained above are
provenance only and grant no current hardware authorization.
```
