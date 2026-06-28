---
document_status: authoritative
last_verified: 2026-06-28
verified_by: codex
---

# USB-Free Field Test

Formal P0 field tests must prove the product-like message path:

```text
device on independent power -> network -> VPS Message Hub -> Web Dashboard
```

USB is allowed for flashing, temporary debugging, and post-failure log export.
It is not allowed as the formal runtime path or the only acceptance evidence.

## Preflight Checklist

```text
[ ] VPS service is running.
[ ] Web Dashboard is reachable.
[ ] Existing GitLab service on the VPS is untouched.
[ ] Device token or secret is configured outside the repository.
[ ] Firmware version and build commit/image are recorded.
[ ] Battery or independent power is ready.
[ ] SIM/network path is ready.
[ ] GNSS antenna is attached when GNSS is in scope.
[ ] Device can run after USB is disconnected.
[ ] PC Simulator has passed R0.
[ ] Real device has passed R1 before R2 outdoor testing.
[ ] test_run_id has been created.
```

## R2.1 Observability Completion Gate

Goal: make field failures explainable before any long stability run.

This gate is required before `STAB-001`, LTE transport gates, battery gates,
or enclosure GNSS comparisons. It does not require flashing new firmware if the
server can derive the observability view from existing compatible telemetry.

Required Dashboard / export state:

- `transport.type`, `transport.rtt_ms`, and `transport.last_error`;
- `runtime.boot_id`, `runtime.uptime_s`, `runtime.free_heap`,
  `runtime.last_reset_reason`, and `runtime.watchdog_count`;
- `command.last_cmd_id`, `command.last_status`, `command.last_ack_status`,
  and command RTT when known;
- `power.battery_mv`, `power.soc_pct`, `power.charging`, and `power.source`;
- `gnss.fix`, `gnss.state`, `gnss.hdop`, `gnss.satellites`,
  `gnss.attempt_ms`, and `gnss.reason_code`;
- `cell.rat`, `cell.operator`, `cell.mcc`, `cell.mnc`, `cell.tac`,
  `cell.cell_id`, `cell.rsrp`, `cell.rsrq`, `cell.rssi`, and `cell.sinr`
  when available.

Acceptance:

- `/api/state` contains a normalized `observability` object for each device.
- test-run export includes `observability_summary`.
- Web can distinguish missing GNSS observation, no-fix, AT unreachable,
  transport error, reset, command timeout/ACK state, and unknown power.
- Unknown fields are shown as `unknown` or `unverified`, not inferred.

## R1 Indoor Real-Device Test Without Real GNSS

Goal: prove that real hardware can boot, connect, report heartbeat or fixed/mock
location, receive a command, and ACK without USB.

Steps:

1. Flash firmware.
2. Record firmware image/commit and device ID.
3. Start or verify VPS Message Hub and Web Dashboard.
4. Power the device independently and disconnect USB.
5. Confirm the server receives boot/status messages.
6. Confirm Dashboard shows online or stale status correctly.
7. Send one harmless command such as `set_report_interval`.
8. Confirm ACK through Web/server logs.

Acceptance evidence must include server logs, Dashboard capture/export, and
test run ID. Serial logs are optional debugging evidence only.

## R2 Outdoor GNSS Test

Goal: prove that real GNSS telemetry reaches the VPS while USB is disconnected.

FW-002A is the pre-driver scaffold for this route. It may be used to prove
`request_location -> location_report -> ACK` on the real device before the
SIM7670G firmware GNSS driver exists, but a scaffold `location_report` with
`gnss_state=driver_not_integrated` is not R2 real-GNSS acceptance evidence.

Steps:

1. Start a field `test_run_id`.
2. Power the device independently and disconnect USB.
3. Move the device outdoors with clear sky view.
4. Observe `gnss.state` moving through `searching`, `fixed`, `lost`, or
   `error`.
5. Walk a short route after fix.
6. Confirm Dashboard shows latest location, last update time, satellites, HDOP,
   and track points.
7. Send a reporting-interval command and confirm ACK.
8. Export the test report.

No-fix is not automatically a failure, but the Dashboard must show `fix=false`
and a useful state instead of appearing empty.

## R3 Reliability Test

Goal: make field failures diagnosable without serial logs.

Test at least:

- short network loss and reconnect;
- GNSS no-fix interval;
- stale/offline transition;
- command timeout and later ACK if recovered;
- local cache or explicit dropped-message report;
- low-power or unknown-power state labeling.

Definition of Done:

- 30 minutes of continuous field operation without device crash;
- reconnect is visible through server/Web state;
- server records `server_received_at`;
- duplicate or delayed `seq` behavior is visible;
- Dashboard distinguishes no-fix, no-network, stale, low-battery, device-error,
  and server-error states.

## Dashboard Required Fields

- `device_id`
- `fw_version`
- `online_status`
- `last_seen_at`
- `device_state`
- `last_error`
- `gnss.fix`
- `gnss.state`
- `gnss.lat`
- `gnss.lon`
- `gnss.satellites`
- `gnss.hdop`
- `network.mode`
- `network.rssi`
- `network.reconnect_count`
- `power.battery_mv`
- `power.battery_percent`
- `message.seq`
- `pending_commands`
- `last_ack`

Unknown or unverified capability must be shown as `unknown` or `unverified`,
not inferred from board name.

## Report Export Fields

Each field-test report should include:

- test run ID;
- board and firmware image/commit;
- connection path;
- start/end timestamps;
- message counts by type;
- latest and historical GNSS state;
- command and ACK history;
- error and reconnect history;
- evidence file paths;
- source labels and unresolved risks.
