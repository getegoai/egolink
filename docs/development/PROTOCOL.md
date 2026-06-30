---
document_status: authoritative
last_verified: 2026-06-29
verified_by: codex
---

# P0 Message Protocol

This is the human-readable protocol baseline for the Ego Link P0 message-hub
path. Machine-readable schemas live in `../../shared/contracts/`:

- `message_hub_status.schema.json`
- `message_hub_event.schema.json`
- `message_hub_command.schema.json`
- `message_hub_ack.schema.json`
- `message_hub_error.schema.json`
- `message_hub_raw_frame_record.schema.json`

Model-facing schemas remain in the same directory and are separate from the
message-hub transport contract.

## Current Version

Current code uses:

```text
protocol_version = egolink.p0.v1
```

Do not introduce another live protocol version such as `0.1` or `0.2` for the
VPS message hub without a Protocol track task. Existing board-local demo
protocols may keep their local versions, but bridge/server traffic must expose
its own `protocol_version`.

## PROTO-002 Raw Frame Transport Profile

`egolink.p0.v1` remains the current Message Hub and Web data model. It is not
the required device wire format for future SIM7670G LTE runtime traffic.

The P0 runtime direction is `raw-frame.p0.v1`:

- device/server transport is raw-frame first, not JSON first;
- the server must persist the original received frame bytes before semantic
  parsing;
- incomplete, malformed, checksum-failed, and unsupported frames must remain
  durable evidence with a parse status;
- Message Hub JSON status/event/command/ACK objects are derived views for Web,
  API, validation, and compatibility;
- firmware should parse a small stable frame header and checksum for normal
  command/ACK operation, not a full JSON command document.

This keeps the demo loop visible while avoiding a brittle firmware dependency
on exact JSON body extraction. Server-side parsers may still produce the
existing `egolink.p0.v1` objects after raw storage succeeds.

### Raw Frame Shape

The P0 raw frame starts with one ASCII header line, optional ASCII metadata
lines, a blank line, and then the exact payload bytes:

```text
EGLK/1 type=command id=cmd-000013 seq=13 len=37 crc32=2A4F8C91
content-type=text/x-egolink-kv

cmd=set_report_interval
interval_ms=5000
```

Minimum header semantics:

| Field | Required | Notes |
|---|---|---|
| `EGLK/1` | yes | Magic and raw-frame version. |
| `type` | yes | `status`, `event`, `command`, `ack`, `error`, `log`, or `raw`. |
| `id` | command/ACK | Command ID, frame ID, or parser-assigned ID. |
| `seq` | preferred | Monotonic per device/session where available. |
| `len` | yes | Payload byte length after the blank line. |
| `crc32` | yes | CRC32 of the payload bytes. |
| `content-type` | yes | `text/x-egolink-kv` for P0 commands unless a task approves another profile. |

The storage/parser result is represented by
`message_hub_raw_frame_record.schema.json`. That schema is a server-side record
contract and does not mean the device wire payload is JSON.

### Derived JSON Boundary

Raw-frame ingest may derive existing Message Hub objects:

| Raw frame type | Derived view |
|---|---|
| `status` | `message_type=status` state and observability. |
| `event` | `message_type=event` telemetry and test-run evidence. |
| `command` | Downlink command state for Web/API compatibility. |
| `ack` | Command ACK row and validator result. |
| `error` | Diagnosable Message Hub error row. |

Failed parse is not data loss. A frame with `parse_result.status=partial`,
`checksum_failed`, `unsupported`, or `malformed` must still be queryable in
test-run evidence by frame ID, timestamp, device ID, and byte/hash metadata.

## Common Envelope

P0 message-hub messages must include:

| Field | Required | Notes |
|---|---|---|
| `protocol_version` | yes | Current value: `egolink.p0.v1`. |
| `device_id` | uplink yes | Stable logical ID; do not infer from COM port. |
| `fw_version` | firmware preferred | Use `unknown` if unavailable. |
| `seq` | uplink yes | Monotonic per device/session where possible. |
| `ts` | current compatibility | Existing PC/Firmware field. |
| `device_timestamp` | target | Device-side Unix timestamp or monotonic marker. |
| `server_received_at` | server yes | Added by server, not by device. |
| `message_type` | yes | `status`, `event`, `command`, `ack`, or `error`. |
| `test_run_id` | field tests | Required for formal field-test evidence. |

