---
id: FIELD-004
title: D1 outdoor multi-hour field run
status: active
priority: high
requires_hardware: true
serves_demo: D1
created: 2026-07-04
last_updated: 2026-07-08

context:
  - docs/product/NORTH_STAR.md
  - docs/development/FIELD_TEST.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - reports/d1_field/FIELD-004-d1-acceptance-20260708-4h/FIELD_RUNBOOK.md

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

本任务服务于 D1；当前最低未验收 Demo 是 D1；n == m，且本任务是 D1 验收的直接执行项。

# Goal

Run the current D1 link outdoors for 3-4 hours so the founder can judge whether
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
- `Coordinate data` shows how many location uploads include latitude/longitude.
  If it is `0 / N` with `Latest missing reason` like
  `cell_observation_without_position_fix` or `gnss_no_fix`, go outdoors and
  wait until at least two coordinate-bearing uploads appear.
- This Web preflight does not claim GNSS accuracy or battery life; it only says
  fresh D1 periodic data is reaching the server.

# Acceptance Criteria

- [ ] Device runs on battery/independent power for 3-4 hours.
- [ ] Dashboard stays usable and shows `Field Ready`, online/stale, upload
      freshness, LTE, location estimate, and power evidence.
- [ ] Dashboard D1 map view shows position points plus a trajectory line from
      recent coordinate-bearing uploads. The D1 Web/API gate must fail
      explainably if fewer than two map points are available, including the
      latest missing-coordinate reason when uploads arrive without lat/lon.
- [ ] Field companion report records sample count, stale samples, raw POST
      success/failure delta, coordinate sample count, and power sample count.
- [ ] Post-run collector summary records Web/API, power, one-page D1 demo
      report, field-observation binding, and bounded artifact summary paths.
- [ ] Post-run D1 Web/API report passes or fails explainably.
- [ ] Post-run power report is generated; it may be WARN/FAIL, but must record
      why.
- [ ] Curated report summaries are synced to the VPS Dashboard `Field Test
      Results` panel.
- [ ] Founder reviews the one-page D1 report; only after acceptance, tag
      `v0.1.0`.
- [ ] The result does not claim location accuracy or battery life unless a later
      acceptance task defines those metrics.
- [ ] Data flywheel, labeling, `MODEL-DEVICE`, `DATA`, and `TRAIN` work remain
      frozen until D2 is accepted.

# Optional Companion Recording

The always-on Web Dashboard is the normal preflight. Run the companion command
when the field session should produce bounded long-run evidence and AMOLED
sidecar visibility.

For the next planned run, use the generated kit:

- Run ID: `FIELD-004-d1-acceptance-20260708-4h`
- Runbook: `reports\d1_field\FIELD-004-d1-acceptance-20260708-4h\FIELD_RUNBOOK.md`
- Checklist: `reports\d1_field\FIELD-004-d1-acceptance-20260708-4h\FIELD_CHECKLIST.md`

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_d1_field_companion.ps1 `
  -HubUrl http://203.0.113.10:8790 `
  -TokenFile server/runtime/vps_message_hub_token.txt `
  -RunId FIELD-004-d1-acceptance-20260708-4h `
  -DeviceId ego-link-r1-connectivity-001 `
  -DurationMinutes 240 `
  -PollIntervalSec 60 `
  -AmoledReadWindowSeconds 10 `
  -OutputRoot reports\d1_field_companion
```

# Post-Run Commands

Recommended one-command collection after returning. The generated v17 runbook
above is the source of exact field-observation report/status paths. This command
explicitly skips data-flywheel, labeling, and training outputs until D2 is
accepted.

```powershell
python scripts\collect_d1_postrun.py `
  --run-id FIELD-004-d1-acceptance-20260708-4h `
  --hub-url http://203.0.113.10:8790 `
  --token-file server/runtime/vps_message_hub_token.txt `
  --device-id ego-link-r1-connectivity-001 `
  --message-test-run-id FIELD-004-d1-acceptance-20260708-4h `
  --min-duration-hours 4 `
  --output-root reports\d1_postrun `
  --web-api-output-dir reports\d1_web_api\FIELD-004-d1-acceptance-20260708-4h `
  --power-output-dir reports\power\FIELD-004-d1-acceptance-20260708-4h `
  --d1-demo-output-dir reports\d1_demo\FIELD-004-d1-acceptance-20260708-4h `
  --field-observation-report reports\d1_field_observation\FIELD-004-d1-acceptance-20260708-4h\d1_field_observation_report.json `
  --field-observation-status reports\d1_field_observation\FIELD-004-d1-acceptance-20260708-4h\d1_field_observation_status.json `
  --skip-data-flywheel `
  --skip-training-chain `
  --skip-training-readiness `
  --skip-labeling-intake `
  --skip-labeling-queue `
  --skip-labeling-review-packet `
  --skip-labeling-decision-template `
  --skip-labeling-decision-validation `
  --json
