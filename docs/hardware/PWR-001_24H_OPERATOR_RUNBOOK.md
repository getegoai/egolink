# PWR-001 24h Battery Baseline Runbook

> Status: operator runbook. This is not measured power evidence.

## Purpose

Serve D1 by recording a USB-Free 24h battery-powered run with timed location,
LTE upload, and power samples visible through the Message Hub. The report is an
engineering baseline only and must not be used as a 48h or 7d product claim.

## Preflight

- Board: `connectivity-node-001` / Waveshare ESP32-S3-SIM7670G-4G.
- Record the physical board revision before choosing MAX17048 pins:
  - documented V2 default: SDA GPIO15 / SCL GPIO16;
  - documented V1 override: SDA GPIO3 / SCL GPIO2.
- Record battery rated capacity, starting condition, firmware commit, firmware
  app version, hub URL, test-run ID, start time, and evidence directory.
- Use a local token file or `EGOLINK_MESSAGE_HUB_TOKEN`; do not write tokens
  into the runbook, reports, commits, or screenshots.

## Prepare Firmware Config

Use a unique test run, for example `PWR-001-YYYYMMDD-24h-001`.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\prepare_fw001_hw_config.ps1 `
  -HostName <message-hub-host> `
  -Port 8790 `
  -TokenFile <local-token-file> `
  -TestRunId PWR-001-YYYYMMDD-24h-001 `
  -EnableSim7670Gnss `
  -EnableSim7670LocationObservation `
  -EnableMax17048Power `
  -Max17048SdaGpio 15 `
  -Max17048SclGpio 16 `
  -Build `
  -Json
```

Use `-Max17048SdaGpio 3 -Max17048SclGpio 2` only for a recorded V1 board.
Flashing, erasing, or power-cycling the board requires explicit operator
intent for that run.

## Run

1. Create or confirm the Message Hub test run ID.
2. Flash the prepared image only after explicit operator approval.
3. Connect battery or independent power, confirm the board remains online, then
   disconnect USB for the runtime portion.
4. Let the device run unattended for at least 24 hours.
5. Do not use serial capture as the runtime data path. Message Hub export is
   the required USB-Free evidence path.
6. Record any reboots, low-battery cutoff, lost LTE service, operator touches,
   or environmental changes in the evidence directory.

## Export And Analyze

```powershell
python scripts\analyze_power_curve.py `
  --hub http://<message-hub-host>:8790 `
  --test-run-id PWR-001-YYYYMMDD-24h-001 `
  --output-dir reports\power\PWR-001-YYYYMMDD-24h-001 `
  --battery-capacity-mah <rated-capacity>
```

Expected outputs:

- `reports/power/PWR-001-YYYYMMDD-24h-001/test_run_export.json`
- `reports/power/PWR-001-YYYYMMDD-24h-001/power_curve_report.json`
- `reports/power/PWR-001-YYYYMMDD-24h-001/power_curve_report.md`

## Acceptance Notes

- `power.source_status` must be `measured` for MAX17048 samples to count as
  battery telemetry evidence.
- `charging_source=mock` remains expected until a charger-state backend is
  integrated and validated.
- A report with less than 24h duration, missing SoC drop, missing battery
  capacity, mock samples, or no timestamped power samples is not a PWR-001 pass.