New fields should be additive. Deleting or renaming existing fields requires a
protocol version change and a compatibility note.

## OBS-001 Additive Observability Fields

OBS-001 adds a normalized observability view for field testing and failure
explanation. These fields are optional in incoming `egolink.p0.v1` messages and
may be supplied directly by firmware, simulator, or derived by the Message Hub
from older fields. They do not replace existing `status`, `location_report`,
`command`, or `ack` behavior.

Recommended additive groups:

| Group | Fields |
|---|---|
| `transport` | `type`, `rtt_ms`, `last_error` |
| `runtime` | `boot_id`, `uptime_s`, `free_heap`, `last_reset_reason`, `watchdog_count` |
| `command` | `last_cmd_id`, `last_status`, `last_ack_status`, `rtt_ms` |
| `power` | `battery_mv`, `soc_pct`, `charging`, `source` |
| `gnss` | `fix`, `state`, `hdop`, `satellites`, `attempt_ms`, `result`, `reason_code` |
| `cell` | `rat`, `operator`, `mcc`, `mnc`, `tac`, `cell_id`, `rsrp`, `rsrq`, `rssi`, `sinr` |
| `lte` | `driver`, `query_ok`, `sim_state`, `registration_state`, `apn_state`, `pdp_state`, `assigned_ip`, `reason_code` |

The Message Hub exposes the derived view as `device.observability` in
`/api/state` and includes `observability_summary` in test-run exports. Unknown
values must remain `unknown` or absent; firmware and Web must not infer LTE,
battery, or GNSS capability from board name alone.

Typical derived state:

```json
{
  "observability": {
    "transport": {
      "type": "wifi",
      "rtt_ms": 42,
      "last_error": null
    },
    "runtime": {
      "boot_id": "boot_count:172",
      "uptime_s": 120.5,
      "free_heap": 123456,
      "last_reset_reason": "poweron",
      "watchdog_count": 0
    },
    "gnss": {
      "fix": false,
      "state": "no_fix",
      "reason_code": "GNSS_NO_FIX"
    }
  }
}
```

## LTE-001A LTE Registration And Cell Observability

LTE-001A adds optional firmware-supplied `cell` and `lte` objects to existing
`status` and `sensor_sample` messages. The Message Hub stores them as normal
`egolink.p0.v1` additive fields and derives `observability.cell`,
`observability.lte`, and LTE reason codes from them.

`cell` describes the radio fingerprint and signal quality:

```json
{
  "cell": {
    "rat": "LTE",
    "operator": "operator-name",
    "mcc": "460",
    "mnc": "01",
    "tac": "0x230A",
    "cell_id": "1234567",
    "rssi": -69,
    "rsrp": -96,
    "rsrq": -12,
    "sinr": 18,
    "registration_state": "registered_home",
    "pdp_state": "active",
    "reason_code": "LTE_READY"
  }
}
```

`lte` describes the SIM7670G query and the stage that blocks LTE readiness:

```json
{
  "lte": {
    "driver": "sim7670g_uart_at",
    "query_ok": true,
    "sim_state": "READY",
    "registration_state": "registered_home",
    "apn_state": "configured",
    "pdp_state": "active",
    "assigned_ip": "10.1.2.3",
    "reason_code": "LTE_READY"
  }
}
```

Expected failure reason codes include `LTE_AT_UNREACHABLE`,
`LTE_SIM_NOT_READY`, `LTE_NOT_REGISTERED`, `LTE_NOT_ATTACHED`,
`LTE_PDP_INACTIVE`, and `LTE_READY`. LTE-001A does not change
`transport.type` to `lte`; the firmware still uses the existing Wi-Fi HTTP
Message Hub path until an explicit LTE HTTP transport task proves uplink,
command polling, and ACK over the SIM7670G data path.

## LTE-002 LTE HTTP Probe Event

LTE-002 uses the existing `message_type=event` envelope with
`event_type=lte_http_probe`. It does not change `egolink.p0.v1`; the probe
adds transport diagnostics so the Message Hub and Dashboard can distinguish an
LTE uplink proof from the previous Wi-Fi HTTP development path.

Required transport envelope fields remain those of a normal event:
`protocol_version`, `device_id`, `ts`, `seq`, `message_type`, `event_type`,
and `priority`.

Recommended additive fields:

