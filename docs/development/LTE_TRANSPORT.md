---
document_status: authoritative
last_verified: 2026-07-01
verified_by: codex
---

# SIM7670G LTE Transport Track

The current validated USB-Free path uses Wi-Fi HTTP to the public VPS Message
Hub. That path is the development baseline, not final product transport
acceptance. The SIM7670G LTE track must be introduced as thin slices so that
each failure stage is visible.

## Scope

P0 LTE transport started with the existing Message Hub HTTP envelope:

```text
HTTP POST telemetry
HTTP GET command polling
HTTP POST ACK
```

LTE-002 proved that HTTP over SIM7670G can reach the VPS for telemetry. The
LTE-003 command-poll attempts then exposed a protocol risk: device-side JSON
body extraction/parsing is a brittle runtime dependency. From PROTO-002 onward,
the command/ACK acceptance path should use the HTTP transport only as a carrier
for raw frames. Server/Web JSON remains a derived compatibility view, not the
device wire truth.

MQTT, raw TCP long connections, and advanced reconnect supervisors remain
deferred until HTTP-carried raw frames prove the minimal product link.

## LTE-001: Registration And Cell State

Goal: make SIM7670G LTE state observable before using it as transport.

### LTE-001A build-verified observability baseline

Completed on 2026-06-28 as a build-verified firmware/server/protocol baseline.
The firmware can optionally query SIM7670G LTE state through the shared UART AT
backend and upload `cell` plus `lte` observation objects over the existing
Wi-Fi HTTP Message Hub path. The Message Hub stores those fields, derives
`observability.lte`, includes LTE reason codes in explainability, and the
Dashboard renders LTE registration, PDP, SIM, and reason state.

Boundary: LTE-001A does not disable Wi-Fi, does not set
`transport.type=lte`, does not prove DNS or HTTP through SIM7670G LTE, and was
not flashed or USB-Free hardware validated in this step.

Required fields:

- SIM state;
- operator;
- RAT;
- registration state;
- APN configuration state;
- PDP state;
- assigned IP when available;
- cell fingerprint: MCC, MNC, TAC, cell ID, RSRP, RSRQ, RSSI, SINR;
- failure reason code for each unavailable stage.

Definition of Done:

- Web can show LTE registration state and cell fingerprint.
- VPS stores the cell observation.
- A failure can be classified as SIM, registration, APN/PDP, DNS, HTTP, or
  server reachability.

## LTE-002: HTTP Uplink Thin-Slice

Goal: send one telemetry message from the ESP32-S3 through SIM7670G LTE to the
VPS.

Implementation shape:

- opt-in firmware mode `CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_ENABLED`;
- Wi-Fi initialization and Wi-Fi Message Hub tasks skipped while probe mode is
  enabled;
- SIM7670G AT HTTP commands POST `event_type=lte_http_probe` to the existing
  `/telemetry` endpoint;
- the probe emits `phase=attempt` and then `phase=result` so the final event
  can carry the first POST's HTTP status and LTE HTTP reason code;
- validation is performed from the VPS Message Hub only by
  `scripts/validate_lte_http_probe.py`.

Definition of Done:

- Wi-Fi is disabled for the run.
- USB is not the runtime data path.
- device posts telemetry to the existing VPS Message Hub.
- `/api/state` shows `transport.type=lte`.
- Dashboard shows LTE last update, cell fingerprint, and signal quality.

Known boundary: if SIM7670G HTTP fails before any request reaches the VPS, the
VPS cannot receive that failure detail through the same failed path. The
validator must report this as no fresh LTE telemetry after the LTE-001B
readiness gate, not as a GNSS, Web, or command-loop failure.

## LTE-003: Command Poll And ACK

Goal: migrate the current Web command queue to LTE HTTP-carried raw-frame
polling without losing the Web/API command semantics.

Current status: paused on the JSON command-poll path after fix7/fix8. The next
runtime acceptance attempt should follow PROTO-002 raw-frame transport instead
of continuing device-side JSON parser fixes.

Implementation shape:

- opt-in firmware mode
  `CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED`;
- Wi-Fi initialization and Wi-Fi Message Hub tasks skipped while command-loop
  mode is enabled;
- SIM7670G AT HTTP `GET` polls a raw command endpoint or negotiates a
  `raw-frame.p0.v1` response from the existing command endpoint;
- the first hardware acceptance command is the harmless
  `set_report_interval` command;
- firmware verifies raw-frame length/checksum and parses compact key/value
  command content instead of a JSON object;
