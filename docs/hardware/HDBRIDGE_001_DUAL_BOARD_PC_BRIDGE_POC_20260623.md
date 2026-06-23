# HDBRIDGE-001 Dual-Board PC Bridge PoC

Date: 2026-06-23

## Goal

Turn the dual-board development architecture into a small PC-side bridge PoC:

- `ESP32-S3-Touch-AMOLED-2.06` acts as the future wearable sensor node.
- `ESP32-S3-SIM7670G-4G` remains the connectivity / GNSS / camera node.
- The PC remains the temporary event bus, ContextRouter host, recorder, replay
  entry point, and debug center.

This task does not exercise live USB serial hardware. It proves the protocol
shape, event-log integration, deterministic routing, and M1 recording boundary
with newline-delimited JSON input.

## Implemented

New bridge core:

```text
pc_simulator/board_bridge.py
scripts/board_bridge.py
```

The bridge accepts one or more JSONL sources:

```powershell
python scripts\board_bridge.py --source boot=boot.jsonl --source wearable=wearable.jsonl --event-log pc_simulator\runtime\events.jsonl
```

The first PoC intentionally uses file/stdin sources instead of pyserial. The
transport can later be replaced by USB CDC readers without changing the event
normalization or recorder contract.

## Protocol Shape

Each board first sends a hello:

```json
{"type":"hello","device_id":"wearable-node-001","role":"wearable_node","protocol_version":"0.1"}
{"type":"hello","device_id":"connectivity-node-001","role":"connectivity_node","protocol_version":"0.1"}
```

The bridge records these as `board_hello` events and binds role to device ID.
It does not depend on COM numbers.

Wearable motion input example:

```json
{
  "source": "wearable-node-001",
  "type": "motion_event",
  "seq": 1024,
  "timestamp_ms": 1782210408000,
  "payload": {
    "impact_score": 0.92,
    "fall_score": 0.78,
    "stationary_seconds": 12
  }
}
```

When `impact_score >= 0.8` or `fall_score >= 0.7`, the PoC writes deterministic
downlink command records:

- `ask_user` to `wearable_node`
- `request_location` to `connectivity_node`

These are recorded as `command_sent` events, not sent to live hardware yet.

## M1 Recording Boundary

`pc_simulator/session_recorder.py` now recognizes bridge motion events as
`imu_motion` sensor frames with:

```text
source_availability=bridge_uplink
source_status=unverified
```

This is deliberate. HDBRIDGE-001 proves that the PC bridge can carry IMU-shaped
events into recording, quality gate, and replay. It does not prove that QMI8658
has been identified, sampled at a known ODR, oriented, calibrated, or measured
for jitter/drops.

## Verification

```powershell
python -m unittest quality_tests.test_board_bridge quality_tests.test_session_recorder quality_tests.test_session_inspector -v
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

Results:

- Targeted bridge/recorder/inspector tests: 12 passed.
- Full repository verification after HDBRIDGE-001: 136 passed.

## Current Boundary

- Verified: PC-side bridge protocol shape, hello role binding, motion-event
  normalization, deterministic command records, `imu_motion` recorder frames,
  and quality-gate compatibility.
- Not verified: live USB serial from the AMOLED board, QMI8658 WHOAMI, real IMU
  sample rate, jitter, dropped samples, orientation, microphone audio capture,
  AMOLED display/touch commands, board-to-board UART, standalone operation, and
  dual-board power behavior.
