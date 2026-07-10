---
id: AMOLED-001
title: AMOLED screen interaction sidecar
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
  - docs/architecture/SYSTEM_OVERVIEW.md
  - docs/architecture/DUAL_BOARD_PC_BRIDGE_ARCHITECTURE.md
  - firmware/AGENTS.md

allowed_paths:
  - firmware/amoled_safety_demo/
  - scripts/run_amoled_ask_user_demo.ps1
  - quality_tests/test_amoled_safety_demo_firmware.py
  - quality_tests/test_amoled_ask_user_demo_script.py
  - docs/current/
  - docs/tasks/
  - docs/generated/

out_of_scope:
  - changing connectivity-node or D1 periodic location firmware
  - changing public Message Hub / raw LTE contracts
  - claiming formal IMU, GNSS, battery, touch, or product acceptance
  - dual-board direct UART wiring
  - replacing the Dashboard as the primary D1 live location surface
---

# Problem

NORTH_STAR keeps the 4G board as the D1 mainline, while the
ESP32-S3-Touch-AMOLED-2.06 board can progress as a screen and touch interaction
sidecar. The existing AMOLED safety demo can show an `ask_user` prompt and
emit touch replies, but its downlink parsing is minimal and the idle screen
does not yet display bridge/server status that would help field testing.

# Expected Result

The AMOLED demo becomes a bounded PC Bridge sidecar:

1. It continues to boot into an idle screen and emit `hello` /
   `display_ready`.
2. It accepts a board-facing `ask_user` JSON line, parses title/prompt/severity
   from root or `payload`, renders the prompt, and emits `command_ack` plus
   `ask_user_rendered`.
3. It accepts a sidecar-only `status_update` JSON line and renders D1/bridge
   status such as LTE state, location/map state, and battery summary.
4. It emits bounded JSON feedback for invalid or unsupported serial commands.
5. It preserves QMI8658 engineering JSONL output and does not affect the 4G
   board firmware.

# Acceptance Criteria

- [x] Firmware uses a structured JSON parser for serial downlink lines instead
      of ad hoc substring extraction.
- [x] `ask_user` prompt text can be supplied by the PC Bridge payload and still
      returns touch `user_confirmation` with the active `cmd_id`.
- [x] `status_update` can update the screen without claiming product location
      accuracy or battery-life acceptance.
- [x] Demo runner can optionally send an initial status update and record the
      corresponding `status_rendered` event.
- [x] Focused tests, context lint, full verify, and an ESP-IDF build pass.
- [x] If the AMOLED USB port is available, flash and run a bounded serial
      smoke that observes `status_rendered` and `ask_user_rendered`.

# Validation Commands

```powershell
python -m unittest quality_tests.test_amoled_safety_demo_firmware quality_tests.test_amoled_ask_user_demo_script -v
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
cd firmware/amoled_safety_demo; . C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py build
```

# Hardware Validation

- Board: ESP32-S3-Touch-AMOLED-2.06 (`wearable-node-001`)
- Firmware image: `firmware/amoled_safety_demo/build/egolink_amoled_safety_demo.bin`
- Connection: Espressif USB Serial/JTAG, auto-detected by USB VID/PID
- Expected output: `hello`, `display_ready`, `status_rendered`,
  `command_ack cmd=ask_user`, and `ask_user_rendered`
- Evidence path: `pc_simulator/runtime/demo_v0_2/<session>.jsonl` plus
  `<session>.summary.json`

# Decisions

- This is a sidecar development path for screen and user interaction; D1 field
  readiness remains owned by the 4G-board upload and Dashboard path.
- `status_update` is a local PC Bridge display helper, not a new public
  Message Hub command contract.

# Completion Evidence

- Changed files:
  - `firmware/amoled_safety_demo/main/app_main.c`
  - `firmware/amoled_safety_demo/main/CMakeLists.txt`
  - `firmware/amoled_safety_demo/README.md`
  - `scripts/run_amoled_ask_user_demo.ps1`
  - `quality_tests/test_amoled_safety_demo_firmware.py`
  - `quality_tests/test_amoled_ask_user_demo_script.py`
  - `docs/current/ACTIVE_BUILD.md`
  - `docs/current/STATUS.md`
  - `docs/generated/PROGRESS_BOARD.md`
  - `docs/generated/progress_board.json`
- Test result:
  - `python -m unittest quality_tests.test_amoled_safety_demo_firmware quality_tests.test_amoled_ask_user_demo_script -v`: PASS, 12 tests.
  - `python scripts/context_lint.py`: PASS.
  - `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1`: PASS, 376 tests.
  - `python scripts\build_progress_board.py`: PASS.
  - `. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py build`: PASS, generated `firmware/amoled_safety_demo/build/egolink_amoled_safety_demo.bin`, binary size `0x9ce30`.
- Hardware result:
  - Flashed `firmware/amoled_safety_demo/build/egolink_amoled_safety_demo.bin` to ESP32-S3-Touch-AMOLED-2.06 on `COM9`.
  - esptool detected ESP32-S3 USB-Serial/JTAG, PSRAM 8MB, MAC `02:00:00:00:00:01`; bootloader/app/partition-table hashes verified and hard reset completed.
  - Bounded smoke `amoled001-sidecar-smoke2-20260704` PASS over `COM9`: `status_update` produced `command_ack` and `status_rendered`; `ask_user` produced `command_ack` and `ask_user_rendered`.
  - Evidence:
    - `pc_simulator/runtime/demo_v0_2/amoled001-sidecar-smoke2-20260704.jsonl`
    - `pc_simulator/runtime/demo_v0_2/amoled001-sidecar-smoke2-20260704.summary.json`
- Remaining risks:
  - This task did not require a fresh physical tap; `user_confirmation` remains covered by earlier AMOLED Demo v0.2/v0.3 evidence.
  - Status display is a PC Bridge sidecar helper, not a public Message Hub command contract and not a replacement for the D1 Dashboard.
  - QMI8658 output remains engineering/demo evidence, not formal product IMU acceptance.
