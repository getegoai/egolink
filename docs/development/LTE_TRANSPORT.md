---
document_status: authoritative
last_verified: 2026-06-28
verified_by: codex
---

# SIM7670G LTE Transport Track

The current validated USB-Free path uses Wi-Fi HTTP to the public VPS Message
Hub. That path is the development baseline, not final product transport
acceptance. The SIM7670G LTE track must be introduced as thin slices so that
each failure stage is visible.

## Scope

P0 LTE transport uses the existing Message Hub HTTP envelope first:

```text
HTTP POST telemetry
HTTP GET command polling
HTTP POST ACK
```

MQTT, raw TCP long connections, and advanced reconnect supervisors are deferred
until HTTP over LTE proves the minimal product link.

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

Definition of Done:

- Wi-Fi is disabled for the run.
- USB is not the runtime data path.
- device posts telemetry to the existing VPS Message Hub.
- `/api/state` shows `transport.type=lte`.
- Dashboard shows LTE last update, cell fingerprint, and signal quality.

## LTE-003: Command Poll And ACK

Goal: migrate the current Web command queue to LTE HTTP polling without
changing command semantics.

Definition of Done:

- Web enqueues a harmless command.
- device polls over LTE.
- firmware executes once and ACKs over LTE.
- duplicate execution, timeout, retry, and stale command states are visible.

## R3.0 LTE Long-Run Gate

Only after LTE-001 through LTE-003 pass should the project run a long LTE
stability and reconnect gate. That gate must cover:

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
