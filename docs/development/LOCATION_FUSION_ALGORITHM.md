---
document_status: authoritative
last_verified: 2026-08-23
verified_by: codex
---

# Server-Derived Location Fusion Algorithm Baseline

This document preserves the server-derived location-fusion and replay baseline.
The algorithm name is **EALE-P0**, short for Evidence-Aware Location Estimator.
[ADR-0012](../architecture/adr/ADR-0012-p0-productization-sprint-1.md)
partially supersedes the earlier server-only live-ownership interpretation:
device Location Engine v0/Sensor Policy v0 now owns the minimum operational
state required offline. EALE-P0 mirrors and derives from versioned evidence; it
does not replace or retroactively rewrite the recorded device state.

EALE-P0 is not a learned positioning model. It is a server-side, derived-only,
explainable rule and scoring layer that turns stored evidence into a
conservative, separately identified `location_belief`. It keeps KR-003 stable:

```text
raw LTE command/location/observation/ACK loop
-> raw-frame storage
-> derived event view
-> DATA-001 observation windows
-> EALE-P0 evidence normalization
-> candidates
-> explainable location_belief
```

`P0-LOC` remains `NOT_RUN`. KR-004, ALG-001/002, a derived belief or an offline
replay is reusable engineering evidence and cannot by itself pass the product
Gate.

## Review Of The Algorithm Discussion

The user-provided algorithm discussion is technically aligned with the current
P0 route:

- It keeps GNSS as the only P0 source that can directly create coordinates.
- It treats Cell/LTE as network, area, and memory evidence, not cell-only
  positioning.
- It treats Wi-Fi as a privacy-reviewed known-place fingerprint, not a map
  positioning service.
- It treats IMU as motion context for hold and stale-decay decisions, not dead
  reckoning.
- It uses power, transport, and runtime as quality and failure-explanation
  inputs rather than position sources.
- It preserves failure windows as useful data instead of filtering them out.
- It keeps learned models out of KR-004 and DATA-001.

The formal design applies these adjustments so the idea fits current repo
contracts:

- Public location states remain `Fine`, `Coarse`, `Predicted`, and `Unknown`
  as defined in `LOCATION_ENGINE.md`.
- More specific outcomes such as `known_place`, `last_known_hold`,
  `coarse_area`, `no_fix`, and `failure` are represented as `substate`,
  `reason`, and `failure_reason`, not as incompatible top-level states.
- Evidence source status uses repository vocabulary:
  `verified`, `observed`, `pc_side_verified`, `unverified`, `mock`,
  `unknown`. Missing or failed evidence is represented as an evidence status
  or quality flag.
- Privacy classes map to existing contracts first: `engineering`,
  `private_location`, `private_media`, and `unknown`.
- Numeric thresholds are initial engineering defaults, not accuracy claims.

## Scope

EALE-P0 is allowed to:

- consume Message Hub test-run exports and DATA-001 samples;
- derive candidate beliefs from GNSS, cell/LTE, Wi-Fi, IMU, power, transport,
  runtime, location memory, commands, ACKs, and raw-frame lineage;
- produce an explainable server-side `location_belief`;
- output `Unknown` when evidence is insufficient;
- retain failure reasons for later replay and dataset analysis.
- compare device belief/policy outputs with a separately versioned server
  derivation while preserving both records.

EALE-P0 is not allowed to:

- change firmware logic or the live device wire protocol;
- train or publish a learned model;
- claim product location accuracy;
- infer precise coordinates from cell-only evidence;
- store raw private Wi-Fi BSSID values by default;
- hide missing or unverified evidence behind fake values.
- order device state by server receive/ingest time when source event-time
  lineage is missing or ambiguous.
- promote a learned or camera-derived result into the P0 operational path.

## Input Unit

EALE-P0 operates on observation windows, not single messages.

The initial supported DATA-001 sample types are:

| sample_type | Use |
|---|---|
| `location_request_window` | Command-scoped window from `request_location` through `location_report`, optional `location_observation`, and ACK. |
| `passive_observation_window` | Periodic or unsolicited location evidence without a downlink command. |
| `known_place_calibration_window` | High-confidence GNSS or operator-labelled window used to seed or verify memory. |
| `failure_window` | No-fix, parse failure, checksum failure, stale command, missing ACK, reset, transport failure, or missing observation. |

Each window must preserve:

