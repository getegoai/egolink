---
document_status: authoritative
last_verified: 2026-08-17
verified_by: codex
---

# A0-002 Unified Timestamp

## Purpose

A0-002 establishes an additive, replayable time-lineage layer for GNSS, LTE,
IMU and Camera observations. It does not reinterpret or replace the existing
`egolink.p0.v1` wire protocol. Its purpose is to make every available time
value explicit about:

- which clock produced it;
- which boot and stream scope its sequence belongs to;
- whether UTC came from the source or a named clock mapping;
- when the server received and ingested it; and
- what uncertainty and immutable source evidence support the alignment.

Unknown time is data. It must remain `null` with a reason code. Receive or
ingest time must never be copied into a missing source or device time field.

## Current Capability Inventory

| Source | Current time evidence | Missing for a trustworthy four-source session |
|---|---|---|
| GNSS | Some Wi-Fi JSON reports have `ts=uptime_ms:<N>`, `seq`, GNSS date/time and later `server_received_at`. Current LTE raw reports retain GNSS date/time, `seq` and receive time. | The LTE raw path has no boot-scoped device monotonic timestamp or explicit GNSS-to-device-clock anchor/uncertainty. |
| LTE / cell | Some heartbeat envelopes expose device uptime, boot count and sequence. Raw location observations expose sequence and server receive time. | Raw observations have no modem/source timestamp or boot-scoped device monotonic timestamp. Receive time is affected by queueing and transport. |
| IMU | `egolink.imu_window.v1` has boot count, capture start/end device uptime in microseconds and per-sample offsets. | No UTC anchor. A sample has deterministic device monotonic time only. |
| Camera | The current camera smoke path prints capture diagnostics. | No structured exposure time, device monotonic timestamp, UTC, boot or Message Hub/session record exists. |

Therefore the current implementation is a contract and offline-validation
foundation only. It cannot close A0-002 or produce an A-R0 Gate PASS.

## Contracts

### `egolink.sensor_time_lineage.v0.1`

Each normalized observation carries all fields, including explicit `null`
values:

```text
observation_id
device_id
source                    # gnss | lte | imu | camera
stream_id
sequence_id
monotonic_clock_domain_id
boot_count
timestamp_monotonic_ns
timestamp_utc
source_timestamp          # raw value, unit, clock, semantics, source field
receive_timestamp_utc
ingest_timestamp_utc
alignment                 # status, origin, mapping, anchor, uncertainty, reasons
lineage                   # evidence scope, session, firmware, source ref/hash
imu_sample_derivation
```

`timestamp_utc`, receive time and ingest time are normalized UTC strings ending
in `Z` or `+00:00`. The raw source representation remains in
`source_timestamp`; normalization does not erase it. The source clock domain
and canonical boot-monotonic clock domain are separate fields because GNSS
UTC, a Camera exposure clock and device uptime are not inherently the same
clock.

Alignment states are:

- `unavailable`: a useful partial clock may exist, but there is no defensible
  monotonic-to-UTC alignment;
- `receive_only`: only server receive/ingest time is available;
- `estimated`: a named monotonic-to-UTC mapping provides both clocks with stated
  uncertainty;
- `verified`: a verified mapping supports both clocks and the uncertainty
  claim. A synchronization anchor is a structured method plus immutable
  evidence reference/hash, never a free-form id alone.

For current bounded IMU windows:

```text
timestamp_monotonic_ns =
  (capture_start_uptime_us + offset_us) * 1000
```

This is deterministic device uptime, not UTC.

### `egolink.clock_mapping_segment.v0.1`

A mapping segment binds one device, canonical monotonic clock domain and boot
to a bounded monotonic interval. It records UTC/monotonic origins, UTC rate
correction, explicit immutable anchors, fit errors and uncertainty. A verified
mapping needs at least two anchors over a non-zero monotonic span. The validator
recomputes every anchor residual and checks declared RMS/max fit error; mapping
uncertainty cannot be smaller than either the fit error or anchor uncertainty.

The mapping equation is:

```text
utc_delta_ns = round_half_even(
  (timestamp_monotonic_ns - monotonic_origin_ns)
  * (1 + utc_rate_correction_ppm / 1_000_000)
)

timestamp_utc_ns = utc_origin_ns + utc_delta_ns
```

`timestamp_monotonic_ns` is never rewritten by this equation. Positive
`utc_rate_correction_ppm` is defined to mean that UTC advances that many extra
nanoseconds per one million monotonic nanoseconds; the explicit name freezes
the sign convention for future producers.

Mappings never cross a boot boundary. A sequence or uptime reset is valid only
in a new boot/clock scope.

## Validator

The standard offline command is:

```powershell
python scripts/validate_sensor_time_lineage.py <records.jsonl> `
  --mappings <clock_mappings.jsonl> `
  --required-sources gnss,lte,imu,camera `
  --output <validation_report.json>
```

Add `--fail-if-ineligible` only when the calling workflow wants structural
Field Session eligibility to control the process exit code.

Exit codes:

- `0`: the input contract is parseable and self-consistent; `field_eligible`
  can still be false;
- `1`: deterministic schema or semantic validation failed, or
  `--fail-if-ineligible` was requested and eligibility is false;
- `2`: the input/schema cannot be read, arguments are invalid, or the result
  cannot be determined.

The report checks:

- strict UTC syntax and explicit time provenance;
- server pipeline causality (`ingest_timestamp_utc >= receive_timestamp_utc`);
- sequence and monotonic ordering inside device/clock/stream/boot scope;
- byte-equivalent duplicate observation idempotency and conflicting duplicate
  rejection;
- exact IMU sample-time derivation;
- mapping identity, range, boot, anchor residual, uncertainty and output
  consistency;
- per-source coverage; and
- cross-source alignment only for a common structured `verified` anchor whose
  method and immutable evidence reference/hash match across all four sources.

Without such a common anchor, `max_observed_anchor_span_ns` and
`max_conservative_alignment_bound_ns` are `null` and the reason is explicit.
The first is the observed UTC span; the second is the worst pairwise span plus
both records' declared uncertainty. Neither is computed from server receive
times.

## Eligibility Is Not Gate Completion

`field_eligible=true` means only that one input bundle is structurally capable
of technical review: all four A0 sources have observed, immutable,
firmware-bound, boot-scoped lineage through a verified mapping in one Field
Session and share one structured, immutable synchronization anchor.
It does not compare the result to an acceptance threshold and does not mark
A0-002 passed. Every report therefore retains:

```text
gate_status = unverified
```

A0-002 can close only after a reviewed real session provides GNSS, LTE, IMU and
Camera observations, time-order checks, source coverage/drop statistics, a
pre-frozen synchronization threshold, measured maximum alignment error,
automated-test evidence and immutable session evidence.

## Known Limits

- No existing producer writes this v0.1 lineage contract yet.
- Current GNSS and LTE raw paths cannot provide trustworthy boot-scoped device
  monotonic time without a later protocol/firmware task.
- Current Camera capture cannot participate until exposure timing and session
  ingestion are implemented.
- Server receive time includes queueing and retry delay and is never a sensor
  time substitute.
- Legacy `ts` can be ISO-looking text, `uptime_ms:<N>` or `raw_frame:<id>`.
  A bare ISO value remains `ambiguous_iso_utc` because `board_bridge` may have
  filled legacy `ts` from `received_at`; only explicit provenance may promote
  it to source UTC.
- A0-003 will define the enclosing Field Session schema. This task does not
  pre-empt that contract.
