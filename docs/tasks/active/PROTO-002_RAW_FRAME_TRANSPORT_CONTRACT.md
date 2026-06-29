---
id: PROTO-002
title: Raw Frame Transport Contract
status: active
priority: high
requires_hardware: false
created: 2026-06-29
last_updated: 2026-06-29

context:
  - docs/CONTEXT_INDEX.md
  - docs/development/DEV_FLOW.md
  - docs/development/PROTOCOL.md
  - docs/development/LTE_TRANSPORT.md
  - docs/development/VPS_MESSAGE_HUB.md
  - shared/contracts/README.md

allowed_paths:
  - docs/current/STATUS.md
  - docs/development/PROTOCOL.md
  - docs/development/LTE_TRANSPORT.md
  - docs/development/VPS_MESSAGE_HUB.md
  - docs/tasks/TASK_TREE.md
  - docs/tasks/active/PROTO-002_RAW_FRAME_TRANSPORT_CONTRACT.md
  - docs/tasks/active/LTE-003_LTE_HTTP_COMMAND_POLL_ACK.md
  - quality_tests/test_message_hub_contracts.py
  - shared/contracts/README.md
  - shared/contracts/message_hub_raw_frame_record.schema.json

out_of_scope:
  - firmware flashing
  - hardware validation
  - changing GitLab or unrelated VPS services
  - deleting existing egolink.p0.v1 JSON APIs
  - storing real private user data or private device logs in the repository
---

# PROTO-002 Raw Frame Transport Contract

## Problem

LTE-003 fix7/fix8 showed that the current device-side JSON command-poll path
can make the main link depend on fragile body extraction and full JSON parsing
inside firmware. Even when the server returns a valid command response, a
single partial read or parse error can erase the useful evidence unless the
raw transfer is captured first.

## Goal

Define a P0 raw-frame transport profile where the device/server runtime path
preserves original bytes before parsing, while the existing Web and Message Hub
JSON views remain derived compatibility APIs.

## Contract Principles

- The server stores every ingress raw frame before semantic parsing.
- Incomplete, malformed, checksum-failed, and unsupported frames are retained
  as raw records with a parse/checksum status.
- Device firmware must parse only a small stable frame header and checksum for
  the P0 command path; full JSON parsing is not required for normal runtime.
- Downlink command payloads use compact raw payloads, such as ASCII key/value
  lines or future TLV, instead of JSON objects.
- Existing `egolink.p0.v1` status/event/command/ack schemas remain the
  server/Web derived view until a later versioned API migration is justified.

## Expected Shape

The raw HTTP profile should add versioned endpoints or content negotiation for
raw frames, for example:

```text
POST /api/v1/devices/{device_id}/raw-ingest
GET  /api/v1/devices/{device_id}/commands/poll.raw
POST /api/v1/devices/{device_id}/commands/{cmd_id}/ack.raw
```

The wire frame starts with a small ASCII header and a blank line, followed by
the exact payload bytes:

```text
EGLK/1 type=command id=cmd-000013 seq=13 len=37 crc32=2A4F8C91
content-type=text/x-egolink-kv

cmd=set_report_interval
interval_ms=5000
```

The server-side durable record is represented by
`shared/contracts/message_hub_raw_frame_record.schema.json`. That schema is a
storage and parser-result contract; it does not mean the device sends JSON.

## Acceptance Criteria

- [ ] Human-readable protocol docs define raw-frame preservation, checksum,
      parse status, and derived JSON boundaries.
- [ ] Machine-readable raw-frame record schema is versioned under
      `shared/contracts/`.
- [ ] Message Hub implementation stores raw ingress bytes before parsing.
- [ ] Dashboard/test-run export can show raw-frame parse status without
      requiring raw private payload display.
- [ ] A firmware slice can poll and ACK `set_report_interval` through the raw
      command profile with USB disconnected at runtime.

## Validation Commands

```powershell
python -m unittest quality_tests.test_message_hub_contracts -v
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

## Hardware Validation

- Board: not applicable for this contract baseline.
- Firmware commit or image: not applicable for this contract baseline.
- Connection path: not applicable for this contract baseline.
- Evidence path: not applicable for this contract baseline.

## Completion Notes

This task intentionally pauses the JSON-only LTE-003 acceptance path. The next
implementation slice should be `SERVER-002` raw-frame ingest/storage plus
`FW-003` raw command poll/ACK, or equivalent task IDs if the task tree already
allocates those names.
