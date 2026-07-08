# D1 Outdoor Field Runbook

> Status: operator runbook and evidence manifest, not hardware evidence.

## Purpose

Serve D1 by running the 4G board on independent power for a multi-hour outdoor shakedown:
GNSS/cell/IMU/power collection -> LTE upload -> server location estimate -> Dashboard map visible.
Accuracy and battery life are explicitly out of scope for this run.

## Identifiers

- Run ID: `FIELD-004-d1-acceptance-20260708-4h`
- Kit version: `D1.field_kit.v17`
- Hub URL: `http://203.0.113.10:8790`
- Device ID: `ego-link-r1-connectivity-001`
- Board ID: `connectivity-node-001`
- Firmware version: `0.1.0-d1-periodic-location`
- Target duration: `4.0 h`
- Location upload interval: `60 s`
- AMOLED port: `auto-detect`
- Board revision: `V2`
- MAX17048 pins: SDA GPIO15 / SCL GPIO16
- Token file reference: `server/runtime/vps_message_hub_token.txt`

## Before Leaving

- [ ] Message Hub health endpoint and Dashboard are reachable from phone.
- [ ] Token is available via local token file or EGOLINK_MESSAGE_HUB_TOKEN, outside git.
- [ ] Run the read-only preflight Web/API gate and confirm D1 state is fresh.
- [ ] Run the AMOLED visible-status preflight and confirm the screen shows the D1 status page.
- [ ] Board revision and MAX17048 SDA/SCL pins are recorded.
- [ ] Firmware commit or binary path is recorded in OPERATOR_NOTES.md.
- [ ] D1 field image is built; flashing is complete only if explicitly intended by the operator.
- [ ] SIM/network path, GNSS antenna, battery, and cable strain relief are ready.
- [ ] Run ID, device ID, firmware version, and target evidence folders are copied to the phone or notes.
- [ ] Calling and SMS are not part of this run and must not be claimed.

### Preflight Web/API Gate

Read-only check that the VPS D1 surface is reachable and current enough to review.

```powershell
python `
  scripts\validate_d1_web_api.py `
  --hub-url `
  http://203.0.113.10:8790 `
  --token-file `
  server/runtime/vps_message_hub_token.txt `
  --review-id `
  FIELD-004-d1-acceptance-20260708-4h-preflight `
  --output-dir `
  reports\d1_web_api\FIELD-004-d1-acceptance-20260708-4h-preflight `
  --device-id `
  ego-link-r1-connectivity-001 `
  --json
```

### Preflight AMOLED Visible Status

Confirm the sidecar screen visibly switches to the D1 status page before leaving.
The sidecar runner sends the `display_status` command to force the full-screen status view.

```powershell
powershell `
  -NoProfile `
  -ExecutionPolicy `
  Bypass `
  -File `
  scripts\run_amoled_d1_status_sidecar.ps1 `
  -HubUrl `
  http://203.0.113.10:8790 `
  -TokenFile `
  server/runtime/vps_message_hub_token.txt `
  -SampleCount `
  1 `
  -PollIntervalSec `
  0 `
  -ReadWindowSeconds `
  10 `
  -SessionId `
  FIELD-004-d1-acceptance-20260708-4h-preflight-amoled `
  -OutputDir `
  reports\amoled_visible_status\FIELD-004-d1-acceptance-20260708-4h\preflight `
  -Reset
```

### Build Or Refresh Firmware Image

This command does not flash firmware.

```powershell
powershell `
  -ExecutionPolicy `
  Bypass `
  -File `
  scripts\run_fw001_hw_r1.ps1 `
  -HostName `
  203.0.113.10 `
  -Port `
  8790 `
  -Scheme `
  http `
  -DeviceId `
  ego-link-r1-connectivity-001 `
  -FwVersion `
  0.1.0-d1-periodic-location `
  -TestRunId `
  FIELD-004-d1-acceptance-20260708-4h `
  -TokenFile `
  server/runtime/vps_message_hub_token.txt `
  -EnableSim7670Gnss `
  -EnableSim7670LteStatus `
  -EnableSim7670LteHttpCommandLoop `
  -EnableSim7670LocationObservation `
  -EnableD1PeriodicLocation `
  -D1PeriodicLocationIntervalSec `
  60 `
  -EnableMax17048Power `
  -Max17048SdaGpio `
  15 `
  -Max17048SclGpio `
  16 `
  -PrepareBuild `
  -Json
