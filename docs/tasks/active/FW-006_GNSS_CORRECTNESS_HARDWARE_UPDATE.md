---
id: FW-006
title: Deploy the FW-005 GNSS correctness image to the connectivity node
status: active
priority: high
requires_hardware: true
serves_demo: D2-D5
created: 2026-08-12
last_updated: 2026-08-12

context:
  - docs/CONTEXT_INDEX.md
  - docs/product/NORTH_STAR.md
  - docs/product/PRODUCT_CHARTER.md
  - docs/product/P0_SCOPE.md
  - docs/current/STATUS.md
  - docs/development/DEV_FLOW.md
  - docs/development/DIRECTOR_WORKFLOW.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - docs/tasks/active/FW-005_SIM7670_GNSS_COORDINATE_RESPONSE_CORRECTNESS.md
  - firmware/AGENTS.md
  - firmware/mqtt_heartbeat/components/sim7670_gnss/sim7670_gnss.c
  - quality_tests/AGENTS.md

allowed_paths:
  - docs/tasks/active/FW-006_GNSS_CORRECTNESS_HARDWARE_UPDATE.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - firmware/mqtt_heartbeat/build_*
  - firmware/mqtt_heartbeat/sdkconfig.*.local
  - reports/

out_of_scope:
  - firmware source or protocol changes
  - flash erase, NVS erase, modem configuration, APN changes, or device commands
  - repeated flashing, indefinite serial monitoring, or field acceptance claims
  - VPS deployment, Dashboard changes, or historical database mutation
execution_state: acceptance_review
owner: director
reviewed_at: 2026-09-22
---

# Goal

Build a clean, identifiable FIELD-011-compatible image containing FW-005 and
replace the current connectivity-node image once on COM3.

# Acceptance Criteria

- [x] A clean ESP-IDF 5.4.2 build retains the verified FIELD-011 LTE/GNSS/QMI
      profile and records exact bootloader/partition/app hashes.
- [x] Exactly one COM3 flash writes the three normal image regions without
      erase-flash or NVS overwrite, and esptool verifies every write.
- [x] One bounded 20-second startup capture shows the expected app identity,
      real QMI8658 probe/idle-stop, and no panic, brownout, or reset loop.
- [x] Current-build documentation records the new image honestly; corrected
      coordinate parsing is not claimed as hardware-verified until a later
      complete GNSS fix response is observed.

# Validation Commands

```powershell
python -m unittest quality_tests.test_fw002b_sim7670_gnss_firmware quality_tests.test_sim7670_gnss_probe quality_tests.test_sim7670_gnss_parser -v
python scripts\context_lint.py
git diff --check
```

# Hardware Validation

- Board: connectivity-node-001, Waveshare ESP32-S3-SIM7670G-4G, PCB revision unknown
- Connection: CH343 ESP32 console COM3
- Operator authorization: update the attached device firmware
- Limits: one flash and one 20-second startup capture; stop on heat, smell,
  disconnect loop, write verification failure, panic, brownout, or reset loop
- Evidence path: `reports/firmware_validation/FW-006-20260812-001/`

# Completion Evidence

- Build/image: a clean ESP-IDF 5.4.2 build from commit `6ba36c2`
  produced app identity `v0.1.0-45-g6ba36c2` and configured firmware version
  `0.1.0-fw005-gnss-correctness`. SHA-256 values were
  `8575327DA79105F868289BF7BDD014A1D7EC50E9ECF3467A68070F9C5477EC32`
  for the 20,928-byte bootloader,
  `7F00B6C042A89B15B0CAC534F82ED988CAF29278FF5700B0C511EB1B5BB7C820`
  for the 3,072-byte partition table, and
  `D52CA34099BE41AFC5F2D9CDF49C22962ECE3A61CFB7083C6189CD69BEBEB827`
  for the 607,488-byte app.
- Flash/startup: exactly one COM3 flash on `connectivity-node-001`
  (`ESP32-S3` revision v0.2, MAC `02:00:00:00:00:03`) wrote only `0x0`,
  `0x8000`, and `0x10000`; all three writes passed esptool hash verification
  and NVS at `0x9000` was not written. The sole 20.0-second capture ran from
  2026-08-12 20:39:00 to 20:39:20 +08:00 and showed the expected app
  identity, one power-on `BOOT_DIAGNOSTICS`, QMI8658 `WHO_AM_I=0x05`, a later
  `source=qmi8658_i2c mock=false` sample, confirmed idle stop, SIM7670 UART
  readiness, `LTE_READY`, and successful periodic location/observation posts,
  with no panic, brownout, or reset loop. `startup_summary.json` reports
  `passed=false` because its overly strict check stopped at the init-time
  `mock=true` line; the raw startup log is authoritative for the later real
  sample.
- Evidence: `reports/firmware_validation/FW-006-20260812-001/image_hashes.json`,
  `clean_build.log`, `flash.log`, `startup_20s.log`, and
  `startup_summary.json`.
- Remaining risks: this USB-attached startup check did not observe a GNSS fix
  or fixed-coordinate response, so the FW-005 corrected coordinate parser and
  complete fixed-response handling remain hardware-unverified. This is not
  outdoor GNSS, USB-free, long-run LTE, IMU-window, mounting/calibration, or
  product-acceptance evidence.

# Builder Prompt

```text
Read docs/tasks/active/FW-006_GNSS_CORRECTNESS_HARDWARE_UPDATE.md in
D:\pywork\egolink. Load only AGENTS.md, docs/CONTEXT_INDEX.md,
quality_tests/AGENTS.md, this packet, and its context entries. Rebuild the
existing FIELD-011 profile from committed FW-005, flash COM3 exactly once, and
capture exactly one bounded 20-second startup log. Obey allowed_paths and
out_of_scope; never erase flash/NVS or change modem settings. Return exact image
hashes, hardware evidence paths, validation results, and remaining risks.
```
