# TIMU-009C-B1 QMI8658 Temporary Fixture Static Capture

Date: 2026-06-24

## Purpose

TIMU-009C-B1 records the first operator-mounted static evidence after the
AMOLED/QMI8658 board was fixed to a paper-box temporary fixture with double-sided
tape. This is a repeatable temporary fixture capture, not a final product
mounting acceptance.

Formal IMU acceptance remains false. The product enclosure, final mounting
direction, final calibration, FIFO/DRDY interrupt behavior, low-power wake, and
instrumented current waveform evidence are still pending.

## Operator Fixture Note

- Operator report: AMOLED/QMI8658 board fixed to a paper box using double-sided
  tape.
- Fixture status: temporary/repeatable fixture, not final product enclosure.
- Target mounting direction: pending final wearable orientation.
- Capture instruction: keep the paper box and USB cable still during the MQTT
  capture window.
- Evidence classification: hardware-observed partial mounting evidence.

## Command

```powershell
python pc_simulator\mqtt_worker.py --host 192.168.31.250 --port 1883 --topic ego/link/ego-link-amoled-qmi8658/status --topic ego/link/ego-link-amoled-qmi8658/event --event-log pc_simulator\runtime\timu009c_b1\timu009c-b1-temporary-fixture-static-20260624-1735.events.jsonl --max-messages 16 --wait-seconds 90
```

Result: PASS, stored 16 MQTT events.

## Raw Evidence

- Event log:
  `pc_simulator/runtime/timu009c_b1/timu009c-b1-temporary-fixture-static-20260624-1735.events.jsonl`
- Summary:
  `pc_simulator/runtime/timu009c_b1/timu009c-b1-temporary-fixture-static-20260624-1735.summary.json`
- M1 recording:
  `pc_simulator/runtime/recordings/timu009c-b1-temporary-fixture-static-20260624-1735/`

## Capture Summary

- Total MQTT events: 16.
- QMI8658 `sensor_sample/device_health` events: 8.
- `mqtt_status` events: 8.
- Sequence range: `11728..11743`.
- Device id: `ego-link-amoled-qmi8658`.
- IMU source: `qmi8658_i2c`.
- IMU mock flag: `imu_sample_mock=false`.

Static accel/gyro summary:

| Axis | Accel mean mg | Accel min mg | Accel max mg | Accel span mg | Gyro mean mdps | Gyro min mdps | Gyro max mdps | Gyro span mdps |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| x | 25.38 | 23 | 27 | 4 | -411.75 | -453 | -359 | 94 |
| y | 92.25 | 92 | 93 | 1 | 1950.62 | 1906 | 2015 | 109 |
| z | -1020.50 | -1021 | -1020 | 1 | -99.12 | -187 | 0 | 187 |

Accel magnitude:

- Mean: `1024.98 mg`.
- Min: `1024.40 mg`.
- Max: `1025.58 mg`.
- Span: `1.18 mg`.

The static accel data is stable and shows gravity dominated by negative Z for
this temporary fixture orientation.

Example samples:

| seq | accel mg x | accel mg y | accel mg z | gyro mdps x | gyro mdps y | gyro mdps z | dropped samples |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 11728 | 23 | 92 | -1020 | -359 | 1921 | 0 | 5872 |
| 11742 | 27 | 93 | -1021 | -421 | 1953 | -187 | 5879 |

## M1 Closure

Recording command:

```powershell
python scripts\session_recorder.py --event-log pc_simulator\runtime\timu009c_b1\timu009c-b1-temporary-fixture-static-20260624-1735.events.jsonl --session-id timu009c-b1-temporary-fixture-static-20260624-1735 --output-dir pc_simulator\runtime\recordings\timu009c-b1-temporary-fixture-static-20260624-1735 --limit 50 --json
```

Result:

- `source_events=16`.
- `sensor_frames=16`.
- `events=0`.
- `annotations=0`.

Quality gate:

```powershell
python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\timu009c-b1-temporary-fixture-static-20260624-1735 --json
```

Result: PASS, `quality_score=0.94`, `errors=0`, `warnings=2`.

Replay:

```powershell
python scripts\replay_session_recording.py pc_simulator\runtime\recordings\timu009c-b1-temporary-fixture-static-20260624-1735 --json
```

Result: PASS, 16 replayed inputs, 16 `risk_type=none` outputs, 0 safety events,
0 base commands.

## Product Acceptance Boundary

This report may be referenced as partial evidence for:

- temporary fixture mounting direction;
- temporary fixture definition;
- backend static capture quality;
- M1 recording/replay closure for the temporary fixture.

It must not be used as pass evidence for final IMU acceptance because the
mechanical stack is not final and the calibration profile is still engineering
stage.

Next hardware step: keep the board fixed, mark the paper box with TOP/OUT/USB
orientation labels, then either capture a higher-rate bridge static window or
move into six-face/equivalent final calibration once the intended product
orientation is decided.
