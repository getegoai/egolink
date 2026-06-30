---
document_status: authoritative
last_verified: 2026-06-30
verified_by: codex
---

# Key Releases

This file records Ego Link P0 engineering key releases. A key release is not a
product readiness claim. It is a versioned Walking Skeleton point with a frozen
scope, evidence manifest, release gate, and explicit non-claims.

## KR-001 P0 USB-Free Raw LTE Location Walking Skeleton

- Status: released engineering key version.
- Release date: 2026-06-30.
- Release version: `0.1.0-key-release-001`.
- Firmware version: `0.1.0-lte004-raw-lte-location`.
- Device/test run: `ego-link-r1-connectivity-001` /
  `lte004-raw-lte-location-20260629-213717`.
- Manifest:
  `docs/current/key_releases/KR-001_USB_FREE_RAW_LTE_LOCATION.json`.
- Gate tool:
  `python scripts\run_key_release_gate.py --manifest docs/current/key_releases/KR-001_USB_FREE_RAW_LTE_LOCATION.json --json`.

### Release Meaning

KR-001 freezes the first USB-Free, Message-First, raw-frame LTE location
backbone:

```text
VPS command queue
-> SIM7670G LTE raw command poll
-> request_location
-> raw LTE location_report
-> server raw storage then derived Web/API view
-> raw LTE ACK
```

### Evidence Summary

- LTE-004 implementation and build passed.
- VPS Message Hub was deployed without touching GitLab.
- `COM4` flash passed after explicit operator confirmation.
- USB-Free runtime validation passed on independent power with USB
  disconnected.
- Runtime command: `cmd-000020` / `request_location`.
- Runtime location report: raw frame `loc-cmd-000020`, `seq=30`,
  `transport.type=lte`, `gnss_query_ok=true`, `gnss_state=no_fix`,
  `fix=false`.
- Runtime ACK: `seq=31`, `LTE_HTTP_OK` / HTTP `200`, command and ACK status
  `ok`.

### Non-Claims

- No product readiness claim.
- No long LTE stability or reconnect recovery claim.
- No outdoor real GNSS fix acceptance claim.
- No final enclosure, battery, charging, power, camera, audio, storage, calling,
  SMS, or dispatch claim.
- No final multi-source location memory or belief-engine acceptance claim.

## KR-002 Location Memory And Explainable No-Fix Gate

- Status: release candidate.
- Release date: 2026-06-30.
- Release version: `0.1.0-key-release-002-rc1`.
- Firmware version: unchanged from KR-001 for this server/Web/API gate.
- Manifest:
  `docs/current/key_releases/KR-002_LOCATION_MEMORY_GATE.json`.
- Gate tool:
  `python scripts\run_key_release_gate.py --manifest docs/current/key_releases/KR-002_LOCATION_MEMORY_GATE.json --json`.

### Release-Candidate Meaning

KR-002 adds the first VPS-side location memory and explainable no-fix gate:

```text
location_report fix=true or location_observation.location_belief
-> location_memory
-> later location_report fix=false records last_no_fix
-> active observability.location_belief becomes Predicted
-> Web/API/export remain explainable
```

It does not change the device wire protocol. Raw-frame storage remains the
transport truth; `location_memory` is a derived Message Hub view.

### Evidence Summary

- Message Hub has a persistent `location_memory` table.
- `/api/state` exposes `location_memory` and
  `observability.location_memory`.
- Test-run export rebuilds the same derived location memory summary.
- Dashboard renders memory state, memory update time, and memory reason.
- `scripts/validate_location_memory_gate.py` can rerun the gate with a
  synthetic device and no hardware or USB runtime dependency.
- Focused Message Hub, Dashboard, and location-memory gate tests pass.
- Full `scripts\verify.ps1` passes with 287 tests.
- VPS Message Hub was redeployed to `203.0.113.10:8790` without touching
  GitLab.
- VPS synthetic gate `location-memory-gate-kr002-20260630` passed:
  latest report no-fix, active belief `Predicted`, memory `Fine`.

### Non-Claims

- No product readiness claim.
- No firmware-side multi-source collection claim.
- No learned personal-place or route-prediction claim.
- No outdoor GNSS acceptance claim.
- No long LTE stability or reconnect recovery claim.
- No final enclosure, mounting, battery, charging, or power behavior claim.

## KR-003 USB-Free Explainable LTE Location Observation Walking Skeleton

- Status: released engineering key version.
- Release date: 2026-06-30.
- Release version: `0.1.0-key-release-003`.
- Firmware version: `0.1.0-loc004a-cell-observation`.
- Device/test runs: `ego-link-r1-connectivity-001` /
  `loc004a-cell-observation-runtime-20260630-001` and
  `loc004a-reboot-aware-20260630-001`.
- Manifest:
  `docs/current/key_releases/KR-003_EXPLAINABLE_LTE_LOCATION_OBSERVATION.json`.
- Gate tool:
  `python scripts\run_key_release_gate.py --manifest docs/current/key_releases/KR-003_EXPLAINABLE_LTE_LOCATION_OBSERVATION.json --json`.
- Gate report:
  `reports/key_releases/KR-003/release_gate_report.json` and
  `reports/key_releases/KR-003/release_gate_report.md`.

### Release Meaning

