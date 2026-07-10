---
id: PROTO-001
title: Message Hub Contract Baseline
status: completed
priority: high
requires_hardware: false
created: 2026-06-27
last_updated: 2026-06-27

context:
  - docs/CONTEXT_INDEX.md
  - docs/development/DEV_FLOW.md
  - docs/development/PROTOCOL.md
  - pc_simulator/protocol.py
  - shared/contracts/README.md

allowed_paths:
  - docs/development/PROTOCOL.md
  - docs/tasks/done/
  - quality_tests/
  - shared/contracts/

out_of_scope:
  - firmware behavior changes
  - pc_simulator behavior changes
  - server or web implementation changes
  - VPS deployment
  - hardware validation
---

# Problem

The project needed a frozen P0 message-hub contract before implementing the VPS
message service. Existing code already used `egolink.p0.v1` with
`status` / `event` / `command` / `ack`, so the contract had to preserve that
behavior rather than invent a new incompatible protocol.

# Expected Result

Message-hub JSON schemas exist for status, event, command, ACK, and error
messages, and tests prove current PC Simulator protocol builders still satisfy
the required envelope fields.

# Acceptance Criteria

- [x] Message-hub schema files exist under `shared/contracts/`.
- [x] Schema protocol version is `egolink.p0.v1`.
- [x] Current status/event/command/ack builders match required schema fields.
- [x] Error contract requires diagnosable `error_code` and `severity`.
- [x] Human-readable protocol docs link to the schemas.

# Validation Commands

```powershell
python -m unittest quality_tests.test_message_hub_contracts quality_tests.test_protocol -v
python scripts/context_lint.py
```

# Hardware Validation

- Board: not applicable.
- Firmware commit or image: not applicable.
- Connection path: not applicable.
- Evidence path: not applicable.

# Completion Evidence

- Changed files:
  - `docs/development/PROTOCOL.md`
  - `quality_tests/test_message_hub_contracts.py`
  - `shared/contracts/README.md`
  - `shared/contracts/message_hub_status.schema.json`
  - `shared/contracts/message_hub_event.schema.json`
  - `shared/contracts/message_hub_command.schema.json`
  - `shared/contracts/message_hub_ack.schema.json`
  - `shared/contracts/message_hub_error.schema.json`
  - `docs/tasks/done/PROTO-001_MESSAGE_HUB_CONTRACT_BASELINE.md`
- Validation result:
  - `python -m unittest quality_tests.test_message_hub_contracts quality_tests.test_protocol -v`: PASS, 7 tests OK.
  - `python scripts/context_lint.py`: PASS.
  - `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`: PASS, 196 tests OK.
- Remaining risks:
  - SERVER-001 still needs to implement the VPS service against these schemas.
  - Firmware currently publishes local MQTT status/event messages; public VPS
    topic namespace still needs a Server-Web implementation decision.