- `device_id`, `test_run_id`, firmware version, command ID, sequence, and
  source event time, boot-scoped monotonic/clock-mapping lineage and server
  receive/ingest time when available;
- raw-frame references with frame ID, byte length, SHA-256, CRC, parser status,
  and parser version;
- derived event references;
- feature groups;
- labels with source and confidence;
- quality flags;
- privacy, redaction, and training flags;
- split assignment and generator version.

## Evidence Normalization

EALE-P0 first normalizes each feature group into source evidence:

```json
{
  "source": "gnss | cell_lte | wifi | imu | power | transport | runtime | memory",
  "present": true,
  "source_status": "verified | observed | pc_side_verified | unverified | mock | unknown",
  "evidence_status": "ok | missing | failed | stale | partial",
  "event_time": "2026-06-30T00:00:00Z",
  "boot_monotonic_ns": 123000000,
  "server_received_at": "2026-06-30T00:00:00Z",
  "age_s": 0,
  "raw_frame_refs": [],
  "derived_event_refs": [],
  "quality_flags": [],
  "privacy_class": "engineering | private_location | private_media | unknown",
  "redaction_state": "none | hashed | bounded_export_only | excluded"
}
```

`source_status` describes whether the source is trustworthy. `evidence_status`
describes whether the evidence exists and is usable in this window. This keeps
an unverified but present source different from a missing source.
`event_time` and its boot/clock lineage drive ordering and freshness. Server
receive/ingest timestamps describe transport and may break no semantic ties;
they must not be substituted for an unavailable source event time.

## Feature Groups

### GNSS

GNSS is the P0 coordinate calibrator. A valid GNSS candidate requires:

```text
fix == true
coordinates are present in bounded evidence/export
source_status in observed|verified
```

Initial quality score:

```text
gnss_quality =
  fix_gate
  * freshness_score
  * hdop_score
  * satellite_score
  * source_status_score
  * lineage_quality
```

Initial defaults:

```text
fix_gate = 1 if fix=true else 0
freshness_score = exp(-age_s / 60)
hdop_score = clamp((8.0 - hdop) / 7.0, 0, 1)
satellite_score = clamp((satellites - 4) / 8, 0, 1)
gnss_radius_m = max(25, hdop * 8)
```

If HDOP or satellites are unknown, EALE-P0 must reduce confidence and add a
quality flag instead of assuming ideal values.

### Cell/LTE

Cell/LTE is evidence for network state, coarse area memory, and consistency.
It is not a coordinate source in P0.

Useful features include RAT, MCC, MNC, TAC or hashed TAC, cell ID or hashed
cell ID, RSRP, RSRQ, RSSI, SINR, registration state, PDP state, assigned IP
presence, LTE reason code, and HTTP phase/status.

Cell/LTE may support a coarse-area candidate only when the current signature
matches prior observed memory. A single cell observation must not create a
precise place or output exact coordinates.

### Wi-Fi

Wi-Fi is known-place evidence. Raw BSSID values are not retained by default.
Long-term Wi-Fi memory should use hashed AP identifiers plus RSSI summaries
after privacy review.

Initial known-place score:

```text
wifi_match_score =
  0.7 * weighted_jaccard(current_ap_hashes, place_ap_hashes)
  + 0.3 * rssi_similarity(shared_aps)

rssi_similarity =
  avg(clamp(1 - abs(current_rssi - reference_rssi) / 30, 0, 1))
```

Initial buckets:

```text
>= 0.75  strong known-place candidate
>= 0.55  weak known-place candidate
<  0.55  no known-place match
```

Until firmware-side Wi-Fi observation is verified in the location path, Wi-Fi
evidence must be marked `unverified`, `mock`, `unknown`, `missing`, or
`failed` as appropriate.

### IMU

IMU is motion context. It can support last-known hold and stale decay, but P0
does not do dead reckoning.

Initial motion rules:

```text
stationary_hold_bonus = 1.0 if stationary_seconds >= 60 and confidence >= 0.7
moving_decay_multiplier = 2.0 if moving else 1.0
```

If IMU evidence is unavailable or unverified, EALE-P0 should avoid both
positive and negative motion assumptions.

### Power

Power is a quality and explainability input. Low or unknown power can explain
incomplete GNSS or Wi-Fi scans, but it does not move the location estimate.