```json
{
  "event_type": "lte_http_probe",
  "source": "sim7670g_lte_http_probe",
  "source_status": "observed",
  "transport": {
    "type": "lte",
    "rtt_ms": 123,
    "last_error": null
  },
  "lte_http": {
    "phase": "result",
    "driver": "sim7670g_uart_at_http",
    "reason_code": "LTE_HTTP_OK",
    "status_code": 200,
    "action_elapsed_ms": 123
  },
  "lte": {
    "driver": "sim7670g_uart_at",
    "reason_code": "LTE_READY"
  }
}
```

Expected LTE HTTP reason codes include `LTE_HTTP_OK`,
`LTE_HTTP_AT_UNREACHABLE`, `LTE_HTTP_UART_INIT_FAILED`,
`LTE_HTTP_INIT_FAILED`, `LTE_HTTP_DATA_FAILED`,
`LTE_HTTP_ACTION_FAILED`, `LTE_HTTP_READ_AT_FAILED`,
`LTE_HTTP_READ_AT_ERROR`, `LTE_HTTP_READ_AT_TIMEOUT`,
`LTE_HTTP_READ_BODY_PARSE_FAILED`, `LTE_HTTP_CLIENT_ERROR`,
`LTE_HTTP_SERVER_ERROR`, and `LTE_HTTP_STATUS_ERROR`.

The first firmware slice sends `phase=attempt` followed by `phase=result` so
the result event can report the HTTP status of the preceding LTE POST. LTE-002
does not implement command polling or ACK over LTE; that remains `LTE-003`.

## LTE-003 LTE HTTP Command ACK

LTE-003 began as a JSON command-poll migration using the existing
`message_type=command` and `message_type=ack` envelopes. Fix7/fix8 evidence
showed that the SIM7670G HTTP command path can reach the VPS and receive a
valid body, while firmware can still fail because the JSON body extraction or
`cJSON_Parse` boundary is brittle.

As of PROTO-002, the JSON command-poll implementation is a legacy diagnostic
path. Do not treat flashing another JSON parser fix as LTE-003 product
progress unless an explicit task says so. The next acceptance path should use
the raw-frame command profile, where firmware reads a small frame header,
verifies length/checksum, executes one harmless command, and posts a raw ACK.

The existing JSON ACK shape remains the derived Web/API compatibility view:

```json
{
  "protocol_version": "egolink.p0.v1",
  "device_id": "ego-link-r1-connectivity-001",
  "fw_version": "0.1.0-lte003-command-loop",
  "seq": 3,
  "ts": "uptime_ms:30000",
  "message_type": "ack",
  "cmd_id": "cmd-000013",
  "status": "ok",
  "message": "lte command loop acknowledged set_report_interval",
  "test_run_id": "lte003-command-loop-20260628-001",
  "transport": {
    "type": "lte",
    "rtt_ms": 123,
    "last_error": null
  },
  "lte_http": {
    "phase": "command_ack",
    "driver": "sim7670g_uart_at_http",
    "poll_reason_code": "LTE_HTTP_OK",
    "poll_status_code": 200,
    "poll_action_elapsed_ms": 123
  },
  "command": {
    "last_cmd_id": "cmd-000013",
    "last_status": "ok",
    "last_ack_status": "ok",
    "duplicate_local_execution_prevented": false
  }
}
```

If the device sees the same pending `cmd_id` again after local execution, it
should re-send ACK without repeating the local command action and set
`duplicate_local_execution_prevented=true`. LTE-003 does not require
`request_location` over LTE; that can be added after the basic command ACK
path is proven.

For the raw-frame path, the first acceptance command remains
`set_report_interval`, but the downlink payload should be compact key/value
content such as:

```text
cmd=set_report_interval
interval_ms=5000
cmd_id=cmd-000013
```

The server should derive the same ACK row and validator evidence from the raw
ACK after the raw frame itself has been stored.

## LTE-004 Raw LTE Request Location

LTE-004 extends the proven raw LTE command/ACK path to the product-relevant
`request_location` command. The device still does not parse JSON from the
server. It polls a raw `command` frame, runs the existing firmware GNSS backend
or explicit no-fix scaffold, uploads one raw `event` frame, then sends a raw
ACK frame.

The raw location event payload uses compact key/value content:

