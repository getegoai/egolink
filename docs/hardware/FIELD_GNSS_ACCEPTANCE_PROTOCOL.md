---
document_status: authoritative
last_verified: 2026-07-11
verified_by: codex
---

# FIELD-003 Outdoor GNSS Acceptance Protocol

This protocol defines the first repeatable outdoor GNSS acceptance run for the
connectivity-node SIM7670G path. It produces engineering evidence only. It does
not make product accuracy claims, change EALE-P0 thresholds, change firmware,
or use USB/serial logs as runtime acceptance evidence.

## Scope

- Board: connectivity-node-001, role connectivity_node, Waveshare ESP32-S3-SIM7670G.
- Runtime connection: independent power with USB disconnected; evidence must reach the VPS Message Hub.
- Required command path: request_location -> location_report, plus location_observation when the flashed image supports it.
- Required output path: reports/gnss/FIELD-003-YYYYMMDD/.
- Analysis tool: python scripts/analyze_gnss_acceptance.py --input <export> --manifest <manifest> --output-dir <evidence-dir>.
- Operator kit: python scripts/prepare_d2_field_kit.py --run-id <run-id>.
- One-command post-run: python scripts/run_location_d2_d5_pipeline.py --hub <hub> --test-run-id <message-test-run-id> --manifest <manifest> --run-id <run-id>.

## Acceptance Design

Use at least one reference point of each required type:

| point_type | Required environment |
|---|---|
| open_sky | Open outdoor area with broad sky view and no nearby overhead cover. |
| street_between_buildings | Street or path with buildings on both sides. |
| tree_cover | Outdoor point under tree canopy or similar foliage cover. |

At each reference point, run at least:

- 5 cold attempts.
- 5 warm attempts.

A cold attempt means the first request_location after the device and GNSS module
have been powered off for at least 10 minutes, then booted on independent power
with USB disconnected.

A warm attempt means a later request_location at the same point while the device
remains on independent power with USB disconnected, within 2 minutes of the
previous completed attempt. If the current firmware consumes only one command
per boot, record that limitation and do not relabel rebooted attempts as warm
attempts.

Reference coordinates must be recorded in field_manifest.json using one of
these methods:

- phone_gnss_5min_average: phone GNSS averaged for at least 5 minutes at the marked point.
- map_pick_satellite_view: map/satellite pick at the marked point.
- survey_marker: a known surveyed marker or published coordinate.

The method, timestamp, latitude, longitude, and point notes are required for
each reference point.

## Evidence Directory

Create this layout before the run:

    reports/gnss/FIELD-003-YYYYMMDD/
      field_manifest.json
      test_run_export.json
      attempts/
        <attempt-id>_arm.json
        <attempt-id>_reconcile.json
      dashboard/
        <optional-dashboard-capture>.png
      gnss_acceptance_report.json
      gnss_acceptance_report.md

The file test_run_export.json is the raw VPS Message Hub export for the run.
The file field_manifest.json is the operator-authored join file that maps each
field attempt to a reference point and command ID. The generated reports are
produced by scripts/analyze_gnss_acceptance.py.

## Field Manifest Template

Fill every placeholder before analysis. Keep exact coordinates only inside the
bounded evidence directory.

    {
      "test_run_id": "FIELD-003-YYYYMMDD-001",
      "board_id": "connectivity-node-001",
      "device_id": "ego-link-r1-connectivity-001",
      "firmware_version": "<record flashed firmware version>",
      "firmware_commit_or_image": "<record git commit or binary path flashed>",
      "connection_path": "vps_message_hub_usb_free",
      "runtime_usb_connected": false,
      "operator": "<name or initials>",
      "started_at": "<ISO-8601 timestamp>",
      "ended_at": "<ISO-8601 timestamp>",
      "reference_points": [
        {
          "point_id": "open_sky_01",
          "name": "<site label>",
          "point_type": "open_sky",
          "reference": {
            "lat": 0.0,
            "lon": 0.0,
            "method": "phone_gnss_5min_average",
            "recorded_at": "<ISO-8601 timestamp>"
          },
          "notes": "<weather, sky view, nearby structures>"
        },
        {
          "point_id": "street_between_buildings_01",
          "name": "<site label>",
          "point_type": "street_between_buildings",
          "reference": {
            "lat": 0.0,
            "lon": 0.0,
            "method": "map_pick_satellite_view",
            "recorded_at": "<ISO-8601 timestamp>"
          },
          "notes": "<building height, road width, blockage>"
        },
        {
          "point_id": "tree_cover_01",
          "name": "<site label>",
          "point_type": "tree_cover",
          "reference": {
            "lat": 0.0,
            "lon": 0.0,
            "method": "phone_gnss_5min_average",
            "recorded_at": "<ISO-8601 timestamp>"
          },
          "notes": "<tree density, wet/dry leaves, sky view>"
        }
      ],
      "attempts": [
        {
          "attempt_id": "open_sky_01-cold-01",
          "point_id": "open_sky_01",
          "mode": "cold",
          "command_id": "<cmd-id from arm report>",
          "started_at": "<ISO-8601 timestamp>",
          "ended_at": "<ISO-8601 timestamp>",
          "operator_notes": "<fix/no-fix visible in dashboard, movement, obstruction>"
        }
      ]
    }

