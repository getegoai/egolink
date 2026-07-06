---
document_status: authoritative
last_verified: 2026-06-30
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

## D1 Long-Run Observer Monitoring

`scripts/observe_d1_field_run.py` is read-only and writes future run samples
incrementally to `d1_field_samples.jsonl` while the observer is still polling.
It also refreshes `d1_field_observation_status.json` at startup, after each
sample, and at completion with running/completed state, sample counts, latest
sequence, latest freshness, and report paths. The final
`d1_field_observation_report.json/.md` is still written at observer exit.
During a long unattended run, the operator can inspect the JSONL or status file
to confirm samples are arriving without using serial logs or sending device
commands. Observer reports with `sample_write_mode=incremental_jsonl` use this
streaming sample path.

This is monitoring convenience only. It does not prove location accuracy,
battery life, GNSS acceptance, LTE long-run acceptance, or product readiness.

## Reboot-Aware Command Validation

Some firmware slices intentionally consume one command per independent-power
boot. For those gates, do not keep enqueueing new commands after the boot-time
command loop has already exited. Use a two-step validator flow.

First arm exactly one command on the VPS and record the command ID:

```powershell
python scripts\validate_lte_command_loop.py `
  --hub http://<operator-vps>:8790 `
  --device-id <device-id> `
  --test-run-id <test-run-id> `
  --expected-fw-version <firmware-version> `
  --command request_location `
  --require-location-report `
  --require-location-observation `
  --arm-only `
  --json
```

Then the operator reboots the device on independent power with USB
disconnected. After the device has had time to poll and upload evidence,
reconcile the same command instead of creating another one:

```powershell
python scripts\validate_lte_command_loop.py `
  --hub http://<operator-vps>:8790 `
  --device-id <device-id> `
  --test-run-id <test-run-id> `
  --expected-fw-version <firmware-version> `
  --expected-ack-test-run-id <firmware-test-run-id> `
  --expected-message-test-run-id <firmware-test-run-id> `
  --command request_location `
  --existing-command-id <cmd-id> `
  --require-location-report `
  --require-location-observation `
  --evidence-since command-created `
  --json
```

`command-created` is the default freshness anchor. It lets reconciliation count
raw-frame evidence uploaded during the USB-Free reboot before the validator
process was restarted. Use `--evidence-since validator-start` only when the
test specifically requires evidence after the current validator invocation.
When the command/test-run batch ID differs from the firmware image's
`CONFIG_EGOLINK_TEST_RUN_ID`, set both `--expected-ack-test-run-id` and
`--expected-message-test-run-id` to the firmware-side value.

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

## STAB-001A Short Baseline Gate Tooling

Goal: make the next USB-Free baseline run judgeable from VPS/Web evidence
instead of serial logs.

`scripts/validate_message_hub_stability.py` remains observation-only by
default. It does not flash firmware, open serial ports, erase flash, or enqueue
downlink commands. For STAB-001A it can be run with stricter requirements:

```powershell
python scripts\validate_message_hub_stability.py `
  --hub http://<operator-vps>:8790 `
  --device-id <device-id> `
  --observation-id <test-run-id> `
  --expected-message-test-run-id <test-run-id> `
  --duration-sec 120 `
  --poll-interval-sec 5 `
  --min-messages 4 `
  --min-location-observations 1 `
  --require-observability `
  --require-location-belief `
  --require-command-ack `
  --require-test-run-export `
  --json
```

The operator or Web may enqueue a harmless command during the observation when
`--require-command-ack` is used. The observer itself does not enqueue it.

Required STAB-001A report state:

- recent messages meeting the minimum message count;
- no sequence regressions unless explicitly allowed;
- at least one `location_observation` when location observation is in scope;
- final device state includes `observability`;
- `location_belief.state` and `location_belief.reason` are present;
- command ACK status is `ok` when command ACK is required;
- test-run export is available and includes `observability_summary`.

STAB-001A proves the gate tooling and simulator/local behavior. A physical
STAB-001 pass still requires operator-confirmed independent power and USB
disconnected for the whole run.

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

Before starting a long field run, run the LTE-005 offline reliability gate over
the most recent key-release export:

```powershell
python scripts\validate_lte_reliability_gate.py --input reports\field_validation\<test-run-id>\test_run_export.json --output-dir reports\lte_reliability\<test-run-id>
```

The gate must not be read as long-run acceptance. `PASS` means the export
contains enough reliability evidence for the checked behaviors. `WARN` means
one or more behaviors, such as reconnect, stale command, or cache/drop-message
reporting, were not exercised and should be planned into the next field run.
`FAIL` means the next field run would be blind or unsafe to interpret.

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
- `reliability.network.last_error`
- `reliability.network.last_reconnect_reason`
- `reliability.cache.queued_message_count`
- `reliability.cache.dropped_message_count`
- `reliability.cache.last_drop_reason`
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
