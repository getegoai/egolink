---
document_status: authoritative
last_verified: 2026-06-30
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
| Time and ordering | `server_received_at`, device `ts`, `uptime_s`, `boot_uptime_ms`, `seq` | Server receive time is the ordering authority. Device time may be monotonic or uptime-like and must not be treated as wall time unless explicitly synchronized. |
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

## Privacy And Retention

Default retention should favor structured evidence and hashes over raw private
payloads.

- Exact coordinates, Wi-Fi fingerprints, audio, images, and private place
  labels need an explicit privacy class.
- Raw audio and raw images are not part of the location-fusion dataset by
  default.
- Wi-Fi AP identifiers should be hashed or otherwise privacy-reviewed before
  long retention.
- Dataset exports under `model_artifacts/` or runtime directories are not
  committed unless explicitly converted into small synthetic fixtures.

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

## DATA-001 Follow-On Direction

The baseline leaves these deliberate next steps:

1. Add operator labels and known-place calibration labels as explicit inputs.
2. Add split-leakage checks across multiple sessions, devices, places, and
   time blocks.
3. Extend feature extraction as real firmware-side Wi-Fi, IMU, and power
   observations become verified.
4. Add Parquet or a database-backed feature store after the JSONL contract
   stabilizes.
5. Add model-training dataset manifests only after consent and privacy policy
   are explicit for the selected runs.

DATA-001 is a data foundation task. It should not introduce a learned fusion
model, change device wire fields, or claim product positioning accuracy.
