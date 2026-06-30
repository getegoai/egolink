---
document_status: authoritative
last_verified: 2026-06-30
verified_by: codex
---

# Ego Adaptive Location Engine

Ego Adaptive Location Engine (EALE) is the P0 location direction after the
USB-Free Message Hub path and firmware-side SIM7670G real GNSS fix were proven.
The frozen P0 algorithm baseline is `LOCATION_FUSION_ALGORITHM.md`.

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

## P0 Rule Engine

Start with rules, not a complex model:

- GNSS fix with acceptable quality -> `Fine`.
- No GNSS but cell or Wi-Fi matches a known place -> `Coarse`.
- Stationary device with stable fingerprint -> keep last-known and decay
  confidence.
- Moving device with changing fingerprint -> lower confidence and request a
  bounded GNSS pulse.
- Known GNSS-bad zone -> reduce GNSS attempt duration or trigger less often.

The formal P0 rule/scoring design is EALE-P0 in
`LOCATION_FUSION_ALGORITHM.md`. That document keeps the public states here
(`Fine`, `Coarse`, `Predicted`, `Unknown`) and represents more detailed
outcomes such as known-place, last-known hold, no-fix, stale, and runtime
failure as reasons, substates, and quality flags.

## Data Assets

Future VPS tables should be introduced by task, not all at once:

- `location_observations`
- `gnss_attempts`
- `cell_fingerprints`
- `wifi_fingerprints`
- `known_places`
- `gnss_bad_zones`
- `route_segments`
- `location_beliefs`
- `observation_windows`
- `location_fusion_samples`
- `dataset_exports`

Training data must not be built from transient Dashboard state. The
algorithm-facing data path is defined in `LOCATION_DATASET.md`: stored raw
frames and derived events are rebuilt into replayable observation windows,
then exported as labelled dataset samples with lineage, privacy class, split
assignment, and generator versions.

## Near-Term Tasks

1. `DATA-001`: completed location-fusion dataset sample/export baseline from
   raw-frame lineage, derived events, labels, and quality checks.
2. `ALG-000`: completed EALE-P0 location fusion algorithm design freeze.
3. `LOC-005A`: add firmware-side real Wi-Fi/IMU/power observation as explicit
   `observed`, `unknown`, or `unverified` inputs.
4. `OBS-003`: make current run, key release, and failure reason visible from
   Web/report surfaces.
5. `ALG-001`: add optional server-side derived `location_belief` generation
   from DATA-001 observation windows.
6. `STAB-001B`: run a short USB-Free KR-003 baseline after data/observability
   gates can explain failures.
7. `LTE-005`: add reconnect, retry, cache, stale-command, and duplicate
   handling gates before long field tests.

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
