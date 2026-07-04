---
id: AMOLED-004
title: Visible D1 status display on AMOLED sidecar
status: done
priority: medium
requires_hardware: true
serves_demo: D1-sidecar
created: 2026-07-04
last_updated: 2026-07-04

context:
  - docs/product/NORTH_STAR.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - docs/tasks/done/AMOLED-003_D1_FIELD_COMPANION_RUNNER.md

allowed_paths:
  - firmware/amoled_safety_demo/main/app_main.c
  - scripts/run_amoled_d1_status_sidecar.ps1
  - quality_tests/test_amoled_safety_demo_firmware.py
  - quality_tests/test_amoled_d1_status_sidecar_script.py
  - docs/current/
  - docs/tasks/
  - docs/generated/

out_of_scope:
  - changing 4G-board firmware or Message Hub protocol
  - changing pin assignments or board hardware configuration
  - claiming GNSS fix, location accuracy, battery life, or product readiness
---

# Goal

Make the AMOLED D1 sidecar visibly switch to a full-screen D1 status page even
when a previous `ask_user` prompt is still active.

# Acceptance Criteria

- [x] `display_status` forces full-screen status UI and clears prompt-active
      state.
- [x] `status_update` can still remain a non-disruptive prompt status update.
- [x] The D1 sidecar runner sends `display_status` for field visibility.
- [x] Focused tests, context lint, full verify, ESP-IDF build, flash, and a
      short visible-status smoke pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_amoled_safety_demo_firmware quality_tests.test_amoled_d1_status_sidecar_script -v
python scripts/context_lint.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1
python scripts\build_progress_board.py
```

# Completion Evidence

- Changed files: `firmware/amoled_safety_demo/main/app_main.c`,
  `scripts/run_amoled_d1_status_sidecar.ps1`,
  `quality_tests/test_amoled_safety_demo_firmware.py`,
  `quality_tests/test_amoled_d1_status_sidecar_script.py`,
  `docs/current/STATUS.md`, `docs/current/ACTIVE_BUILD.md`, and this task
  packet.
- Test result: focused tests passed:
  `python -m unittest quality_tests.test_amoled_safety_demo_firmware quality_tests.test_amoled_d1_status_sidecar_script -v`.
  `python scripts/context_lint.py` passed. `python scripts/build_progress_board.py`
  regenerated the board with `done=80`. Full `scripts\verify.ps1` passed with
  386 tests. `git diff --check` reported no errors.
- Hardware result: ESP-IDF v5.4.2 build passed and produced
  `firmware/amoled_safety_demo/build/egolink_amoled_safety_demo.bin`, size
  `0x9cea0`. Flash to AMOLED `COM9` passed for ESP32-S3 MAC
  `02:00:00:00:00:01`; bootloader/app/partition-table hashes were verified.
  Direct visible-status smoke `amoled004-visible-status-vps-smoke2-20260704`
  passed with `cmd=display_status`, `command_ack_count=2`, and
  `status_rendered_count=2`. Companion smoke
  `amoled004-companion-visible-vps-smoke-20260704` passed with
  `command_ack_count=1` and `status_rendered_count=1`. Evidence:
  `reports/amoled_visible_status/amoled004-visible-status-20260704/sidecar_fix1/amoled004-visible-status-vps-smoke2-20260704.summary.json`
  and
  `reports/d1_field_companion/amoled004-companion-visible-vps-smoke-20260704/d1_field_companion_summary.json`.
- Remaining risks: this proves the PC-connected AMOLED sidecar display path,
  not USB-Free display acceptance, GNSS fix, location accuracy, battery life,
  enclosure behavior, or product readiness.