KR-003 freezes the first USB-Free raw LTE location loop that carries both GNSS
attempt evidence and real firmware-side SIM7670G cell/LTE observation:

```text
VPS command queue
-> SIM7670G LTE raw command poll
-> request_location
-> raw LTE location_report
-> raw LTE location_observation
-> server raw storage then derived cell/LTE/belief Web/API view
-> raw LTE ACK
```

It also freezes the field-test workflow for one-command-per-boot slices:

```text
arm command
-> operator reboots USB-disconnected device on independent power
-> reconcile same cmd_id from VPS evidence
```

### Evidence Summary

- LOC-004A implementation, VPS deployment, guarded build, and COM4 flash
  passed.
- USB-Free runtime evidence reconciled PASS for `cmd-000021`: raw
  `location_report`, raw `location_observation`, and raw ACK all arrived over
  LTE.
- FIELD-002 reboot-aware validator tooling passed focused and full regression
  gates.
- FIELD-002A hardware smoke passed for `cmd-000023` after the operator rebooted
  on independent power with USB disconnected. The validator reused the same
  command ID and matched command-created location evidence.
- Runtime `location_observation` showed LTE cell ID `180571649`, LTE-ready
  reason code, assigned LTE IP, `transport.type=lte`, and
  `location_belief.state=Unknown`.

### Non-Claims

- No product readiness claim.
- No GNSS fix or outdoor GNSS acceptance claim.
- No cell-only positioning claim.
- No learned personal-place, route prediction, or final fusion-engine claim.
- No long LTE stability or reconnect recovery claim.
- No final enclosure, mounting, battery, charging, or power behavior claim.

## KR-004 Multi-Source Explainable Location Evidence Baseline

- Status: release candidate.
- Release date: 2026-06-30.
- Release version: `0.1.0-key-release-004-rc1`.
- Firmware version: `0.1.0-loc005a-source-states`.
- Device/test run: `ego-link-r1-connectivity-001` /
  `loc005a-source-states-20260630-001`.
- Manifest:
  `docs/current/key_releases/KR-004_MULTI_SOURCE_EXPLAINABLE_LOCATION_EVIDENCE.json`.
- Gate tool:
  `python scripts\run_key_release_gate.py --manifest docs/current/key_releases/KR-004_MULTI_SOURCE_EXPLAINABLE_LOCATION_EVIDENCE.json --json`.
- Gate report:
  `reports/key_releases/KR-004/release_gate_report.json` and
  `reports/key_releases/KR-004/release_gate_report.md`.

### Release-Candidate Meaning

KR-004 freezes the current explainable multi-source location evidence path:

```text
KR-003 raw LTE command/location/observation/ACK loop
-> LOC-005A Wi-Fi/IMU/power source-state evidence slots
-> OBS-003 current_run and failure visibility
-> ALG-001 server-derived EALE-P0 conservative location_belief
-> DATA-001 dataset-window readiness with training disabled by default
```

It is a release candidate because the gate now passes and Web/API identify the
current LOC-005A run as `KR-004`, but formal promotion from `release_candidate`
to `released` should happen after report review.

### Evidence Summary

- LOC-005A USB-Free runtime evidence passed for `cmd-000024` on independent
  power with USB disconnected.
- Runtime evidence includes raw LTE `location_report`, raw LTE
  `location_observation`, and raw LTE ACK.
- Runtime `location_observation` includes SIM7670G cell/LTE evidence plus
  explicit Wi-Fi `disabled` / `missing`, IMU `unverified` / `mock`, and power
  `mock` source-state labels.
- OBS-003 makes current run, key release, command/ACK chain, raw evidence,
  derived location, and failure reason visible in Web/API/export surfaces.
- ALG-001 makes EALE-P0 derived belief visible. The current run remains
  `Unknown` / `no_precise_fix` with reason
  `gnss_no_fix_cell_lte_observed_no_position_memory`, not a cell-only
  position.
- DATA-001 readiness is visible as `failure_window` /
  `candidate_with_warnings`, with `training_allowed=false`.
- KR-004 gate passed with JSON checks over LOC-005A runtime evidence and the
  authenticated current-run EALE-P0 snapshot.
- The VPS Message Hub was redeployed with the KR-004 manifest; existing GitLab
  service remained active.

### Non-Claims

- No product readiness claim.
- No GNSS fix or outdoor GNSS acceptance claim.
- No cell-only positioning claim.
- No Wi-Fi positioning or raw BSSID retention claim.
- No product IMU mounting, calibration, or motion-classification acceptance
  claim.
- No battery accuracy, charging, or product power behavior claim.
- No learned model, learned personal-place, route prediction, or
  positioning-accuracy claim.
- No long LTE stability or reconnect recovery claim.
- No final enclosure, mounting, camera, audio, storage, calling, SMS, or
  dispatch claim.

## Release Gate Policy

Every key release should have:

- a machine-readable manifest under `docs/current/key_releases/`;
- an evidence-first gate report generated by `scripts/run_key_release_gate.py`;
- committed status/task docs plus local field evidence paths;
- explicit non-claims;
- a short list of next gates.

Short repeat tests are optional confidence checks. They are not the release
mechanism. The release mechanism is the manifest plus targeted gates that can be
rerun for the specific feature or task being changed.
