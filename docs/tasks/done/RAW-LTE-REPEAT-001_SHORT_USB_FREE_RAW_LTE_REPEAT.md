---
id: RAW-LTE-REPEAT-001
title: Short USB-Free Raw LTE Repeat Validation
status: completed
priority: high
requires_hardware: true
created: 2026-06-29
last_updated: 2026-06-29

context:
  - docs/CONTEXT_INDEX.md
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/development/FIELD_TEST.md
  - docs/development/LTE_TRANSPORT.md
  - docs/tasks/done/FW-003_RAW_FRAME_LTE_COMMAND_LOOP.md

allowed_paths:
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/RAW-LTE-REPEAT-001_SHORT_USB_FREE_RAW_LTE_REPEAT.md
  - scripts/run_fw001_hw_r1.ps1
  - scripts/validate_lte_command_loop.py
  - quality_tests/test_lte_command_loop_validation.py
  - quality_tests/test_fw001_hw_runner.py

out_of_scope:
  - firmware changes or flashing
  - long LTE stability testing
  - reconnect stress testing beyond explicit cold-boot repeat attempts
  - GNSS-over-LTE acceptance
  - battery, power, enclosure, or product acceptance
---

# RAW-LTE-REPEAT-001 Short USB-Free Raw LTE Repeat Validation

## Goal

Repeat the FW-003 raw-frame command/ACK loop over a few short,
operator-controlled independent-power cold boots. This confirms FW-003 was not
a one-off success before the project moves into longer LTE stability or
GNSS-over-LTE work.

## Operator Requirement

Each attempt requires the operator to cold boot the connectivity node on
independent power with USB disconnected, then explicitly confirm the validation
window can start. The validator should not enqueue repeat commands after the
one-shot firmware command task has already exited.

## Acceptance

- [x] Run at least two additional short USB-Free raw command/ACK attempts after
      separate independent-power cold boots.
- [x] Each PASS shows `transport.type=lte`,
      `lte_http.phase=command_ack`, `poll_reason_code=LTE_HTTP_OK`,
      raw command parse status, command status, and evidence paths.
- [x] Any FAIL is recorded as explainable evidence, not hidden or overwritten.
- [x] No USB serial runtime data path is used.
- [x] No firmware flash is performed.

## Attempt Log

- Attempt 1 (`raw-lte-repeat-001-a1-20260629-190720`) ran after the operator
  cold-booted the connectivity node on independent power with USB disconnected.
  The first validator invocation created `cmd-000018` and observed a healthy
  raw LTE ACK, but returned FAIL because it compared the repeat attempt
  `test_run_id` with the firmware build-time ACK `test_run_id`. That
  false-negative is recorded in
  `reports/field_validation/raw-lte-repeat-001-a1-20260629-190720/validation_reconciliation.md`.
  After updating the validator to accept an explicit expected ACK
  `test_run_id`, the same existing command was rechecked without queueing a
  new command and passed. Evidence:
  `reports/field_validation/raw-lte-repeat-001-a1-20260629-190720/lte_command_loop_report.md`.
  The ACK showed `transport.type=lte`, `lte_http.phase=command_ack`,
  `poll_reason_code=LTE_HTTP_OK`, `poll_status_code=200`,
  `command.parse_status=raw_command_selected`, command status `ok`, and ACK
  status `ok`.
- Attempt 2 (`raw-lte-repeat-001-a2-20260629-210939`) ran after a separate
  operator-confirmed independent-power cold boot with USB disconnected. The
  validator created `cmd-000019` and passed without reconciliation. Evidence:
  `reports/field_validation/raw-lte-repeat-001-a2-20260629-210939/lte_command_loop_report.md`.
  The ACK showed `fw_version=0.1.0-fw003-raw-command-loop`,
  `transport.type=lte`, `lte_http.phase=command_ack`,
  `poll_reason_code=LTE_HTTP_OK`, `poll_status_code=200`,
  `poll_action_elapsed_ms=680`, `command.parse_status=raw_command_selected`,
  `command.command_count=1`, command status `ok`, and ACK status `ok`.

## Completion Result

RAW-LTE-REPEAT-001 is satisfied with two short USB-Free raw LTE repeats after
separate independent-power cold boots. The next project step should remain a
bounded Walking Skeleton increment; this result is not permission to skip into
unbounded long-run stability testing.

## Completion Boundary

This is still a short repeat gate. Passing it does not prove long LTE
stability, reconnect recovery under poor signal, GNSS-over-LTE, battery/power,
or product readiness.
