---
id: LOC-004A
title: Real Cell Location Observation
status: completed
priority: high
requires_hardware: true
created: 2026-06-30
last_updated: 2026-06-30

context:
  - docs/CONTEXT_INDEX.md
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/development/LOCATION_ENGINE.md
  - docs/development/LTE_TRANSPORT.md
  - docs/development/PROTOCOL.md
  - docs/tasks/done/LOC-003_LOCATION_MEMORY_GATE.md
  - docs/tasks/done/LTE-004_RAW_LTE_REQUEST_LOCATION_THIN_SLICE.md
  - firmware/AGENTS.md
  - firmware/mqtt_heartbeat/README.md
  - shared/contracts/

allowed_paths:
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/development/LOCATION_ENGINE.md
  - docs/development/LTE_TRANSPORT.md
  - docs/development/PROTOCOL.md
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/LOC-004A_REAL_CELL_LOCATION_OBSERVATION.md
  - firmware/mqtt_heartbeat/README.md
  - firmware/mqtt_heartbeat/components/sim7670_gnss/Kconfig.projbuild
  - firmware/mqtt_heartbeat/main/app_main.c
  - server/message_hub.py
  - scripts/prepare_fw001_hw_config.ps1
  - scripts/run_fw001_hw_r1.ps1
  - scripts/validate_lte_command_loop.py
  - quality_tests/test_fw001_hw_config.py
  - quality_tests/test_fw001_hw_runner.py
  - quality_tests/test_lte_command_loop_validation.py
  - quality_tests/test_message_hub_server.py
  - quality_tests/test_mqtt_heartbeat_firmware.py

out_of_scope:
  - flashing firmware without explicit operator confirmation
  - claiming a hardware runtime pass before USB-Free validation
  - inferring a user position from cell-only data
  - learned known-place matching, Wi-Fi/IMU/power fusion, or route prediction
  - long LTE stability, reconnect, battery, power, enclosure, or product readiness
  - modifying GitLab or unrelated VPS services
---

# LOC-004A Real Cell Location Observation

## Goal

Add the first real firmware-side cell/LTE observation to the raw-frame
Walking Skeleton:

```text
request_location
-> raw LTE location_report for GNSS fix/no-fix
-> raw LTE location_observation for SIM7670G cell/LTE evidence
-> Message Hub stores raw frames first
-> Web/API/export show derived cell, LTE, and belief evidence
-> raw LTE ACK
```

This is an explainability increment before long LTE testing. It makes weak or
no-fix location attempts inspectable from the VPS/Web path without USB logs.

## Acceptance

- [x] Message Hub derives raw key/value `event_type=location_observation`
      frames into structured `cell`, `lte`, `transport`, `lte_http`, and
      `location_belief` fields while retaining raw-frame evidence.
- [x] Explicit `location_belief.state=Unknown` observations do not erase an
      existing useful `Fine`, `Coarse`, or `Predicted` location memory.
- [x] Firmware adds default-off
      `CONFIG_EGOLINK_SIM7670_LOCATION_OBSERVATION_ENABLED`.
- [x] When enabled, raw LTE `request_location` uploads the LTE-004
      `location_report` and then a command-scoped raw
      `location_observation`.
- [x] Config and runner scripts can enable the observation path and imply the
      required LTE status and raw command-loop settings.
- [x] `scripts/validate_lte_command_loop.py` can require a matching LTE
      `location_observation` for the same command ID.
- [x] Focused firmware/server/validator/runner tests pass.
- [x] `python scripts/context_lint.py` passes.
- [x] Full `scripts/verify.ps1` passes if behavior changes.
- [x] Firmware flashes on `COM4` after explicit operator confirmation.
- [x] USB-Free runtime evidence reconciles as PASS for
      `request_location -> location_report -> location_observation -> ACK`
      after independent-power reboot with USB disconnected.

## Evidence

- VPS deployment:
  Message Hub redeployed to `203.0.113.10:8790` without touching GitLab.
