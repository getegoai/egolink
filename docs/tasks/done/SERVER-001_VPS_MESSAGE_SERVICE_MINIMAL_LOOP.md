---
id: SERVER-001
title: VPS Message Service Minimal Loop
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
  - docs/current/ROADMAP_EGOLINK_P0.md
  - shared/contracts/

allowed_paths:
  - .gitignore
  - README.md
  - docs/current/
  - docs/tasks/
  - quality_tests/
  - scripts/
  - server/

out_of_scope:
  - firmware behavior changes
  - pc_simulator behavior changes
  - shared contract changes
  - VPS deployment
  - GitLab changes on the VPS
  - hardware validation
  - storing real credentials
---

# Problem

R0 needed a minimal deployable message service before PC Simulator and later
firmware could use the USB-Free VPS path.

# Expected Result

A dependency-free HTTP service can run locally or on the VPS, store messages in
SQLite, expose the minimal API from `VPS_MESSAGE_HUB.md`, and show a tiny
browser dashboard for device/message inspection.

# Acceptance Criteria

- [x] Service supports device registration.
- [x] Service accepts heartbeat/status and telemetry/event messages.
- [x] Service stores commands and exposes command polling.
- [x] Service accepts ACK and updates command status.
- [x] Service accepts diagnosable errors.
- [x] Service exposes device list, latest/history telemetry, test-run records,
      `/health`, `/api/state`, and a minimal dashboard.
- [x] Runtime DB lives under ignored `server/runtime/`.
- [x] VPS deployment script exists without storing passwords.
- [x] No VPS credentials are stored and no remote deployment is performed.

# Validation Commands

```powershell
python -m unittest quality_tests.test_message_hub_server quality_tests.test_message_hub_contracts -v
python scripts/context_lint.py
```

# Hardware Validation

- Board: not applicable.
- Firmware commit or image: not applicable.
- Connection path: not applicable.
- Evidence path: not applicable.

# Completion Evidence

- Changed files:
  - `.gitignore`
  - `README.md`
  - `docs/current/STATUS.md`
  - `docs/tasks/TASK_TREE.md`
  - `docs/tasks/done/SERVER-001_VPS_MESSAGE_SERVICE_MINIMAL_LOOP.md`
  - `quality_tests/test_message_hub_server.py`
  - `scripts/deploy_message_hub_vps.ps1`
  - `scripts/run_message_hub.py`
  - `server/.env.example`
  - `server/__init__.py`
  - `server/message_hub.py`
- Validation result:
  - `python -m unittest quality_tests.test_message_hub_server quality_tests.test_message_hub_contracts -v`: PASS, 7 tests OK.
  - `python scripts/context_lint.py`: PASS.
  - `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`: PASS, 201 tests OK.
- Remaining risks:
  - SIM-001 still needs a PC Simulator client loop against this HTTP service.
  - VPS deployment needs an operator-approved credential-safe path and must not
    modify existing GitLab.
