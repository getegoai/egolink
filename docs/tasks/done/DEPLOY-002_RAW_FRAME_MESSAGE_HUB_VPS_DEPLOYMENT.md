---
id: DEPLOY-002
title: Raw Frame Message Hub VPS Deployment
status: completed
priority: high
requires_hardware: false
created: 2026-06-29
completed_at: 2026-06-29
last_updated: 2026-06-29

context:
  - docs/CONTEXT_INDEX.md
  - docs/development/VPS_MESSAGE_HUB.md
  - docs/tasks/done/SERVER-002_RAW_FRAME_INGEST_STORAGE.md
  - scripts/deploy_message_hub_vps.ps1

allowed_paths:
  - docs/current/STATUS.md
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/DEPLOY-002_RAW_FRAME_MESSAGE_HUB_VPS_DEPLOYMENT.md

out_of_scope:
  - firmware behavior changes
  - hardware flashing or validation
  - changing GitLab or unrelated VPS services
  - storing real VPS passwords or bearer tokens in the repository
---

# DEPLOY-002 Raw Frame Message Hub VPS Deployment

## Problem

SERVER-002 added raw-frame storage and routes locally. The USB-Free message
path needed the same Message Hub build on the operator VPS before firmware can
use raw command polling in field tests.

## Expected Result

The VPS `egolink-message-hub.service` runs the SERVER-002 build, still listens
on the existing field-test port, keeps bearer-token API protection, and accepts
raw command poll plus raw ACK over the public path.

## Acceptance Criteria

- [x] Existing GitLab service/files are not modified.
- [x] `egolink-message-hub.service` restarts successfully.
- [x] Service listens on `0.0.0.0:8790`.
- [x] `/health` is reachable over the VPS path.
- [x] `/api/state` returns `401` without a bearer token.
- [x] Authenticated `/api/state` includes `raw_frames`.
- [x] `GET /commands/poll.raw` returns an `EGLK/1` raw command frame.
- [x] `POST /commands/{cmd_id}/ack.raw` stores a raw ACK and updates the
      command status to `ok`.

## Validation Commands

```powershell
$env:EGOLINK_MESSAGE_HUB_TOKEN = (Get-Content -LiteralPath server/runtime/vps_message_hub_token.txt -Raw).Trim()
powershell -ExecutionPolicy Bypass -File scripts\deploy_message_hub_vps.ps1 -HostName 203.0.113.10 -SshKey "$HOME\.ssh\egolink_vps_ed25519" -Public
```

The remote smoke used Python stdlib HTTP calls with the token loaded from the
ignored local token file. The token value was not printed or committed.

## Hardware Validation

- Board: not applicable.
- Firmware commit or image: not applicable.
- Connection path: not applicable.
- Evidence path: not applicable.

## Completion Evidence

- Remote service: `egolink-message-hub.service` active after restart.
- Remote listen: `0.0.0.0:8790`.
- Public `/health`: PASS.
- Unauthenticated `/api/state`: PASS, returned `401`.
- Authenticated `/api/state`: PASS, response includes `raw_frames`.
- Raw-frame smoke:
  - Device ID: `ego-link-r0-raw-vps-smoke`.
  - Test run ID: `raw-frame-vps-smoke-20260629-174047`.
  - `GET /api/v1/devices/ego-link-r0-raw-vps-smoke/commands/poll.raw`:
    PASS, HTTP 200, content type `text/x-egolink-frame; profile=raw-frame.p0.v1`,
    body starts with `EGLK/1 type=command`.
  - `POST /api/v1/devices/ego-link-r0-raw-vps-smoke/commands/{cmd_id}/ack.raw`:
    PASS, `ack_parse_status=ok`, command status `ok`.
  - Raw frame records: PASS, two latest raw frames with parse status `ok`.
- Remaining risks:
  - Firmware does not yet emit raw frames.
  - This deployment is still HTTP-only and should move behind HTTPS or a tunnel
    before longer public field trials.
