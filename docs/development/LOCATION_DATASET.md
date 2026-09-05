---
document_status: authoritative
last_verified: 2026-08-23
verified_by: codex
---

# Location Fusion Dataset Baseline

This document defines the data boundary for Ego Link P0 location fusion and
future model-training collection. It extends the EALE direction in
`LOCATION_ENGINE.md` and feeds the EALE-P0 algorithm baseline in
`LOCATION_FUSION_ALGORITHM.md` without changing the live wire protocol.

The current rule is:

```text
raw frame evidence
-> derived Web/API/event view
-> replayable observation window
-> labelled dataset sample
-> model or rule evaluation
```

Under [ADR-0012](../architecture/adr/ADR-0012-p0-productization-sprint-1.md),
this is the server evidence/replay/derived-fusion path. Device Location Engine
v0 remains the operational live-state owner; dataset or server outputs do not
silently replace its recorded belief or policy state. Sprint 1 AI is
data/replay first and non-blocking. `P0-LOC` remains `NOT_RUN` until named
device integration and representative field acceptance are run.

Do not train directly from transient Dashboard state. Dashboard state is an
operator view. Training data must be rebuilt from stored raw evidence,
derived events, labels, and a manifest.

## Current Data Truth Layers

| Layer | Current authority | Purpose |
|---|---|---|
| Raw transport evidence | `message_hub_raw_frame_record.schema.json` and the Message Hub `raw_frames` table | Preserve exact received payload metadata, byte length, hash, CRC, frame ID, parser status, and parse failure reason before semantic conversion. |
| Derived event view | `message_hub_event.schema.json` and Message Hub events | Provide normalized `location_report`, `location_observation`, LTE, GNSS, power, IMU, Wi-Fi, and belief fields for Web/API/export compatibility. |
| Test-run export | `/api/v1/test-runs/{test_run_id}/export` | Rebuild a bounded run with messages, raw-frame summaries, observability summary, commands, ACKs, and failure explanations. |
| Session recording | PC Simulator recording directories | Preserve replayable safety-loop windows, sensor frames, events, annotations, quality reports, and replay outputs. |
| Dataset sample | `shared/contracts/location_fusion_sample.schema.json` and `scripts/export_location_fusion_dataset.py` | Immutable algorithm sample that links raw evidence, derived features, labels, privacy class, split assignment, and generator versions. |

## Current Algorithm-Relevant Inputs

These groups are already represented in contracts or current task docs. Some
are proven by KR-003, while others remain mock, unknown, or unverified.

| Group | Important fields | Current P0 state |
|---|---|---|
| Identity and lineage | `device_id`, `fw_version`, `test_run_id`, `cmd_id`, `frame_id`, `seq`, `boot_id`, parser version | Available for raw LTE command/location slices. `cmd_id` links `request_location`, `location_report`, `location_observation`, and ACK. |
| Time and ordering | source/capture time, `boot_id`, boot-scoped monotonic time, UTC anchor/clock mapping, `server_received_at`, `ingest_time`, `seq` | Source event time plus boot-scoped monotonic/clock-mapping lineage is the semantic ordering authority. Receive/ingest time records transport behavior and must not replace missing or ambiguous event time. |
| GNSS | `fix`, `lat`, `lon`, `satellites`, `hdop`, `gnss_state`, `gnss_query_ok`, `source_status` | Firmware-side GNSS fix has been observed in prior USB-Free evidence; KR-003 location reports were no-fix but diagnosable. Coordinates must stay in bounded evidence/export stores, not copied into current docs. |
| Cell/LTE radio | `cell_rat`, `mcc`, `mnc`, `tac`, `cell_id`, `rsrp`, `rsrq`, `rssi`, `sinr`, registration/PDP state, `assigned_ip`, LTE reason code | KR-003 proves real firmware-side SIM7670G cell/LTE observation over LTE raw frames. It does not infer position from cell data. |
| Transport/runtime | `transport.type`, LTE HTTP phase/status/reason, RTT/action elapsed, reset reason, uptime, free heap, watchdog/reset counters | Available enough to explain failed field runs and distinguish no-fix from transport or runtime failure. |
| Wi-Fi fingerprint | AP hash, RSSI, scan state, scan duration | Contract/server/simulator baseline exists. Real firmware-side Wi-Fi observation is not yet verified for the location path. Raw private BSSID should not be retained by default. |
| IMU motion | motion state, confidence, activity label, stationary seconds, raw/window reference | QMI8658 evidence exists on the wearable path, but firmware-side location-observation fusion with connectivity-node records is not yet verified. |
| Power | battery voltage, SOC estimate, charging state, power source and source label | Contract fields exist. Product battery/power behavior remains unverified. |
| Belief and labels | `location_belief.state`, radius, confidence, source, reason; `safety_annotation`; user confirmation | Location belief is currently rule-derived. User confirmation and annotation tooling exist for safety sessions, but location-specific labelled dataset samples are future work. |

