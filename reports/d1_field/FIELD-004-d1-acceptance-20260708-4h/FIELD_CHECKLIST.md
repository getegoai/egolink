# D1 Outdoor Field Checklist

- Run ID: `FIELD-004-d1-acceptance-20260708-4h`

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

## Start Run

- [ ] Confirm independent battery or power-bank supply.
- [ ] Disconnect USB before counting runtime evidence.
- [ ] Record local and UTC start time.
- [ ] Confirm Dashboard D1 panel becomes fresh before walking away.

## During Run

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