## Preflight

The recommended starting point is the generated kit under
`reports/d2_field/<run-id>/`. The kit does not contact hardware or the VPS;
it creates this protocol's strict 30-attempt manifest plus read-only preflight
and post-run commands.

1. Confirm the VPS Message Hub and Web Dashboard are reachable.
2. Confirm the existing GitLab service on the VPS is untouched.
3. Confirm EGOLINK_MESSAGE_HUB_TOKEN is set outside the repository.
4. Record the board, firmware version, firmware commit or image, SIM/network readiness, GNSS antenna state, power source, and expected device ID.
5. Create the evidence directory and an attempts/ subdirectory.
6. Mark the three reference points and record their reference coordinates.
7. Confirm the device can run on independent power with USB disconnected.
8. Confirm the field run will not use serial logs as acceptance evidence.

PowerShell setup:

    $Hub = "http://<operator-vps>:8790"
    $DeviceId = "ego-link-r1-connectivity-001"
    $BoardId = "connectivity-node-001"
    $TestRunId = "FIELD-003-YYYYMMDD-001"
    $FwVersion = "<expected firmware version>"
    $FirmwareTestRunId = "<firmware CONFIG_EGOLINK_TEST_RUN_ID if different>"
    $EvidenceDir = "reports\gnss\FIELD-003-YYYYMMDD"
    New-Item -ItemType Directory -Force "$EvidenceDir\attempts", "$EvidenceDir\dashboard" | Out-Null

## Attempt Procedure

Repeat this procedure for every cold and warm attempt. For cold attempts, power
the device off for at least 10 minutes before the arm step, then boot on
independent power with USB disconnected. For warm attempts, keep the device at
the same reference point, powered, and USB disconnected.

1. Set an attempt ID that matches field_manifest.json.

    $AttemptId = "open_sky_01-cold-01"

2. Arm exactly one request_location command and save the arm report.

    python scripts\validate_lte_command_loop.py --hub $Hub --device-id $DeviceId --board-id $BoardId --test-run-id $TestRunId --expected-fw-version $FwVersion --expected-ack-test-run-id $FirmwareTestRunId --expected-message-test-run-id $FirmwareTestRunId --connection-path independent_power_usb_disconnected --command request_location --require-location-report --require-location-observation --arm-only --output-dir "$EvidenceDir\attempts\$AttemptId" --json | Tee-Object -FilePath "$EvidenceDir\attempts\$($AttemptId)_arm.json"

3. Copy command.cmd_id from the arm report into the attempt row in field_manifest.json.
4. For a cold attempt, boot or reboot the board on independent power with USB disconnected after the command is armed. For a warm attempt, leave the board powered and stationary at the reference point.
5. Reconcile the exact command ID and save the reconcile report.

    $CmdId = "<cmd-id from arm report>"
    python scripts\validate_lte_command_loop.py --hub $Hub --device-id $DeviceId --board-id $BoardId --test-run-id $TestRunId --expected-fw-version $FwVersion --expected-ack-test-run-id $FirmwareTestRunId --expected-message-test-run-id $FirmwareTestRunId --connection-path independent_power_usb_disconnected --command request_location --existing-command-id $CmdId --require-location-report --require-location-observation --evidence-since command-created --output-dir "$EvidenceDir\attempts\$AttemptId" --json | Tee-Object -FilePath "$EvidenceDir\attempts\$($AttemptId)_reconcile.json"

6. Record started_at, ended_at, point ID, mode, command ID, and notes in field_manifest.json.
7. Do not count an attempt unless the VPS export contains the matching command and GNSS observation evidence.

If the firmware image does not support location_observation, remove
--require-location-observation only after recording that limitation in the
manifest notes. The analysis still requires location_report evidence.

## Export And Analysis

After all attempts are complete:

1. Export the full Message Hub test run to reports/gnss/FIELD-003-YYYYMMDD/test_run_export.json.
2. Run the analyzer:

    python scripts\analyze_gnss_acceptance.py --input "$EvidenceDir\test_run_export.json" --manifest "$EvidenceDir\field_manifest.json" --output-dir "$EvidenceDir"

The report computes:

