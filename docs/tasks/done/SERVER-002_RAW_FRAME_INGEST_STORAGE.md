---
id: SERVER-002
title: Raw Frame Ingest And Storage
status: completed
priority: high
requires_hardware: false
created: 2026-06-29
last_updated: 2026-06-29
completed_at: 2026-06-29

context:
  - docs/CONTEXT_INDEX.md
  - docs/development/VPS_MESSAGE_HUB.md
  - docs/development/PROTOCOL.md
  - docs/tasks/active/PROTO-002_RAW_FRAME_TRANSPORT_CONTRACT.md
  - shared/contracts/message_hub_raw_frame_record.schema.json
  - server/message_hub.py
  - quality_tests/test_message_hub_server.py

allowed_paths:
  - docs/current/STATUS.md
  - docs/development/VPS_MESSAGE_HUB.md
  - docs/tasks/TASK_TREE.md
  - docs/tasks/active/SERVER-002_RAW_FRAME_INGEST_STORAGE.md
  - quality_tests/test_message_hub_server.py
  - server/message_hub.py

out_of_scope:
  - firmware behavior changes
  - hardware flashing or validation
  - VPS deployment
  - changing GitLab or unrelated VPS services
  - removing existing JSON endpoints
  - storing real private logs or credentials in the repository
---

# SERVER-002 Raw Frame Ingest And Storage

## Problem

PROTO-002 defines a raw-frame-first transport direction, but the Message Hub
must be able to store raw frames before firmware can rely on that path.

## Expected Result

The standard-library Message Hub can accept HTTP-carried raw frames, store the
original payload bytes and parse status in SQLite, expose recent raw records
for field-test/debug use, and still derive existing command/ACK JSON views for
Web/API compatibility where possible.

## Acceptance Criteria

- [x] SQLite has a durable raw-frame table separate from parsed messages.
- [x] `POST /api/v1/devices/{device_id}/raw-ingest` stores raw bytes before
      semantic parsing.
- [x] Malformed, checksum-failed, unsupported, and partial frames are retained
      with parse status instead of dropped.
- [x] `GET /api/v1/devices/{device_id}/raw-frames` exposes metadata and parser
      status without requiring raw private payload display.
- [x] Raw command polling and raw ACK endpoints are available for the next
      firmware slice while legacy JSON endpoints remain intact.

## Validation Commands

```powershell
python -m unittest quality_tests.test_message_hub_server quality_tests.test_message_hub_contracts -v
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

## Hardware Validation

- Board: not applicable for this server slice.
- Firmware commit or image: not applicable for this server slice.
- Connection path: not applicable for this server slice.
- Evidence path: not applicable for this server slice.

## Completion Notes

This task is the server half of the raw-frame pivot. Firmware raw-frame
generation and USB-Free LTE validation remain separate follow-up tasks.

## Completion Evidence

- Changed files:
  - `server/message_hub.py`
  - `quality_tests/test_message_hub_server.py`
  - `docs/development/VPS_MESSAGE_HUB.md`
  - `docs/current/STATUS.md`
  - `docs/tasks/TASK_TREE.md`
  - `docs/tasks/done/SERVER-002_RAW_FRAME_INGEST_STORAGE.md`
- Validation result:
  - `python -m unittest quality_tests.test_message_hub_server -v`: PASS, 12 tests.
  - `python -m unittest quality_tests.test_message_hub_contracts -v`: PASS, 7 tests.
  - `python scripts/context_lint.py`: PASS.
  - `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`: PASS, 278 tests.
  - `git diff --check`: PASS.
- Hardware result: not applicable; no hardware action was performed.
- Deployment result: not deployed to the VPS in this step.
- Remaining risks:
  - Firmware does not yet emit or ACK raw frames.
  - The VPS service must still be redeployed before remote devices can use the
    new raw-frame routes.
