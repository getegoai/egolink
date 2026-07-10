---
id: FIELD-002
title: USB-Free Reboot-Aware Command Validator
status: completed
priority: high
requires_hardware: false
created: 2026-06-30
last_updated: 2026-06-30

context:
  - docs/CONTEXT_INDEX.md
  - docs/current/STATUS.md
  - docs/development/DEV_FLOW.md
  - docs/development/FIELD_TEST.md
  - docs/tasks/done/LOC-004A_REAL_CELL_LOCATION_OBSERVATION.md
  - scripts/validate_lte_command_loop.py
  - scripts/run_fw001_hw_r1.ps1

allowed_paths:
  - docs/current/STATUS.md
  - docs/development/FIELD_TEST.md
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/FIELD-002_USB_FREE_REBOOT_AWARE_COMMAND_VALIDATOR.md
  - docs/tasks/done/LOC-004A_REAL_CELL_LOCATION_OBSERVATION.md
  - firmware/mqtt_heartbeat/README.md
  - scripts/validate_lte_command_loop.py
  - scripts/run_fw001_hw_r1.ps1
  - quality_tests/test_lte_command_loop_validation.py
  - quality_tests/test_fw001_hw_runner.py

out_of_scope:
  - flashing firmware
  - enqueuing real VPS/device commands during this tooling update
  - changing firmware command-loop behavior
  - changing Message Hub storage or public protocol
  - claiming a new hardware runtime pass
  - long LTE stability, reconnect, battery, power, enclosure, or product readiness
---

# FIELD-002 USB-Free Reboot-Aware Command Validator

## Goal

Make short USB-Free command validation fit the real field workflow where a
firmware image may consume only one command per independent-power boot.

The tool must support a clean two-step flow:

```text
arm command on VPS
-> operator reboots USB-disconnected device on independent power
-> reconcile the same command ID from VPS raw-frame evidence
```

## Acceptance

- [x] The LTE command validator can create or select a command and exit in
      `--arm-only` mode without waiting for runtime ACK.
- [x] Existing-command reconciliation uses the command creation timestamp as
      the default freshness anchor for required `location_report` and
      `location_observation` evidence.
- [x] Operators can still request the stricter old window with
      `--evidence-since validator-start`.
- [x] Existing-command reconciliation can separate command batch identity from
      firmware message identity with `--expected-message-test-run-id`.
- [x] The guarded PowerShell runner exposes `-ArmLteCommandOnly` and
      `-LteEvidenceSince`.
- [x] Reports include the evidence freshness anchor and explain arm-only mode.
- [x] Focused validator and runner tests pass.

## Implementation

- `scripts/validate_lte_command_loop.py` now accepts
  `--evidence-since command-created|validator-start|test-run-created`.
  The default is `command-created`, which lets a post-reboot reconciliation
  include location frames uploaded before the validator process restarted.
- `scripts/validate_lte_command_loop.py --arm-only` writes normal JSON and
  Markdown reports with result `ARMED`, command ID, command status, and the
  next-step boundary. It does not wait for ACK, `location_report`, or
  `location_observation`.
- `--expected-message-test-run-id` lets required `location_report` and
  `location_observation` messages use the firmware image's
  `CONFIG_EGOLINK_TEST_RUN_ID` when it differs from the command/test-run batch
  ID. ACKs keep using the existing `--expected-ack-test-run-id`.
- `scripts/run_fw001_hw_r1.ps1` passes the new validator options through as
  `-ArmLteCommandOnly`, `-LteEvidenceSince`, and
  `-ExpectedMessageTestRunId`.
- The field-test documentation and firmware README now describe the two-step
  arm/reboot/reconcile workflow for LOC-004A-style command gates.

## Validation

- `python -m unittest quality_tests.test_lte_command_loop_validation quality_tests.test_fw001_hw_runner -v`:
  PASS, 14 tests.
- `python scripts/context_lint.py`: PASS.
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`: PASS, 294
  tests.
- `git diff --check`: PASS; PowerShell reported only the existing line-ending
  normalization warning for `scripts/run_fw001_hw_r1.ps1`.

## Boundary

FIELD-002 is tooling only. It did not touch firmware, flash hardware, enqueue a
real VPS command, modify the VPS service, or claim a new runtime hardware pass.
It reduces false negatives in later USB-Free field runs by preserving the
actual command ID and evidence time window.

The follow-on hardware smoke for this tooling is recorded separately as
`FIELD-002A Reboot-Aware Validator USB-Free Smoke`.
