---
document_status: authoritative
last_verified: 2026-07-03
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
- LOC-005A completed the first firmware/server/Web source-state slots for
  Wi-Fi, IMU, and power in raw LTE `location_observation`, with explicit
  `disabled`, `missing`, `mock`, or `unverified` labels.

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
- EALE-P0 algorithm design is frozen as a server-side, derived-only,
  explainable rule/scoring baseline.

Remaining R2.5 work:

- LOC-005A source-state fields are implemented, but privacy-reviewed Wi-Fi
  fingerprints, product-topology IMU data, and real battery/power
  instrumentation are still unverified;
- known-place matching and richer rule-based belief updates remain
  LOC-005+/ALG-001+ work;
- product GNSS, enclosure, LTE long-run, and battery/power acceptance remain
  R3 gates.

### R3.0-R3.2 Product Gates

R3.0 validates LTE long-run and reconnect behavior. R3.1 validates independent
power and battery accuracy. R3.2 validates GNSS performance under enclosure,
mounting, and body/vehicle conditions. None of these may be inferred from
build success, USB serial logs, or the current Wi-Fi transport gate.

## 2026-07-04 D1 Field-Test Result Visibility And Next Runs

D1 is now in a live shakedown posture: the connectivity node periodically
uploads LTE D1 state to the VPS, the Dashboard shows the current estimate,
upload success, and power curve entry point, and the AMOLED companion can mirror
the state while connected as a PC sidecar.

Current evidence lives in two places:

- live state: VPS Message Hub database, visible through Dashboard and
  authenticated `/api/state`;
- run results: bounded report files under `reports/`, now surfaced by the
  Dashboard `Field Test Results` panel when the curated summaries are present
  on the VPS.

Immediate next task:

- `FIELD-004`: a 2-3 hour outdoor D1 walk/run using the 4G board as the primary
  device, battery/independent power, and optional AMOLED sidecar. The run should
  produce D1 field-companion evidence, a D1 Web/API report, and a power-curve
  report. After the run, sync only report summaries to the VPS Dashboard.

Near-term follow-up:

- finish `PWR-001` with a longer battery/power baseline once the short outdoor
  run proves the reporting loop is stable;
- promote the D1 demo only after the field report shows stable uploads,
  interpretable location state, and a started power curve without claiming
  accuracy or battery life.

Later tasks:

- `MAP-001`: replace the placeholder grid with an optional map/track provider
  after a provider/key/privacy decision. Until then the map block remains a
  no-API coordinate/estimate placeholder.
- D2 begins only after D1 has a usable field report: Wi-Fi/known-place inputs,
  reference-point error measurement, and first accuracy metrics.
- D3 follows D2 with 24h wearable-style power/reliability evidence.

## 2026-07-04 On-Device AI And Data Flywheel Side Track

The D1 link-through path is now good enough to start the V1 AI/data side track
without blocking outdoor field and power runs. The order is:

- keep FIELD-004 and PWR-001 as the source of reliable device, location, and
  power evidence;
- use M1 session recordings plus annotations as the bridge into the data
  flywheel, not transient Dashboard state;
- use DATA-003 to store bounded training-candidate records in a local SQLite
  candidate store while keeping `training_allowed=false`;
- add labeling and collection protocol work before any MotionNet training;
- run MotionNet-class models in shadow mode first, then measure RAM, flash,
  latency, and sleep-vs-inference power before any device-side release gate.

Current AI/data boundary:

- done: DATA-002 flywheel spec, DATA-003 candidate-store baseline, and
  DATA-004 data-flywheel control-plane visibility;
- active/planned: M1-002/M1-005/M1-006 data foundation and collection work,
  and MotionNet-class baseline work;
- done: DATA-005 candidate review queue can list bounded candidate summaries
  and conservatively approve, reject, or return records for changes without
  exposing raw records or enabling training before review gates pass;
- done: TRAIN-001 dataset/experiment handoff can export reviewed,
  training-allowed candidates into bounded manifests for a later training
  runner without starting model training;
- done: DATA-006 data-flywheel pipeline runner can ingest explicitly named
  session recordings, refresh data-flywheel status, and export the training
  dataset manifest from one post-run command;
- done: TRAIN-002 training experiment registry writes a bounded
  `training_experiment_plan` from the dataset manifest so a future runner has
  explicit readiness, gates, planned metrics, and non-claims;
