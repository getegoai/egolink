---
id: UI-001
title: Field-friendly Web dashboard and AMOLED status screen
status: done
priority: high
requires_hardware: true
serves_demo: D1
created: 2026-07-04
last_updated: 2026-07-04

context:
  - docs/product/NORTH_STAR.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - docs/development/DEV_FLOW.md

allowed_paths:
  - server/message_hub.py
  - firmware/amoled_safety_demo/main/app_main.c
  - scripts/run_amoled_d1_status_sidecar.ps1
  - quality_tests/test_message_hub_dashboard.py
  - quality_tests/test_amoled_safety_demo_firmware.py
  - quality_tests/test_amoled_d1_status_sidecar_script.py
  - docs/current/
  - docs/tasks/done/UI-001_FIELD_FRIENDLY_WEB_AMOLED_UI.md

out_of_scope:
  - changing public Message Hub API contracts
  - changing 4G connectivity-node firmware behavior
  - changing pin assignments or hardware control behavior
  - implementing calling or SMS
  - claiming GNSS accuracy, battery life, or product readiness
  - deploying to VPS unless separately validated and recorded
---

# Problem

The D1 Web dashboard already exposes the required live evidence, but the
highest-priority field signals are buried in long metric lists. The AMOLED
companion screen renders the same status as plain centered text, which is hard
to scan while carrying the device outdoors.

# Expected Result

Make both views friendlier for several-hour field tests without changing the
underlying D1 protocol:

- Web dashboard presents D1 first, with a map surface, status strip, and grouped
  location/uplink/power/evidence sections.
- AMOLED `display_status` renders a compact D1 field status screen with clear
  labels for link, location, power, and upload status.
- The sidecar payload remains finite, read-only, and suitable for a small
  display.

# Acceptance Criteria

- [x] `render_dashboard()` keeps existing D1 markers while adding stable,
      scan-friendly D1 layout markers.
- [x] AMOLED firmware keeps `ask_user`, `status_update`, and `display_status`
      contract behavior, while `display_status` is visually structured for D1.
- [x] The AMOLED sidecar still reads `/api/state`, sends only `display_status`
      over the AMOLED serial bridge, and does not contact the 4G board or issue
      Message Hub commands.
- [x] Focused UI/server/firmware tests pass.
- [x] `python scripts/context_lint.py` passes.
- [x] If firmware is changed, ESP-IDF build passes and a bounded AMOLED smoke is
      recorded when hardware is available.
- [x] `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1` passes when
      time allows.

# Validation Commands

```powershell
python -m unittest quality_tests.test_message_hub_dashboard quality_tests.test_amoled_safety_demo_firmware quality_tests.test_amoled_d1_status_sidecar_script -v
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `server/message_hub.py`,
  `firmware/amoled_safety_demo/main/app_main.c`,
  `scripts/run_amoled_d1_status_sidecar.ps1`, focused tests, this task packet,
  and `docs/current/STATUS.md`.
- Test result: focused UI/AMOLED tests passed (17 tests);
  `python scripts/context_lint.py` passed; `python -m py_compile
  server/message_hub.py` passed; `powershell -ExecutionPolicy Bypass -File
  scripts\verify.ps1` passed with 387 tests.
- Web deployment result: `scripts/deploy_message_hub_vps.ps1 -HostName
  203.0.113.10 -SshKey <local ignored key> -Public` deployed the Message Hub,
  restarted `egolink-message-hub.service` on `0.0.0.0:8790`, and did not modify
  GitLab. `/health` returned `ok=true`, unauthenticated `/api/state` returned
  `401`, Dashboard HTML contained the new D1 UI markers, and read-only D1
  Web/API gate `ui001-web-vps-20260704` passed.
- Hardware result: ESP-IDF v5.4.2 AMOLED build passed; flashing to `COM9`
  passed for ESP32-S3 MAC `02:00:00:00:00:01`; bounded smoke
  `ui001-amoled-friendly-smoke-20260704` passed with
  `command_ack_count=1` and `status_rendered_count=1`.
- Evidence path:
  `reports/d1_web_api/ui001-web-vps-20260704/d1_web_api_report.md`;
  `reports/amoled_visible_status/ui001-amoled-friendly-smoke-20260704/ui001-amoled-friendly-smoke-20260704.summary.json`.
- Remaining risks: Codex in-app browser was unavailable, so no screenshot
  evidence was captured; AMOLED visual layout should still be operator-observed
  on the physical screen. This task does not claim GNSS accuracy, battery life,
  USB-Free display acceptance, calling/SMS, or product readiness.
