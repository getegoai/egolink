---
id: LTE-009
title: Raw POST Retry Fault Injection
status: in_progress
priority: high
requires_hardware: true
created: 2026-07-01
last_updated: 2026-07-01

context:
  - docs/CONTEXT_INDEX.md
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/development/PROTOCOL.md
  - docs/development/LTE_TRANSPORT.md
  - docs/tasks/done/LTE-008_BOUNDED_RAW_POST_RETRY_OBSERVABILITY.md
  - firmware/AGENTS.md
  - quality_tests/AGENTS.md

allowed_paths:
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/development/PROTOCOL.md
  - docs/development/LTE_TRANSPORT.md
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/LTE-009_RAW_POST_RETRY_FAULT_INJECTION.md
  - firmware/mqtt_heartbeat/components/sim7670_gnss/Kconfig.projbuild
  - firmware/mqtt_heartbeat/main/app_main.c
  - scripts/prepare_fw001_hw_config.ps1
  - scripts/run_fw001_hw_r1.ps1
  - server/message_hub.py
  - quality_tests/test_fw001_hw_config.py
  - quality_tests/test_fw001_hw_runner.py
  - quality_tests/test_mqtt_heartbeat_firmware.py
  - quality_tests/test_message_hub_server.py

out_of_scope:
  - flashing firmware without explicit operator confirmation
  - modifying GitLab or unrelated VPS services
  - changing required raw-frame fields
  - implementing durable store-forward cache
  - claiming reconnect recovery, long LTE stability, battery/power behavior,
    enclosure behavior, GNSS acceptance, or product readiness
---

# LTE-009 Raw POST Retry Fault Injection

## Goal

Exercise the LTE-008 bounded raw POST retry path through a controlled,
VPS-visible failure: the first raw LTE `location_report` POST is retained as
raw evidence and rejected with HTTP 503, then the existing firmware retry
reposts the same raw frame successfully.

## Acceptance

- [x] Message Hub can detect `test_inject_raw_post_fail_once=true`, retain the
      first raw frame as `parse_result.status=injected_failure`, and return
      HTTP 503 without deriving the failed attempt.
- [x] A repeated POST of the same raw frame is accepted and derived normally.
- [x] Firmware exposes a default-off
      `CONFIG_EGOLINK_SIM7670_LTE_HTTP_RAW_POST_FAIL_ONCE_TEST` switch.
- [x] Test builds can add `test_inject_raw_post_fail_once=true` to raw LTE
      `location_report` payloads while normal builds leave it disabled.
- [x] Build/runner scripts can enable the switch through an explicit
      `-EnableRawPostFailOnceTest` flag.
- [x] USB-Free validator can require retained fail-once raw retry evidence
      through `--require-raw-post-fail-once` / `-RequireRawPostFailOnce`.
- [x] Guarded ESP-IDF build passes without flashing.
- [x] VPS deployment keeps GitLab untouched and smoke-verifies the deployed
      fail-once code path without writing synthetic device rows into the live
      service database.
- [ ] Optional hardware gate flashes only after explicit operator
      confirmation and validates the fail-once retry path over independent
      power with USB disconnected.

## Evidence

- Message Hub:
  `server/message_hub.py` can retain the first marked raw frame as
  `parse_result.status=injected_failure` and return HTTP 503 without deriving
  a Web/API message from that failed attempt.
- Firmware:
  `firmware/mqtt_heartbeat/components/sim7670_gnss/Kconfig.projbuild` adds
  `CONFIG_EGOLINK_SIM7670_LTE_HTTP_RAW_POST_FAIL_ONCE_TEST`, default `n`;
  `firmware/mqtt_heartbeat/main/app_main.c` adds
  `test_inject_raw_post_fail_once=true` only when that switch is enabled.
- Build/runner:
  `scripts/prepare_fw001_hw_config.ps1` and `scripts/run_fw001_hw_r1.ps1`
  expose `-EnableRawPostFailOnceTest`; `scripts/validate_lte_command_loop.py`
  and `scripts/run_fw001_hw_r1.ps1` expose the validation gate
  `--require-raw-post-fail-once` / `-RequireRawPostFailOnce`.
- Focused tests:
  `python -m unittest quality_tests.test_message_hub_server quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_fw001_hw_config quality_tests.test_fw001_hw_runner -v`
  passed with 47 tests.
- Validator focused tests:
  `python -m unittest quality_tests.test_lte_command_loop_validation quality_tests.test_fw001_hw_runner -v`
  passed with 16 tests and covered retained `injected_failure` raw evidence,
  later `ok` retry-derived `location_report`, and runner flag propagation.
- Full verification:
  `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passed with
  319 tests after adding the validator gate.
- Context and whitespace:
  `python scripts/context_lint.py` passed; `git diff --check` passed with only
  Windows line-ending warnings.
- ESP-IDF guarded build:
  `powershell -ExecutionPolicy Bypass -File scripts\prepare_fw001_hw_config.ps1 -HostName 203.0.113.10 -FwVersion 0.1.0-lte009-raw-post-retry-fault -TestRunId lte009-raw-post-retry-fault-20260701-001 -BuildDir build_lte009_raw_post_retry_fault -EnableSim7670Gnss -EnableSim7670LocationObservation -EnableRawPostFailOnceTest -Build -Json`
  passed and generated
  `firmware/mqtt_heartbeat/build_lte009_raw_post_retry_fault/egolink_mqtt_heartbeat.bin`
  (`301776` bytes) from app version `10e28fe`. The script did not flash
  hardware.
- VPS deployment:
  `scripts/deploy_message_hub_vps.ps1 -HostName 203.0.113.10 -SshKey <local ignored key> -Public`
  deployed the Message Hub to `/opt/egolink-message-hub` and restarted
  `egolink-message-hub.service` on `0.0.0.0:8790` without touching GitLab.
  Public checks passed: `/health` OK, unauthenticated `/api/state` returned
  `401`, and authenticated `/api/state` returned current state.
- VPS-local smoke:
  a temporary in-memory store using the deployed `/opt/egolink-message-hub`
  code verified first raw POST HTTP `503` /
  `raw_post_fail_once_injected`, retained raw status `injected_failure`, no
  derived telemetry after the failed attempt, second POST success, one derived
  `location_report`, and exported raw statuses `injected_failure` plus `ok`.

## Completion Boundary

LTE-009 is a controlled fault-injection and retry-evidence slice. It does not
implement durable offline cache, prove reconnect recovery, prove long LTE
stability, prove battery/power behavior, prove GNSS acceptance, or make a
product-readiness claim.