- SIM7670G AT HTTP `POST` sends a raw ACK frame;
- the Message Hub stores raw frames first, then derives the existing ACK row
  with additive `transport.type=lte`, `lte_http.phase`, and poll HTTP
  status/reason fields so validation can distinguish LTE ACKs from the earlier
  Wi-Fi Message Hub path.

Definition of Done:

- Web enqueues a harmless command.
- device polls over LTE.
- firmware executes once and ACKs over LTE.
- duplicate execution, timeout, retry, and stale command states are visible.

## LTE-004: Raw Request Location Thin Slice

Goal: extend the raw LTE command loop from `set_report_interval` to
`request_location` without returning to device-side JSON parsing.

Implementation shape:

- Web/VPS enqueues `request_location`.
- device receives it from `/commands/poll.raw` as an `EGLK/1 type=command`
  frame;
- firmware queries the SIM7670G GNSS backend when enabled, otherwise returns an
  explicit no-fix scaffold state;
- firmware posts an `EGLK/1 type=event` raw frame to `/raw-ingest` with
  `event_type=location_report`, `location_request_cmd_id`, GNSS state/fix
  fields, and `transport_type=lte`;
- Message Hub stores the raw frame first, then derives the existing
  `location_report` Web/API view;
- firmware posts the raw ACK only after the location frame upload attempt.

Definition of Done:

- raw `request_location` command is selected and executed over LTE;
- raw `location_report` is visible in Message Hub raw-frame evidence;
- derived Web/API `latest_location` is updated from that raw event;
- validator can require both the command ACK and a fresh LTE `location_report`
  for the same command ID;
- no-fix is acceptable only when the GNSS state and source status explain the
  failure.

## LOC-004A: Raw Cell Location Observation

Goal: make LTE/GNSS location attempts explainable before long-run LTE testing
by uploading real firmware-side SIM7670G cell/LTE observation over the same
raw-frame Message Hub path.

Implementation shape:

- Web/VPS enqueues `request_location`.
- firmware posts the LTE-004 raw `location_report` for GNSS fix/no-fix;
- when `CONFIG_EGOLINK_SIM7670_LOCATION_OBSERVATION_ENABLED=y`, firmware then
  queries SIM7670G LTE status and posts a second `EGLK/1 type=event` raw frame
  with `event_type=location_observation`;
- the observation includes cell RAT, MCC/MNC/TAC/cell ID when available,
  signal metrics, registration/PDP state, LTE reason code, and
  `location_belief_state=Unknown`;
- Message Hub stores the raw frame first, derives `cell`, `lte`, `transport`,
  `lte_http`, and `location_belief` fields, and preserves prior useful
  `location_memory` when the new belief is `Unknown`;
- the host validator can require a command-scoped LTE `location_observation`
  in addition to the LTE `location_report` and ACK.

Definition of Done:

- firmware build can enable the opt-in observation path without changing the
  default LTE-004 image;
- raw `location_observation` is visible in Message Hub raw-frame evidence;
- Web/API `latest_location_observation`, `observability.cell`,
  `observability.lte`, and `observability.location_belief` update from the
  derived event;
- validator `--require-location-observation` fails if the cell/LTE observation
  is missing or not LTE-marked;
- no product position is inferred from cell-only data in this slice.

## LTE-005: Offline Reliability Gate Baseline

Goal: make the next LTE/reconnect/stability work explainable before starting a
long field run.

Implementation shape:

- `scripts/validate_lte_reliability_gate.py` reads an existing Message Hub
  `test_run_export.json`;
- the gate checks command lifecycle visibility, stale/pending command
  explanation, duplicate local execution protection, LTE transport/reason-code
  evidence, raw-frame retention, reconnect/reset observability,
  cache/drop-message observability, and sequence reset/duplicate visibility;
- the gate returns `FAIL` only for evidence risks such as missing LTE transport,
  missing raw-frame retention, unexplained stale pending commands, or repeated
  command execution without duplicate prevention;
- behaviors not exercised by the current export, such as cache/drop-message
  reporting, remain `WARN` or `NOT_OBSERVED` instead of being treated as a
  stability claim.

Definition of Done:

- the gate can run offline against LOC-005A `test_run_export.json`;
- the current LOC-005A export produces an explainable `WARN`, not a false
  product-stability pass;
- focused unit tests cover a KR-004-shaped export, stale pending command
  visibility, duplicate-execution failure, and report writing;
- no firmware, VPS runtime, protocol, hardware, or long-run stability behavior
  is changed by this tooling baseline.

