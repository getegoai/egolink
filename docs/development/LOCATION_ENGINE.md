---
document_status: authoritative
last_verified: 2026-08-23
verified_by: codex
---

# Ego Adaptive Location Engine

Under [ADR-0012](../architecture/adr/ADR-0012-p0-productization-sprint-1.md),
Ego Link has two explicit location layers:

```text
device Location Engine v0 + Sensor Policy v0
-> versioned observation and operational state
-> server mirror, event-time timeline, replay, comparison and derived fusion
```

The device layer is the live operational authority needed to act offline. The
server-side Evidence-Aware Location Estimator (EALE-P0) in
`LOCATION_FUSION_ALGORITHM.md` remains a reusable derived-fusion and replay
baseline; it is not the sole owner of current device state. `P0-LOC` is
currently `NOT_RUN`. LOC-020/POLICY-010 code or replay evidence does not by
itself pass that Gate.

EALE is not "wait for GPS". It is:

```text
low-power observation
-> bounded GNSS calibration pulse
-> location belief
-> field memory
-> explainable safety state
```

## Principles

- GNSS is a high-cost calibrator, not a permanent blocking dependency.
- No-fix is valid telemetry when it includes state, attempt budget, and reason.
- Location is represented as a belief with radius, confidence, source, and
  reason, not only a coordinate pair.
- Cell, Wi-Fi, IMU, power, and transport context are product data assets.
- Personal location memory is built from observed field evidence, not from
  unlabelled assumptions.
- Device state reduction follows source event time plus boot-scoped monotonic
  and clock-mapping lineage. Server receive/ingest order must not manufacture
  a newer device state.
- LOC-020 binds every trusted coordinate to an actual `timestamp_utc_ns`,
  `gnss_source_utc_ns`, or boot-counted/clock-domain-scoped monotonic timestamp;
  its millisecond lane must equal `event_time_ms`, and the selected capture
  field is retained in `evidence_ref`. A string such as `capture_event` alone
  is not time evidence.
- Learned fusion and camera/context work start with data quality, replay and
  offline/shadow comparison. They are non-blocking L2/L3 work in Sprint 1.

## Device Operational State

Location Engine v0 owns at least:

- mobility, GNSS and LTE state;
- last trusted location and its source event time;
- current public location belief, accuracy, confidence, source and
  uncertainty;
- battery and effective Sensor Policy state;
- GNSS attempt/backoff and action lineage.

Sensor Policy configuration has both a structural schema and the required
`egolink.sensor_policy.semantic.v0.1` validator. The latter covers finite
numbers and cross-field threshold/order rules that standard JSON Schema cannot
express. Firmware, VPS and replay must port the named validator identically.

These dimensions remain separate. Public belief is
`Fine | Coarse | Predicted | Unknown`; mobility is independent; Sensor Policy
uses `STABLE | MOVING | LOCATION_UNCERTAIN | SOS | LOW_BATTERY`, with SOS
overriding low-battery budgets without erasing the battery condition. Server
derived beliefs carry their own generator/config identity and never silently
overwrite the recorded device belief.

## GNSS-Denied Growth Strategy (non-blocking in Sprint 1)

Proposed ADR-0007 defines a product extension of EALE for founder review
without changing the EALE-P0 public states or the ADR-0004 rule-first boundary:

```text
quality-gated GNSS anchor; optional bounded-place/BLE coarse anchors
-> personal place nodes and route segments
-> cell/BLE/motion/barometer/time evidence
-> bounded Top-K hypotheses
-> Fine | Coarse | Predicted | Unknown
-> uncertainty-driven bounded sensing
```

Top-K hypotheses preserve ambiguity internally; they do not authorize several
precise map dots or a guessed coordinate. A known-place or route hypothesis
may produce `Coarse` or `Predicted` only with an area/radius, freshness,
reason, and evidence references. Stale or conflicting hypotheses become
`Unknown`.