## Sample Unit

The dataset unit for location fusion should be an observation window, not a
single message row.

Recommended initial window:

```text
window_id
device_id
test_run_id
start_server_received_at
end_server_received_at
start_event_time
end_event_time
clock_mapping_refs[]
anchor_event_id
anchor_cmd_id
raw_frame_refs[]
derived_event_refs[]
features
labels
quality
privacy
split
generator
```

The first useful window types are:

- `location_request_window`: from command creation through
  `location_report`, optional `location_observation`, and ACK.
- `passive_observation_window`: periodic status/observation evidence without a
  downlink command.
- `known_place_calibration_window`: a high-confidence GNSS or operator-labelled
  place used to seed or verify memory.
- `failure_window`: no-fix, partial frame, checksum failure, transport failure,
  reset, stale command, or missing ACK.

Incomplete and malformed data should be retained as dataset candidates with a
failure label. They are often more valuable for robustness than perfect runs.
Rows whose event order is ambiguous or unavailable must be counted and
excluded from order-dependent comparisons rather than guessed from arrival
order.

## Minimum Dataset Manifest

Every exported dataset shard should include a manifest with:

- source test-run IDs and session IDs;
- source device IDs and firmware versions;
- parser and feature-generator versions;
- raw-frame hash coverage and redaction policy;
- schema versions;
- train/validation/test split rule;
- label sources and label confidence;
- privacy class and consent/training flags;
- known gaps and excluded evidence.

The split rule must avoid leakage. Do not randomly split individual rows from
the same field session across train and test. Prefer session-, device-, place-,
or time-blocked splits.

## Motion Labels

The first approved learned-model dataset target is IMU motion state, not
location belief. Reuse the raw-frame/message evidence and bounded export path;
do not create a second ingest pipeline just for model work.

- high-quality GNSS speed plus stable fix quality can generate weak
  moving/not-moving candidates;
- `speed > 2 m/s` alone must not label `vehicle`, and it cannot separate
  walking from vehicle;
- exclude no-fix windows, unstable speed, poor-quality fixes, and transition
  windows from automatic high-confidence labels;
- use controlled runs or reviewed labels for the three-class ground truth;
- split by whole session/device/place/time block so adjacent IMU windows do
  not leak across train and test;
- compare against a threshold/features rules baseline before training, then
  require shadow-mode, footprint, latency, and power evidence before device
  control is enabled.

`scripts/assess_motion_data_readiness.py` is the pre-export gate. It reads a
bounded Message Hub field export in memory and writes only aggregate counts:
real/mock IMU coverage, cadence, good-fix speed coverage, IMU/GNSS join
coverage, weak-label balance, and blockers. It never writes coordinates,
cells, raw messages, training rows, or walking/vehicle labels. A passing gate
permits a later dataset export task; it does not permit model training.

## Privacy And Retention

Default retention should favor structured evidence and hashes over raw private
payloads. Product-demo and V1 field-test exports must also obey
`../product/PRODUCT_DEMO_PRIVACY_BOUNDARY.md`.

