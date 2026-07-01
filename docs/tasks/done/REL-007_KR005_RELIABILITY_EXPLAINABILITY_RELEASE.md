---
id: REL-007
title: KR-005 Reliability Explainability Release
status: completed
priority: high
requires_hardware: true
created: 2026-07-01
last_updated: 2026-07-01

context:
  - docs/CONTEXT_INDEX.md
  - docs/current/STATUS.md
  - docs/current/KEY_RELEASES.md
  - docs/current/ACTIVE_BUILD.md
  - docs/development/DEV_FLOW.md
  - docs/development/PROTOCOL.md
  - docs/development/LTE_TRANSPORT.md
  - docs/tasks/done/LTE-005_LTE_RELIABILITY_GATE_BASELINE.md
  - docs/tasks/done/OBS-004_RELIABILITY_OBSERVABILITY_BASELINE.md
  - docs/tasks/done/LTE-006_FIRMWARE_SIDE_RELIABILITY_NONCLAIM_OBSERVABILITY.md
  - docs/tasks/done/REL-006_KR005_RELIABILITY_EXPLAINABILITY_RELEASE_GATE.md
  - firmware/AGENTS.md

allowed_paths:
  - docs/current/STATUS.md
  - docs/current/KEY_RELEASES.md
  - docs/current/ACTIVE_BUILD.md
  - docs/current/key_releases/KR-005_RELIABILITY_EXPLAINABILITY_PREFLIGHT.json
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/REL-007_KR005_RELIABILITY_EXPLAINABILITY_RELEASE.md
  - firmware/mqtt_heartbeat/main/app_main.c
  - quality_tests/test_mqtt_heartbeat_firmware.py

out_of_scope:
  - VPS deployment or GitLab changes
  - changing raw-frame framing or required protocol fields
  - implementing durable store-forward cache
  - claiming reconnect recovery, long LTE stability, GNSS acceptance,
    battery/power behavior, enclosure behavior, or product readiness
---

# REL-007 KR-005 Reliability Explainability Release

## Goal

Promote KR-005 from release candidate to released engineering key version after
LTE-006 fix1 proves the compact raw LTE `location_observation` runtime path.

## Acceptance

- [x] Compact LTE-006 `location_observation` payload so the frame stays below
      the known SIM7670G HTTP large-payload risk range.
- [x] Preserve explainability fields for cell/LTE, Wi-Fi, IMU, power,
      network state, cache non-claim, transport, and location belief.
- [x] Build LTE-006 fix1 with a fresh firmware version and test run ID.
- [x] Flash LTE-006 fix1 on `COM4` after explicit operator confirmation.
- [x] Validate one USB-Free `request_location` runtime with independent power
      and USB disconnected.
- [x] Re-run the LTE-005 reliability gate over the LTE-006 fix1 export.
- [x] Promote KR-005 manifest to released while preserving non-claims.

## Evidence

- Fix1 source commit: `98781de`.
- Build:
  `firmware/mqtt_heartbeat/build_lte006_reliability_nonclaim_fix1/egolink_mqtt_heartbeat.bin`
  (`299824` bytes).
- Flash: `COM4`, ESP32-S3 QFN56 rev v0.2, MAC `02:00:00:00:00:03`;
  bootloader, app, and partition table hashes verified.
- USB-Free runtime:
  `reports/field_validation/lte006-reliability-nonclaim-fix1-20260701-001/`.
- Runtime command: `cmd-000026` / `request_location`.
- Runtime location report: raw frame `loc-cmd-000026`, `seq=60`,
  `transport.type=lte`, `gnss_query_ok=true`, `gnss_state=no_fix`,
  `fix=false`.
- Runtime location observation: raw frame `obs-cmd-000026`, `seq=61`,
  `cell.rat=LTE`, `cell.cell_id=180571649`, `lte.reason_code=LTE_READY`,
  assigned IP `10.141.88.185`, Wi-Fi `disabled` / `missing`, IMU
  `unverified` / `mock`, power `mock`, and
  `location_belief.state=Unknown`.
- Runtime ACK: raw frame `cmd-000026`, `seq=62`, status `ok`,
  `LTE_HTTP_OK` / HTTP `200`, and matching test run ID
  `lte006-reliability-nonclaim-fix1-20260701-001`.
- LTE-005 reliability gate over the fix1 export:
  `reports/lte_reliability/lte006-reliability-nonclaim-fix1-20260701-001/`
  returned expected `WARN` because real cache/drop-message evidence is still
  absent.

## Validation

- `python -m unittest quality_tests.test_key_release_gate quality_tests.test_lte_reliability_gate quality_tests.test_mqtt_heartbeat_firmware -v`:
  PASS, 25 tests.
- `python scripts/context_lint.py`: PASS.
- `powershell -ExecutionPolicy Bypass -File scripts\prepare_fw001_hw_config.ps1 -HostName 203.0.113.10 -FwVersion 0.1.0-lte006-reliability-nonclaim-fix1 -TestRunId lte006-reliability-nonclaim-fix1-20260701-001 -BuildDir build_lte006_reliability_nonclaim_fix1 -EnableSim7670Gnss -EnableSim7670LocationObservation -Build -Json`:
  PASS.
- `powershell -ExecutionPolicy Bypass -File scripts\run_fw001_hw_r1.ps1 -HostName 203.0.113.10 -FwVersion 0.1.0-lte006-reliability-nonclaim-fix1 -TestRunId lte006-reliability-nonclaim-fix1-20260701-001 -BuildDir build_lte006_reliability_nonclaim_fix1 -EnableSim7670Gnss -EnableSim7670LocationObservation -Validate -OperatorConfirmedIndependentPower -OperatorConfirmedUsbDisconnected -LteEvidenceSince command-created -LteCommandName request_location -RequireLteLocationReport -RequireLteLocationObservation -ExpectedAckTestRunId lte006-reliability-nonclaim-fix1-20260701-001 -ExpectedMessageTestRunId lte006-reliability-nonclaim-fix1-20260701-001 -ValidationTimeoutSec 420 -ValidationPollIntervalSec 5 -Json`:
  PASS.
- `python scripts\validate_lte_reliability_gate.py --input reports\field_validation\lte006-reliability-nonclaim-fix1-20260701-001\test_run_export.json --output-dir reports\lte_reliability\lte006-reliability-nonclaim-fix1-20260701-001 --json`:
  expected `WARN`.
- `python scripts\run_key_release_gate.py --manifest docs/current/key_releases/KR-005_RELIABILITY_EXPLAINABILITY_PREFLIGHT.json --json`:
  PASS with no warnings.
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`: PASS,
  314 tests.

## Completion Boundary

KR-005 is now a released engineering key version for the explainable reliability
preflight slice. It proves one USB-Free LTE command/report/observation/ACK
runtime with explicit network/cache non-claims. It does not prove long LTE
stability, reconnect recovery, durable offline cache, cache/drop-message
reliability, GNSS fix, battery accuracy, charging, product power behavior,
enclosure behavior, learned model behavior, or product readiness.
