---
id: DEMO-004
title: Full Demo Orchestrator
status: completed
priority: high
requires_hardware: true
created: 2026-06-26
owner: codex
---

# Goal

Finish a repeatable end-to-end P0 demo runner that ties the already working
AMOLED IMU confirmation loop into GNSS evidence, mock-only audio evidence,
recording, replay, and quality gates.

The demo must keep real-vs-mock boundaries explicit. In particular, audio may
be included only as structured mock evidence until a real microphone path is
accepted.

# Context

- `docs/CONTEXT_INDEX.md`
- `docs/product/PRODUCT_CHARTER.md`
- `docs/product/P0_SCOPE.md`
- `docs/current/STATUS.md`
- `docs/current/ACTIVE_BUILD.md`
- `docs/architecture/SYSTEM_OVERVIEW.md`
- `docs/hardware/BOARD_MATRIX.md`
- `pc_simulator/AGENTS.md`
- `quality_tests/AGENTS.md`
- `shared/contracts/`

# Allowed Paths

- `pc_simulator/full_safety_demo.py`
- `scripts/run_full_safety_demo.py`
- `quality_tests/test_full_safety_demo.py`
- `docs/tasks/active/DEMO-004_FULL_DEMO_ORCHESTRATOR.md`
- `docs/current/ACTIVE_BUILD.md`
- `docs/current/STATUS.md`

# Out Of Scope

- Real emergency dispatch, calling, SMS, or cloud integration.
- Claiming production fall-detection accuracy.
- Claiming real audio capture or microphone acceptance.
- Firmware pin, board configuration, or protocol changes.
- Board-to-board UART implementation.

# Acceptance Criteria

- [x] A single CLI can run the complete Demo v0.5 flow from either live hardware captures or existing evidence files.
- [x] The flow includes AMOLED IMU/touch evidence, SIM7670G GNSS/AT evidence or an explicit allowed no-fix/failure boundary, mock-only audio evidence, session recording, quality gate, and replay.
- [x] The summary reports Demo v0.1 through v0.5 stage gates with explicit pass/fail and source-boundary notes.
- [x] Session recording remains privacy-safe: no raw audio or images are captured.
- [x] Unit tests cover the full demo event builder and CLI using fixture evidence.
- [x] Context lint and full repository verification pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_full_safety_demo -v
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
```

# Hardware Validation

- Board: ESP32-S3-Touch-AMOLED-2.06 and ESP32-S3-SIM7670G-4G
- Connection: USB serial ports discovered at runtime; recent evidence used `COM9` for AMOLED and `COM6` for SIM7670G AT.
- Expected output: full demo summary with quality and replay pass.
- Evidence path:
  - Full Demo v0.5 summary: `pc_simulator/runtime/demo_full_v0_5/demo-full-v05-20260626-live-gnss.summary.json`
  - Full Demo v0.5 event log: `pc_simulator/runtime/demo_full_v0_5/demo-full-v05-20260626-live-gnss.events.jsonl`
  - Full Demo v0.5 recording: `pc_simulator/runtime/demo_full_v0_5/recordings/demo-full-v05-20260626-live-gnss/`
  - SIM7670G GNSS probe report: `pc_simulator/runtime/demo_full_v0_5/gnss/20260626-195321/gnss_probe.md`

# Completion Evidence

- Changed files:
  - `pc_simulator/full_safety_demo.py`
  - `scripts/run_full_safety_demo.py`
  - `quality_tests/test_full_safety_demo.py`
  - `docs/tasks/active/DEMO-004_FULL_DEMO_ORCHESTRATOR.md`
  - Local current-state notes were also updated in `docs/current/ACTIVE_BUILD.md` and `docs/current/STATUS.md`, but `docs/current/` is currently an untracked context-migration directory and is not part of the implementation commit.
- Test result:
  - Full demo focused tests passed: `python -m unittest quality_tests.test_full_safety_demo -v`
  - Full demo fixture smoke passed: `python scripts/run_full_safety_demo.py --session-id demo-full-smoke-20260626-r2 --runtime-dir pc_simulator/runtime/demo_full_smoke --amoled-jsonl pc_simulator/runtime/demo_v0_3_live_hardware/amoled/demo-v03-live-amoled-imu-20260626-r4.jsonl --location-event-json pc_simulator/runtime/demo_v0_3_live_hardware_fixed/gnss/20260626-190513/gnss_probe.json --json`
  - Full demo live GNSS smoke passed: `python scripts/run_full_safety_demo.py --session-id demo-full-v05-20260626-live-gnss --runtime-dir pc_simulator/runtime/demo_full_v0_5 --amoled-jsonl pc_simulator/runtime/demo_v0_3_live_hardware/amoled/demo-v03-live-amoled-imu-20260626-r4.jsonl --probe-all-sim-ports --gnss-warmup-seconds 2 --gnss-poll-count 2 --gnss-poll-interval-seconds 1 --allow-gnss-failure --json`
  - Context lint passed: `python scripts/context_lint.py`
  - Full repository validation passed: `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1` (`192` tests OK)
- Hardware result:
  - Used prior same-run AMOLED hardware capture from `COM9` containing real QMI8658 `motion_event`, `ask_user_rendered`, and `user_confirmation response=safe`.
  - Live SIM7670G GNSS AT probe selected `COM6`; AT gate passed, GNSS fix remained `false` / `no_fix`.
  - Full Demo v0.5 summary reports all stage gates passed, quality score `0.94`, and replay pass.
- Remaining risks:
  - Audio evidence is mock-only structured evidence; no raw audio is captured and real microphone acceptance remains unverified.
  - GNSS real outdoor fix remains unverified in this indoor run.
  - IMU trigger is still a demo heuristic, not product fall-detection accuracy or MotionNet output.