```text
event_type=location_report
priority=normal
fw_version=0.1.0-lte004-raw-lte-location
test_run_id=lte004-raw-lte-location-20260629-001
seq=42
source=sim7670g_firmware_gnss
source_status=unverified
fix=false
gnss_state=no_fix
gnss_source=sim7670g_uart_at
gnss_driver=uart_at
gnss_query_ok=true
lat=null
lon=null
satellites=null
hdop=null
location_request_cmd_id=cmd-000020
transport_type=lte
lte_http_phase=location_report
lte_http_driver=sim7670g_uart_at_http
```

The Message Hub must store the original `EGLK/1 type=event` frame first. It may
then derive the existing `egolink.p0.v1` `message_type=event` /
`event_type=location_report` compatibility view for Web, API, and validators.
A no-fix report is acceptable for this transport slice when the report is
explicit and diagnosable. A malformed or checksum-failed location frame remains
raw evidence and must not be silently dropped.

## LOC-004A Raw LTE Cell Location Observation

LOC-004A keeps LTE-004's `request_location -> location_report -> ACK` loop and
adds a second raw `event` frame for firmware-side cell/LTE observation. The
device/server wire truth remains `EGLK/1` raw-frame bytes. The Message Hub
stores the original frame first, then derives a compatible
`event_type=location_observation` JSON/Web/API view.

The raw observation payload uses compact key/value content:

```text
event_type=location_observation
priority=normal
fw_version=0.1.0-loc004a-cell-observation
test_run_id=loc004a-cell-observation-20260630-001
seq=43
source=sim7670g_firmware_cell
source_status=observed
location_request_cmd_id=cmd-000021
cell_rat=LTE
cell_mcc=460
cell_mnc=01
cell_tac=2A0B
cell_id=01AF23
cell_rsrp=-91
cell_rsrq=-12
cell_sinr=17
cell_registration_state=registered_home
cell_pdp_state=active
cell_reason_code=LTE_READY
lte_driver=sim7670g_uart_at
lte_query_ok=true
lte_registered=true
lte_pdp_active=true
lte_assigned_ip=10.1.2.3
lte_reason_code=LTE_READY
location_belief_state=Unknown
location_belief_source=cell,lte
location_belief_reason=cell_observation_without_position_fix
transport_type=lte
lte_http_phase=location_observation
lte_http_driver=sim7670g_uart_at_http
```

`location_belief_state=Unknown` means the firmware produced real cell/LTE
evidence but did not infer a user position. The server must retain the evidence
without erasing prior useful `location_memory`. If usable memory already exists,
the active belief may be derived as `Predicted` with reason
`last_known_after_unknown_location_observation`.

## LOC-002 Location Observation Event

LOC-002 adds the compatible `event_type=location_observation` event. It keeps
the same `message_type=event` envelope and does not replace
`location_report`. Firmware, simulator, and future LTE transports may upload
both:

- `location_report`: command-scoped GNSS fix/no-fix result.
- `location_observation`: multi-source location evidence and belief state.

Required transport envelope fields remain those of a normal event:
`protocol_version`, `device_id`, `ts`, `seq`, `message_type`, `event_type`,
and `priority`.

Recommended optional groups:

| Group | Meaning |
|---|---|
| `gnss` | GNSS enabled/fix/quality/attempt result. |
| `cell` | LTE RAT, operator, MCC/MNC, TAC, cell ID, and signal quality. |
| `wifi` | privacy-preserving AP hashes and RSSI; no raw private BSSID by default. |
| `imu` | motion state and confidence. |
| `power` | battery voltage, state-of-charge estimate, charging state, source. |
| `location_belief` | `Fine` / `Coarse` / `Predicted` / `Unknown`, radius, confidence, source, and reason. |

Example coarse observation:

```json
{
  "protocol_version": "egolink.p0.v1",
  "device_id": "ego-link-r0-sim",
  "fw_version": "0.1.0-sim",
  "seq": 12,
  "ts": "2026-06-28T02:40:00Z",
  "message_type": "event",
  "event_type": "location_observation",
  "priority": "normal",
  "source": "pc_simulator_location_observation",
  "source_status": "mock",
  "gnss": {
    "enabled": true,
    "fix": false,
    "state": "no_fix",
    "attempt_ms": 30000,
    "result": "no_fix"
  },
  "cell": {
    "rat": "LTE",
    "mcc": "460",
    "mnc": "01",
    "tac": "0x230A",
    "cell_id": "mock-cell-001",
    "rsrp": -71
  },
  "wifi": {
    "scan_enabled": true,
    "aps": [
      {
        "bssid_hash": "mock_hash_1",
        "rssi": -62
      }
    ]
  },
  "imu": {
    "motion": "stationary",
    "confidence": 0.93
  },
  "location_belief": {
    "state": "Coarse",
    "radius_m": 180,
    "confidence": 0.72,
    "source": ["cell", "wifi_memory"],
    "reason": "matched_mock_known_place"
  }
}
```