```

### Flash Only With Explicit Operator Intent

Replace `<COMx>` with the observed ESP32-S3 console port only when you intend to write firmware.

```powershell
powershell `
  -ExecutionPolicy `
  Bypass `
  -File `
  scripts\run_fw001_hw_r1.ps1 `
  -HostName `
  203.0.113.10 `
  -Port `
  8790 `
  -Scheme `
  http `
  -DeviceId `
  ego-link-r1-connectivity-001 `
  -FwVersion `
  0.1.0-d1-periodic-location `
  -TestRunId `
  FIELD-004-d1-acceptance-20260708-4h `
  -TokenFile `
  server/runtime/vps_message_hub_token.txt `
  -EnableSim7670Gnss `
  -EnableSim7670LteStatus `
  -EnableSim7670LteHttpCommandLoop `
  -EnableSim7670LocationObservation `
  -EnableD1PeriodicLocation `
  -D1PeriodicLocationIntervalSec `
  60 `
  -EnableMax17048Power `
  -Max17048SdaGpio `
  15 `
  -Max17048SclGpio `
  16 `
  -PrepareBuild `
  -Flash `
  -FlashPort `
  <COMx> `
  -IUnderstandFlashWritesFirmware `
  -Json
```

## Start Run

- [ ] Confirm independent battery or power-bank supply.
- [ ] Disconnect USB before counting runtime evidence.
- [ ] Record local and UTC start time.
- [ ] Confirm Dashboard D1 panel becomes fresh before walking away.

Optional short check after USB is disconnected:

```powershell
powershell `
  -ExecutionPolicy `
  Bypass `
  -File `
  scripts\run_fw001_hw_r1.ps1 `
  -HostName `
  203.0.113.10 `
  -Port `
  8790 `
  -Scheme `
  http `
  -DeviceId `
  ego-link-r1-connectivity-001 `
  -FwVersion `
  0.1.0-d1-periodic-location `
  -TestRunId `
  FIELD-004-d1-acceptance-20260708-4h `
  -TokenFile `
  server/runtime/vps_message_hub_token.txt `
  -EnableSim7670Gnss `
  -EnableSim7670LteStatus `
  -EnableSim7670LteHttpCommandLoop `
  -EnableSim7670LocationObservation `
  -EnableD1PeriodicLocation `
  -D1PeriodicLocationIntervalSec `
  60 `
  -EnableMax17048Power `
  -Max17048SdaGpio `
  15 `
  -Max17048SclGpio `
  16 `
  -Validate `
  -OperatorConfirmedIndependentPower `
  -OperatorConfirmedUsbDisconnected `
  -LteCommandName `
  request_location `
  -RequireLteLocationObservation `
  -ValidationTimeoutSec `
  300 `
  -Json
```

## During Run

Preferred one-command live run: starts the D1 observer and AMOLED display sidecar with the same run ID.

```powershell
powershell `
  -NoProfile `
  -ExecutionPolicy `
  Bypass `
  -File `
  scripts\run_d1_field_companion.ps1 `
  -HubUrl `
  http://203.0.113.10:8790 `
  -TokenFile `
  server/runtime/vps_message_hub_token.txt `
  -RunId `
  FIELD-004-d1-acceptance-20260708-4h `
  -DeviceId `
  ego-link-r1-connectivity-001 `
  -DurationMinutes `
  240 `
  -PollIntervalSec `
  60 `
  -AmoledReadWindowSeconds `
  10 `
  -OutputRoot `
  reports\d1_field_companion
```

Read-only live observer, if a laptop or stable PC can stay online during the field run:

```powershell
python `
  scripts\observe_d1_field_run.py `
  --hub-url `
  http://203.0.113.10:8790 `
  --token-file `
  server/runtime/vps_message_hub_token.txt `
  --run-id `
  FIELD-004-d1-acceptance-20260708-4h `
  --output-dir `
  reports\d1_field_observation\FIELD-004-d1-acceptance-20260708-4h `
  --device-id `
  ego-link-r1-connectivity-001 `
  --duration-minutes `
  240 `
  --poll-interval-sec `
  60 `
  --max-stale-sec `
  180 `
  --json
