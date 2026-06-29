---
id: RAW-LTE-REPEAT-001
title: Short USB-Free Raw LTE Repeat Validation
status: active
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
  - docs/tasks/active/RAW-LTE-REPEAT-001_SHORT_USB_FREE_RAW_LTE_REPEAT.md
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

- [ ] Run at least two additional short USB-Free raw command/ACK attempts after
      separate independent-power cold boots.
- [ ] Each PASS shows `transport.type=lte`,
      `lte_http.phase=command_ack`, `poll_reason_code=LTE_HTTP_OK`,
      raw command parse status, command status, and evidence paths.
- [ ] Any FAIL is recorded as explainable evidence, not hidden or overwritten.
- [ ] No USB serial runtime data path is used.
- [ ] No firmware flash is performed.

## Completion Boundary

This is still a short repeat gate. Passing it does not prove long LTE
stability, reconnect recovery under poor signal, GNSS-over-LTE, battery/power,
or product readiness.