The Message Hub treats `location_observation` as location evidence for
`latest_location`, exposes the latest observation as
`latest_location_observation`, and derives `observability.location_belief` for
Dashboard and export. This is a contract/server/simulator baseline only; it
does not claim firmware-side cell, Wi-Fi, IMU, or power observation until those
sources are exercised by later tasks.

## LOC-003 Derived Location Memory View

LOC-003 does not add a required device wire field. It adds a Message Hub
derived view:

- `devices[].location_memory` in `/api/state`.
- `devices[].observability.location_memory` in `/api/state`.
- `observability_summary.latest_observability.location_memory` in test-run
  exports.

The server updates memory from existing location evidence:

- `location_observation.location_belief` updates memory state, radius,
  confidence, source, and reason.
- `location_report fix=true` creates a `Fine` GNSS calibration memory.
- `location_report fix=false` stores `last_no_fix` but does not erase the last
  valid memory.
- `location_observation.location_belief.state=Unknown` stores
  `last_unknown_observation` but does not erase an existing `Fine`, `Coarse`,
  or `Predicted` memory.
- If the latest report is no-fix but memory exists,
  `observability.location_belief.state` becomes `Predicted` and the reason is
  `last_known_after_gnss_no_fix`.
- If the latest observation is explicit `Unknown` but memory exists,
  `observability.location_belief.state` becomes `Predicted` and the reason is
  `last_known_after_unknown_location_observation`.

The raw-frame rule remains unchanged: original frames are stored first, then
the Message Hub derives JSON/Web/API views. Location memory is derived state,
not a replacement for retained raw evidence.

## Message Types

### Heartbeat / Status

Existing compatibility uses `message_type=status`; the product-facing concept is
heartbeat.

```json
{
  "protocol_version": "egolink.p0.v1",
  "device_id": "ego-link-001",
  "fw_version": "unknown",
  "seq": 1025,
  "ts": "2026-06-27T03:00:10Z",
  "message_type": "status",
  "reset_reason": "poweron",
  "boot_count": 12,
  "boot_uptime_ms": 3610000,
  "payload": {
    "state": "online",
    "uptime_sec": 3610,
    "free_heap": 123456,
    "rssi": -75,
    "battery_mv": null
  }
}
```

### Telemetry / Event

Existing compatibility uses `message_type=event` plus `event_type`. GNSS,
sensor, network, and power reports should keep explicit source and truth labels.

```json
{
  "protocol_version": "egolink.p0.v1",
  "device_id": "ego-link-001",
  "fw_version": "0.1.0",
  "seq": 1026,
  "ts": "2026-06-27T03:00:20Z",
  "message_type": "event",
  "event_type": "location_report",
  "test_run_id": "field-20260627-001",
  "payload": {
    "gnss": {
      "fix": false,
      "state": "searching",
      "lat": null,
      "lon": null,
      "satellites": 0,
      "hdop": null,
      "source": "firmware",
      "source_status": "unverified"
    }
  }
}
```

FW-002 introduces the first firmware-side `location_report` command/telemetry
scaffold. Until a SIM7670G firmware GNSS driver is integrated, the firmware may
return an explicit no-fix report instead of silently omitting location data:

```json
{
  "protocol_version": "egolink.p0.v1",
  "device_id": "ego-link-r1-connectivity-001",
  "fw_version": "0.1.0-fw002-location-scaffold",
  "seq": 2049,
  "ts": "uptime_ms:120000",
  "message_type": "event",
  "event_type": "location_report",
  "priority": "normal",
  "test_run_id": "fw002-location-20260627-001",
  "source": "firmware_gnss_scaffold",
  "source_status": "unverified",
  "fix": false,
  "gnss_state": "driver_not_integrated",
  "lat": null,
  "lon": null,
  "satellites": 0,
  "hdop": null,
  "location_request_cmd_id": "cmd-000004"
}
```

`driver_not_integrated` is not a real GNSS result. It only proves that the
device received `request_location`, emitted the expected telemetry envelope,
and kept the no-fix state visible for the field-test report.