- VPS smoke:
  `loc004a-vps-cell-observation-smoke-20260630-012442` posted a synthetic raw
  `location_observation` frame and passed with parse status `ok`, derived
  `event_type=location_observation`, `cell.rat=LTE`,
  `cell.cell_id=01AF23`, `lte.reason_code=LTE_READY`,
  `transport.type=lte`, `location_belief.state=Unknown`, and redacted raw
  payload in export. Evidence:
  `reports/location_observation/loc004a-vps-cell-observation-smoke-20260630-012442/vps_smoke_report.json`.
- Server parser tests:
  `quality_tests/test_message_hub_server.py` covers raw cell observation
  derivation and Unknown observation memory preservation.
- Validator tests:
  `quality_tests/test_lte_command_loop_validation.py` covers
  `--require-location-observation`.
- Firmware/static config tests:
  `quality_tests/test_mqtt_heartbeat_firmware.py`,
  `quality_tests/test_fw001_hw_config.py`, and
  `quality_tests/test_fw001_hw_runner.py`.
- Build target:
  `0.1.0-loc004a-cell-observation` with
  `CONFIG_EGOLINK_SIM7670_LOCATION_OBSERVATION_ENABLED=y`.
- Build artifact:
  `firmware/mqtt_heartbeat/build_loc004a_cell_observation/egolink_mqtt_heartbeat.bin`
  (`298416` bytes).
- Focused tests:
  `python -m unittest quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_fw001_hw_config quality_tests.test_fw001_hw_runner quality_tests.test_lte_command_loop_validation quality_tests.test_message_hub_server`
  passed with 50 tests.
- Repository gates:
  `python scripts/context_lint.py` PASS; `powershell -ExecutionPolicy Bypass
  -File scripts\verify.ps1` PASS with 292 tests; `git diff --check` PASS.
- ESP-IDF guarded build:
  `scripts\prepare_fw001_hw_config.ps1` with
  `-EnableSim7670Gnss -EnableSim7670LocationObservation -BuildDir
  build_loc004a_cell_observation -Build` PASS.
- Flash:
  `reports/field_validation/loc004a-cell-observation-20260630-001/flash_report.md`
  records PASS on `COM4`; ESP32-S3 QFN56 rev v0.2 detected, bootloader/app/
  partition table written, hashes verified, and hard reset completed.
- USB-Free runtime reconciliation:
  `reports/field_validation/loc004a-cell-observation-runtime-20260630-001/validation_reconciliation.md`
  records `RECONCILED_PASS` for `cmd-000021`. After the operator rebooted the
  independent-powered device with USB disconnected, firmware consumed the
  pending command and uploaded raw `location_report` frame `loc-cmd-000021`
  (`seq=2`, `fix=false`, `gnss_state=no_fix`, `gnss_query_ok=true`,
  `transport.type=lte`), raw `location_observation` frame `obs-cmd-000021`
  (`seq=3`, `cell.rat=LTE`, `cell.cell_id=180571649`, `cell.rsrp=-98`,
  `lte.reason_code=LTE_READY`, assigned IP `10.91.147.246`,
  `location_belief.state=Unknown`, `transport.type=lte`), and raw ACK
  `cmd-000021` (`seq=4`, command/ACK status `ok`, `LTE_HTTP_OK` / HTTP
  `200`). Stale command `cmd-000022` from a later validator attempt was
  server-side cancelled as queue hygiene and is not counted as hardware
  evidence.

## Follow-Up Hardware Gate

The bounded USB-Free runtime gate has passed by reconciliation. The
one-command-per-boot validator timing issue observed during this run is tracked
and addressed by `FIELD-002 USB-Free Reboot-Aware Command Validator`, which
adds `--arm-only` plus command-created evidence anchoring for existing-command
reconciliation.

## Boundary

LOC-004A is not a product location engine. A cell-only observation can be real
evidence while the location belief remains `Unknown`. Known-place matching,
Wi-Fi fingerprints, IMU/power fusion, decay models, long LTE stability, and
product readiness remain separate tasks.
