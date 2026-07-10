---
id: FIELD-002A
title: Reboot-Aware Validator USB-Free Smoke
status: completed
priority: high
requires_hardware: true
created: 2026-06-30
last_updated: 2026-06-30

context:
  - docs/CONTEXT_INDEX.md
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/development/FIELD_TEST.md
  - docs/tasks/done/FIELD-002_USB_FREE_REBOOT_AWARE_COMMAND_VALIDATOR.md
  - docs/tasks/done/LOC-004A_REAL_CELL_LOCATION_OBSERVATION.md

allowed_paths:
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/FIELD-002A_REBOOT_AWARE_VALIDATOR_USB_FREE_SMOKE.md
  - docs/tasks/done/FIELD-002_USB_FREE_REBOOT_AWARE_COMMAND_VALIDATOR.md

out_of_scope:
  - firmware changes or flashing
  - changing Message Hub service behavior
  - modifying GitLab or unrelated VPS services
  - claiming a new product location engine, GNSS fix, long LTE stability,
    reconnect, battery, power, enclosure, or product readiness
---

# FIELD-002A Reboot-Aware Validator USB-Free Smoke

## Goal

Prove the new FIELD-002 arm/reboot/reconcile validator flow on the real
connectivity node without USB as the runtime data path.

## Acceptance

- [x] Arm a single `request_location` command on the VPS and record the
      command ID.
- [x] Operator reboots the connectivity node on independent power with USB
      disconnected.
- [x] Reconcile the same command ID with `--existing-command-id`, not a newly
      queued command.
- [x] Required `location_report`, `location_observation`, and ACK evidence are
      matched from command-created time.
- [x] ACK and message evidence can use the firmware image test-run ID while
      the command batch uses the FIELD-002A test-run ID.

## Evidence

- Device: `ego-link-r1-connectivity-001`,
  Waveshare ESP32-S3-SIM7670G-4G connectivity node.
- Firmware: `0.1.0-loc004a-cell-observation`, flashed earlier from source/app
  commit `d9e4389`; binary
  `firmware/mqtt_heartbeat/build_loc004a_cell_observation/egolink_mqtt_heartbeat.bin`.
- Connection path: independent power with USB disconnected at runtime.
- Test run ID: `loc004a-reboot-aware-20260630-001`.
- Arm command: `cmd-000023`, created at
  `2026-06-30T03:41:16.220610+00:00`, result `ARMED`.
- Operator action: independent-power reboot with USB disconnected, then
  existing-command reconciliation of `cmd-000023`.
- Reconciliation result: PASS, completed at
  `2026-06-30T03:44:21.882392+00:00`.
- Evidence path:
  `reports/field_validation/loc004a-reboot-aware-20260630-001/lte_command_loop_report.md`.
- Raw `location_report`: frame `loc-cmd-000023`, `seq=2`,
  `server_received_at=2026-06-30T03:42:31.631449+00:00`,
  `fix=false`, `gnss_state=no_fix`, `gnss_query_ok=true`,
  `transport.type=lte`.
- Raw `location_observation`: frame `obs-cmd-000023`, `seq=3`,
  `server_received_at=2026-06-30T03:42:34.221879+00:00`,
  `cell.rat=LTE`, `cell.cell_id=180571649`, `cell.rsrp=-97`,
  `lte.reason_code=LTE_READY`, assigned IP `10.31.138.19`,
  `location_belief.state=Unknown`, `transport.type=lte`.
- Raw ACK: frame `cmd-000023`, `seq=4`,
  `server_received_at=2026-06-30T03:42:35.838005+00:00`,
  command/ACK status `ok`, `transport.type=lte`,
  `lte_http.phase=command_ack`, `LTE_HTTP_OK` / HTTP `200`,
  `poll_action_elapsed_ms=530`.
- Identity split: command batch `test_run_id` is
  `loc004a-reboot-aware-20260630-001`; ACK and required location messages use
  firmware-side `test_run_id` `loc004a-cell-observation-20260630-001`.

## Boundary

FIELD-002A validates the reboot-aware validator workflow and the bounded raw
LTE `request_location -> location_report -> location_observation -> ACK`
slice for one command. It does not validate GNSS fix, cell-only positioning,
long LTE stability, reconnect recovery, battery/power behavior, enclosure
behavior, or product readiness.