- done: DATA-007 Dashboard/API visibility can surface the latest bounded
  training experiment plan and explicitly sync only curated experiment-plan
  summaries;
- done: DATA-009 synthetic scenario generator can produce explicit
  synthetic-only recordings for no-hardware data-flywheel dry-runs without
  treating them as field evidence or release metrics;
- done: TRAIN-003 training-run preflight can check a TRAIN-002 plan plus
  TRAIN-001 manifest before real runner integration while keeping measured
  metrics at `not_run`;
- done: DATA-010 Dashboard/API visibility can surface the latest bounded
  TRAIN-003 preflight and curated deploy summaries without exposing raw
  records, private training endpoints, or model artifacts;
- done: TRAIN-004 training feature manifest export can turn a ready TRAIN-001
  dataset plus TRAIN-003 preflight into bounded JSONL feature rows for a future
  runner, while keeping labels separate from features and producing no raw
  tensors, model artifacts, or measured metrics;
- done: DATA-011 Dashboard/API visibility can surface the latest bounded
  TRAIN-004 feature manifest and curated deploy summaries without exposing
  JSONL row contents, raw tensors, private training endpoints, or model
  artifacts;
- blocked from claims: MotionNet accuracy, on-device deployment acceptance,
  and model power/battery impact until measured evidence exists.

DATA-004 answers the immediate visibility gap: the live Message Hub database
remains the operational evidence store, while curated data-flywheel summaries
show candidate counts, review queues, split-leakage blockers, and model-training
readiness without exposing raw candidate records. DATA-006/TRAIN-002 now turn
reviewed candidates into dataset manifests and bounded training-experiment
plans, DATA-009 can dry-run the path with explicit synthetic-only records,
TRAIN-003 can preflight the runner handoff, DATA-010 makes that preflight
visible, and TRAIN-004 exports the bounded feature rows a future runner should
consume. DATA-011 then makes the feature-manifest readiness visible before any
model is evaluated or shipped.

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

The product-demo closed loop is not the current KR-006. KR-006 is already the
raw POST retry fault-injection baseline. The demo loop should be tracked after
the reconnect/store-forward evidence baseline, as `KR-008` with the first
demo-report baseline tracked by `DEMO-008`:

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

Inputs:

- R3 reliability baseline;
- at least one repeatable field test.
- raw LTE command/report/observation/ACK backbone;
- DATA-001 observation windows and EALE-P0 derived belief;
- user confirmation or Safety Companion event records;
- report export and replay evidence.

Current implementation baseline:

- `DEMO-008` adds an offline product-demo report generator that composes an
  existing Message Hub test-run export with an existing full safety-demo
  summary, then writes `product_demo_report.json` / `.md` plus supporting
  DATA-001 and EALE-P0 reports.
- The first report is a `WARN` composite-evidence artifact, not a KR-008
  release. Its internal `web_console_replay_review` remains pending until a
  later regenerated or same-run report binds DEMO-010 Web review evidence.
- `DEMO-009` adds that first Dashboard review path: `/api/state` includes
  `product_demo`, `/api/v1/product-demo/latest` returns a bounded summary, and
  the Dashboard renders a Product Demo panel. KR-008 still needs a same-run or
  explicitly accepted demo scenario plus a manifest before release.
- `DEMO-010` adds a repeatable Product Demo Web review gate:
  `scripts/validate_product_demo_web_review.py` checks Message Hub health, the
  Product Demo API, `/api/state` consistency, Dashboard markers, and the
  release-readiness boundary. The first read-only VPS gate passed as
  `demo010-vps-20260703-001`, but KR-008 still remains unreleased because the
  report is WARN/composite and not a same-run product scenario.
- `DEMO-011` binds DEMO-010 evidence back into the product-demo report
  generator through `--web-review-report`. The first bound report has all eight
  flow gates passing and is copied to the VPS Dashboard report store, but it
  still remains `WARN` because the evidence is composite, location belief is
  `Unknown`, dataset/model-training readiness is false, and no KR-008 manifest
  exists.

Outputs:

- device list;
- device detail page;
- map and track history;
- message log;
- command and ACK history;
- current-run location belief and source evidence;
- safety/user-confirmation decision trail;
- field-test report export;
- demo-session replay/review page;
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
- user trigger or safety-event flow can request location/status and produce a
  reviewable report;
- non-developers can understand whether the device is working, what the
  location belief means, and why a failure or no-fix happened.