```

- [ ] Keep the device running outdoors for about 4 hours.
- [ ] Run the live field companion from this kit if a laptop or stable PC can stay online.
- [ ] Keep the AMOLED sidecar visible when practical; record if it becomes blank, stale, or disconnected.
- [ ] Check the Dashboard periodically from phone; do not use serial as the runtime evidence path.
- [ ] Record gaps, reboots, lost service, charging changes, or operator touches with timestamps.
- [ ] If USB must be reconnected, record the runtime stop first and treat later data as a new segment.

## After Run

- [ ] Record local and UTC stop time plus visible Dashboard state.
- [ ] Run the one-command post-run collector from this kit.
- [ ] Confirm the D1 Web/API report, power curve, one-page D1 report, and post-run summary are generated before closing the run.
- [ ] Use the individual Web/API, power, and D1 demo commands only when troubleshooting.
- [ ] Sync curated Field Test Results to the VPS Dashboard.
- [ ] Do not run data-flywheel, labeling, MODEL-DEVICE, DATA, or TRAIN work as part of D1 acceptance.
- [ ] After founder acceptance, create tag v0.1.0 and attach the one-page D1 report to the acceptance note.
- [ ] Keep raw Message Hub export, generated reports, and OPERATOR_NOTES.md together.
- [ ] Do not claim location accuracy, battery life, GNSS acceptance, or 24h PWR-001 pass from a short D1 run.

### Recommended Post-Run Collector

Runs field-observation binding, the Web/API gate, power curve, one-page D1 evidence report, and one bounded artifact summary. It explicitly skips data-flywheel, labeling, and TRAIN reports until D2 has been accepted.

```powershell
python `
  scripts\collect_d1_postrun.py `
  --run-id `
  FIELD-004-d1-acceptance-20260708-4h `
  --hub-url `
  http://203.0.113.10:8790 `
  --token-file `
  server/runtime/vps_message_hub_token.txt `
  --device-id `
  ego-link-r1-connectivity-001 `
  --message-test-run-id `
  FIELD-004-d1-acceptance-20260708-4h `
  --min-duration-hours `
  4 `
  --output-root `
  reports\d1_postrun `
  --web-api-output-dir `
  reports\d1_web_api\FIELD-004-d1-acceptance-20260708-4h `
  --power-output-dir `
  reports\power\FIELD-004-d1-acceptance-20260708-4h `
  --d1-demo-output-dir `
  reports\d1_demo\FIELD-004-d1-acceptance-20260708-4h `
  --field-observation-report `
  reports\d1_field_observation\FIELD-004-d1-acceptance-20260708-4h\d1_field_observation_report.json `
  --field-observation-status `
  reports\d1_field_observation\FIELD-004-d1-acceptance-20260708-4h\d1_field_observation_status.json `
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

### Individual Web/API Gate

Use these individual commands only when troubleshooting or rerunning one component.

```powershell
python `
  scripts\validate_d1_web_api.py `
  --hub-url `
  http://203.0.113.10:8790 `
  --token-file `
  server/runtime/vps_message_hub_token.txt `
  --review-id `
  FIELD-004-d1-acceptance-20260708-4h-web `
  --output-dir `
  reports\d1_web_api\FIELD-004-d1-acceptance-20260708-4h `
  --device-id `
  ego-link-r1-connectivity-001 `
  --json
```

### Power Curve

For a short field shakedown this uses the kit duration as the minimum duration. It is not a 24h PWR-001 pass.

```powershell
python `
  scripts\analyze_power_curve.py `
  --hub `
  http://203.0.113.10:8790 `
  --test-run-id `
  FIELD-004-d1-acceptance-20260708-4h `
  --token-file `
  server/runtime/vps_message_hub_token.txt `
  --output-dir `
  reports\power\FIELD-004-d1-acceptance-20260708-4h `
  --min-duration-hours `
  4 `
  --battery-capacity-mah `
  <rated-capacity-mah> `
  --json
```

### D1 Evidence Report

```powershell
python `
  scripts\build_d1_demo_report.py `
  --web-api-report `
  reports\d1_web_api\FIELD-004-d1-acceptance-20260708-4h\d1_web_api_report.json `
  --power-curve-report `
  reports\power\FIELD-004-d1-acceptance-20260708-4h\power_curve_report.json `
  --report-id `
  FIELD-004-d1-acceptance-20260708-4h `
  --output-dir `
  reports\d1_demo\FIELD-004-d1-acceptance-20260708-4h `
  --json
```

### Sync Dashboard Summaries

This syncs curated D1 field report summaries to the Web Dashboard. It does not copy candidate DBs, feature-row JSONL, raw JSONL logs, model artifacts, or private payloads.

```powershell
powershell `
  -ExecutionPolicy `
  Bypass `
  -File `
  scripts\deploy_message_hub_vps.ps1 `
  -HostName `
  203.0.113.10 `
  -SshKey `
  '$HOME\.ssh\egolink_vps_ed25519' `
  -Public `
  -IncludeFieldReportSummaries
```

### Acceptance Tag

Run only after founder accepts the one-page D1 report.

```powershell
git tag -a v0.1.0 -m "D1 link-through accepted"
```

## Boundaries

- This generator only writes local kit files.
- It does not read or persist token values.
- It does not contact hardware, open serial ports, flash firmware, send Message Hub commands, deploy code, or modify GitLab.
- Operator commands that flash firmware or send commands are explicitly labeled and require operator intent.
- AMOLED sidecar commands are PC-connected display aids and are not USB-Free product acceptance evidence.
- Voice calling and SMS are unverified and not implemented in the current D1 run path.
- A multi-hour D1 shakedown is not a 24h PWR-001 pass or a product battery-life claim.
- Data flywheel, labeling, MODEL-DEVICE, DATA, and TRAIN work is frozen until D2 is accepted.

## Non-Claims

- `location_accuracy_not_claimed`
- `battery_life_not_claimed`
- `gnss_acceptance_not_claimed`
- `calling_not_claimed`
- `sms_not_claimed`
- `model_training_not_claimed`
- `model_metrics_not_claimed`
- `pwr001_24h_pass_not_claimed`
- `product_readiness_not_claimed`
