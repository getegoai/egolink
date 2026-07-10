---
id: RELIABILITY-001A
title: USB-Free Stability Observer And Reset Diagnostics
status: completed
priority: high
requires_hardware: true
created: 2026-06-27
last_updated: 2026-06-27

context:
  - docs/CONTEXT_INDEX.md
  - docs/development/DEV_FLOW.md
  - docs/development/FIELD_TEST.md
  - docs/development/PROTOCOL.md
  - docs/development/VPS_MESSAGE_HUB.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - firmware/AGENTS.md
  - docs/tasks/done/FIELD-001B_FW002B_USB_FREE_SIM7670_GNSS_AT_VALIDATION.md

allowed_paths:
  - docs/current/
  - docs/development/
  - docs/hardware/
  - docs/tasks/
  - firmware/mqtt_heartbeat/
  - quality_tests/
  - scripts/
  - shared/contracts/
  - reports/field_validation/

out_of_scope:
  - claiming reconnect reliability acceptance
  - claiming outdoor GNSS fix or real coordinates
  - claiming SIM7670G LTE data transport
  - changing pin assignments or board wiring assumptions
  - flashing firmware without explicit operator intent
  - sending downlink commands during the stability observer run
  - long serial captures
  - storing real VPS passwords, bearer tokens, Wi-Fi secrets, or private logs
---

# Problem

FIELD-001B proved the FW-002B command/location/ACK loop, but R3 field
reliability still needs failure diagnosis without USB serial logs. A short
USB-Free observation should be able to detect stale devices, message gaps, and
sequence regressions from the VPS alone. When a reset is detected, later
firmware should report reset metadata through the same message path.

# Expected Result

Add an observation-only Message Hub stability script, run it against the current
USB-Free FW-002B fix1 device, and add build-verified firmware reset diagnostics
fields for the next flashed image.

# Acceptance Criteria

- [x] Stability observer reads only the VPS Message Hub.
- [x] Stability observer does not flash, open serial, erase flash, or enqueue
      commands.
- [x] Observer writes JSON/Markdown evidence under ignored
      `reports/field_validation/`.
- [x] Observer detects sequence regression as a failure by default.
- [x] Firmware status and `sensor_sample` payloads include additive
      `reset_reason`, `boot_count`, and `boot_uptime_ms` fields.
- [x] Message Hub schemas and protocol docs list the reset diagnostic fields.
- [x] HTTP + SIM7670G GNSS opt-in diagnostic firmware build passes.

# Validation Commands

```powershell
python -m unittest quality_tests.test_message_hub_stability_validation quality_tests.test_fw001_hw_validation quality_tests.test_fw002_gnss_scaffold -v
python -m unittest quality_tests.test_message_hub_contracts quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_message_hub_stability_validation -v
powershell -ExecutionPolicy Bypass -File scripts\run_fw001_hw_r1.ps1 -HostName <operator-vps> -FwVersion 0.1.0-fw002c-resetdiag -TestRunId fw002c-resetdiag-build-20260627-171124 -BuildDir build_fw002c_resetdiag -PrepareBuild -EnableSim7670Gnss -Json
python scripts\validate_message_hub_stability.py --hub http://<operator-vps>:8790 --device-id ego-link-r1-connectivity-001 --observation-id stability-fw002b-fix1-20260627-170758 --duration-sec 90 --poll-interval-sec 5 --min-messages 4 --max-last-seen-age-sec 45 --max-message-gap-sec 35 --expected-fw-version 0.1.0-fw002b-sim7670-gnss-fix1 --expected-message-test-run-id fw002b-fix1-gnss-r1-20260627-163246 --json
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Hardware Observation

- Board: `connectivity-node-001`, Waveshare ESP32-S3-SIM7670G-4G.
- Observed firmware version: `0.1.0-fw002b-sim7670-gnss-fix1`.
- Device ID: `ego-link-r1-connectivity-001`.
- Runtime connection path: `independent_power_usb_disconnected`, continued
  from FIELD-001B operator confirmation.
- Observation ID: `stability-fw002b-fix1-20260627-170758`.
- Evidence path:
  - `reports/field_validation/stability-fw002b-fix1-20260627-170758/stability_observation_report.md`
  - `reports/field_validation/stability-fw002b-fix1-20260627-170758/stability_observation_report.json`
  - `reports/field_validation/stability-fw002b-fix1-20260627-170758/observed_messages.json`
  - `reports/field_validation/stability-fw002b-fix1-20260627-170758/device_snapshots.json`

# Decisions

- The observer is intentionally command-free. It is for passive R3 preflight
  and does not mutate device behavior.
- The live observation failed and is kept as evidence. Messages advanced to
  `seq=125` / `uptime_ms=919403`, then reset to `seq=1` /
  `uptime_ms=1988` at `2026-06-27T09:08:26Z`.
- FW-002C reset diagnostics are build-verified but not flashed. The current
  hardware still runs FW-002B fix1 and therefore cannot yet report
  `reset_reason` or persistent `boot_count`.
- Follow-up: `RELIABILITY-001B` later flashed FW-002C reset diagnostics,
  reproduced repeated `panic` resets in fix1, and passed the short USB-Free
  stability gate with fix2.

# Completion Evidence

- Changed files:
  - `docs/current/ACTIVE_BUILD.md`
  - `docs/current/STATUS.md`
  - `docs/development/PROTOCOL.md`
  - `docs/hardware/BOARD_MATRIX.md`
  - `docs/tasks/TASK_TREE.md`
  - `docs/tasks/done/RELIABILITY-001A_USB_FREE_STABILITY_OBSERVER_RESET_DIAGNOSTICS.md`
  - `firmware/mqtt_heartbeat/README.md`
  - `firmware/mqtt_heartbeat/main/app_main.c`
  - `quality_tests/test_message_hub_stability_validation.py`
  - `quality_tests/test_mqtt_heartbeat_firmware.py`
  - `scripts/validate_message_hub_stability.py`
  - `shared/contracts/message_hub_event.schema.json`
  - `shared/contracts/message_hub_status.schema.json`
- Live observation result:
  - `scripts\validate_message_hub_stability.py`: FAIL by design, detected one
    sequence regression during a 90-second USB-Free observation.
- Build result:
  - `scripts\run_fw001_hw_r1.ps1 -PrepareBuild -EnableSim7670Gnss`: PASS.
  - Firmware image:
    `firmware/mqtt_heartbeat/build_fw002c_resetdiag/egolink_mqtt_heartbeat.bin`.
- Validation result:
  - `python -m unittest quality_tests.test_message_hub_stability_validation quality_tests.test_fw001_hw_validation quality_tests.test_fw002_gnss_scaffold -v`: PASS, 6 tests.
  - `python -m unittest quality_tests.test_message_hub_contracts quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_message_hub_stability_validation -v`: PASS, 14 tests.
  - `python scripts/context_lint.py`: PASS.
  - `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`: PASS,
    233 tests.
- Remaining risks:
  - At RELIABILITY-001A completion, FW-002C reset diagnostics had not been
    flashed or runtime-validated. Follow-up runtime validation is recorded in
    `RELIABILITY-001B`.
  - At RELIABILITY-001A completion, the observed reboot cause was still
    unknown until reset diagnostics could be flashed and another USB-Free
    observation could be run.
  - Outdoor real GNSS fix, SIM7670G LTE data transport, and product power
    behavior remain unverified.