FW-002B adds an opt-in firmware SIM7670G UART/AT GNSS backend without changing
the envelope. When `CONFIG_EGOLINK_SIM7670_GNSS_ENABLED=y`, the same
`request_location` command may return module-derived no-fix or fix telemetry:

```json
{
  "protocol_version": "egolink.p0.v1",
  "device_id": "ego-link-r1-connectivity-001",
  "fw_version": "0.1.0-fw002b-sim7670-gnss",
  "seq": 2050,
  "ts": "uptime_ms:180000",
  "message_type": "event",
  "event_type": "location_report",
  "priority": "normal",
  "test_run_id": "fw002b-gnss-20260627-001",
  "source": "sim7670g_firmware_gnss",
  "source_status": "unverified",
  "fix": false,
  "gnss_state": "no_fix",
  "gnss_source": "sim7670g_uart_at",
  "gnss_driver": "uart_at",
  "gnss_query_ok": true,
  "lat": null,
  "lon": null,
  "satellites": null,
  "hdop": null,
  "raw_command": "AT+CGNSSINFO",
  "raw_response": "+CGNSSINFO:,,,,,,,,,,,,,,,,,",
  "location_request_cmd_id": "cmd-000005"
}
```

The firmware-side SIM7670G backend reports no-fix and unreachable states as
`source_status=unverified`. When the module response contains parsed latitude
and longitude and `fix=true`, firmware should report `source_status=observed`;
that marks hardware observation, not final product GNSS acceptance. It may
also report `gnss_state=at_unreachable` or `uart_init_failed`; those are
diagnosable firmware-side states, not location fixes.

### Command

```json
{
  "protocol_version": "egolink.p0.v1",
  "message_type": "command",
  "device_id": "ego-link-001",
  "cmd_id": "cmd-0001",
  "cmd": "set_report_interval",
  "created_at": "2026-06-27T03:00:30Z",
  "payload": {
    "interval_ms": 5000
  }
}
```

Known P0 Message Hub commands:

| Command | Required behavior |
|---|---|
| `set_report_interval` | Adjust or acknowledge the requested reporting interval without changing safety-critical behavior. |
| `request_location` | Upload one `location_report` event and then ACK the command. A scaffold implementation must report `fix=false`, `source_status=unverified`, and a clear `gnss_state` such as `driver_not_integrated`; a real GNSS implementation must report `fix=false` while searching and `fix=true` with coordinates when fixed. |

### ACK

```json
{
  "protocol_version": "egolink.p0.v1",
  "device_id": "ego-link-001",
  "fw_version": "0.1.0",
  "seq": 1027,
  "ts": "2026-06-27T03:00:32Z",
  "message_type": "ack",
  "cmd_id": "cmd-0001",
  "status": "ok",
  "message": "report interval updated"
}
```

### Error

```json
{
  "protocol_version": "egolink.p0.v1",
  "device_id": "ego-link-001",
  "fw_version": "0.1.0",
  "seq": 1028,
  "ts": "2026-06-27T03:03:30Z",
  "message_type": "error",
  "payload": {
    "error_code": "GNSS_NO_FIX_TIMEOUT",
    "severity": "warning",
    "message": "GNSS no fix for 180 seconds",
    "recoverable": true
  }
}
```

## Field Rules

- GNSS must distinguish `fix=false` from no data. Do not silently omit failed
  fixes.
- Coordinates use decimal degrees, altitude uses meters, speed uses m/s, HDOP
  is numeric when known.
- Power fields must label mock, estimated, measured, or unknown sources.
- Network fields should include mode, RSSI, reconnect count, and last network
  error when known.
- Device state should use stable values such as `booting`, `idle`,
  `field_test`, `reconnecting`, `error`, or `unknown`.
- Reset diagnostics may appear on `status` and `sensor_sample` messages as
  `reset_reason`, `boot_count`, and `boot_uptime_ms`. These fields are for
  USB-Free stability diagnosis and do not by themselves prove power behavior.
- Error codes use uppercase snake case.

## Compatibility Rules

1. Add optional fields before changing existing required fields.
2. Keep source labels explicit: `verified`, `observed`, `mock`,
   `pc_side_verified`, `unknown`, or `unverified`.
3. `server_received_at` is server authority for receive order.
4. Protocol changes land in Protocol tasks before Firmware or Server-Web tasks.
5. Existing local topics and PC Simulator behavior remain supported until a
   migration task updates tests and firmware together.
