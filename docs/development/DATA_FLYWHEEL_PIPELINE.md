---
document_status: authoritative
last_verified: 2026-07-05
verified_by: codex
---

# DATA-002 Data Flywheel Pipeline Specification

This document defines the V1 data-flywheel pipeline for Ego Link. It turns
consented, privacy-reviewed sessions into training-candidate records for later
offline model work.

It does not collect private data, train a model, change firmware behavior,
change public wire protocol, implement guardian accounts, implement an OTA
model path, or certify legal compliance.

## Default Boundary

Every product-demo, field-test, or DATA-001-derived record starts with:

```text
training_allowed=false
raw_audio_allowed=false
raw_image_allowed=false
raw_wifi_bssid_retention=false
```

A record may become training eligible only after explicit consent evidence,
privacy review, quality review, split-leakage review, and deletion/retention
rules are attached. Records may be useful for release review or regression
analysis while still remaining `training_allowed=false`.

## Inputs

DATA-002 may reference these source types:

- Message Hub raw-frame summaries, derived events, commands, ACKs, and bounded
  test-run exports.
- PC or device session recordings with manifests, sensor frames, events,
  annotations, quality reports, replay reports, and file hashes.
- DATA-001 location-fusion samples and manifests.
- User confirmations such as `safe`, `needs_help`, and `no_response`.
- Operator or reviewer labels created by a later labeling-loop task.
- Product-demo privacy gate results from
  `../product/PRODUCT_DEMO_PRIVACY_BOUNDARY.md`.
- Future model experiment summaries and footprint measurements.

Each input must preserve source status: real firmware, PC-side probe, mock,
synthetic, replay, unknown, or unverified. A Dashboard view is not a training
source by itself; training candidates must be rebuilt from stored evidence,
labels, and manifests.

## Pipeline Stages

| Stage | Purpose | Required gate |
|---|---|---|
| 1. Capture session | Create a bounded session or test-run manifest with `session_id`, device role, firmware/model versions, source status, and evidence refs. | Session manifest exists and source status is explicit. |
| 2. Normalize evidence | Rebuild derived views from raw frames, event logs, recordings, and DATA-001 samples. | Raw payload bytes are not copied into committed docs or generated summaries. |
| 3. Classify consent and privacy | Attach consent context, privacy class, redaction state, and default training flags. | `training_allowed=false` unless a later reviewed policy changes it. |
| 4. Package bounded evidence | Store refs, hashes, parser status, coordinate redaction state, and feature summaries. | Private coordinates, raw Wi-Fi identifiers, raw audio, and raw images stay blocked by default. |
| 5. Derive labels | Convert user confirmations and reviewer annotations into explicit labels with source and confidence. | Label source is recorded; private free text is absent or redacted. |
| 6. Build candidate record | Create a stable candidate record with evidence, features, labels, quality, privacy, lineage, and split fields. | Record validates against the DATA-002 minimum fields below. |
| 7. Review quality and leakage | Check quality gates, missing evidence, duplicate lineage, and split leakage. | Session-, device-, place-, or time-blocked split rule is applied. |
| 8. Promote to candidate store | Mark records as reviewed candidates for offline evaluation or future model training. | Consent, privacy, retention, deletion, and split states are all present. |
| 9. Run offline experiments | Train or evaluate future models only from eligible reviewed candidates. | Model experiment records bind dataset manifest, metrics, non-claims, and rollback plan. |
| 10. Review update path | Decide whether a model can ship through server update and device OTA. | Planned only; no production OTA model path exists yet. |

## Minimum Candidate Record

The pipeline should preserve these fields for every candidate record:

| Field group | Required fields |
|---|---|
| Identity | `record_id`, `session_id`, `window_id`, `candidate_type`, `created_at` |
| Source refs | `test_run_id`, `cmd_id`, `frame_id`, `event_id`, `recording_path`, `sample_id`, `raw_frame_hashes` |
| Device context | `device_id`, `device_role`, `firmware_version`, `model_version`, `source_status`, `transport_type` |
| Consent | `consent_required`, `consent_status`, `consent_evidence_ref`, `reviewed_by`, `reviewed_at`, `training_allowed` |
| Privacy | `privacy_class`, `coordinate_redaction`, `wifi_identifier_policy`, `guardian_data_state`, `raw_audio_allowed`, `raw_image_allowed` |
| Retention and deletion | `retain_until`, `retention_basis`, `delete_request_id`, `deletion_state` |
| Evidence | `evidence_refs`, `parser_status`, `parse_failure_reason`, `redaction_state`, `payload_bytes_retained` |
| Features | `feature_groups`, `feature_generator_version`, `feature_quality`, `missing_feature_reasons` |
| Labels | `label_set`, `label_source`, `label_confidence`, `label_review_state`, `confirmation_outcome` |
| Quality | `quality_gate`, `quality_score`, `known_gaps`, `excluded_evidence`, `blockers` |
| Split | `split_name`, `split_strategy`, `split_group_key`, `split_leakage_checked` |
| Lineage | `schema_versions`, `generator_versions`, `source_manifest_hash`, `parent_dataset_id` |
| Release review | `experiment_id`, `model_candidate_id`, `release_gate_state`, `ota_update_state` |

