---
id: FIELD-004
title: D1 outdoor multi-hour field run
status: active
priority: high
requires_hardware: true
serves_demo: D1
created: 2026-07-04
last_updated: 2026-07-04

context:
  - docs/product/NORTH_STAR.md
  - docs/development/FIELD_TEST.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - reports/d1_field/d1-outdoor-kit-20260704/FIELD_RUNBOOK.md

allowed_paths:
  - reports/
  - docs/current/STATUS.md
  - docs/tasks/active/FIELD-004_D1_OUTDOOR_MULTI_HOUR_RUN.md

out_of_scope:
  - changing firmware during the field run
  - sending 4G-board serial commands
  - claiming location accuracy or battery life
  - raw private coordinate publication outside bounded evidence
---

# Goal

Run the current D1 link outdoors for 2-3 hours so the founder can judge whether
the LTE upload loop, visible estimate, and power curve are stable enough to keep
building on.

# Operator Setup

- Primary device: `connectivity_node` Waveshare ESP32-S3-SIM7670G-4G.
- Optional companion: AMOLED board on PC USB for live `D1 FIELD` display.
- Normal runtime path: device -> LTE -> VPS Message Hub -> Web Dashboard,
  kept continuously available for ad hoc field checks.
- Evidence path: `reports/d1_field_companion/FIELD-004-<date>/` plus post-run
  Web/API and power reports.

# Normal Always-On Preflight

Before leaving, open `http://203.0.113.10:8790/` and check the `D1 Link
Through` panel:

- `Field Ready ready` and fresh `Upload Freshness` mean the LTE periodic upload
  loop is live enough to start walking.
- `Field Ready stale`, `not ready`, or `waiting` means wait for the next upload
  or check device power, SIM/LTE, and placement before treating the run as live.
- This Web preflight does not claim GNSS accuracy or battery life; it only says
  fresh D1 periodic data is reaching the server.

# Acceptance Criteria

- [ ] Device runs on battery/independent power for 2-3 hours.
- [ ] Dashboard stays usable and shows `Field Ready`, online/stale, upload
      freshness, LTE, location estimate, and power evidence.
- [ ] Field companion report records sample count, stale samples, raw POST
      success/failure delta, coordinate sample count, and power sample count.
- [ ] Post-run D1 Web/API report passes or fails explainably.
- [ ] Post-run power report is generated; it may be WARN/FAIL, but must record
      why.
- [ ] Curated report summaries are synced to the VPS Dashboard `Field Test
      Results` panel.
- [ ] The result does not claim location accuracy or battery life unless a later
      acceptance task defines those metrics.

# Optional Companion Recording

The always-on Web Dashboard is the normal preflight. Run the companion command
when the field session should produce bounded long-run evidence and AMOLED
sidecar visibility.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_d1_field_companion.ps1 `
  -HubUrl http://203.0.113.10:8790 `
  -DurationMinutes 180 `
  -PollIntervalSec 30 `
  -ReadWindowSeconds 8 `
  -SessionId FIELD-004-d1-outdoor-YYYYMMDD `
  -OutputDir reports\d1_field_companion\FIELD-004-d1-outdoor-YYYYMMDD
```

# Post-Run Commands

```powershell
python scripts\validate_d1_web_api.py --hub-url http://203.0.113.10:8790 --review-id FIELD-004-d1-outdoor-YYYYMMDD --output-dir reports\d1_web_api\FIELD-004-d1-outdoor-YYYYMMDD --json

python scripts\analyze_power_curve.py --hub http://203.0.113.10:8790 --test-run-id FIELD-004-d1-outdoor-YYYYMMDD --output-dir reports\power\FIELD-004-d1-outdoor-YYYYMMDD --min-duration-hours 2 --json

python scripts\build_d1_demo_report.py --web-api-report reports\d1_web_api\FIELD-004-d1-outdoor-YYYYMMDD\d1_web_api_report.json --power-curve-report reports\power\FIELD-004-d1-outdoor-YYYYMMDD\power_curve_report.json --report-id FIELD-004-d1-outdoor-YYYYMMDD --output-dir reports\d1_demo\FIELD-004-d1-outdoor-YYYYMMDD --json

python scripts\summarize_data_flywheel.py --run-id FIELD-004-d1-outdoor-YYYYMMDD-data-flywheel --json

powershell -ExecutionPolicy Bypass -File scripts\deploy_message_hub_vps.ps1 -HostName 203.0.113.10 -SshKey $HOME\.ssh\egolink_vps_ed25519 -Public -IncludeFieldReportSummaries -IncludeDataFlywheelSummaries
```

# Completion Evidence

- Changed files:
- Runtime:
- Web/API report:
- Power report:
- VPS Dashboard result visibility:
- Remaining risks:
