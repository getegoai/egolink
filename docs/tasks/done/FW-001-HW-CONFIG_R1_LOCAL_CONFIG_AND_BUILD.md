---
id: FW-001-HW-CONFIG
title: R1 Local Config And Build
status: completed
priority: high
requires_hardware: false
created: 2026-06-27
last_updated: 2026-06-27

context:
  - docs/CONTEXT_INDEX.md
  - docs/development/DEV_FLOW.md
  - docs/development/FIELD_TEST.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - firmware/AGENTS.md
  - firmware/mqtt_heartbeat/README.md
  - docs/tasks/done/FW-001-HW-PREP_R1_USB_FREE_VALIDATION_KIT.md

allowed_paths:
  - docs/current/
  - docs/tasks/
  - firmware/mqtt_heartbeat/
  - quality_tests/
  - scripts/

out_of_scope:
  - flashing firmware
  - erasing flash
  - changing device permissions
  - starting serial captures
  - changing pin assignments or board wiring assumptions
  - SIM7670G AT/GNSS control changes
  - real GNSS, LTE, battery, camera, audio, or product power validation claims
  - storing real VPS IPs, passwords, bearer tokens, Wi-Fi secrets, or private device logs in tracked files
---

# Problem

The FW-001-HW hardware run needs a repeatable way to create a local ignored
R1 HTTP firmware config, bind it to a test run, and build the firmware without
copying real VPS or token values into tracked files.

# Expected Result

The repository provides a host-side preparation script that writes
`firmware/mqtt_heartbeat/sdkconfig.vps.local`, records the exact build command
for R1, and can optionally run the HTTP opt-in build. The generated local file
is ignored by Git and can include real runtime values.

# Acceptance Criteria

- [x] Script can create `sdkconfig.vps.local` from parameters, env vars, or the
      ignored VPS token file.
- [x] Script can reuse existing Wi-Fi settings from firmware `sdkconfig`
      without printing secrets.
- [x] Script can optionally run the HTTP Message Hub ESP-IDF build using
      `sdkconfig.defaults;sdkconfig.vps.local`.
- [x] Tests protect generated config shape, ignored-file boundary, and build
      command shape.
- [x] No hardware flash or serial capture is performed.

# Validation Commands

```powershell
python -m unittest quality_tests.test_fw001_hw_config -v
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Hardware Validation

- Board: not run in this task.
- Firmware commit or image: `firmware/mqtt_heartbeat/build_fw001_hw/egolink_mqtt_heartbeat.bin`.
- Connection path: not applicable.
- Evidence path: ignored local config and build directory only.

# Completion Evidence

- Changed files:
  - `docs/tasks/done/FW-001-HW-CONFIG_R1_LOCAL_CONFIG_AND_BUILD.md`
  - `docs/tasks/TASK_TREE.md`
  - `docs/current/STATUS.md`
  - `firmware/mqtt_heartbeat/README.md`
  - `quality_tests/test_fw001_hw_config.py`
  - `scripts/prepare_fw001_hw_config.ps1`
- Local ignored outputs:
  - `firmware/mqtt_heartbeat/sdkconfig.vps.local`
  - `firmware/mqtt_heartbeat/build_fw001_hw/egolink_mqtt_heartbeat.bin`
- Validation result:
  - `python -m unittest quality_tests.test_fw001_hw_config -v`: PASS, 3 tests.
  - `powershell -ExecutionPolicy Bypass -File scripts\prepare_fw001_hw_config.ps1 -HostName <operator-vps> -TokenFile server\runtime\vps_message_hub_token.txt -Build -Json`: PASS by artifact check; first shell invocation timed out while `ninja` continued, but the build completed and produced the binary.
- Remaining risks:
  - This task did not flash firmware, disconnect USB, or observe a real device
    heartbeat on the VPS.
  - The local build artifact embeds runtime field-test configuration from an
    ignored local file and must not be treated as a shareable release image.
  - Real GNSS, LTE module control, battery, camera, audio, and product power
    behavior remain unverified by this task.
