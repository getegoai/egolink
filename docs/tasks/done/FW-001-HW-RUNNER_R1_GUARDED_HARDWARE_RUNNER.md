---
id: FW-001-HW-RUNNER
title: R1 Guarded Hardware Runner
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
  - docs/tasks/done/FW-001-HW-PREP_R1_USB_FREE_VALIDATION_KIT.md
  - docs/tasks/done/FW-001-HW-CONFIG_R1_LOCAL_CONFIG_AND_BUILD.md

allowed_paths:
  - docs/current/
  - docs/tasks/
  - firmware/mqtt_heartbeat/README.md
  - quality_tests/
  - scripts/

out_of_scope:
  - automatically flashing firmware without explicit operator flags
  - erasing flash
  - changing device permissions
  - starting serial captures
  - changing pin assignments or board wiring assumptions
  - SIM7670G AT/GNSS control changes
  - real GNSS, LTE, battery, camera, audio, or product power validation claims
  - storing real VPS IPs, passwords, bearer tokens, Wi-Fi secrets, or private device logs in tracked files
---

# Problem

FW-001-HW is now ready for a real hardware run, but the operator steps still
need a guarded one-command entry point that cannot accidentally flash firmware
or send validation commands without explicit confirmation.

# Expected Result

Add a PowerShell R1 runner that can prepare/build, optionally flash when the
operator passes explicit flash flags, and optionally run the USB-Free Message
Hub validation only after the operator confirms independent power and USB
disconnect.

# Acceptance Criteria

- [x] Default execution prints a plan and performs no hardware action.
- [x] Flash phase requires a serial port and an explicit
      `IUnderstandFlashWritesFirmware` flag.
- [x] Validation phase requires explicit independent-power and
      USB-disconnected confirmations.
- [x] Runner reuses existing prepare and validation scripts instead of
      duplicating their logic.
- [x] Tests protect the guard rails and command shape.
- [x] No hardware flash, serial capture, or validation command is run by this
      task.

# Validation Commands

```powershell
python -m unittest quality_tests.test_fw001_hw_runner -v
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Hardware Validation

- Board: not run in this task.
- Firmware commit or image: not flashed in this task.
- Connection path: not applicable.
- Evidence path: not applicable.

# Completion Evidence

- Changed files:
  - `docs/tasks/done/FW-001-HW-RUNNER_R1_GUARDED_HARDWARE_RUNNER.md`
  - `docs/tasks/TASK_TREE.md`
  - `docs/current/STATUS.md`
  - `firmware/mqtt_heartbeat/README.md`
  - `quality_tests/test_fw001_hw_runner.py`
  - `scripts/run_fw001_hw_r1.ps1`
- Validation result:
  - `python -m unittest quality_tests.test_fw001_hw_runner -v`: PASS, 5 tests.
  - `powershell -ExecutionPolicy Bypass -File scripts\run_fw001_hw_r1.ps1 -HostName <operator-vps> -TestRunId fw001-hw-r1-plan-smoke -Json`: PASS, plan-only; no prepare/build, flash, or validation phase ran.
- Remaining risks:
  - This task did not flash firmware, disconnect USB, send a Message Hub
    validation command, or observe a real device heartbeat.
  - True `FW-001-HW` acceptance still requires operator-confirmed flashing,
    independent power, USB-disconnected runtime, and VPS heartbeat/ACK
    evidence.
