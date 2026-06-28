---
document_status: authoritative
last_verified: 2026-06-28
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
