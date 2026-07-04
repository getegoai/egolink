---
id: AMOLED-002
title: AMOLED D1 status sidecar runner
status: completed
priority: medium
requires_hardware: true
serves_demo: D1-sidecar
created: 2026-07-04
last_updated: 2026-07-04

context:
  - docs/product/NORTH_STAR.md
  - docs/current/ACTIVE_BUILD.md
  - docs/current/STATUS.md
  - docs/hardware/BOARD_MATRIX.md
  - docs/development/DEV_FLOW.md
  - docs/tasks/done/AMOLED-001_SCREEN_INTERACTION_SIDECAR.md

allowed_paths:
  - scripts/run_amoled_d1_status_sidecar.ps1
  - quality_tests/test_amoled_d1_status_sidecar_script.py
  - docs/current/
  - docs/tasks/
  - docs/generated/

out_of_scope:
  - changing firmware
  - changing public Message Hub / raw LTE contracts
  - sending commands to the 4G board or Message Hub command queue
  - claiming location accuracy, battery life, GNSS acceptance, or touch acceptance
---

# Problem

AMOLED-001 can render a `status_update`, but the operator still needs to hand
craft the status JSON. For field testing, the screen sidecar should be able to
mirror the current D1 Web/API state so the operator can glance at the wearable
screen while the VPS Dashboard remains the formal D1 surface.

# Expected Result

A bounded host runner reads `/api/state`, converts the selected device's
`d1_link` summary into a sidecar-only `status_update`, sends it to the AMOLED
USB Serial/JTAG port, records board JSONL, and writes a JSON summary. It reads
Message Hub state only and writes only to the AMOLED sidecar serial port.

# Acceptance Criteria

- [x] Runner auto-detects the AMOLED USB Serial/JTAG port by Espressif VID/PID
      and does not hardcode `COM9`.
- [x] Runner reads the Message Hub token from `EGOLINK_MESSAGE_HUB_TOKEN` or
      the local runtime token file without printing it.
- [x] Runner converts `d1_link` freshness, map mode/coordinate, LTE/cell state,
      raw POST counters, location-event count, and power evidence into
      `status_update` payload fields.
- [x] Runner is bounded by sample count / read window and writes JSONL plus
      summary evidence.
- [x] Focused tests, context lint, full verify, progress-board generation, and
      hardware smoke pass when the AMOLED port and Hub are available.

# Validation Commands

```powershell
python -m unittest quality_tests.test_amoled_d1_status_sidecar_script -v
python scripts/context_lint.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1
python scripts\build_progress_board.py
```

# Hardware Validation

- Board: ESP32-S3-Touch-AMOLED-2.06 (`wearable-node-001`)
- Firmware image: current AMOLED-001 `firmware/amoled_safety_demo`
- Connection: Espressif USB Serial/JTAG, auto-detected or explicitly `COM9`
- Expected output: at least one `status_rendered` matching the generated
  `cmd_id`
- Evidence path: `pc_simulator/runtime/amoled_d1_status_sidecar/<session>.jsonl`
  plus `<session>.summary.json`

# Decisions

- This runner is a field-operator sidecar helper. It does not replace the VPS
  Dashboard and does not create a new public device command contract.

# Completion Evidence

- Changed files:
  - `scripts/run_amoled_d1_status_sidecar.ps1`
  - `quality_tests/test_amoled_d1_status_sidecar_script.py`
  - `docs/current/ACTIVE_BUILD.md`
  - `docs/current/STATUS.md`
  - `docs/generated/PROGRESS_BOARD.md`
  - `docs/generated/progress_board.json`
- Test result:
  - `python -m unittest quality_tests.test_amoled_d1_status_sidecar_script -v`: PASS, 5 tests.
  - `python scripts/context_lint.py`: PASS.
  - `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1`: PASS, 381 tests.
  - `python scripts\build_progress_board.py`: PASS.
- Hardware result:
  - `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_amoled_d1_status_sidecar.ps1 -HubUrl http://203.0.113.10:8790 -Port COM9 -SampleCount 1 -ReadWindowSeconds 10 -SessionId amoled002-d1-status-vps-smoke2-20260704`: PASS.
  - AMOLED sidecar observed `command_ack` and `status_rendered` for `cmd_id=amoled002-d1-status-vps-smoke2-20260704-status-1`.
  - Last payload rendered current VPS D1 state: `D1 estimate_visible fresh 2s / LTE registered_home/active`, `Loc estimate_without_coordinate / no_fix`, `Battery 87% / 4275mV`, `POST 99 ok / 0 fail / loc 21`.
  - Evidence:
    - `pc_simulator/runtime/amoled_d1_status_sidecar/amoled002-d1-status-vps-smoke2-20260704.jsonl`
    - `pc_simulator/runtime/amoled_d1_status_sidecar/amoled002-d1-status-vps-smoke2-20260704.summary.json`
- Remaining risks:
  - This is still a PC-connected AMOLED sidecar, not USB-Free field acceptance.
  - It reads the VPS state and writes only to AMOLED serial; it does not control the 4G board.
  - The displayed `estimate_without_coordinate / no_fix` state does not claim GNSS fix or location accuracy.