- per-point fix rate;
- per-point and overall TTFF distribution for fixed attempts;
- haversine error distance from the reference coordinate;
- overall and per-point HDOP-vs-error correlation when enough fixed pairs exist;
- comparison against the EALE-P0 gnss_radius_m = max(25, hdop * 8) Fine radius assumption.

The generated report must state one of:

- no_revision_indicated_by_this_run;
- revision_indicated;
- insufficient_fixed_hdop_error_pairs.

Any EALE-P0 threshold revision is out of scope for FIELD-003 and must be a
separate ALG task.

## Fillable Evidence Checklist

Run metadata:

| Field | Value |
|---|---|
| Evidence directory | reports/gnss/FIELD-003-YYYYMMDD/ |
| Test run ID |  |
| Operator |  |
| Board ID | connectivity-node-001 |
| Device ID |  |
| Firmware version |  |
| Firmware commit or image |  |
| Power source |  |
| GNSS antenna attached | yes / no |
| Runtime USB disconnected | yes / no |
| VPS Message Hub URL |  |
| Start timestamp |  |
| End timestamp |  |
| Weather / sky notes |  |

Reference points:

| point_id | point_type | reference method | lat | lon | recorded_at | notes |
|---|---|---|---:|---:|---|---|
| open_sky_01 | open_sky |  |  |  |  |  |
| street_between_buildings_01 | street_between_buildings |  |  |  |  |  |
| tree_cover_01 | tree_cover |  |  |  |  |  |

Attempts:

| attempt_id | point_id | mode | cmd_id | started_at | ended_at | VPS evidence path | notes |
|---|---|---|---|---|---|---|---|
| open_sky_01-cold-01 | open_sky_01 | cold |  |  |  |  |  |
| open_sky_01-cold-02 | open_sky_01 | cold |  |  |  |  |  |
| open_sky_01-cold-03 | open_sky_01 | cold |  |  |  |  |  |
| open_sky_01-cold-04 | open_sky_01 | cold |  |  |  |  |  |
| open_sky_01-cold-05 | open_sky_01 | cold |  |  |  |  |  |
| open_sky_01-warm-01 | open_sky_01 | warm |  |  |  |  |  |
| open_sky_01-warm-02 | open_sky_01 | warm |  |  |  |  |  |
| open_sky_01-warm-03 | open_sky_01 | warm |  |  |  |  |  |
| open_sky_01-warm-04 | open_sky_01 | warm |  |  |  |  |  |
| open_sky_01-warm-05 | open_sky_01 | warm |  |  |  |  |  |
| street_between_buildings_01-cold-01 | street_between_buildings_01 | cold |  |  |  |  |  |
| street_between_buildings_01-cold-02 | street_between_buildings_01 | cold |  |  |  |  |  |
| street_between_buildings_01-cold-03 | street_between_buildings_01 | cold |  |  |  |  |  |
| street_between_buildings_01-cold-04 | street_between_buildings_01 | cold |  |  |  |  |  |
| street_between_buildings_01-cold-05 | street_between_buildings_01 | cold |  |  |  |  |  |
| street_between_buildings_01-warm-01 | street_between_buildings_01 | warm |  |  |  |  |  |
| street_between_buildings_01-warm-02 | street_between_buildings_01 | warm |  |  |  |  |  |
| street_between_buildings_01-warm-03 | street_between_buildings_01 | warm |  |  |  |  |  |
| street_between_buildings_01-warm-04 | street_between_buildings_01 | warm |  |  |  |  |  |
| street_between_buildings_01-warm-05 | street_between_buildings_01 | warm |  |  |  |  |  |
| tree_cover_01-cold-01 | tree_cover_01 | cold |  |  |  |  |  |
| tree_cover_01-cold-02 | tree_cover_01 | cold |  |  |  |  |  |
| tree_cover_01-cold-03 | tree_cover_01 | cold |  |  |  |  |  |
| tree_cover_01-cold-04 | tree_cover_01 | cold |  |  |  |  |  |
| tree_cover_01-cold-05 | tree_cover_01 | cold |  |  |  |  |  |
| tree_cover_01-warm-01 | tree_cover_01 | warm |  |  |  |  |  |
| tree_cover_01-warm-02 | tree_cover_01 | warm |  |  |  |  |  |
| tree_cover_01-warm-03 | tree_cover_01 | warm |  |  |  |  |  |
| tree_cover_01-warm-04 | tree_cover_01 | warm |  |  |  |  |  |
| tree_cover_01-warm-05 | tree_cover_01 | warm |  |  |  |  |  |

Completion:

| Item | Value |
|---|---|
| field_manifest.json complete | yes / no |
| test_run_export.json saved | yes / no |
| Analyzer JSON report path |  |
| Analyzer Markdown report path |  |
| Fix rate summary copied to run notes | yes / no |
| EALE-P0 radius assessment |  |
| Board matrix update prepared after measured evidence review | yes / no |