## OBS-004: Reliability Observability Baseline

Goal: give firmware, simulator, and server/Web a shared place to surface
reconnect/cache/drop-message evidence before long-run LTE testing.

Implementation shape:

- `status`, `event`, and raw-frame-derived rows may carry optional
  `reliability.network` and `reliability.cache` groups;
- Message Hub preserves the original message/raw frame, then derives
  `observability.reliability` and `run_context.reliability`;
- Dashboard shows network reconnect count/reason/error and cache queue/drop
  counts;
- machine-readable status/event contracts allow the additive `reliability`
  object;
- no default `reliability.cache` is synthesized when firmware has not
  reported cache/drop-message evidence.

Definition of Done:

- server tests cover JSON `reliability` ingestion and raw-frame KV derivation;
- Dashboard tests cover visible reconnect/cache labels;
- LTE-005 still reports the current LOC-005A export as `WARN` until real
  cache/drop-message evidence exists;
- no firmware flash, VPS deploy, or long LTE stability run is part of this
  baseline.

## LTE-006: Firmware-Side Reliability Non-Claim Observability

Goal: let the raw LTE `location_observation` path explain current network and
cache capability state without claiming long-run reliability.

Implementation shape:

- LOC-005A raw KV `location_observation` adds `network_mode`,
  `network_rssi`, `network_state`, and `network_last_error`;
- the same payload adds `cache_state=not_enabled`,
  `cache_source_status=unverified`, and
  `cache_last_drop_reason=cache_not_enabled`;
- `cache_state=not_enabled` is a capability non-claim: the server may expose
  it in `reliability.cache`, but LTE-005 must continue to return `WARN` until
  concrete queue/drop counters or store-forward state are observed;
- the firmware payload remains raw-frame/KV and does not introduce JSON as the
  LTE wire payload.

Definition of Done:

- firmware static tests protect the raw KV fields;
- LTE-005 tests prove `cache_state=not_enabled` does not pass cache/drop
  observability;
- ESP-IDF build passes without flashing;
- no USB-Free runtime pass, reconnect recovery, cache durability, long LTE
  stability, battery/power behavior, enclosure behavior, or product-readiness
  claim is made until hardware validation is explicitly run.

## LTE-007: Volatile Cache Drop Observability

Goal: make the current raw LTE send/drop path observable before long LTE
stability or reconnect testing, without claiming durable store-forward.

Implementation shape:

- firmware keeps current-boot raw LTE POST counters for attempts, successes,
  failures, and drops;
- raw LTE `location_observation` and raw LTE ACK payloads include
  `network_raw_post_attempt_count`, `network_raw_post_success_count`,
  `network_raw_post_failure_count`, `cache_state=volatile_outbox`,
  `cache_source_status=observed`, `cache_queued_message_count=0`,
  `cache_dropped_message_count`, `cache_oldest_message_age_ms=0`, and
  `cache_last_drop_reason`;
- frame-build failures, payload truncation, and HTTP POST failures update the
  volatile drop counters and last-drop reason;
- LTE-005 can treat the volatile queue/drop counters as cache/drop
  observability evidence, while release docs still reject any cache durability
  or reconnect recovery claim;
- the firmware payload remains raw-frame/KV and does not introduce JSON as the
  LTE wire payload.

Definition of Done:

- focused firmware tests protect the volatile counter fields;
- LTE-005 tests prove `cache_state=volatile_outbox` with concrete counters can
  pass `G6_RECONNECT_CACHE_OBSERVABILITY`;
- ESP-IDF build passes without flashing;
- no USB-Free runtime pass, durable offline cache, reconnect recovery, long LTE
  stability, battery/power behavior, enclosure behavior, or product-readiness
  claim is made until hardware validation is explicitly run.

## R3.0 LTE Long-Run Gate

Only after the LTE reliability preflight path has concrete observability should
the project run a long LTE stability and reconnect gate. LTE-005 is a preflight
gate: it proves that the export can explain failure modes, not that the device
has already survived a long field run. LTE-007 adds current-boot volatile
outbox counters, but it still is not durable store-forward or reconnect
acceptance. The later long-run gate must cover:

- LTE registration failure;
- PDP activation failure;
- DNS failure;
- HTTP request failure;
- VPS short unavailability;
- command polling timeout;
- ACK loss;
- GNSS and LTE active in the same test window;
- restart recovery and command idempotency;
- weak-signal backoff.

Passing the Wi-Fi USB-Free stability gate does not prove any of the above.
