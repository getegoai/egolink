---
document_status: authoritative
last_verified: 2026-06-28
verified_by: codex
---

# Ego Link P0 Walking Skeleton Roadmap

This roadmap is the near-term USB-Free, VPS Message-First route for P0
development. The broader P0-to-product migration remains in
`../roadmap/P0_TO_PRODUCT_MIGRATION.md`.

## 2026-06-28 Route Update: Observable First

After FW-002C resetdiag fix3 produced the first USB-Free firmware-side
SIM7670G real GNSS fix through the VPS Message Hub, the next stage is not a
long blind stability run. The route is now:

```text
R2.1 observability completion gate
-> R2.2 short USB-Free baseline stability gate
-> R2.3 SIM7670G LTE data transport thin-slice
-> R2.4 LTE command loop gate
-> R2.5 multi-source location observation and memory MVP
-> R3.0 LTE long-run and reconnect gate
-> R3.1 independent-power and battery accuracy gate
-> R3.2 enclosure / mounting GNSS gate
```

This keeps the Walking Skeleton alive while making failures explainable before
longer field runs. A long USB-Free run over the current Wi-Fi HTTP path can
only validate the development transport, scheduler, VPS, Web, command ACK, and
GNSS task interaction. It cannot replace LTE transport, battery, enclosure, or
product power evidence.

### R2.1: Observability Completion Gate

Goal: make failures diagnosable before longer tests.

Required visible state:

- current transport type, RTT, and last transport error;
- GNSS fix/no-fix, attempt duration, quality fields, and reason code;
- SIM7670G cellular registration and cell fingerprint fields when available;
- command last command ID, status, ACK status, and round-trip time;
- reset reason, boot identity, uptime, watchdog count, and free heap;
- power voltage, state-of-charge estimate, charging state, and source label;
- location state as `Fine`, `Coarse`, `Predicted`, or `Unknown` when the
  location-observation contract is active.

Definition of Done:

- `/api/state` exposes a normalized observability view without requiring new
  firmware fields.
- test-run export includes an observability summary.
- Dashboard shows enough state to distinguish no-fix, transport failure,
  command timeout, reset, low/unknown power, and missing observation.
- The change is additive to `egolink.p0.v1`.

### R2.2: USB-Free Baseline Stability Gate

Goal: run the current transport briefly, without USB runtime dependency, to
check scheduler, VPS, Web, command ACK, GNSS command, and reconnect behavior.

Definition of Done:

- device runtime evidence comes from the VPS and Web, not serial logs;
- sequence continuity, last-seen age, command ACK, GNSS state, reset
  diagnostics, and reason codes are visible in export;
- failures produce diagnosable reason codes;
- this gate is explicitly not LTE product-link acceptance.

### R2.3: SIM7670G LTE Data Transport Thin-Slice

Goal: prove the device can send one minimal telemetry message to the VPS over
SIM7670G LTE with Wi-Fi disabled.

Definition of Done:

- LTE registration, PDP activation, assigned IP, HTTP POST result, and
  `transport.type=lte` are visible;
- Web shows LTE last update, cell fingerprint, and signal quality;
- failure states identify whether the problem is SIM, registration, PDP, DNS,
  HTTP, or server reachability.

### R2.4: LTE Command Loop Gate

Goal: move the existing HTTP command queue, polling, execution, and ACK loop to
the LTE transport without changing the command envelope.

Definition of Done:

- Web can enqueue a harmless command;
- device polls over LTE, executes once, and ACKs over LTE;
- duplicate execution, timeout, and retry state are visible.

### R2.5: Multi-Source Location Observation MVP

Goal: move from coordinate-only GNSS reporting to a multi-source observation
and belief model.

Current increment:

- LOC-002 completed the `location_observation` contract/server/simulator
  baseline.
- LOC-003 completed the first VPS-side `location_memory` table and active
  `Predicted` belief gate for the case where a later GNSS report is no-fix but
  a prior memory exists.
- LOC-004A completed the first raw LTE firmware-side SIM7670G cell/LTE
  `location_observation` gate and KR-003 released it as an engineering Walking
  Skeleton point.

Definition of Done:

- device or simulator can upload `location_observation` or additive
  observation fields containing GNSS, cell, Wi-Fi, IMU, power, and
  `location_belief`;
- Web shows `Fine`, `Coarse`, `Predicted`, or `Unknown` instead of only
  "GPS success/failure";
- VPS can query GNSS attempts, cell fingerprints, and belief records by
  `test_run_id`.
- dataset tooling can rebuild observation windows from raw-frame lineage,
  derived events, labels, and quality checks instead of using transient
  Dashboard state.

Remaining R2.5 work:

- firmware-side real Wi-Fi/IMU/power observation is still unverified;
- known-place matching, dataset export, and richer rule-based belief updates
  remain DATA-001/LOC-005+ work;
- product GNSS, enclosure, LTE long-run, and battery/power acceptance remain
  R3 gates.

### R3.0-R3.2 Product Gates

R3.0 validates LTE long-run and reconnect behavior. R3.1 validates independent
power and battery accuracy. R3.2 validates GNSS performance under enclosure,
mounting, and body/vehicle conditions. None of these may be inferred from
build success, USB serial logs, or the current Wi-Fi transport gate.

## R0: VPS + PC Simulator Simulated Loop

Goal: prove the public message hub and dashboard without hardware.

Inputs:

- PC Simulator virtual device.
- VPS Message Hub.
- Web Dashboard.

Outputs:

- virtual device online;
- simulated heartbeat and GNSS telemetry;
- command queued from Web/API;
- PC Simulator ACK recorded.

Modules:

- `server/` or selected VPS service directory;
- `pc_simulator/`;
- `web/` or Dashboard surface;
- `docs/development/PROTOCOL.md`.

Not Allowed:

- firmware behavior changes;
- hardware claims;
- real private credentials in repository files.

Definition of Done:

- browser can show one virtual device online through VPS data;
- simulated location updates continuously;
- command status changes from pending to ACK;
- messages are stored in logs or database;
- no hardware is required.

## R1: Real Hardware Loop Without Real GNSS

Goal: prove real device networking and command ACK without USB runtime
dependency.

Inputs:

- real firmware on independent power;
- fixed or mock location;
- VPS Message Hub and Dashboard.

Outputs:

- boot/status messages from the real device;
- Dashboard online/stale status;
- command ACK from the real device.

Modules:

- `firmware/` network and heartbeat path;
- Server-Web command queue;
- Dashboard device status.

Not Allowed:

- using serial logs as the only acceptance evidence;
- changing protocol fields without a Protocol task;
- claiming real GNSS, battery, or sensor evidence from mock data.

Definition of Done:

- device runs with USB disconnected;
- server receives boot and periodic heartbeat;
- Web shows real device status;
- command ACK is visible in server/Web evidence;
- evidence identifies board, firmware image/commit, timestamp, and paths.

## R2: Real GNSS Outdoor Loop

Goal: report real GNSS fix/no-fix state and track points through the VPS while
USB is disconnected.

Inputs:

- R1 passed device;
- GNSS antenna and outdoor sky view;
- field `test_run_id`.

Outputs:

- `fix=false` reports while searching;
- `fix=true` reports with lat/lon/satellites/HDOP when fixed;
- Dashboard latest location and track;
- command ACK for report interval or equivalent harmless command.

Modules:

- firmware GNSS collection and telemetry packaging;
- server telemetry storage;
- Dashboard GNSS state and track view;
- `docs/development/FIELD_TEST.md`.

Not Allowed:

- PC-side USB AT probe as product-side GNSS behavior;
- silent no-data when GNSS has no fix;
- unrelated AI or UI rewrites.

Definition of Done:

- outdoor test runs with USB disconnected;
- Dashboard shows transition from searching/no-fix to fixed or a clear failure
  reason;
- report export includes evidence paths and unresolved risks.

## R3: Field Reliability Version

Goal: make weak network, slow GNSS, disconnects, and device errors observable
without serial logs.

Inputs:

- R2-capable path;
- planned weak-network or reconnect test.

Outputs:

- reconnect state;
- cache or dropped-message accounting;
- server receive timestamps;
- device health and error state.

Modules:

- firmware reconnect and local cache;
- protocol sequence/dedup fields;
- server dedup and diagnostics;
- Dashboard health state.

Not Allowed:

- hiding failures behind generic offline status;
- unversioned protocol changes;
- claiming battery or power metrics without verified source labels.

Definition of Done:

- 30-minute field run completes without crash;
- short network outage recovers or is explicitly diagnosed;
- Web distinguishes no-fix, no-network, stale, low-battery, device-error, and
  server-error states.

## R4: Product Demo Version

Goal: make a non-developer understandable product prototype demo.

Inputs:

- R3 reliability baseline;
- at least one repeatable field test.

Outputs:

- device list;
- device detail page;
- map and track history;
- message log;
- command and ACK history;
- field-test report export;
- basic remote configuration.

Modules:

- Server-Web;
- Dashboard;
- protocol docs and schemas;
- deployment docs.

Not Allowed:

- making cloud AI a required safety path;
- storing raw private audio/image/screen data by default;
- depending on USB, serial monitor, or development tools during demo.

Definition of Done:

- a product demo can be completed from Web Dashboard only;
- online, location, track, command, ACK, error, and report states are visible;
- non-developers can understand whether the device is working.