The historical plan implements this path with lookup, clustering, transition
statistics, thresholds, and conservative decay. Under ADR-0012 these assets may
feed server-derived/offline replay but do not precede LOC-021/FIELD-020 and do
not become an unmeasured device dependency. ADR-0004 still approves only IMU
motion state as a learned candidate. Source-reliability, GNSS-acquisition, or
sensing-value models are post-P0 research ideas requiring a later
founder-reviewed ADR/task before they may affect policy or belief; no model
directly regresses latitude/longitude.

Current ESP32-S3 Wi-Fi may support engineering experiments. ADR-0008
supersedes the prior ADR-0006 production-radio topology and reopens the
screenless EgoLink Core A0/A1 2.4 GHz decision. Production Wi-Fi scan, BLE,
antenna, power, coexistence, privacy, and exact-part behavior all remain
`unverified`; the location baseline therefore cannot require Wi-Fi. Cellular
memory and any future authenticated, fresh, proximity-bounded BLE/Wi-Fi anchor
remain optional, source-labelled evidence until a later accepted hardware and
privacy decision enables them.

## Power Scheduler Boundary

ADR-0003 adopts an `L0`..`L4` low-power location scheduler for planning sensor
and reporting budgets. These scheduler states are separate from the public
EALE-P0 location states below:

- `L0` Deep Sleep / Safe Still;
- `L1` Low Power Watch;
- `L2` Moving Normal;
- `L3` Uncertain Locate;
- `L4` Emergency Track.

The scheduler decides when GNSS, Wi-Fi, LTE, IMU, display, and report cadence
should be active. It does not output user-facing location belief and must not
replace `Fine`, `Coarse`, `Predicted`, or `Unknown`. Any implementation must
emit additive telemetry for state entry/exit, transition reason, GNSS attempt
budget, power source/status, and emergency override reason before it can be
accepted.

## P0 Location States

| State | Meaning |
|---|---|
| `Fine` | GNSS or equivalent high-confidence fix. |
| `Coarse` | Cell, Wi-Fi, or known-place estimate with bounded uncertainty. |
| `Predicted` | Last-known or route/motion-based estimate with decaying confidence. |
| `Unknown` | Not enough evidence; do not output fake coordinates. |

## Location Observation Shape

`LOC-002` should add either `event_type=location_observation` or compatible
additive fields on an existing location event. The transport envelope remains
`egolink.p0.v1`.

Recommended payload groups:

- `transport`: current path, RTT, and last transport error.
- `gnss`: enabled state, fix state, quality, attempt duration, result.
- `cell`: LTE RAT, operator, MCC/MNC, TAC, cell ID, and signal quality.
- `wifi`: scan state and privacy-preserving AP fingerprints.
- `imu`: stationary/moving/running/vehicle state and confidence.
- `power`: battery voltage, state-of-charge estimate, charging state, source.
- `location_belief`: state, radius, confidence, sources, and reason.

Exact user coordinates and Wi-Fi fingerprints must stay inside bounded evidence
or explicitly privacy-reviewed data stores. Current docs should describe the
evidence shape without copying private coordinates.

LOC-021 freezes `egolink.location_state_envelope.v0.1` as an additive contract
around the Location Engine v0 state. It binds device, boot, session,
observation, sequence, source-event nanoseconds and the exact Sensor Policy
identity without changing the existing `egolink.p0.v1` event envelope.
`server_receive_time_ms` is trusted-adapter transport evidence only; it cannot
own ordering, state age or location freshness. The live adapter, persistence
and device producer remain unimplemented until their named LOC-021 slices.

## P0 Rule Engine

Start with rules, not a complex model:

- GNSS fix with acceptable quality -> `Fine`.
- No GNSS but cell or Wi-Fi matches a known place -> `Coarse`.
- Stationary device with stable fingerprint -> keep last-known and decay
  confidence.