## Data Class Rules

- GNSS coordinates: exact private coordinates stay in bounded evidence/export
  stores. Current docs and generated summaries use redacted refs unless a task
  records explicit authorization.
- Cell/LTE signatures: usable as network and area evidence, never as
  cell-only coordinates. Long retention needs privacy review.
- Wi-Fi identifiers: raw BSSID/SSID retention is disabled by default. Hashed
  fingerprints need salt, rotation, retention, and consent policy before use.
- IMU windows: structured windows and feature summaries are allowed as bounded
  evidence. Training use waits for collection protocol and consent.
- User confirmations: confirmation outcomes may become labels only with label
  source, confidence, and consent context.
- Audio: raw microphone clips and derived voice labels are excluded by default.
  Any future audio path requires a separate task, consent, retention limit, and
  privacy review.
- Image/camera: raw images and thumbnails are excluded from current
  data-flywheel training. Capability evidence can remain redacted.
- Guardian/contact data: absent, synthetic, or redacted only; not training
  data.
- VPS logs and raw frames: refs, IDs, hashes, parser status, and counts may be
  used; secrets, bearer tokens, private logs, and payload bytes are excluded.

## Candidate States

DATA-002 uses explicit states instead of implied readiness:

```text
captured
classified
packaged
labelled
candidate
reviewed_training_candidate
experiment_input
release_candidate

session_blocked
consent_blocked
privacy_blocked
quality_blocked
split_leakage_blocked
deletion_requested
ota_blocked
```

`reviewed_training_candidate` is the first state where a record may have
`training_allowed=true`. `release_candidate` still requires product safety,
model-footprint, regression, rollback, and update-path review before any
server or device deployment.

## Split And Leakage Rules

Do not randomly split rows from the same real-world session across train,
validation, and test sets. Prefer blocking by session, device, place, time
window, or field-test campaign. A candidate with unclear lineage or possible
cross-split leakage remains `split_leakage_blocked`.

Deleted or deletion-requested records must be removed from future training
candidate manifests before any experiment starts. Manifests should preserve a
redacted deletion audit record without retaining private payloads.

## Model And OTA Boundary

DATA-002 prepares candidate data; it does not perform model training. Future
model work must produce a dataset manifest, model card, metrics, false-positive
review, safety non-claim statement, footprint measurement, rollback plan, and
release gate.

TRAIN-002 is the current bridge after dataset export: it registers a bounded
training experiment plan with dataset readiness, runner handoff status, planned
metrics, inherited gates, and non-claims. It still does not integrate a GPU
runner, call a training server, produce model weights, measure metrics, or
change device behavior.

TRAIN-003 is the current bridge after experiment registration: it checks a
TRAIN-002 plan plus a TRAIN-001 dataset manifest and writes a bounded
training-run preflight report. The preflight can acknowledge synthetic-only
dry-runs, verify required bounded record fields, and record split/label/source
counts. It still does not train, evaluate, upload, or deploy a model, does not
integrate a private training server, and does not write measured metrics.

DATA-010 can expose the latest TRAIN-003 preflight through Web/API and curated
deployment summaries. It is visibility only: status, checks, gates, split/label
counts, synthetic acknowledgement, and `not_run` measured-metric placeholders
are allowed; private training endpoints, raw records, candidate DBs, runtime
logs, model artifacts, and measured model claims are not.

TRAIN-004 is the current bridge after runner preflight: it exports bounded
manifest-summary feature rows from an explicitly named TRAIN-001 dataset
manifest plus TRAIN-003 preflight report. It can produce a synthetic dry-run
feature set only with explicit acknowledgement, keeps target labels separate
from feature fields, and does not generate MotionNet tensors or raw IMU window
features. It still does not train, evaluate, upload, or deploy a model.

DATA-011 can expose the latest TRAIN-004 feature manifest through Web/API and
curated deployment summaries. It is visibility only: feature-set status,
dataset/preflight match, row count, feature scope, target-boundary guard,
synthetic policy, required-field checks, gates, and `not_run` measured metrics
are allowed. JSONL row contents, raw records, candidate DBs, runtime logs,
private training endpoints, raw tensors, model artifacts, and measured model
claims are not.

TRAIN-005 can run a local runner-input dry-run from an explicitly named
TRAIN-004 feature manifest plus JSONL rows. It validates row count, feature-set
matching, required bounded row fields, target-label leakage, and synthetic
acknowledgement, then writes a dry-run report. It still does not train,
evaluate, upload, or deploy a model, and `not_run` remains the only measured
metric state.