Useful fields include voltage, SOC estimate, charging state, power source,
source label, and source status.

### Transport And Runtime

Transport/runtime evidence explains whether a location failure is a GNSS
problem, device runtime problem, parser problem, or network problem.

Examples:

```text
missing_location_report + command_sent -> transport_or_runtime_failure
location_report_no_fix + ACK_ok -> gnss_no_fix_transport_ok
parse_failure -> raw_frame_parse_failure
checksum_failed -> raw_frame_checksum_failure
stale_command -> stale_command_ignored
reset_after_command -> device_reset_during_location_request
```

## Candidate Generation

EALE-P0 generates candidates before it decides on a belief.

| Candidate | Condition | Public state |
|---|---|---|
| `GNSSCandidate` | Valid GNSS fix and acceptable quality. | `Fine` |
| `KnownPlaceCandidate` | Strong Wi-Fi, operator note, user confirmation, or GNSS calibration memory. | `Coarse` |
| `LastKnownCandidate` | Recent trusted memory plus motion context. | `Predicted` |
| `CellAreaCandidate` | Cell signature matches prior memory. | `Coarse` or `Unknown` |
| `FailureCandidate` | Runtime, transport, parser, no-fix, stale, reset, or missing-evidence failure. | `Unknown` |

### GNSSCandidate

GNSS dominates when it is valid:

```json
{
  "candidate_type": "gnss_fix",
  "state": "Fine",
  "source": "gnss",
  "radius_m": 25,
  "score": 0.82,
  "reason": "gnss_fix_valid",
  "evidence_refs": {}
}
```

Exact coordinates may be present only in bounded evidence/export paths where
privacy rules allow them.

### KnownPlaceCandidate

Known-place candidates can come from Wi-Fi fingerprint memory, operator notes,
user confirmations, or high-confidence GNSS calibration windows.

Known places may have no coordinates. If privacy policy does not allow
coordinate release, EALE-P0 can still output a place state and reason without
lat/lon.

### LastKnownCandidate

Last-known hold is conservative. Radius grows with age:

```text
radius_m =
  last_radius_m
  + age_s * growth_rate_mps * moving_decay_multiplier

growth_rate_mps = 0.5 if stationary else 2.0
max_hold_age_s = 1800
```

After `max_hold_age_s`, the candidate becomes stale and should usually degrade
to `Unknown` with a stale reason.

### CellAreaCandidate

Cell memory is low-confidence coarse evidence. It can support "same general
area as prior known evidence" but must not output cell-only exact coordinates.

### FailureCandidate

Failure candidates are first-class outputs. They make "no location" explainable
and useful for DATA-001 and future robustness work.

## Fusion Decision

EALE-P0 uses dominance, consistency, and decay:

1. Valid GNSS dominates, with Wi-Fi/cell/IMU as supporting evidence.
2. If GNSS is unavailable and a strong known-place candidate exists, output
   `Coarse` with known-place substate.
3. If no strong known place exists but last-known memory is fresh and IMU says
   stationary, output `Predicted` with last-known-hold substate.
4. If only cell evidence exists, output a coarse area only if prior memory
   supports it; otherwise output `Unknown` with `no_precise_fix`.
5. If transport/runtime/parser failure prevents location evidence, output
   `Unknown` with a failure reason rather than `gnss_no_fix`.

Conflicts reduce confidence and add flags. For example, a valid GNSS fix with
a strong conflicting known-place fingerprint should keep GNSS dominant but add
`context_conflict` and reduce confidence.

## Confidence

Candidate confidence is conservative:

```text
candidate_score =
  source_weight
  * source_quality
  * freshness_score
  * consistency_score
  * lineage_quality
  * privacy_allowed_gate
```

Initial source weights:

| Source | Role | Initial weight |
|---|---:|---:|
| Valid GNSS fix | Coordinate calibrator | 1.00 |
| Wi-Fi known place | Indoor place evidence | 0.75 |
| Last known plus stationary | Conservative hold | 0.55 |
| Cell memory | Coarse area support | 0.35 |
| IMU | Motion modifier | not standalone |
| Power | Quality modifier | not standalone |
| Transport/runtime | Explainability modifier | not standalone |

Lineage quality:

```text
1.0 raw_frame_refs + derived_event_refs + cmd_id + seq + parser status present
0.7 derived events complete but raw lineage missing
0.4 partial lineage
0.0 cannot trace evidence
```

