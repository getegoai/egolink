---
id: SIM-001
title: PC Simulator Message Hub Loop
status: completed
priority: high
requires_hardware: false
created: 2026-06-27
last_updated: 2026-06-27

context:
  - docs/CONTEXT_INDEX.md
  - docs/development/DEV_FLOW.md
  - docs/development/VPS_MESSAGE_HUB.md
  - docs/development/PROTOCOL.md
  - pc_simulator/AGENTS.md
  - shared/contracts/

allowed_paths:
  - README.md
  - docs/current/
  - docs/tasks/
  - pc_simulator/
  - quality_tests/
  - scripts/

out_of_scope:
  - firmware behavior changes
  - protocol version changes
  - server schema changes
  - VPS deployment
  - hardware validation
---

# Problem

R0 needed a PC Simulator client that uses the message-hub API as a virtual
device instead of relying on hand-written HTTP requests.

# Expected Result

The simulator can register with the message hub, send status and mock GNSS
telemetry, poll pending commands, and return ACKs using `egolink.p0.v1`.

# Acceptance Criteria

- [x] Client builds current protocol heartbeat/status messages.
- [x] Client builds current protocol `location_report` event messages.
- [x] Client polls pending commands.
- [x] Client ACKs commands.
- [x] CLI can run one R0 cycle against a local message hub.

# Validation Commands

```powershell
python -m unittest quality_tests.test_message_hub_client quality_tests.test_message_hub_server -v
python scripts/context_lint.py
```

# Hardware Validation

- Board: not applicable.
- Firmware commit or image: not applicable.
- Connection path: not applicable.
- Evidence path: not applicable.

# Completion Evidence

- Changed files:
  - `README.md`
  - `docs/current/STATUS.md`
  - `docs/tasks/TASK_TREE.md`
  - `docs/tasks/done/SIM-001_PC_SIMULATOR_MESSAGE_HUB_LOOP.md`
  - `pc_simulator/message_hub_client.py`
  - `quality_tests/test_message_hub_client.py`
  - `scripts/run_message_hub_simulator.py`
- Validation result:
  - `python -m unittest quality_tests.test_message_hub_client quality_tests.test_message_hub_server -v`: PASS, 5 tests OK.
  - `python scripts/context_lint.py`: PASS.
  - `python scripts/run_message_hub_simulator.py --hub http://127.0.0.1:8790 --device-id ego-link-r0-cli --create-demo-command --json`: PASS against local Message Hub.
  - `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`: PASS, 201 tests OK.
- Remaining risks:
  - WEB-001 still needs a fuller field-test Dashboard.
  - SERVER-001 still needs credential-safe VPS deployment.
