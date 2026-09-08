---
id: L1-000
title: Restore contract-consistent green L1 engineering baseline
status: accepted_for_transition
priority: critical
lane: A
execution_state: completed
requires_hardware: false
created: 2026-08-23
last_updated: 2026-08-23

context:
  - docs/current/FIRST_LAUNCH_EXECUTION.md
  - docs/development/PROTOCOL.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md

allowed_paths:
  - docs/tasks/done/L1-000_HEAD_CONTRACT_AND_TEST_RECOVERY.md
  - firmware/mqtt_heartbeat/main/app_main.c
  - firmware/mqtt_heartbeat/main/Kconfig.projbuild
  - server/message_hub.py
  - scripts/run_imu_capture_session.py
  - tools/run_ft001b_imu_burst.py
  - quality_tests/test_mqtt_heartbeat_firmware.py
  - quality_tests/test_message_hub_dashboard.py
  - quality_tests/test_message_hub_server.py
  - quality_tests/test_imu_capture_session.py
  - quality_tests/test_ft001b_imu_burst.py
  - scripts/verify.ps1

out_of_scope:
  - changing the frozen public IMU-window protocol or schemas
  - claiming discrete IMU windows are continuous capture or L2 mobility evidence
  - flashing, device commands, deployment, or hardware evidence
---

# Goal

Restore a green contract-consistent HEAD for the L1/FT work while keeping the
frozen bounded IMU primitive distinct from the parallel L2 continuous-capture
path.

# Serves

L1 Location priority; prerequisite for FT-001B.

# Acceptance Criteria

- [x] Firmware, Message Hub, protocol, schemas, tools, and focused tests agree
      that `capture_imu_window` is exactly 100 real samples at 50 ms.
- [x] The burst helper accepts only that frozen bounded primitive and labels
      its output as discrete preflight evidence, never FT continuous evidence.
- [x] Dashboard all-history selection updates the map, preserves the 200-point
      bound, explains trajectory limitations, and converts `datetime-local`
      values to valid offset ISO input.
- [x] Dashboard tests protect the current all-history UI instead of the removed
      recent-trajectory panel.
- [x] `scripts/verify.ps1` returns a non-zero process code when validation
      fails.
- [x] Focused tests, full verification, context lint, and `git diff --check`
      pass.

# Validation Commands

```powershell
python -B -m unittest quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_message_hub_dashboard quality_tests.test_ft001b_imu_burst -v
python scripts/context_lint.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1
git diff --check
```

# Completion Evidence

- Changed files: firmware exact-100/Kconfig, Message Hub raw lineage and
  Dashboard behavior, FT preflight helper, focused tests, and `verify.ps1`.
- Test result: focused L1/Message Hub suite `151/151` PASS; repository suite
  `821/821` PASS; `context_lint` PASS; `git diff --check` PASS. An intentional
  pre-fix full-suite failure returned process code `1`, proving validation
  failure propagation; the corrected rerun returned `0`.
- Hardware result: not required; no hardware operation authorized.
- Remaining risks: `L2-001` still requires a contract-first continuous capture
  and persistent-spool implementation, but it does not precede or block
  FT-001B hardware execution.

# Builder Prompt

```text
Read docs/tasks/done/L1-000_HEAD_CONTRACT_AND_TEST_RECOVERY.md in
D:\pywork\egolink. Load only AGENTS.md, docs/CONTEXT_INDEX.md, and the files
listed in this packet's context. This is Lane A; do only this task, obey
allowed_paths and out_of_scope. Restore the frozen exact-100 IMU-window
contract, current Dashboard history behavior, and truthful validation exit
status. Run every validation command. Do not flash, deploy, send a device
command, claim hardware evidence, update STATUS, or move this packet to done.
Return changed files, exact validation output, evidence paths and remaining
risks.
```