UI should prefer `confidence_bucket` over raw numeric confidence so users do
not treat an engineering score as a calibrated probability.

## Derived Location Belief

ALG-001 may add a machine-readable contract. The initial shape should remain
compatible with existing location states:

```json
{
  "location_belief": {
    "state": "Fine | Coarse | Predicted | Unknown",
    "substate": "gnss_fix | known_place | last_known_hold | coarse_area | no_precise_fix | failure",
    "source": "gnss | wifi_memory | last_known | cell_memory | runtime",
    "lat": null,
    "lon": null,
    "place_id": null,
    "radius_m": 50,
    "confidence": 0.72,
    "confidence_bucket": "high | medium | low | unknown",
    "freshness_s": 12,
    "reason": "wifi_fingerprint_match_stationary",
    "failure_reason": null,
    "quality_flags": [],
    "evidence_refs": {
      "raw_frame_refs": [],
      "derived_event_refs": [],
      "anchor_cmd_id": null,
      "anchor_event_id": null
    },
    "privacy": {
      "privacy_class": "engineering | private_location | private_media | unknown",
      "redaction_state": "none | hashed | bounded_export_only | excluded",
      "training_allowed": false
    },
    "generator": {
      "name": "EALE-P0",
      "version": "0.1.0",
      "config_hash": null
    }
  }
}
```

Coordinates must be omitted or redacted unless the selected output path and
privacy policy allow private location output.

## Location Memory

Known-place memory is privacy-first. A future record should carry:

- `place_id`;
- label and label source;
- optional coordinate with privacy class;
- hashed Wi-Fi fingerprint summary;
- hashed or bounded cell signature summary;
- source window IDs;
- training and export flags.

Allowed write/update sources:

- high-confidence GNSS calibration;
- explicit user confirmation;
- operator note;
- repeated stable Wi-Fi plus cell signature;
- privacy/consent policy allows the selected retention.

A single cell-only observation must not create an exact place.

## Learned Model Path

Learned models are not part of KR-004 or Productization Sprint 1. AI work is
data/replay first: future learned components may be evaluated offline and then
in Shadow Mode only after DATA-001 has enough labelled, privacy-cleared
samples. A later accepted decision is required before any learned output can
affect device policy or the product belief:

- Source Reliability Model: predicts evidence reliability, not location.
- Known Place Classifier: predicts `place_id` from hashed Wi-Fi/cell and
  context.

Recommended early model families are simple and inspectable: kNN fingerprint
matching, logistic regression, random forest, gradient boosting, or a small
MLP. A learned component should enter a release candidate only if it reduces
false high-confidence beliefs without weakening lineage or privacy.

## Historical KR-004 Engineering Gate Direction

KR-004 is "Multi-source explainable location evidence baseline", not
"accurate fusion positioning".

Recommended acceptance:

1. KR-003 raw LTE command/location/observation/ACK loop does not regress.
2. DATA-001 can rebuild observation windows from location reports,
   observations, ACKs, and raw-frame summaries.
3. Wi-Fi, IMU, and power evidence in the firmware-side location path are
   either observed, verified, unverified, unknown, mock, missing, or failed;
   they are not silently fabricated.
4. Web/API/report surfaces show current run, key release, command, ACK, raw
   frame, derived observation, and failure reason.
5. EALE-P0 design is frozen by this document.
6. Optional server-side `location_belief` generation is implemented
   separately under ALG-001 and clearly marked as derived/conservative until
   release.
7. Failure windows are retained.
8. No product readiness, GNSS acceptance, cell-only positioning, learned-model,
   or positioning-accuracy claim is made.

## Next Tasks

- `LOC-005A`: completed firmware-side Wi-Fi, IMU, and power observation
  source-state slots as explicit evidence.
- `OBS-003`: completed Web/API/report visibility for current run, key release,
  raw evidence, derived observation, command/ACK chain, and failure reason.
- `ALG-001`: completed optional server-side EALE-P0 derived
  `location_belief` visibility for current run, export, and Dashboard
  surfaces.
- `ALG-002`: completed offline EALE-P0 coverage evaluation over DATA-001
  JSONL for evidence, failure, lineage, feature, privacy, and training
  readiness metrics.
- `ALG-003`: prototype learned source reliability only after sufficient real
  labelled samples exist.