```

Use the component commands below only when rerunning or troubleshooting one
step:

```powershell
python scripts\validate_d1_web_api.py --hub-url http://203.0.113.10:8790 --review-id FIELD-004-d1-acceptance-20260708-4h --output-dir reports\d1_web_api\FIELD-004-d1-acceptance-20260708-4h --json

python scripts\analyze_power_curve.py --hub http://203.0.113.10:8790 --test-run-id FIELD-004-d1-acceptance-20260708-4h --output-dir reports\power\FIELD-004-d1-acceptance-20260708-4h --min-duration-hours 4 --json

python scripts\build_d1_demo_report.py --web-api-report reports\d1_web_api\FIELD-004-d1-acceptance-20260708-4h\d1_web_api_report.json --power-curve-report reports\power\FIELD-004-d1-acceptance-20260708-4h\power_curve_report.json --report-id FIELD-004-d1-acceptance-20260708-4h --output-dir reports\d1_demo\FIELD-004-d1-acceptance-20260708-4h --json

powershell -ExecutionPolicy Bypass -File scripts\deploy_message_hub_vps.ps1 -HostName 203.0.113.10 -SshKey $HOME\.ssh\egolink_vps_ed25519 -Public -IncludeFieldReportSummaries
```

# Acceptance Tag

After the founder accepts the one-page D1 report:

```powershell
git tag -a v0.1.0 -m "D1 link-through accepted"
```

# Progress Evidence

- 2026-07-08 Director reset:
  - Current lowest unaccepted demo is D1; this task is the D1 acceptance path.
  - Generated D1-only field kit v17:
    `reports/d1_field/FIELD-004-d1-acceptance-20260708-4h/`.
  - D1 Dashboard map point plus recent trajectory is now a D1 Web/API
    acceptance gate.
  - Data flywheel, labeling, `MODEL-DEVICE`, `DATA`, and `TRAIN` work is
    explicitly frozen until D2 is accepted; existing assets are retained for
    later reuse.
- 2026-07-05 unattended read-only D1 observation:
  - Board/device: `connectivity-node-001` /
    `ego-link-r1-connectivity-001`.
  - Firmware reported by server: `0.1.0-d1-periodic-location`.
  - Connection path: device -> LTE/network -> VPS Message Hub -> Web/API.
  - Evidence:
    `reports/d1_field_observation/FIELD-004-d1-outdoor-unattended-20260705-140133/d1_field_observation_report.json`
    and `.md`, plus `d1_field_samples.jsonl`.
  - Result: `WARN`; the observer read the VPS API successfully for 181/181
    samples over roughly 3 hours, but the latest D1 upload did not advance.
  - Key facts: coordinate samples 181; upload window stayed at
    `2026-07-05T06:00:21.377132+00:00`; max freshness reached `10934.0 s`;
    location event delta `0`; raw POST delta `0 ok / 0 fail`; power sample
    delta `0`; battery stayed `4276 mV / 100%` in the stale server view.
  - Warnings: `d1_upload_freshness_exceeded_threshold` and
    `d1_location_event_count_did_not_advance`.
- 2026-07-05 post-deploy Message Hub stability observation:
  - Evidence:
    `reports/message_hub_stability/DATA-007-post-deploy-stability-20260705-1430/stability_observation_report.json`
    and `.md`, plus `device_snapshots.json`.
  - Result: `FAIL`; the server stayed reachable, but this observation saw
    `0` new telemetry-history messages for `ego-link-r1-connectivity-001`, and
    final `last_seen_at` age was `10737.3 s`.
  - The script is observation-only and did not enqueue commands.
- Final read-only API check on 2026-07-05T17:06+08:00:
  - `last_seen_at=2026-07-05T06:01:03.386419+00:00`, `last_seq=9275`,
    `field_readiness.reason=periodic_upload_too_old`, upload freshness about
    `11214 s`, and `training_experiment.status=blocked_dataset_not_ready`.
  - Interpretation: the VPS and Dashboard are running, but the D1 device should
    be treated as stale until a new Dashboard upload appears before departure.

# Completion Evidence

- Changed files:
- Runtime:
- Post-run collector:
- Web/API report:
- Power report:
- VPS Dashboard result visibility:
- Remaining risks:
