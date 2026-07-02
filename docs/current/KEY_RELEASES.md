---
document_status: authoritative
last_verified: 2026-07-03
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

- Status: released engineering key version.
- Release date: 2026-06-30.
- Release version: `0.1.0-key-release-004`.
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

### Release Meaning

KR-004 freezes the current explainable multi-source location evidence path:

```text
KR-003 raw LTE command/location/observation/ACK loop
-> LOC-005A Wi-Fi/IMU/power source-state evidence slots
-> OBS-003 current_run and failure visibility
-> ALG-001 server-derived EALE-P0 conservative location_belief
-> DATA-001 dataset-window readiness with training disabled by default
```

It is a released engineering key version because the KR-004 gate passes, Web/API
identify the current LOC-005A run as `KR-004`, and the post-candidate ALG-002
offline DATA-001 evidence/failure coverage report supports release review while
preserving the model-training and positioning-accuracy non-claims.

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
- ALG-002 can regenerate the DATA-001 JSONL shard for the LOC-005A export and
  produce an offline EALE-P0 coverage report. The current local report is
  `warn`: one retained `failure_window`, one `gnss_no_fix` failure mode,
  raw-frame and derived-event lineage present, zero Fine candidates, and
  `model_training_ready=false`.
- KR-004 gate passed with JSON checks over LOC-005A runtime evidence, the
  authenticated current-run EALE-P0 snapshot, and the ALG-002 offline dataset
  coverage report.
- The VPS Message Hub was redeployed with the released KR-004 manifest; public
  `/health` returned `ok=true`, unauthenticated `/api/state` returned HTTP
  401, authenticated current-run key-release status returned `released`, and
  existing GitLab service remained active.

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

## KR-005 Reliability Explainability Preflight Baseline

- Status: released engineering key version.
- Release date: 2026-07-01.
- Release version: `0.1.0-key-release-005`.
- Firmware version: `0.1.0-lte006-reliability-nonclaim-fix1`.
- Device/test run: `ego-link-r1-connectivity-001` /
  `lte006-reliability-nonclaim-fix1-20260701-001`.
- Manifest:
  `docs/current/key_releases/KR-005_RELIABILITY_EXPLAINABILITY_PREFLIGHT.json`.
- Gate tool:
  `python scripts\run_key_release_gate.py --manifest docs/current/key_releases/KR-005_RELIABILITY_EXPLAINABILITY_PREFLIGHT.json --json`.
- Gate report:
  `reports/key_releases/KR-005/release_gate_report.json` and
  `reports/key_releases/KR-005/release_gate_report.md`.

### Release Meaning

KR-005 freezes the reliability explainability preflight path:

```text
LTE-005 offline reliability gate
-> OBS-004 reliability.network/cache visibility
-> LTE-006 fix1 compact raw LTE location_observation network/cache non-claim fields
-> USB-Free request_location runtime evidence over SIM7670G LTE
-> KR-005 release gate
```

It is a released engineering key version because the compact LTE-006 fix1
payload passed a real USB-Free runtime command on independent power with USB
disconnected, and the KR-005 gate now binds that evidence. It is still a
preflight baseline: it explains missing cache/reconnect capability rather than
claiming those mechanisms are implemented.

### Evidence Summary

- LTE-005 checks command lifecycle visibility, stale/pending command
  explanation, duplicate guard fields, LTE transport/reason codes, failure
  explanation, reconnect/reset and cache/drop observability, raw-frame
  retention, and sequence visibility.
- OBS-004 exposes optional `reliability.network` and `reliability.cache`
  fields through Message Hub storage, exports, current-run context, and Web
  Dashboard.
- LTE-006 fix1 firmware build passed with
  `0.1.0-lte006-reliability-nonclaim-fix1`; the binary is
  `firmware/mqtt_heartbeat/build_lte006_reliability_nonclaim_fix1/egolink_mqtt_heartbeat.bin`.
- LTE-006 fix1 compacts raw LTE `location_observation` to stay below the
  SIM7670G HTTP payload danger zone while preserving `network_mode=LTE`,
  `network_rssi`, `network_state`, `network_last_error`,
  `cache_state=not_enabled`, `cache_source_status=unverified`,
  `cache_last_drop_reason=cache_not_enabled`, source-state labels, and belief
  explanation.
- COM4 flash passed after explicit operator confirmation; app image size was
  `299824` bytes and bootloader/app/partition hashes verified.
- USB-Free runtime validation passed after the operator connected independent
  power and disconnected USB. Command `cmd-000026` produced raw LTE
  `location_report seq=60`, raw LTE `location_observation seq=61`, and raw
  LTE ACK `seq=62`, all with test run
  `lte006-reliability-nonclaim-fix1-20260701-001`.
- Runtime `location_observation` showed LTE `reason_code=LTE_READY`, cell ID
  `180571649`, RSSI `-92`, RSRP `-97`, assigned IP `10.141.88.185`, Wi-Fi
  `disabled` / `missing`, IMU `unverified` / `mock`, power `mock`, and
  `location_belief.state=Unknown`.
- LTE-005 over the fix1 runtime export returns expected `WARN`: concrete
  cache/drop-message evidence is still absent, raw-frame retention remains
  `PASS`, and the gate does not synthesize false cache evidence.
- KR-005 gate passed with all manifest gates `PASS`.

### Non-Claims

- No product readiness claim.
- No long LTE stability claim.
- No reconnect recovery claim.
- No durable offline cache or store-forward claim.
- No cache/drop-message reliability claim.
- No GNSS fix or outdoor GNSS acceptance claim.
- No battery accuracy, charging, or product power behavior claim.
- No learned model, learned personal-place, route prediction, or
  positioning-accuracy claim.
- No final enclosure, mounting, camera, audio, storage, calling, SMS, or
  dispatch claim.

### Next Gates

- LTE-007 has since added build-verified and USB-Free runtime-validated
  current-boot volatile outbox counters: POST attempt/success/failure counts
  plus observed cache drop counters. The Message Hub/Web derivation was
  redeployed without touching GitLab, and LTE-005 now sees G6 cache/drop
  observability as `PASS` on the LTE-007 export.
- LTE-008 has since added bounded current-boot raw POST retry and Cache Retry
  visibility. COM4 flash passed, but USB-Free runtime attempt 1 failed in an
  explainable way with `location_observation_payload_truncated`. LTE-008 fix1
  is build-verified, flashed on COM4, and USB-Free runtime validated with
  `cmd-000030`: raw LTE `location_report`, `location_observation`, and ACK all
  reached the VPS with matching firmware/test-run IDs and retry visibility.
  This proves the healthy-link retry-visibility slice, not an actual
  retry-after-failure case.
- LTE-009 has since proved a controlled raw POST fail-once retry and is frozen
  as KR-006 below. The next gate should move toward reconnect recovery or
  bounded store-forward design before any long LTE stability gate.

## KR-006 Raw POST Retry Fault Injection Baseline

- Status: released engineering key version.
- Release date: 2026-07-01.
- Release version: `0.1.0-key-release-006`.
- Firmware version: `0.1.0-lte009-raw-post-retry-fault`.
- Device/test run: `ego-link-r1-connectivity-001` /
  `lte009-raw-post-retry-fault-20260701-001`.
- Manifest:
  `docs/current/key_releases/KR-006_RAW_POST_RETRY_FAULT_INJECTION.json`.
- Gate tool:
  `python scripts\run_key_release_gate.py --manifest docs/current/key_releases/KR-006_RAW_POST_RETRY_FAULT_INJECTION.json --json`.
- Gate report:
  `reports/key_releases/KR-006/release_gate_report.json` and
  `reports/key_releases/KR-006/release_gate_report.md`.

### Release Meaning

KR-006 freezes the first controlled retry-fault proof on the USB-Free raw LTE
location backbone:

```text
VPS command queue
-> SIM7670G LTE raw command poll
-> request_location
-> first raw LTE location_report retained as injected_failure / HTTP 503
-> same raw frame retried and derived as location_report
-> raw LTE location_observation carries retry counters
-> raw LTE ACK completes the command
-> KR-006 release gate
```

It is a released engineering key version because LTE-009 passed one real
USB-Free runtime on independent power with USB disconnected, and the KR-006
manifest now checks both derived runtime fields and retained raw-frame evidence.
It is still a bounded current-boot retry slice: it proves one injected
first-POST failure recovery, not reconnect recovery or durable store-forward.

### Evidence Summary

- LTE-008 fix1 provides the bounded current-boot raw POST retry helper and
  retry counter visibility.
- LTE-009 adds a default-off firmware fail-once test switch and a Message Hub
  raw-ingest fail-once path. The first marked raw frame is retained as
  `parse_result.status=injected_failure` and HTTP `503` is returned without
  deriving a Web/API message; the repeated frame is accepted and derived.
- Message Hub was deployed to `203.0.113.10:8790` without touching GitLab.
  Public health/auth checks passed, and a VPS-local in-memory smoke proved
  first POST `503`, retained raw failure, no derived telemetry from the failed
  attempt, then retry success.
- Guarded ESP-IDF build produced
  `firmware/mqtt_heartbeat/build_lte009_raw_post_retry_fault/egolink_mqtt_heartbeat.bin`
  (`301776` bytes).
- COM4 flash passed after explicit operator confirmation. Flash evidence is
  under
  `reports/field_validation/lte009-raw-post-retry-fault-20260701-001/flash_report.md`.
- USB-Free runtime validation passed after the operator connected independent
  power and disconnected USB. Command `cmd-000031` produced retained raw LTE
  `location_report` failure, retry-derived `location_report seq=27`, raw LTE
  `location_observation seq=28`, and raw LTE ACK `seq=29`.
- Runtime `location_observation` showed LTE `reason_code=LTE_READY`, cell ID
  `180571649`, assigned IP `10.13.10.229`,
  `location_belief.state=Unknown`, retry policy
  `single_retry_current_boot`, retry counters `1/1/0`, and raw POST counters
  `2/1/1`.
- Raw LTE ACK completed the command as `ok` with `LTE_HTTP_OK` / HTTP `200`,
  retry counters `1/1/0`, and raw POST counters `3/2/1`.
- KR-006 gate passed with raw-frame checks proving the retained failed frame
  and the retry-derived frame share the same `loc-cmd-000031` payload hash.

### Non-Claims

- No product readiness claim.
- No long LTE stability claim.
- No reconnect recovery claim.
- No durable offline cache or store-forward claim.
- No multi-message outage recovery claim.
- No GNSS fix or outdoor GNSS acceptance claim.
- No battery accuracy, charging, or product power behavior claim.
- No learned model, learned personal-place, route prediction, or
  positioning-accuracy claim.
- No final enclosure, mounting, camera, audio, storage, calling, SMS, or
  dispatch claim.

### Next Gates

- Design reconnect recovery evidence before treating modem/network
  interruptions as recovered.
- Design bounded store-forward semantics before claiming durable offline cache.
- Add a later long-run LTE reliability gate only after reconnect and
  store-forward evidence are visible.
- Keep GNSS acceptance, battery/power behavior, and enclosure behavior outside
  this retry gate.

## KR-007 Reconnect Store-Forward Evidence Baseline

- Status: released engineering key version.
- Release date: 2026-07-02.
- Release version: `0.1.0-key-release-007`.
- Firmware version:
  `0.1.0-lte011-reconnect-store-forward-test-fix1`.
- Device/test run: `ego-link-r1-connectivity-001` /
  `lte011-reconnect-store-forward-test-fix1-20260702-001`.
- Manifest:
  `docs/current/key_releases/KR-007_RECONNECT_STORE_FORWARD_EVIDENCE.json`.
- Gate tool:
  `python scripts\run_key_release_gate.py --manifest docs/current/key_releases/KR-007_RECONNECT_STORE_FORWARD_EVIDENCE.json --json`.
- Gate report:
  `reports/key_releases/KR-007/release_gate_report.json` and
  `reports/key_releases/KR-007/release_gate_report.md`.

### Release Meaning

KR-007 freezes the current LTE-011 fix1 reconnect/store-forward evidence
baseline:

```text
LTE raw request_location loop
-> raw LTE location_report
-> raw LTE location_observation carries reconnect/store-forward evidence
-> raw LTE ACK shows post-reconnect recovery/cache drain evidence
-> LTE-010 offline reconnect/store-forward gate PASS
```

It is a released engineering key version because LTE-011 fix1 passed one real
USB-Free runtime on independent power with USB disconnected, the LTE-010
offline gate passed over that export, and the KR-007 manifest gate passed after
promotion. It is still a default-off test-mode evidence slice: it proves the
evidence shape needed for reconnect/store-forward review, not real modem
reconnect recovery or durable store-forward.

### Evidence Summary

- LTE-011 base image produced an explainable FAIL for `cmd-000032`: the device
  uploaded raw LTE `location_report` and ACK, but the raw LTE
  `location_observation` was dropped before POST with
  `location_observation_payload_truncated`.
- LTE-011 fix1 increased only the raw LTE `location_observation` local
  payload/frame buffers to `2050`/`2400` bytes.
- COM4 flash passed after explicit operator confirmation. Flash evidence is
  under
  `reports/field_validation/lte011-reconnect-store-forward-test-fix1-20260702-001/flash_report.md`.
- USB-Free runtime validation passed after the operator connected independent
  power and disconnected USB. Command `cmd-000033` produced raw LTE
  `location_report seq=28`, raw LTE `location_observation seq=29`, and raw LTE
  ACK `seq=30`.
- Runtime `location_observation` showed reconnect count `1`, reconnect reason
  `pdp_reactivate`, network failure reason `LTE_HTTP_ACTION_FAILED`,
  `cache_state=store_forward`, queued message count `1`, oldest age
  `12000 ms`, and dropped message count `0`.
- ACK completed as `ok` with `LTE_HTTP_OK` / HTTP `200`, network
  `ready_after_reconnect`, raw POST counters `2/2/0`, and cache queue drained
  to `0`.
- LTE-010 offline gate passed all five gates over the LTE-011 fix1 export:
  LTE runtime chain, reconnect attempt visibility, failure reason visibility,
  post-reconnect ACK, and store-forward evidence.

### Non-Claims

- No product readiness claim.
- No real modem reconnect recovery claim.
- No durable local storage or durable offline cache claim.
- No queue replay or multi-message outage recovery claim.
- No long LTE stability claim.
- No GNSS fix or outdoor GNSS acceptance claim.
- No battery accuracy, charging, or product power behavior claim.
- No learned model, learned personal-place, route prediction, or
  positioning-accuracy claim.
- No final enclosure, mounting, camera, audio, storage, calling, SMS, or
  dispatch claim.

### Next Gates

- Design real reconnect recovery evidence before treating modem/network
  interruptions as recovered.
- Design durable bounded store-forward semantics before claiming offline cache
  or replay.
- Add a later long-run LTE reliability gate only after real reconnect and
  store-forward evidence are visible.
- Track the product-demo closed loop as KR-008 / `DEMO-008`, not KR-006 or
  KR-007.

## Planned Gates After KR-007

KR-006 remains assigned to raw POST retry fault injection, and KR-007 is a
reconnect/store-forward evidence candidate. The product-demo loop from the
user-provided fusion-algorithm discussion remains valid, but it belongs to a
later gate.

### KR-008 / DEMO-008 Product Demo Closed Loop Candidate

The product-demo closed loop should be tracked after KR-007 as KR-008, with
`DEMO-008` carrying the first demo-report baseline:

```text
user trigger or safety event
-> device requests location/status
-> LTE raw-frame uplink
-> multi-source evidence aggregation
-> EALE-P0 location_belief generation
-> user confirmation or safety rule decision
-> report export
-> Web console replay/review
```

This gate should combine the existing raw LTE backbone, DATA-001 observation
windows, EALE-P0 derived belief, Safety Companion/user-confirmation records,
report export, and Web replay/review. It should still avoid product-readiness
claims unless R3 reliability, battery/power, enclosure, and GNSS acceptance
gates have also passed.

`DEMO-008` now provides the first offline report baseline through
`scripts/build_product_demo_report.py`. It can compose an existing Message Hub
test-run export with an existing safety-demo summary and produce
`product_demo_report.json` / `.md` plus supporting DATA-001 and EALE-P0
outputs. The first local report is intentionally `WARN`: it uses composite
existing evidence rather than a same-run product scenario, preserves the
current `Unknown` / `gnss_no_fix` location belief, and marks Web console
replay/review as pending. Dashboard visibility is now handled by DEMO-009 and
the repeatable DEMO-010 gate, but KR-008 should still not be manifested or
promoted until a same-run or regenerated product-demo report binds that Web
review evidence and clears the release blockers.

`DEMO-009` adds the first Message Hub Dashboard review surface for that report:
`/api/state` now includes `product_demo`, `/api/v1/product-demo/latest` returns
a bounded product-demo summary, and the Dashboard renders a Product Demo panel.
This makes DEMO-008 reviewable from Web/API, but it still does not create a
KR-008 release because the first report remains composite evidence and not a
same-run product scenario. The DEMO-009 Dashboard surface has also been
deployed to the VPS Message Hub with the DEMO-008 report copied under
`/opt/egolink-message-hub/reports/product_demo/`; this is deployment evidence,
not a KR-008 release manifest.

`DEMO-010` adds a repeatable Product Demo Web review gate through
`scripts/validate_product_demo_web_review.py`. The gate checks `/health`,
`/api/v1/product-demo/latest`, `/api/state` consistency, Dashboard Product Demo
markers, and the explicit release boundary. The read-only VPS run
`demo010-vps-20260703-001` passed against `203.0.113.10:8790`, confirming that
the current report is Web/API reviewable while preserving
`ready_for_kr008_release=false`. The underlying DEMO-008 report remains a
`WARN` composite artifact, and its internal `web_console_replay_review` field
still says `not_run` until a later same-run or regenerated product-demo report
binds this gate evidence.

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
