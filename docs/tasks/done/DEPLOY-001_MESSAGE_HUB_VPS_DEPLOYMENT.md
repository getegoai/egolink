---
id: DEPLOY-001
title: Message Hub VPS Deployment
status: completed
priority: high
requires_hardware: false
created: 2026-06-27
last_updated: 2026-06-27

context:
  - docs/CONTEXT_INDEX.md
  - docs/development/DEV_FLOW.md
  - docs/development/VPS_MESSAGE_HUB.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/tasks/done/SERVER-001_VPS_MESSAGE_SERVICE_MINIMAL_LOOP.md
  - docs/tasks/done/SIM-001_PC_SIMULATOR_MESSAGE_HUB_LOOP.md
  - docs/tasks/done/WEB-001_MESSAGE_HUB_DASHBOARD_BASELINE.md

allowed_paths:
  - docs/current/
  - docs/tasks/
  - quality_tests/
  - scripts/
  - server/

out_of_scope:
  - firmware behavior changes
  - hardware validation
  - GitLab changes on the VPS
  - storing real VPS passwords or bearer tokens in the repository
---

# Problem

The Walking Skeleton needed a real USB-Free message path on an
operator-provided VPS, not only a local service.

# Expected Result

The Message Hub is deployed as a systemd service on the operator-provided VPS,
listens on the field-test HTTP port, protects API access with a bearer token,
and accepts the PC Simulator R0 loop over the public VPS path.

# Acceptance Criteria

- [x] SSH key authentication works without persisting the VPS password.
- [x] `egolink-message-hub.service` is installed and active.
- [x] Service listens on `0.0.0.0:8790`.
- [x] `/health` is reachable over the VPS path.
- [x] `/api/state` returns `401` without a bearer token.
- [x] `/api/state` works with the bearer token.
- [x] PC Simulator completes register, heartbeat, mock GNSS location report,
      command polling, and ACK over the VPS path.
- [x] GitLab on the VPS is not modified.

# Validation Commands

```powershell
python -m unittest quality_tests.test_message_hub_dashboard quality_tests.test_message_hub_server quality_tests.test_message_hub_client -v
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
python scripts/run_message_hub_simulator.py --hub http://<operator-vps>:8790 --device-id ego-link-r0-vps-auth-smoke --create-demo-command --json
```

# Hardware Validation

- Board: not applicable.
- Firmware commit or image: not applicable.
- Connection path: not applicable.
- Evidence path: not applicable.

# Completion Evidence

- Changed files:
  - `docs/current/STATUS.md`
  - `docs/tasks/TASK_TREE.md`
  - `docs/tasks/done/DEPLOY-001_MESSAGE_HUB_VPS_DEPLOYMENT.md`
  - `quality_tests/test_message_hub_dashboard.py`
  - `quality_tests/test_message_hub_server.py`
  - `scripts/deploy_message_hub_vps.ps1`
  - `server/message_hub.py`
- Runtime evidence:
  - Remote systemd unit: `/etc/systemd/system/egolink-message-hub.service`.
  - Remote SQLite DB: `/var/lib/egolink-message-hub/message_hub.db`.
  - Remote bearer-token env file: `/etc/egolink-message-hub.env`, mode `600`.
  - Local ignored token note: `server/runtime/vps_message_hub_token.txt`.
- Validation result:
  - SSH key login: PASS.
  - Remote service: PASS, `egolink-message-hub.service` active.
  - Public listen: PASS, `0.0.0.0:8790`.
  - Public `/health`: PASS.
  - Unauthenticated `/api/state`: PASS, returns `401`.
  - Authenticated `/api/state`: PASS.
  - PC Simulator VPS loop: PASS for `ego-link-r0-vps-auth-smoke`.
  - `python -m unittest quality_tests.test_message_hub_dashboard quality_tests.test_message_hub_server quality_tests.test_message_hub_client -v`: PASS, 8 tests.
  - `python scripts/context_lint.py`: PASS.
  - `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`: PASS, 204 tests.
- Remaining risks:
  - The service is still HTTP-only and should move behind HTTPS or a tunnel
    before longer public field trials.
  - The browser dashboard stores the bearer token in browser localStorage.
  - Real hardware heartbeat/ACK is still `FW-001`; this task used PC Simulator
    only.