- Moving device with changing fingerprint -> lower confidence and request a
  bounded GNSS pulse.
- Known GNSS-bad zone -> reduce GNSS attempt duration or trigger less often.

The server-derived rule/scoring design is EALE-P0 in
`LOCATION_FUSION_ALGORITHM.md`. That document keeps the public states here
(`Fine`, `Coarse`, `Predicted`, `Unknown`) and represents more detailed
outcomes such as known-place, last-known hold, no-fix, stale, and runtime
failure as reasons, substates, and quality flags.

ADR-0004 freezes this as the P0 product decision. Cell/Wi-Fi matching,
known-place and GNSS-bad-zone discovery, and belief fusion use explainable
lookup, history statistics, clustering, thresholds, and rules. P0 does not add
a learned location-fusion model merely to make this path appear more
intelligent.

The only current learned-model candidate is IMU motion state
(`stationary`/`walking`/`vehicle`) because it can directly inform the low-power
scheduler and GNSS pulse policy. It remains a candidate until a rules baseline,
held-out real-session evaluation, int8 resource measurements, shadow-mode
behavior, and inference power evidence pass.

## Data Assets

Future VPS materialized tables or query views should be introduced by task,
not all at once:

- `location_observations`
- `gnss_attempts`
- `cell_fingerprints`
- `wifi_fingerprints`
- `known_places`
- `gnss_bad_zones`
- `route_segments`
- `location_beliefs`
- `observation_windows`

These names are a target data model, not a claim that every physical table
exists today. The current Message Hub truth is `raw_frames`, normalized
`messages`, and the LOC-003 `location_memory` table. Bounded exporters should
rebuild algorithm and training views from that evidence until measured scale
or query cost justifies another store.
- `location_fusion_samples`
- `dataset_exports`

Training data must not be built from transient Dashboard state. The
algorithm-facing data path is defined in `LOCATION_DATASET.md`: stored raw
frames and derived events are rebuilt into replayable observation windows,
then exported as labelled dataset samples with lineage, privacy class, split
assignment, and generator versions.

## Near-Term Tasks

Current ADR-0012 execution takes precedence over the historical inventory
below:

1. `LOC-020`: accepted device-semantic Location Engine v0 PC reference; not
   product or hardware evidence.
2. `POLICY-010`: accepted configurable Sensor Policy v0 PC reference; the
   named semantic validator must be ported by every consumer.
3. `REPLAY-010`: accepted event-time replay/comparison over Field Session
   artifacts; data/replay evidence only.
4. `LOC-021`: integrate the reducer/config identity into device runtime,
   server mirror and Guardian view.
5. `FIELD-020`: run representative outdoor/indoor/GNSS-denied/motion/power
   evidence after LOC-021. Only named acceptance may change `P0-LOC`.

Historical/reusable task lineage:

1. `DATA-001`: completed location-fusion dataset sample/export baseline from
   raw-frame lineage, derived events, labels, and quality checks.
2. `ALG-000`: completed EALE-P0 location fusion algorithm design freeze.
3. `LOC-005A`: completed firmware-side Wi-Fi/IMU/power source-state slots in
   raw LTE `location_observation` as explicit `disabled`, `missing`, `mock`,
   `observed`, or `unverified` inputs.
4. `LOC-005B+`: add privacy-reviewed Wi-Fi fingerprints, product-topology IMU
   observations, and real battery/power instrumentation behind those stable
   source-state slots.
5. `OBS-003`: completed current run, key release, and failure reason
   visibility from Web/report surfaces.
6. `ALG-001`: completed optional server-side EALE-P0 derived
   `location_belief` view for current run, exports, and Dashboard visibility.
7. `ALG-002`: completed offline EALE-P0 evaluation over DATA-001 JSONL for
   evidence, failure, lineage, feature, privacy, and model-training readiness
   metrics before KR-004 promotion review.
