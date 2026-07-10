---
id: AMOLED-003
title: D1 field companion runner with AMOLED sidecar
status: done
priority: medium
requires_hardware: true
serves_demo: D1-sidecar
created: 2026-07-04
last_updated: 2026-07-04

context:
  - docs/product/NORTH_STAR.md
  - docs/current/ACTIVE_BUILD.md
  - docs/current/STATUS.md
  - docs/development/DEV_FLOW.md
  - docs/tasks/done/AMOLED-002_D1_STATUS_SIDECAR_RUNNER.md

allowed_paths:
  - scripts/run_d1_field_companion.ps1
  - quality_tests/test_d1_field_companion_script.py
  - docs/current/
  - docs/tasks/
  - docs/generated/

out_of_scope:
  - changing firmware
  - changing Message Hub or raw LTE protocol contracts
  - flashing hardware
  - sending Message Hub commands or 4G-board serial commands
  - claiming GNSS fix, location accuracy, battery life, or USB-Free acceptance
---

# Problem

D1 field testing currently has two useful tools: the read-only D1 field
observer and the AMOLED D1 status sidecar. Operators still need to start them
separately and manually keep run IDs aligned.

# Expected Result

A bounded companion runner starts the D1 field observer and AMOLED sidecar with
the same run ID, duration, sample count, and poll interval, then writes one
summary pointing to both evidence sets. It preserves the observer as the formal
D1 evidence path and treats AMOLED as a PC-connected sidecar.

# Acceptance Criteria

- [x] Runner launches `scripts/observe_d1_field_run.py` and
      `scripts/run_amoled_d1_status_sidecar.ps1` with shared run ID and bounded
      sample count / poll interval.
- [x] Runner redirects child stdout/stderr to files and waits for both children
      before exiting.
- [x] Runner writes JSON and Markdown summaries with child exit codes, evidence
      paths, and non-claim scope.
- [x] Runner supports `-NoAmoled` / `-NoObserver` for focused troubleshooting.
- [x] Focused tests, context lint, full verify, progress-board generation, and
      a short companion smoke pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_d1_field_companion_script -v
python scripts/context_lint.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1
python scripts\build_progress_board.py
```

# Hardware Validation

- Board: ESP32-S3-Touch-AMOLED-2.06 (`wearable-node-001`) for the sidecar
- Firmware image: current AMOLED-001/002 `firmware/amoled_safety_demo`
- Connection: Espressif USB Serial/JTAG, auto-detected or explicitly `COM9`
- Expected output: companion summary shows observer child success and AMOLED
  child `status_rendered_count >= 1`
- Evidence path: `reports/d1_field_companion/<run_id>/`

# Decisions

- The companion runner is a field operator convenience wrapper. It does not
  replace the D1 observer report or the VPS Dashboard.

# Completion Evidence

- Changed files: `scripts/run_d1_field_companion.ps1`,
  `quality_tests/test_d1_field_companion_script.py`, `docs/current/STATUS.md`,
  `docs/current/ACTIVE_BUILD.md`, and this task packet.
- Test result: focused companion tests passed:
  `python -m unittest quality_tests.test_d1_field_companion_script -v`.
  `python scripts/context_lint.py` passed. `python scripts/build_progress_board.py`
  regenerated the board with `done=79`. Full `scripts\verify.ps1` passed with
  386 tests. `git diff --check` reported no errors.
- Hardware result: `amoled003-companion-vps-smoke5-20260704` PASS on AMOLED
  `COM9`. Evidence:
  `reports/d1_field_companion/amoled003-companion-vps-smoke5-20260704/d1_field_companion_summary.json`.
  The observer child reported one successful VPS sample from
  `ego-link-r1-connectivity-001`; the AMOLED sidecar child reported
  `command_ack_count=1` and `status_rendered_count=1`.
- Remaining risks: this is still a PC-connected display companion. It does not
  prove USB-Free display acceptance, GNSS fix, location accuracy, battery life,
  enclosure behavior, or product readiness.