- Exact coordinates, Wi-Fi fingerprints, audio, images, and private place
  labels need an explicit privacy class.
- Raw audio and raw images are not part of the location-fusion dataset by
  default.
- Wi-Fi AP identifiers should be hashed or otherwise privacy-reviewed before
  long retention.
- Product-demo evidence is not training data by default; use
  `training_allowed=false` until explicit consent and privacy review select a
  run for DATA-002 or model work.
- Dataset exports under `model_artifacts/` or runtime directories are not
  committed unless explicitly converted into small synthetic fixtures.
- P0 VPS location memory is transitional engineering storage. Product known
  places, common routes, and GNSS-bad zones migrate to the device or local Ego
  Base by default; server retention requires explicit consent, minimization,
  purpose, and deletion policy.

## Implemented DATA-001 Baseline

`DATA-001` establishes the first dataset-generation path without changing the
live device wire protocol:

- Contract: `shared/contracts/location_fusion_sample.schema.json`.
- Exporter: `scripts/export_location_fusion_dataset.py`.
- Input: a Message Hub test-run export JSON object.
- Output: `samples.jsonl` plus `manifest.json`; the default output root is
  ignored runtime/report storage under `reports/location_fusion_datasets/`.
- Unit tests: `quality_tests/test_location_fusion_dataset_export.py`.

The exporter currently builds command-scoped `location_request_window`,
`known_place_calibration_window`, passive observation windows, and raw-frame
failure windows. It keeps raw payload bytes out of dataset samples, preserves
raw-frame IDs and hashes, flags private coordinates, and blocks training by
default when private location appears.

EALE-P0 consumes these windows as algorithm inputs. It should treat the
dataset labels as evidence and quality annotations, not as permission to train
a learned model or claim positioning accuracy.

## Implemented ALG-002 Coverage Evaluation

`ALG-002` adds an offline EALE-P0 dataset evaluator on top of DATA-001:

- Evaluator: `scripts/evaluate_eale_p0_dataset.py`.
- Input: DATA-001 `samples.jsonl` plus `manifest.json`.
- Output: `eale_p0_dataset_report.json` plus
  `eale_p0_dataset_report.md`; the default output root is ignored
  runtime/report storage under `reports/location_fusion_eale/`.
- Unit tests: `quality_tests/test_eale_p0_dataset_evaluation.py`.

The evaluator reports sample counts, label states, failure modes, raw-frame
lineage coverage, derived-event coverage, feature-group coverage, source-state
coverage, privacy/training flags, and EALE-P0 review counters such as retained
failure windows, no-fix Unknown samples, Fine candidates, and cell/LTE evidence
that must not become a position by itself.

This is a release-review and corpus-quality tool. It does not train a model,
change DATA-001 schema, change device wire fields, or claim positioning
accuracy. A dataset can be acceptable evidence for release review while still
being explicitly not ready for learned-model training.

## DATA-001 Follow-On Direction

The baseline leaves these deliberate next steps:

1. Complete REPLAY-010 event-time policy comparison with explicit excluded and
   ambiguous-row counts; do not claim accuracy or power savings without ground
   truth and measured energy.
2. Add operator labels and known-place calibration labels as explicit inputs.
3. Add split-leakage checks across multiple sessions, devices, places, and
   time blocks.
4. Extend feature extraction as real firmware-side Wi-Fi, IMU, and power
   observations become verified.
5. Add Parquet or a database-backed feature store after the JSONL contract
   stabilizes.
6. Add model-training dataset manifests only after consent and privacy policy
   are explicit for the selected runs.

DATA-001 is a data foundation task. It should not introduce a learned fusion
model, change device wire fields, or claim product positioning accuracy.

`DATA_FLYWHEEL_PIPELINE.md` defines the follow-on DATA-002 pipeline contract
for promoting session/test-run evidence into consented, privacy-reviewed
training-candidate records. DATA-002 remains a pipeline specification: it does
not collect private data, train a learned model, implement a training-candidate
store, or implement server/device OTA.