8. `STAB-001B`: run a short USB-Free KR-003 baseline after data/observability
   gates can explain failures.
9. `LTE-005`: add reconnect, retry, cache, stale-command, and duplicate
   handling gates before long field tests.
10. `LOC-006`: freeze the GNSS-denied anchor, personal place/route-memory,
    bounded-hypothesis, privacy, radio, and evaluation strategy.
11. `LOC-007` (planned after LOC-006 review): implement the smallest
    privacy-reviewed personal place/route memory plus GNSS-masked replay and a
    known-place false-positive gate.
12. `PWR-003` keeps its ADR-0003 meaning: additive scheduler-state telemetry
    and initial measured rule budgets. Any post-P0 reliability or adaptive
    sensing model needs a later founder-reviewed ADR/task and labelled corpus.

## LOC-002 Baseline

LOC-002 establishes the first `location_observation` server/simulator
baseline:

- `event_type=location_observation` is accepted under `egolink.p0.v1`.
- PC Simulator can upload mock GNSS, cell, Wi-Fi, IMU, power, and
  `location_belief`.
- Message Hub treats both `location_report` and `location_observation` as
  location evidence.
- Dashboard can display location state, belief confidence/radius, belief
  source, belief reason, Wi-Fi AP count, and IMU motion.

Boundary: LOC-002 does not prove firmware-side cell fingerprint collection,
real Wi-Fi scanning, real IMU fusion, battery accuracy, location-memory tables,
or a rule engine. Those remain later tasks.

## LOC-003 / LOC-004A Server Memory Gate Baseline

LOC-003 adds the first VPS-side memory table and a small active-belief rule:

- `location_observation` with `location_belief` updates persistent
  `location_memory`.
- `location_report fix=true` creates a `Fine` GNSS calibration memory.
- `location_report fix=false` records `last_no_fix` but does not erase the
  last useful memory.
- `location_observation.location_belief.state=Unknown` records
  `last_unknown_observation` but does not erase a useful `Fine`, `Coarse`, or
  `Predicted` memory.
- When the latest location report is no-fix but memory exists, the active
  `observability.location_belief` becomes `Predicted` with reason
  `last_known_after_gnss_no_fix`.
- When the latest location observation is explicit `Unknown` but memory exists,
  the active `observability.location_belief` becomes `Predicted` with reason
  `last_known_after_unknown_location_observation`.
- `/api/state`, Dashboard, and test-run export expose both active belief and
  preserved memory.
- `scripts/validate_location_memory_gate.py` can rerun this gate with a
  synthetic device and no hardware action.

Boundary: this is not final EALE. It does not prove firmware-side cell/Wi-Fi/
IMU/power collection, learned personal places, route prediction, real outdoor
GNSS acceptance, LTE long-run reliability, or product readiness.

LOC-004A adds the first firmware-side cell/LTE observation path to this rule
set. During raw LTE `request_location`, firmware can upload a command-scoped
`location_observation` with real SIM7670G cell/LTE evidence and an explicit
`Unknown` belief. This makes weak/no-fix location attempts explainable without
depending on USB logs. It still does not estimate a position from cell data;
that belongs to later known-place and fusion tasks.

## DATA-001 Fusion Dataset Baseline

DATA-001 creates the data foundation for later fusion algorithms:

- raw frames remain the transport truth;
- derived `location_report`, `location_observation`, command, ACK, and
  observability views remain explainable features;
- training samples are observation windows with raw-frame references, not
  single Dashboard snapshots;
- failed and partial frames are retained as diagnosable samples;
- labels keep their source, confidence, consent/training flags, and privacy
  class;
- train/validation/test splits avoid leakage across the same session, device,
  place, or time block.

Boundary: DATA-001 should not train a learned model, publish cell-only
positioning accuracy, or change device wire fields.

EALE does not replace the existing `request_location -> location_report -> ACK`
loop. It extends it into an explainable location system.
