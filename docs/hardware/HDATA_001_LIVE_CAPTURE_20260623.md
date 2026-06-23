# HDATA-001 Live Capture - 2026-06-23

## Scope

This report records the bounded HDATA-001 live capture performed after flashing
the HPWR-001 `firmware/mqtt_heartbeat` build to the Waveshare
ESP32-S3-SIM7670G-4G board.

This is a data-capture evidence note only. It does not claim real current draw,
battery runtime, true battery telemetry, camera data, microphone data, IMU data,
SD storage, or ESP32-side SIM7670G control.

## Commands

```powershell
. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py -p COM4 flash
python scripts\egolink_board_probe.py --skip-esp-log --probe-all-sim-ports
python pc_simulator\mqtt_worker.py --host 192.168.31.250 --port 1883 --event-log pc_simulator\runtime\hdata-001-hpwr-live-20260623-0906-events.jsonl --max-messages 6 --wait-seconds 120 --process-safety --safety-process-limit 20
python scripts\sim7670_gnss_probe.py --warmup-seconds 5 --poll-count 3 --poll-interval-seconds 2 --device-id ego-link-001 --event-log pc_simulator\runtime\hdata-001-hpwr-live-20260623-0906-events.jsonl
python scripts\session_recorder.py --event-log pc_simulator\runtime\hdata-001-hpwr-live-20260623-0906-events.jsonl --session-id hdata-001-hpwr-live-20260623-0906 --output-dir pc_simulator\runtime\recordings\hdata-001-hpwr-live-20260623-0906 --json
python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\hdata-001-hpwr-live-20260623-0906 --json
python scripts\replay_session_recording.py pc_simulator\runtime\recordings\hdata-001-hpwr-live-20260623-0906 --json
```

## Evidence Paths

- Board probe: `reports/board_validation/20260623-090047/probe.md`
- GNSS probe: `reports/gnss_validation/20260623-090637/gnss_probe.md`
- Clean event log: `pc_simulator/runtime/hdata-001-hpwr-live-20260623-0906-events.jsonl`
- Clean recording: `pc_simulator/runtime/recordings/hdata-001-hpwr-live-20260623-0906/`
- Quality report: `pc_simulator/runtime/recordings/hdata-001-hpwr-live-20260623-0906/session_quality_report.md`
- Replay report: `pc_simulator/runtime/recordings/hdata-001-hpwr-live-20260623-0906/session_replay_report.md`

## Observed Hardware State

| Item | Observed Result |
|---|---|
| ESP32-S3 debug serial | `COM4`, CH343, flash succeeded |
| SIM7670G AT ports | `COM6` and `COM7`, model `SIM7670G-MNGV` |
| SIM / LTE | SIM ready, CSQ `18,0`, LTE registered, packet attached |
| RNDIS | Windows Remote NDIS adapter visible |
| MQTT broker | LAN broker `192.168.31.250:1883` |
| GNSS | AT reachable, GNSS powered, indoor no-fix |

## Clean MQTT Samples

The clean event log contains 6 device MQTT messages:

| Type | Seq | RSSI | Heap | Power Marker | Notes |
|---|---:|---:|---:|---|---|
| `sensor_sample/device_health` | 25 | -34 | 260136 | `POWER_MARKER_000102` | `battery_source=mock`, GPIO marker disabled |
| `mqtt_status` | 26 | -34 | n/a | `POWER_MARKER_000106` | `power_state=UPLOAD` |
| `mqtt_status` | 27 | -48 | n/a | `POWER_MARKER_000110` | `power_state=UPLOAD` |
| `mqtt_status` | 28 | -47 | n/a | `POWER_MARKER_000114` | `power_state=UPLOAD` |
| `sensor_sample/device_health` | 29 | -32 | 260172 | `POWER_MARKER_000118` | `battery_source=mock`, GPIO marker disabled |
| `mqtt_status` | 30 | -53 | n/a | `POWER_MARKER_000122` | `power_state=UPLOAD` |

All observed HPWR marker payload fields were present in the live MQTT data:
`power_state_elapsed_ms`, `power_state_cumulative_ms`, `power_marker_seq`,
`power_serial_marker_id`, `power_gpio_marker_id`, and
`power_gpio_marker_enabled=false`.

## GNSS Sample

The GNSS probe selected `COM6`, confirmed `gnss_power_state=1`, and wrote:

```json
{
  "event_type": "location_report",
  "seq": 31,
  "source": "sim7670g_gnss",
  "fix": false,
  "gnss_state": "no_fix",
  "port": "COM6",
  "raw_response": "+CGNSSINFO: ,,,,,,,,"
}
```

## Recording Result

The clean recording produced:

- Source events: 9
- Sensor frames: 7
- Events: 2
- Frame types: `device_health=2`, `device_status=4`, `gnss_report=1`
- Quality gate: PASS, `quality_score=0.94`, `errors=0`, `warnings=2`
- Replay: PASS, `replayed_inputs=7`, `risk_types.none=7`, `safety_events=0`, `base_commands=0`

Expected warnings remain:

- `firmware_version_unknown`
- `annotations_empty`

## Boundaries

- `battery=87` and `charging=false` are still mock fields.
- GPIO power marker output is still disabled; only serial/payload marker IDs are available.
- GNSS no-fix confirms the PC-side AT probe and event path, not a real location fix.
- IMU, microphone, physical SOS GPIO, SD storage, true battery telemetry, camera capture in the current firmware, and ESP32-side SIM7670G control remain unavailable or unverified.