DATA-012 can expose the latest TRAIN-005 runner dry-run through Web/API and
curated deployment summaries. It is visibility only: runner-input status,
row-count matching, split/label/source summaries, target-leakage guard,
synthetic policy, gates, and `not_run` measured metrics are allowed. JSONL row
contents, raw records, candidate DBs, runtime logs, private training endpoints,
raw tensors, model artifacts, and measured model claims are not.

TRAIN-006 can run aggregate baseline evaluation over an explicitly named
TRAIN-004 feature manifest, TRAIN-004 feature rows, and TRAIN-005 runner
dry-run report. Synthetic rows require explicit acknowledgement and produce
synthetic integration metrics only. TRAIN-006 still does not train a model,
write model artifacts or model cards, integrate a training server, measure
footprint/power, deploy on-device inference, or allow release claims.

DATA-013 can expose the latest TRAIN-006 baseline-eval summary through Web/API
and curated deployment summaries. It is visibility only: status, aggregate
baseline metrics, synthetic policy, row counts, gates, and report paths are
allowed. JSONL row contents, raw records, private case rows, private endpoints,
model artifacts, model cards, footprint/power measurements, and release claims
are not.

DATA-014 extends the D1 post-run collector so a ready DATA-006/TRAIN-002
handoff can immediately continue through TRAIN-003 preflight, TRAIN-004
feature export, TRAIN-005 runner dry-run, and TRAIN-006 baseline eval from one
local command. If the dataset handoff is not ready, the training chain is
skipped with an explainable reason. DATA-014 still does not train a model,
deploy to devices, copy feature-row JSONL to the Dashboard, or produce model
artifacts, model cards, measured footprint/power data, or release claims.

TRAIN-007 can bind the explicit dataset manifest, TRAIN-003 preflight,
TRAIN-004 feature manifest and rows, TRAIN-005 runner dry-run, and TRAIN-006
baseline eval into one bounded handoff bundle for a future local/GPU training
runner or training server. It stores refs, hashes, row counts, readiness gates,
and non-claims only. It still does not copy feature-row JSONL contents, call a
training endpoint, train or evaluate a real model, produce model artifacts or
model cards, deploy on-device inference, measure footprint/power, or allow
release claims.

DATA-009 may generate synthetic-only session recordings to exercise this
pipeline while hardware runs are pending. Synthetic records must be explicitly
marked `synthetic_only=true`, kept separate from field evidence, and used only
for dry-run integration. Even when `--review-synthetic` promotes them through
the review gate, the result is not a release acceptance metric and cannot
support real-world model performance, power, latency, footprint, or product
readiness claims.

Server model updates and device OTA are part of the V1 direction, but are
`planned_not_implemented` here. No firmware, device protocol, Message Hub
deployment, or OTA update behavior changes in DATA-002.

## First Implementation Order

1. Keep this specification as the current DATA-002 contract.
2. Let M1-002 produce device-side session manifests compatible with the
   minimum candidate record.
3. Let M1-005 add a labeling loop that writes label source, confidence, and
   consent context.
4. Let M1-006 execute collection protocol runs for real negative samples and
   controlled simulated positives.
5. Let DATA-009 run synthetic-only pipeline dry-runs while real field evidence
   is still sparse.
6. Let TRAIN-002 keep registering bounded experiment plans from reviewed
   dataset manifests until a real training runner task exists.
7. Let TRAIN-003 keep checking runner preflight readiness without producing
   model artifacts or measured metrics.
8. Let DATA-010 surface the latest runner preflight status in Web/API without
   exposing raw records or private training details.
9. Let TRAIN-004 export bounded training feature manifests only after the
   dataset and preflight gates pass.
10. Let DATA-011 surface the latest feature manifest status in Web/API without
   exposing JSONL row contents or private training details.
11. Let TRAIN-005 validate runner input shape from the feature manifest and
    rows before any real runner integration.
12. Let DATA-012 surface the latest runner dry-run status in Web/API without
    exposing JSONL row contents or private training details.
13. Let TRAIN-006 run aggregate baseline evaluation only after the TRAIN-005
    runner-input gate passes; synthetic metrics remain integration-only.
14. Let DATA-013 surface latest baseline-eval status in Web/API without
    exposing row contents, private training details, or model artifacts.
15. Let DATA-014 bind TRAIN-003..006 into the D1 post-run collector after a
    ready dataset handoff, keeping blocked/not-ready runs explainable.
16. Let TRAIN-007 build a bounded training handoff bundle for a future runner
    or training server without copying feature rows or starting training.
17. Let MODEL-001 and MotionNet work consume only reviewed candidate records
    whose manifests still pass consent, privacy, retention, deletion, quality,
    and split-leakage checks.
